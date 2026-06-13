# 统一多提供商 LLM API 设计详解

> 基于 `packages/ai/src/providers/` 源码分析

---

## 概述：什么是统一多提供商 LLM API？

### 本质问题抽象

表面痛点只是症状，真正需要解决的是三个本质问题：

```
┌────────────────────────────────────────────────────────────────┐
│                     本质问题一：异构性                          │
├────────────────────────────────────────────────────────────────┤
│  问题本质：                                                     │
│  Anthropic、OpenAI、Google 是三个完全不同的"世界"               │
│  - 协议不同：SSE 格式、事件命名、数据结构                        │
│  - 能力不同：图片、thinking、工具调用支持度                      │
│  - 约束不同：ID 格式限制、token 限制、参数格式                   │
│                                                                 │
│  表面症状：                                                     │
│  ❌ API 格式完全不同                                            │
│  ❌ 消息结构、字段名、事件类型都不统一                           │
│  ❌ 某些模型不支持图片、某些不支持 thinking                      │
│                                                                 │
│  核心挑战：如何让上层代码不感知这些差异？                        │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│                     本质问题二：流式性                          │
├────────────────────────────────────────────────────────────────┤
│  问题本质：                                                     │
│  LLM 生成是"涌现"过程，不是一次性产出                           │
│  - 内容逐 token 生成，无法预知完整结果                          │
│  - 生成过程可能被中断（错误、超时、用户取消）                    │
│  - 需要实时反馈，不能阻塞等待                                    │
│                                                                 │
│  表面症状：                                                     │
│  ❌ 每个 API 的 SSE 格式各异                                    │
│  ❌ 流式调用中途失败，如何处理？                                 │
│  ❌ 用户要等到全部内容生成完才能看到第一个字                     │
│                                                                 │
│  核心挑战：如何建模"涌现过程"，让数据实时流动？                  │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│                     本质问题三：迁移性                          │
├────────────────────────────────────────────────────────────────┤
│  问题本质：                                                     │
│  对话历史是"状态"，但不同提供商状态格式不互通                    │
│  - 加密内容（thinkingSignature）只对原模型有效                  │
│  - ID 格式限制不同（Anthropic ≤64字符，OpenAI 450+字符）        │
│  - 能力差异（从有图片模型切换到无图片模型）                      │
│                                                                 │
│  表面症状：                                                     │
│  ❌ 用户切换模型时，历史消息可能不兼容                           │
│  ❌ Anthropic 的 thinkingSignature 对 OpenAI 无效               │
│  ❌ 工具调用 ID 格式跨模型不兼容                                 │
│                                                                 │
│  核心挑战：如何让"状态"在不同"世界"之间迁移？                    │
└────────────────────────────────────────────────────────────────┘
```

---

### 设计核心：三个抽象原则

对应三个本质问题，设计遵循三个核心原则：

```
┌────────────────────────────────────────────────────────────────┐
│                 原则一：统一抽象层（解决异构性）                 │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  核心思想：                                                     │
│  "在差异之上建立统一，让上层只看到统一接口"                      │
│                                                                 │
│  实现：                                                         │
│  ┌─────────────┐                                                │
│  │ Anthropic   │──►                                             │
│  └─────────────┘    ┌─────────────────┐    ┌─────────────────┐  │
│  ┌─────────────┐──► │   适配器层       │──► │ 统一内部格式    │  │
│  │ OpenAI      │──► │ (anthropic.ts)  │    │ AssistantMessage│  │
│  └─────────────┘    │ (openai.ts)     │    │ - content[]     │  │
│  ┌─────────────┐──► │ (google.ts)     │    │ - usage         │  │
│  │ Google      │──► └─────────────────┘    │ - stopReason    │  │
│  └─────────────┘                           └─────────────────┘  │
│                                                                 │
│  关键技术：                                                     │
│  - 适配器模式：每个提供商一个适配器                              │
│  - 注册表模式：统一入口，Map<api, adapter>                       │
│  - 懒加载：按需加载适配器，减少资源消耗                          │
│                                                                 │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│                 原则二：事件流模型（解决流式性）                 │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  核心思想：                                                     │
│  "把涌现过程建模为事件流，而不是一次性结果"                      │
│                                                                 │
│  传统模型（结果导向）：                                         │
│  request ──────► [等待] ──────► response                        │
│                   (阻塞)                                        │
│                                                                 │
│  事件流模型（过程导向）：                                       │
│  request ──────► event1 ─► event2 ─► event3 ─► done             │
│                   (实时流动)                                    │
│                                                                 │
│  关键技术：                                                     │
│  - EventStream：实现 AsyncIterable，支持 for await...of         │
│  - delta + partial：增量 + 累积，满足不同消费场景               │
│  - 错误即事件：错误不打断流，作为事件推送                        │
│                                                                 │
│  为什么重要？                                                   │
│  - 实时反馈：用户立即看到第一个字                                │
│  - 可中断：用户可以随时取消，已生成内容不丢失                    │
│  - 可组合：多个流可以 merge、filter、transform                   │
│                                                                 │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│                 原则三：状态转换层（解决迁移性）                 │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  核心思想：                                                     │
│  "状态迁移时，转换不兼容部分，保留兼容部分"                      │
│                                                                 │
│  转换规则：                                                     │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ 内容类型      │ 同模型   │ 跨模型                          │ │
│  ├───────────────────────────────────────────────────────────┤ │
│  │ text         │ 保留     │ 保留                             │ │
│  │ thinking     │ 保留     │ 转为 text（丢弃加密签名）        │ │
│  │ redacted     │ 保留     │ 丢弃                             │ │
│  │ toolCall     │ 保留     │ ID 格式标准化                    │ │
│  │ image        │ 保留     │ 目标不支持时降级为占位符文本     │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  关键技术：                                                     │
│  - transformMessages：统一转换入口                              │
│  - isSameModel 判断：同模型保留原样，跨模型转换                  │
│  - normalizeToolCallId：ID 格式标准化                           │
│  - replaceImagesWithPlaceholder：图片降级                       │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

---

### 设计目标映射

将表面目标映射到核心原则：

| 表面目标 | 对应原则 | 原理 |
|---------|---------|------|
| 应用层只调用 `stream()` | 统一抽象层 | 适配器隐藏差异 |
| 不关心底层是谁 | 统一抽象层 | 注册表统一入口 |
| 流式数据实时传递 | 事件流模型 | AsyncIterable + delta |
| 错误不打断流 | 事件流模型 | 错误即事件 |
| 按需加载 | 统一抽象层 | 懒加载减少资源 |
| 跨提供商兼容 | 状态转换层 | transformMessages |

---

## 一、整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      应用层                                  │
│         stream(model, context, options)                     │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                      注册层                                  │
│    api: "anthropic-messages" → lazyAnthropicWrapper         │
│    api: "openai-responses"   → lazyOpenAIWrapper            │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼ 动态 import
┌─────────────────────────────────────────────────────────────┐
│                      提供商层                                │
│    anthropic.ts / openai.ts / google.ts / ...               │
│    - SSE 解析                                                │
│    - 消息格式转换                                            │
│    - 统一事件输出                                            │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼ HTTP SSE
┌─────────────────────────────────────────────────────────────┐
│                      LLM API 层                              │
│    Anthropic API / OpenAI API / Google API                  │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、逐层解析：问题 → 原则 → 实现

> 每一层都对应一个本质问题，实现一个核心原则

---

### 第 1 层：注册表 + 懒加载

#### 对应本质问题：**异构性**

```
问题：Anthropic、OpenAI、Google 是三个完全不同的"世界"
挑战：如何让上层代码不感知这些差异？
```

#### 实现核心原则：**统一抽象层**

```
原则："在差异之上建立统一，让上层只看到统一接口"
实现：注册表模式 + 懒加载 + 类型包装
```

#### 具体实现

**问题分解**：
- 问题 1: 如何让应用层不关心具体是哪个提供商？ → 注册表统一入口
- 问题 2: 用户只用 Anthropic，为什么要加载 OpenAI、Google 的代码？ → 懒加载
- 问题 3: 如何保证类型安全？ → 类型包装

**代码实现**：

```typescript
// 1. 注册表：统一入口，Map<api, adapter>
const registry = new Map<string, Provider>();

export function registerApiProvider(api: string, stream: StreamFunction) {
    registry.set(api, stream);
}

export function getApiProvider(api: string): StreamFunction | undefined {
    return registry.get(api);  // 👈 上层只调用这个，不关心具体是谁
}

// 2. 懒加载：首次使用才 import
function createLazyStream(loadModule: () => Promise<Module>) {
    return (model, context, options) => {
        const stream = new EventStream();
        
        loadModule()  // 👈 首次调用才 import("./anthropic.ts")
            .then(module => module.stream(model, context, options))
            .catch(error => stream.push({ type: "error", error }));
        
        return stream;  // 👈 立即返回，不阻塞
    };
}

// 3. 类型包装：运行时校验 + 泛型
function wrapStream<TApi extends Api>(api: TApi, stream: StreamFunction<TApi>) {
    return (model, context, options) => {
        if (model.api !== api) {
            throw new Error(`Mismatched api: ${model.api} expected ${api}`);
        }
        return stream(model as Model<TApi>, context, options);
    };
}

// 注册
registerApiProvider({
    api: "anthropic-messages",
    stream: createLazyStream(() => import("./anthropic.ts")),  // 👈 按需加载
});
```

#### 设计呼应

| 本质问题 | 核心原则 | 关键技术 |
|---------|---------|---------|
| 异构性：不同提供商是不同"世界" | 统一抽象层：在差异之上建立统一 | 注册表统一入口 + 懒加载 + 类型包装 |

---

### 第 2 层：SSE 解析

#### 对应本质问题：**流式性**

```
问题：LLM 生成是"涌现"过程，不是一次性产出
挑战：如何建模"涌现过程"，让数据实时流动？
```

#### 实现核心原则：**事件流模型**

```
原则："把涌现过程建模为事件流，而不是一次性结果"
实现：SSE 解析器 + 流式 JSON 解析
```

#### 具体实现

**问题分解**：
- 问题 1: 不同 API 的 SSE 格式完全不同 → 每个提供商独立解析器
- 问题 2: 如何处理连接中断、解析失败？ → try-catch + 错误事件
- 问题 3: 如何增量解析 JSON（工具调用参数）？ → partial-json 库

**不同 API 的 SSE 格式对比**：

| API | SSE 格式 | 特点 |
|-----|---------|------|
| Anthropic | `event: content_block_delta`<br>`data: {"delta":{"text":"Hello"}}` | 事件类型明确 |
| OpenAI | `data: {"choices":[{"delta":{"content":"Hello"}}]}` | 无事件类型，只有 data |
| Google | 完全不同的 JSON 结构 | 需要独立解析 |

**代码实现**：

```typescript
// SSE 解析器：逐行读取，解析事件
async function* parseSSE(body: ReadableStream) {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    
    while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value);
        
        // 逐行解析
        for (const line of buffer.split("\n")) {
            if (line.startsWith("data: ")) {
                yield JSON.parse(line.slice(6));  // 👈 产出事件
            }
        }
    }
}

// 流式 JSON 解析：解析不完整的 JSON
export function parseStreamingJson<T>(partialJson: string): T {
    try {
        return JSON.parse(partialJson);  // 尝试直接解析
    } catch {
        return partialParse(partialJson);  // 👈 partial-json 库解析不完整 JSON
    }
}

// 使用：边解析边推送事件
for await (const event of parseSSE(response.body)) {
    if (event.type === "content_block_delta") {
        stream.push({ type: "text_delta", delta: event.delta.text });
    }
}
```

#### 设计呼应

| 本质问题 | 核心原则 | 关键技术 |
|---------|---------|---------|
| 流式性：LLM 生成是涌现过程 | 事件流模型：建模涌现过程 | SSE 解析器 + partial-json |

---

### 第 3 层：消息格式统一

#### 对应本质问题：**异构性**

```
问题：不同提供商消息结构、字段名完全不同
挑战：如何让上层只看到统一格式？
```

#### 实现核心原则：**统一抽象层**

```
原则："在差异之上建立统一"
实现：统一内部格式 + 转换函数
```

#### 具体实现

**问题分解**：
- 问题 1: Anthropic 用 content blocks 数组 → 统一用数组
- 问题 2: OpenAI 用 content 字符串或数组 → 统一用数组
- 问题 3: 工具调用的字段名不同（input vs arguments） → 统一为 arguments
- 问题 4: thinking block 格式不同 → 统一 thinking + thinkingSignature

**格式对比**：

| 内容类型 | Anthropic | OpenAI | 统一内部格式 |
|---------|-----------|--------|-------------|
| 文本 | `{type: "text", text: "..."}` | `delta.content` | `{type: "text", text: "..."}` |
| 思考 | `{type: "thinking", thinking: "...", signature: "..."}` | 无 | `{type: "thinking", thinking: "...", thinkingSignature: "..."}` |
| 工具调用 | `{type: "tool_use", id, name, input}` | `{id, function.name, function.arguments}` | `{type: "toolCall", id, name, arguments}` |

**代码实现**：

```typescript
// 统一内部格式
interface AssistantMessage {
    role: "assistant";
    content: ContentBlock[];  // 👈 统一用数组
    usage: Usage;
    stopReason: StopReason;
}

// Anthropic → 内部
function fromAnthropic(block) {
    if (block.type === "text") return { type: "text", text: block.text };
    if (block.type === "thinking") return { type: "thinking", thinking: block.thinking, thinkingSignature: block.signature };
    if (block.type === "tool_use") return { type: "toolCall", id: block.id, name: block.name, arguments: block.input };  // 👈 input → arguments
}

// OpenAI → 内部
function fromOpenAI(chunk) {
    if (chunk.choices[0].delta.content) {
        return { type: "text", text: chunk.choices[0].delta.content };
    }
    if (chunk.choices[0].delta.tool_calls) {
        return { type: "toolCall", id: chunk.id, name: chunk.function.name, arguments: chunk.function.arguments };
    }
}
```

#### 设计呼应

| 本质问题 | 核心原则 | 关键技术 |
|---------|---------|---------|
| 异构性：字段名、结构不同 | 统一抽象层：在差异之上建立统一 | 统一内部格式 + 转换函数 |

---

### 第 4 层：事件驱动 + 统一抽象

#### 对应本质问题：**流式性**

```
问题：LLM 生成是流式的，如何让应用层实时收到？
挑战：如何解耦底层与应用层？
```

#### 实现核心原则：**事件流模型**

```
原则："把涌现过程建模为事件流"
实现：EventStream + delta + partial
```

#### 具体实现

**问题分解**：
- 问题 1: LLM 生成是流式的，如何让应用层实时收到？ → EventStream 实现 AsyncIterable
- 问题 2: 不同事件类型，如何统一处理？ → 统一事件类型定义
- 问题 3: 如何让应用层不关心底层细节？ → 只暴露事件，隐藏内部

**事件类型设计**：

```typescript
type AssistantMessageEvent =
    | { type: "start"; partial: AssistantMessage }          // 开始
    | { type: "text_delta"; delta: string; partial: AssistantMessage }     // 文本增量
    | { type: "thinking_delta"; delta: string; partial: AssistantMessage } // 思考增量
    | { type: "toolcall_start"; toolCall: ToolCall; partial: AssistantMessage }  // 工具调用开始
    | { type: "toolcall_delta"; delta: string; partial: AssistantMessage }      // 工具调用增量
    | { type: "done"; message: AssistantMessage }           // 完成
    | { type: "error"; error: AssistantMessage };           // 错误
```

**delta vs partial 双模式**：

| 字段 | 含义 | 用途 |
|-----|------|------|
| `delta` | 本次新增的一小段 | 追加显示（打字机效果） |
| `partial` | 当前完整状态 | 整体替换、访问元数据 |

**EventStream 实现**：

```typescript
class EventStream implements AsyncIterable<Event> {
    private queue: Event[] = [];
    private resolvers: ((value: Event) => void)[] = [];
    private ended = false;
    
    push(event: Event) {
        if (this.resolvers.length > 0) {
            this.resolvers.shift()!(event);  // 👈 有人等待，直接交付
        } else {
            this.queue.push(event);          // 👈 暂存队列
        }
    }
    
    end() { this.ended = true; }
    
    async *[Symbol.asyncIterator]() {  // 👈 支持 for await...of
        while (!this.ended || this.queue.length > 0) {
            if (this.queue.length > 0) {
                yield this.queue.shift()!;
            } else {
                yield new Promise<Event>(resolve => this.resolvers.push(resolve));  // 👈 等待新事件
            }
        }
    }
}

// 使用：消费事件流
for await (const event of stream) {
    if (event.type === "text_delta") {
        process.stdout.write(event.delta);  // 👈 打字机效果
    }
}
```

#### 设计呼应

| 本质问题 | 核心原则 | 关键技术 |
|---------|---------|---------|
| 流式性：如何实时传递 | 事件流模型：建模涌现过程 | EventStream + delta/partial + AsyncIterable |

---

### 第 5 层：错误处理

#### 对应本质问题：**流式性**

```
问题：流式调用中途失败，如何处理？
挑战：不能用 throw 打断流，需要保留已生成内容
```

#### 实现核心原则：**事件流模型**

```
原则："错误也是事件，不打断流"
实现：错误即事件 + 保留部分结果
```

#### 具体实现

**问题分解**：
- 问题 1: 流式调用中途失败，如何通知应用层？ → 推送 error 事件
- 问题 2: 不能用 throw 打断流 → 错误作为事件，不抛异常
- 问题 3: 需要保留已生成的部分内容 → output 包含已生成内容

**传统方式 vs 事件驱动方式**：

```typescript
// ❌ 传统方式：throw 打断流
try {
    for await (const chunk of stream) { ... }
} catch (e) {
    // 流被打断，已生成内容丢失
}

// ✅ 事件驱动：错误也是事件
for await (const event of stream) {
    if (event.type === "error") {
        // 处理错误，已生成内容在 event.error 中
        console.log("部分内容:", event.error.content);
    }
}
```

**代码实现**：

```typescript
export const streamAnthropic = (model, context, options) => {
    const stream = new EventStream();
    
    (async () => {
        const output = createEmptyMessage();  // 👈 初始化输出
        
        try {
            stream.push({ type: "start", partial: output });
            
            for await (const event of parseSSE(response.body)) {
                // 处理事件，更新 output
                output.content.push(...);
                stream.push({ type: "text_delta", delta: ..., partial: output });
            }
            
            stream.push({ type: "done", message: output });
            stream.end();
        } catch (error) {
            // 👈 错误处理：不 throw，推送事件
            output.stopReason = "error";
            output.errorMessage = error.message;
            stream.push({ type: "error", error: output });  // 👈 output 包含已生成内容
            stream.end();  // 👈 正常结束流
        }
    })();
    
    return stream;
};
```

#### 设计呼应

| 本质问题 | 核心原则 | 关键技术 |
|---------|---------|---------|
| 流式性：中途失败如何处理 | 事件流模型：错误即事件 | error 事件 + 保留部分结果 |

---

### 第 6 层：跨供应商消息转换

#### 对应本质问题：**迁移性**

```
问题：对话历史是"状态"，但不同提供商状态格式不互通
挑战：如何让"状态"在不同"世界"之间迁移？
```

#### 实现核心原则：**状态转换层**

```
原则："状态迁移时，转换不兼容部分，保留兼容部分"
实现：transformMessages + isSameModel + normalizeToolCallId
```

#### 具体实现

**问题分解**：
- 问题 1: Anthropic 的 thinkingSignature 对 OpenAI 无效 → 跨模型丢弃加密签名
- 问题 2: 工具调用 ID 格式不同 → normalizeToolCallId 标准化
- 问题 3: 某些模型不支持图片 → 图片降级为占位符
- 问题 4: 加密的 thinking block 跨模型无效 → 丢弃或转文本

**转换规则表**：

| 内容类型 | 同模型 | 跨模型 | 原因 |
|---------|--------|--------|------|
| text | 保留 | 保留 | 无差异 |
| thinking | 保留 | 转为 text | 加密签名无效 |
| redacted thinking | 保留 | 丢弃 | 只对原模型有效 |
| toolCall | 保留 | ID 标准化 | 格式限制不同 |
| image | 保留 | 降级为占位符 | 能力差异 |

**代码实现**：

```typescript
function transformMessages(messages: Message[], targetModel: Model): Message[] {
    return messages.map(msg => {
        if (msg.role === "assistant") {
            const isSameModel = msg.model === targetModel.id;  // 👈 判断是否跨模型
            
            return {
                ...msg,
                content: msg.content.map(block => {
                    // 加密 thinking：跨模型丢弃
                    if (block.type === "thinking" && block.redacted && !isSameModel) {
                        return [];  // 👈 丢弃
                    }
                    
                    // 普通 thinking：跨模型转文本
                    if (block.type === "thinking" && !isSameModel) {
                        return { type: "text", text: block.thinking };  // 👈 转文本
                    }
                    
                    // 工具调用：跨模型标准化 ID
                    if (block.type === "toolCall" && !isSameModel) {
                        return { ...block, id: normalizeToolCallId(block.id) };  // 👈 ID 标准化
                    }
                    
                    return block;  // 👈 同模型保留原样
                }).filter(Boolean),
            };
        }
        
        // 用户消息：检查图片支持
        if (msg.role === "user" && !targetModel.input.includes("image")) {
            return {
                ...msg,
                content: msg.content.map(block =>
                    block.type === "image"
                        ? { type: "text", text: "(image omitted)" }  // 👈 图片降级
                        : block
                ),
            };
        }
        
        return msg;
    });
}

// ID 标准化：Anthropic 要求 ≤64 字符，只允许 [a-zA-Z0-9_-]
function normalizeToolCallId(id: string): string {
    return id.replace(/[^a-zA-Z0-9_-]/g, "_").slice(0, 64);
}
```

#### 设计呼应

| 本质问题 | 核心原则 | 关键技术 |
|---------|---------|---------|
| 迁移性：状态格式不互通 | 状态转换层：转换不兼容部分 | transformMessages + isSameModel + normalizeToolCallId |

---

### 层次与原则对应总表

| 层次 | 对应本质问题 | 实现核心原则 | 关键技术 |
|-----|-------------|-------------|---------|
| **第 1 层**：注册表+懒加载 | 异构性 | 统一抽象层 | 注册表 + 懒加载 + 类型包装 |
| **第 2 层**：SSE解析 | 流式性 | 事件流模型 | SSE解析器 + partial-json |
| **第 3 层**：消息格式统一 | 异构性 | 统一抽象层 | 统一内部格式 + 转换函数 |
| **第 4 层**：事件驱动 | 流式性 | 事件流模型 | EventStream + delta/partial |
| **第 5 层**：错误处理 | 流式性 | 事件流模型 | 错误即事件 + 保留部分结果 |
| **第 6 层**：跨供应商转换 | 迁移性 | 状态转换层 | transformMessages + ID标准化 |

**三条主线**：

```
异构性 ──► 统一抽象层 ──► 第1层（注册表） + 第3层（消息格式）

流式性 ──► 事件流模型 ──► 第2层（SSE解析） + 第4层（事件驱动） + 第5层（错误处理）

迁移性 ──► 状态转换层 ──► 第6层（跨供应商转换）
```

---

## 三、完整最小实现示例

```typescript
// ==================== 1. 统一类型 ====================
// types.ts
interface Message {
    role: "user" | "assistant" | "toolResult";
    content: ContentBlock[];
    model?: string;
}

interface ContentBlock {
    type: "text" | "thinking" | "toolCall";
    text?: string;
    thinking?: string;
    id?: string;
    name?: string;
    arguments?: object;
}

type Event =
    | { type: "start" }
    | { type: "text_delta"; delta: string }
    | { type: "done" }
    | { type: "error"; message: string };

// ==================== 2. 事件流 ====================
// event-stream.ts
class EventStream implements AsyncIterable<Event> {
    private queue: Event[] = [];
    private ended = false;

    push(event: Event) { this.queue.push(event); }
    end() { this.ended = true; }

    async *[Symbol.asyncIterator]() {
        while (!this.ended || this.queue.length > 0) {
            while (this.queue.length > 0) yield this.queue.shift()!;
            if (!this.ended) await new Promise(r => setTimeout(r, 10));
        }
    }
}

// ==================== 3. 注册表 ====================
// registry.ts
const registry = new Map<string, StreamFn>();

function register(api: string, stream: StreamFn) {
    registry.set(api, stream);
}

function getProvider(api: string) {
    return registry.get(api);
}

// ==================== 4. 懒加载 ====================
// lazy.ts
function lazyStream(load: () => Promise<Module>): StreamFn {
    return (model, ctx, opts) => {
        const stream = new EventStream();
        load().then(m => m.stream(model, ctx, opts, stream)).catch(e => {
            stream.push({ type: "error", message: e.message });
            stream.end();
        });
        return stream;
    };
}

// ==================== 5. Anthropic 提供商 ====================
// anthropic.ts
function streamAnthropic(model, ctx, opts, stream: EventStream) {
    stream.push({ type: "start" });

    fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: { "x-api-key": opts.apiKey },
        body: JSON.stringify({
            model: model.id,
            messages: convertMessages(ctx.messages),
            stream: true,
        }),
    }).then(async res => {
        for await (const line of parseSSE(res.body!)) {
            if (line.type === "content_block_delta") {
                stream.push({ type: "text_delta", delta: line.delta.text });
            }
        }
        stream.push({ type: "done" });
        stream.end();
    }).catch(e => {
        stream.push({ type: "error", message: e.message });
        stream.end();
    });
}

// ==================== 6. SSE 解析 ====================
// sse.ts
async function* parseSSE(body: ReadableStream) {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value);

        for (const line of buffer.split("\n")) {
            if (line.startsWith("data: ")) {
                yield JSON.parse(line.slice(6));
            }
        }
        buffer = "";
    }
}

// ==================== 7. 消息转换 ====================
// transform.ts
function convertMessages(messages: Message[]): any[] {
    return messages.map(m => ({
        role: m.role,
        content: m.content.map(b => {
            if (b.type === "text") return { type: "text", text: b.text };
            if (b.type === "toolCall") return { type: "tool_use", id: b.id, name: b.name, input: b.arguments };
            return b;
        }),
    }));
}

function transformForTarget(messages: Message[], targetModel: string): Message[] {
    return messages.map(m => m.model !== targetModel ? {
        ...m,
        content: m.content.map(b => b.type === "thinking" ? { type: "text", text: b.thinking } : b),
    } : m);
}

// ==================== 8. 注册内置提供商 ====================
// register-builtins.ts
register("anthropic-messages", lazyStream(() => import("./anthropic.ts")));
register("openai-responses", lazyStream(() => import("./openai.ts")));

// ==================== 9. 应用层使用 ====================
// app.ts
const provider = getProvider("anthropic-messages");
const stream = provider(
    { id: "claude-3-opus", api: "anthropic-messages" },
    { messages: transformForTarget(historyMessages, "claude-3-opus") },
    { apiKey: process.env.ANTHROPIC_API_KEY }
);

for await (const event of stream) {
    if (event.type === "text_delta") {
        process.stdout.write(event.delta);  // 打字机效果
    }
    if (event.type === "done") {
        console.log("\n完成");
    }
    if (event.type === "error") {
        console.error("错误:", event.message);
    }
}
```

---

## 四、额外技巧

### 1. Unicode 代理对清理

```typescript
// 防止不完整的 Unicode 字符导致 API 失败
export function sanitizeSurrogates(text: string): string {
    return text.replace(
        /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/g,
        ""
    );
}
```

### 2. JSON 修复

```typescript
// LLM 可能生成非法 JSON，修复后解析
export function repairJson(json: string): string {
    // 转义字符串内的控制字符
    // 修复非法转义序列
}
```

### 3. 缓存控制

```typescript
// Anthropic 支持 prompt caching
params.system = [
    {
        type: "text",
        text: systemPrompt,
        cache_control: { type: "ephemeral" },  // 👈 缓存标记
    },
];
```

---

## 五、总结：问题 → 原则 → 实现

### 三条主线

```
┌─────────────────────────────────────────────────────────────────┐
│  本质问题         核心原则              实现层次                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  异构性    ───►   统一抽象层   ───►   第1层 + 第3层             │
│  (不同世界)       (差异之上统一)        (注册表 + 消息格式)      │
│                                                                 │
│  流式性    ───►   事件流模型   ───►   第2层 + 第4层 + 第5层     │
│  (涌现过程)       (建模涌现)            (SSE + Event + 错误)    │
│                                                                 │
│  迁移性    ───►   状态转换层   ───►   第6层                     │
│  (状态不互通)     (转换不兼容)          (transformMessages)      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 每层对应关系

| 层次 | 本质问题 | 核心原则 | 关键技术 |
|-----|---------|---------|---------|
| **第 1 层**：注册表+懒加载 | 异构性：不同提供商是不同"世界" | 统一抽象层：在差异之上建立统一 | 注册表 + 懒加载 + 类型包装 |
| **第 2 层**：SSE解析 | 流式性：LLM 生成是涌现过程 | 事件流模型：建模涌现过程 | SSE解析器 + partial-json |
| **第 3 层**：消息格式统一 | 异构性：字段名、结构不同 | 统一抽象层：在差异之上建立统一 | 统一内部格式 + 转换函数 |
| **第 4 层**：事件驱动 | 流式性：如何实时传递 | 事件流模型：建模涌现过程 | EventStream + delta/partial |
| **第 5 层**：错误处理 | 流式性：中途失败如何处理 | 事件流模型：错误即事件 | error事件 + 保留部分结果 |
| **第 6 层**：跨供应商转换 | 迁移性：状态格式不互通 | 状态转换层：转换不兼容部分 | transformMessages + ID标准化 |

---

## 六、设计模式总结

| 模式 | 对应原则 | 应用场景 |
|-----|---------|---------|
| **适配器模式** | 统一抽象层 | 不同 API 格式 → 统一内部格式 |
| **注册表模式** | 统一抽象层 | 统一管理多个提供商 |
| **懒加载模式** | 统一抽象层 | 按需加载，减少资源消耗 |
| **事件驱动模式** | 事件流模型 | 流式数据实时传递 |
| **状态转换模式** | 状态转换层 | 跨提供商兼容转换 |
| **防御性编程** | 所有原则 | Unicode/JSON 修复，防止失败 |

---

## 七、核心启示

### 1. 抽象比列举更重要

```
表面痛点：
- API 格式不同
- SSE 格式各异
- 消息结构不同

本质问题：
- 异构性：不同提供商是不同"世界"
```

**启示**：不要只解决表面症状，找到本质问题，抽象出核心原则。

### 2. 原则指导实现

```
原则："在差异之上建立统一"

→ 注册表：统一入口
→ 懒加载：按需加载
→ 类型包装：运行时校验
→ 消息格式：统一内部结构
```

**启示**：一个原则可以指导多个层次的实现。

### 3. 层次相互呼应

```
第1层（注册表）解决异构性 ──► 第3层（消息格式）也解决异构性

两者共同实现"统一抽象层"原则
```

**启示**：不同层次可能解决同一个问题，需要整体设计。