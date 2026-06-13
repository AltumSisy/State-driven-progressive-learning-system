# agent-loop.ts 与 agent.ts 在统一多提供商 LLM API 设计中的角色分析

> 基于 `packages/agent/src/` 源码分析，参考统一多提供商 LLM API 设计框架

---

## 一、整体架构视角：它们在哪个位置？

```
┌─────────────────────────────────────────────────────────────────┐
│                      应用层                                      │
│         用户代码：Agent.prompt() / Agent.continue()             │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│              状态管理层：agent.ts (Agent 类)                     │
│  - AgentState：消息列表、工具列表、流式状态                      │
│  - 消息队列：steering / follow-up                               │
│  - 事件订阅：生命周期事件分发                                    │
│  - 高级 API：prompt(), continue(), steer(), followUp()          │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼ 调用 runAgentLoop
┌─────────────────────────────────────────────────────────────────┐
│              编排层：agent-loop.ts (agent-loop 函数)             │
│  - 主循环逻辑：LLM 调用 → 工具执行 → 结果处理                    │
│  - 消息转换边界：AgentMessage[] → Message[]                     │
│  - 事件流：AgentEvent → 上层订阅                                 │
│  - 工具编排：并行/顺序执行、前后钩子                             │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼ 调用 streamFn (默认 streamSimple)
┌─────────────────────────────────────────────────────────────────┐
│              统一抽象层：@earendil-works/pi-ai                   │
│  - 注册表：Map<api, provider>                                    │
│  - 适配器：anthropic.ts / openai.ts / google.ts                 │
│  - EventStream：AsyncIterable<AssistantMessageEvent>            │
│  - 统一格式：AssistantMessage / ContentBlock[]                  │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼ HTTP SSE
┌─────────────────────────────────────────────────────────────────┐
│                      LLM API 层                                  │
│    Anthropic API / OpenAI API / Google API                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## 二、agent-loop.ts：编排层的核心角色

### 本质定位：**业务逻辑编排器**

```
┌────────────────────────────────────────────────────────────────┐
│                   agent-loop.ts 的角色                          │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  本质问题：                                                     │
│  Agent 的"思考-行动-观察"循环如何协调？                         │
│  - LLM 调用、工具执行、消息流转需要统一编排                      │
│  - 不同阶段需要不同的事件通知                                    │
│  - 消息格式在边界处需要转换                                      │
│                                                                 │
│  核心职责：                                                     │
│  1. 主循环编排：LLM 响应 → 工具调用 → 工具结果 → 继续或停止     │
│  2. 消息转换边界：AgentMessage[] → Message[] (统一内部格式)     │
│  3. 事件流发射：AgentEvent 通知上层状态变化                      │
│  4. 工具执行编排：并行/顺序、before/after 钩子                   │
│                                                                 │
│  设计原则：                                                     │
│  - "在边界处转换，在内部统一"                                   │
│  - "事件驱动，不阻塞流"                                         │
│  - "可配置，可扩展"                                             │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

---

### 关键设计点 1：消息转换边界

**这是 agent-loop 与统一 LLM API 设计的关键连接点。**

```typescript
// agent-loop.ts: streamAssistantResponse 函数
async function streamAssistantResponse(...) {
    // 👇 内部使用 AgentMessage[] (扩展格式)
    let messages = context.messages;  // AgentMessage[]
    
    // 👇 边界处转换：AgentMessage[] → Message[]
    const llmMessages = await config.convertToLlm(messages);
    
    // 👇 构造 LLM context (统一格式)
    const llmContext: Context = {
        systemPrompt: context.systemPrompt,
        messages: llmMessages,  // Message[]
        tools: context.tools,
    };
    
    // 👇 调用统一 API (不关心是哪个提供商)
    const response = await streamFunction(config.model, llmContext, options);
}
```

**为什么这样设计？**

| 设计层 | 消息格式 | 原因 |
|--------|---------|------|
| **Agent 内部层** | `AgentMessage[]` | 需要额外字段：timestamp、steering/followUp 标记等 |
| **LLM 调用边界** | `Message[]` | 统一格式，屏蔽提供商差异 |
| **提供商层** | Anthropic/OpenAI/Google 格式 | 适配器自动转换 |

**转换函数的职责：**

```typescript
// agent.ts 中的默认实现
function defaultConvertToLlm(messages: AgentMessage[]): Message[] {
    return messages.filter(
        (message) => message.role === "user" || 
                     message.role === "assistant" || 
                     message.role === "toolResult"
    );
}
```

- 过滤掉不需要发送给 LLM 的消息类型
- 可以扩展：压缩历史、摘要、格式调整等

---

### 关键设计点 2：事件流设计

**AgentEvent 类型设计：**

```typescript
type AgentEvent =
    | { type: "agent_start" }                    // 整个循环开始
    | { type: "turn_start" }                     // 单轮对话开始
    | { type: "message_start"; message }         // 消息开始
    | { type: "message_update"; message }        // 消息更新（流式）
    | { type: "message_end"; message }           // 消息结束
    | { type: "tool_execution_start"; ... }      // 工具开始执行
    | { type: "tool_execution_end"; ... }        // 工具执行结束
    | { type: "turn_end"; message, toolResults } // 单轮结束
    | { type: "agent_end"; messages }            // 整个循环结束
```

**事件流特点：**

1. **层次化设计**：
   - `agent_start/end`：整体生命周期
   - `turn_start/end`：单轮对话生命周期
   - `message_start/update/end`：单个消息生命周期
   - `tool_execution_start/end`：工具执行生命周期

2. **实时通知**：
   - `message_update` 实时推送流式内容
   - `tool_execution_start/end` 实时通知工具状态

3. **完整状态**：
   - `agent_end` 包含完整消息列表
   - `turn_end` 包含本轮的 assistant 消息和工具结果

---

### 关键设计点 3：工具执行编排

**并行 vs 顺序执行：**

```typescript
// agent-loop.ts: executeToolCalls 函数
async function executeToolCalls(...) {
    const toolCalls = assistantMessage.content.filter(c => c.type === "toolCall");
    
    // 👇 检查是否有工具要求顺序执行
    const hasSequentialToolCall = toolCalls.some(
        (tc) => currentContext.tools?.find(t => t.name === tc.name)?.executionMode === "sequential"
    );
    
    // 👇 根据配置决定执行模式
    if (config.toolExecution === "sequential" || hasSequentialToolCall) {
        return executeToolCallsSequential(...);
    }
    return executeToolCallsParallel(...);
}
```

**before/after 钩子设计：**

```typescript
// 准备阶段
if (config.beforeToolCall) {
    const beforeResult = await config.beforeToolCall({ assistantMessage, toolCall, args, context }, signal);
    if (beforeResult?.block) {
        // 👇 阻止工具执行
        return { kind: "immediate", result: createErrorToolResult("Blocked"), isError: true };
    }
}

// 执行阶段
const result = await tool.execute(toolCall.id, args, signal, (partialResult) => {
    // 👇 实时更新回调
    emit({ type: "tool_execution_update", ... });
});

// 后处理阶段
if (config.afterToolCall) {
    const afterResult = await config.afterToolCall({ ... }, signal);
    // 👇 可以修改结果
    result = { content: afterResult.content ?? result.content, ... };
}
```

**设计启示：**

| 设计点 | 对应原则 | 原因 |
|--------|---------|------|
| 消息转换边界 | 统一抽象层 | 屏蔽提供商差异，Agent 内部自由扩展 |
| 事件流设计 | 事件流模型 | 实时通知、层次化生命周期、可中断 |
| 工具编排 | 状态转换层 | 并行/顺序、前后钩子、结果修改 |

---

## 三、agent.ts：状态管理层的核心角色

### 本质定位：**状态管理器 + 高级接口封装**

```
┌────────────────────────────────────────────────────────────────┐
│                   agent.ts (Agent 类) 的角色                    │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  本质问题：                                                     │
│  如何让应用层不关心底层循环细节？                                │
│  - 状态需要持久化、可访问                                        │
│  - 消息需要队列化（steering/follow-up）                         │
│  - 生命周期事件需要订阅机制                                      │
│  - 控制需要简单 API                                             │
│                                                                 │
│  核心职责：                                                     │
│  1. 状态管理：AgentState (messages, tools, streaming, ...)     │
│  2. 消息队列：PendingMessageQueue (steering/follow-up)         │
│  3. 事件订阅：listeners Set, 事件分发                           │
│  4. 高级 API：prompt(), continue(), steer(), followUp()        │
│  5. 运行管理：activeRun, AbortController, waitForIdle()        │
│                                                                 │
│  设计原则：                                                     │
│  - "状态可观测，运行可控制"                                     │
│  - "事件可订阅，队列可配置"                                     │
│  - "API 简单，内部复杂"                                         │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

---

### 关键设计点 1：状态管理

**AgentState 设计：**

```typescript
type AgentState = {
    systemPrompt: string;          // 系统提示词
    model: Model;                  // 当前模型
    tools: AgentTool[];            // 工具列表
    messages: AgentMessage[];      // 消息历史
    
    thinkingLevel: "off" | "low" | "medium" | "high";  // 思考级别
    
    isStreaming: boolean;          // 是否在流式生成
    streamingMessage?: AgentMessage;  // 当前正在生成的消息
    pendingToolCalls: Set<string>;    // 正在执行的工具
    errorMessage?: string;            // 错误信息
};
```

**MutableAgentState 的巧妙设计：**

```typescript
function createMutableAgentState(initialState?) {
    let tools = initialState?.tools?.slice() ?? [];
    let messages = initialState?.messages?.slice() ?? [];
    
    return {
        // 👇 getter 返回副本，setter 接受并复制
        get tools() { return tools; },
        set tools(nextTools) { tools = nextTools.slice(); },
        
        get messages() { return messages; },
        set messages(nextMessages) { messages = nextMessages.slice(); },
        
        isStreaming: false,
        streamingMessage: undefined,
        ...
    };
}
```

**设计启示：**
- getter/setter 模式：保证数组是副本，避免外部直接修改
- 流式状态：`isStreaming`、`streamingMessage` 实时反映当前运行状态
- 工具状态：`pendingToolCalls` 跟踪正在执行的工具

---

### 关键设计点 2：消息队列机制

**PendingMessageQueue 设计：**

```typescript
class PendingMessageQueue {
    private messages: AgentMessage[] = [];
    public mode: QueueMode;  // "one-at-a-time" | "all"
    
    enqueue(message: AgentMessage): void {
        this.messages.push(message);
    }
    
    drain(): AgentMessage[] {
        if (this.mode === "all") {
            // 👇 一次性取出所有
            const drained = this.messages.slice();
            this.messages = [];
            return drained;
        }
        
        // 👇 取出第一个
        const first = this.messages[0];
        this.messages = this.messages.slice(1);
        return [first];
    }
}
```

**两种队列：**

| 队列类型 | 注入时机 | 用途 | QueueMode |
|---------|---------|------|-----------|
| **steering** | 当前 assistant turn 结束后 | 中途注入，打断当前流程 | "one-at-a-time" 或 "all" |
| **follow-up** | agent 即将停止时 | 后续任务，延续流程 | "one-at-a-time" 或 "all" |

**使用场景：**

```typescript
// Steering：用户中途发送新指令
agent.steer({ role: "user", content: [{ type: "text", text: "请停下来" }] });

// Follow-up：agent 完成后自动执行下一个任务
agent.followUp({ role: "user", content: [{ type: "text", text: "现在帮我整理" }] });
```

---

### 关键设计点 3：事件订阅机制

**订阅设计：**

```typescript
class Agent {
    private readonly listeners = new Set<(event: AgentEvent, signal: AbortSignal) => Promise<void> | void>();
    
    subscribe(listener: (event: AgentEvent, signal: AbortSignal) => Promise<void> | void): () => void {
        this.listeners.add(listener);
        // 👇 返回 unsubscribe 函数
        return () => this.listeners.delete(listener);
    }
    
    private async processEvents(event: AgentEvent): Promise<void> {
        // 1. 更新内部状态
        switch (event.type) {
            case "message_start":
                this._state.streamingMessage = event.message;
                break;
            case "message_end":
                this._state.messages.push(event.message);
                break;
            ...
        }
        
        // 2. 👇 分发给所有订阅者
        const signal = this.activeRun?.abortController.signal;
        for (const listener of this.listeners) {
            await listener(event, signal);
        }
    }
}
```

**设计特点：**
- 事件订阅者可以收到 AbortSignal，用于中断处理
- 订阅者可以是异步的，会等待所有订阅者完成
- 返回 unsubscribe 函数，方便清理

---

### 关键设计点 4：运行管理

**activeRun 设计：**

```typescript
type ActiveRun = {
    promise: Promise<void>;       // 当前运行的 Promise
    resolve: () => void;          // Promise 的 resolve 函数
    abortController: AbortController;  // Abort 控制器
};

class Agent {
    private activeRun?: ActiveRun;
    
    private async runWithLifecycle(executor: (signal: AbortSignal) => Promise<void>): Promise<void> {
        if (this.activeRun) {
            throw new Error("Agent is already processing.");
        }
        
        // 👇 创建 activeRun
        const abortController = new AbortController();
        let resolvePromise = () => {};
        const promise = new Promise<void>((resolve) => {
            resolvePromise = resolve;
        });
        this.activeRun = { promise, resolve: resolvePromise, abortController };
        
        // 👇 设置流式状态
        this._state.isStreaming = true;
        
        try {
            await executor(abortController.signal);
        } catch (error) {
            await this.handleRunFailure(error, abortController.signal.aborted);
        } finally {
            // 👇 清理 activeRun
            this.finishRun();
        }
    }
    
    abort(): void {
        // 👇 中止当前运行
        this.activeRun?.abortController.abort();
    }
    
    waitForIdle(): Promise<void> {
        // 👇 等待当前运行完成
        return this.activeRun?.promise ?? Promise.resolve();
    }
}
```

**设计启示：**
- activeRun 管理整个运行周期：Promise、AbortController、resolve
- 状态与运行分离：`isStreaming` 等状态实时反映，但运行对象独立管理
- waitForIdle：等待所有事件订阅者处理完成（包括 agent_end）

---

## 四、两者协作：完整的调用链

### 从 prompt() 到 streamSimple 的完整流程

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. 应用层调用                                                   │
│    agent.prompt("帮我写一个脚本")                               │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. agent.ts: 状态管理层                                         │
│    - 检查 activeRun（不允许并发）                               │
│    - normalizePromptInput: string → AgentMessage[]              │
│    - runWithLifecycle: 创建 AbortController                     │
│    - 设置 isStreaming = true                                    │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. agent.ts → agent-loop.ts                                     │
│    runAgentLoop(messages, context, config, emit, signal)        │
│    - emit: processEvents (状态更新 + 事件分发)                   │
│    - config: 包含 convertToLlm, streamFn 等                     │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. agent-loop.ts: 编排层                                        │
│    - emit({ type: "agent_start" })                              │
│    - emit({ type: "turn_start" })                               │
│    - emit({ type: "message_start", message })                   │
│    - runLoop: 主循环                                             │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. agent-loop.ts: 消息转换边界                                  │
│    streamAssistantResponse:                                     │
│    - messages: AgentMessage[] (内部格式)                        │
│    - llmMessages = convertToLlm(messages) → Message[]           │
│    - llmContext = { systemPrompt, messages: llmMessages, tools }│
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ 6. 统一抽象层: @earendil-works/pi-ai                            │
│    streamSimple(model, llmContext, options)                     │
│    - getApiProvider(model.api) → 注册表查找                     │
│    - lazyWrapper → 动态 import anthropic.ts / openai.ts         │
│    - 返回 EventStream<AssistantMessageEvent>                    │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ 7. 提供商适配器                                                 │
│    anthropic.ts:                                                │
│    - fetch Anthropic API                                        │
│    - parseSSE: 逐行解析 SSE                                      │
│    - 转换为 AssistantMessageEvent                               │
│    - push({ type: "text_delta", delta, partial })               │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼ (事件流向上传递)
┌─────────────────────────────────────────────────────────────────┐
│ 8. agent-loop.ts: 处理事件                                      │
│    for await (const event of response) {                        │
│        switch (event.type) {                                    │
│            case "text_delta":                                   │
│                emit({ type: "message_update", ... })            │
│        }                                                        │
│    }                                                            │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼ (事件分发)
┌─────────────────────────────────────────────────────────────────┐
│ 9. agent.ts: processEvents                                      │
│    - 更新 _state.streamingMessage                               │
│    - 分发给所有 listeners                                        │
│    - for (const listener of this.listeners) {                   │
│        await listener(event, signal);                           │
│    }                                                            │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼ (应用层收到)
┌─────────────────────────────────────────────────────────────────┐
│ 10. 应用层订阅者                                                │
│    agent.subscribe((event, signal) => {                         │
│        if (event.type === "message_update") {                   │
│            console.log(event.message.content);  // 实时显示     │
│        }                                                        │
│    });                                                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 五、设计模式总结

### agent-loop.ts 的设计模式

| 模式 | 应用场景 | 原因 |
|-----|---------|------|
| **编排模式** | 主循环：LLM → 工具 → 结果 | 协调多个阶段的执行顺序 |
| **转换边界模式** | AgentMessage[] → Message[] | 屏蔽提供商差异，Agent 内部自由扩展 |
| **事件发射模式** | AgentEvent 流 | 实时通知、层次化生命周期 |
| **钩子模式** | beforeToolCall / afterToolCall | 可扩展的工具执行控制 |
| **策略模式** | 并行 vs 顺序执行 | 根据工具特性选择执行策略 |

### agent.ts 的设计模式

| 模式 | 应用场景 | 原因 |
|-----|---------|------|
| **状态管理模式** | AgentState | 持久化、可观测的状态 |
| **队列模式** | steering / follow-up | 消息注入、任务延续 |
| **观察者模式** | subscribe / listeners | 事件订阅、生命周期监听 |
| **生命周期模式** | runWithLifecycle / activeRun | 运行周期管理、中断控制 |
| **门面模式** | prompt() / continue() / steer() | 简单 API，隐藏内部复杂性 |

---

## 六、与统一多提供商 LLM API 设计的关系

### 三条主线的对应关系

```
┌─────────────────────────────────────────────────────────────────┐
│  统一抽象层原则     agent-loop.ts 的实现         agent.ts 的角色 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  异构性 ──► 统一抽象层 ──► 消息转换边界          ──► 不感知差异 │
│  (不同世界)        (差异之上)    (AgentMessage → Message)        │
│                                                                 │
│  流式性 ──► 事件流模型 ──► AgentEvent 流        ──► 事件订阅   │
│  (涌现过程)        (建模涌现)    (实时通知、层次化)              │
│                                                                 │
│  迁移性 ──► 状态转换层 ──► 消息过滤/转换        ──► 状态管理   │
│  (状态不互通)      (转换不兼容)  (convertToLlm)                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 关键启示

**1. agent-loop.ts 是"桥梁"**

```
Agent 内部世界 (AgentMessage[])     ←→     统一 LLM API 世界 (Message[])
                              │
                        转换边界
                              │
                    convertToLlm()
```

- AgentMessage 可以有额外字段（timestamp、metadata）
- Message[] 是统一格式，所有提供商都能处理
- 转换边界让 Agent 内部自由扩展，同时保持与统一 API 的兼容

**2. agent.ts 是"门面"**

```
应用层                          ←→     Agent 内部复杂性
                              │
                        Agent 类
                              │
            prompt() / continue() / steer() / followUp()
```

- 简单的 API：用户不需要关心 agent-loop 的细节
- 状态管理：用户可以随时访问 state.messages、state.isStreaming
- 队列机制：用户可以通过 steer() / followUp() 注入消息
- 事件订阅：用户可以监听所有生命周期事件

**3. 协作形成完整闭环**

```
应用层 → Agent (状态管理) → agent-loop (编排) → 统一 API → 提供商
        ↑                    ↓                      ↓
        └────────── 事件流 ────────── 事件流 ────────── SSE
```

- 应用层通过 Agent API 控制
- Agent 管理状态、队列、订阅
- agent-loop 编排循环、转换消息、发射事件
- 统一 API 屏蔽提供商差异
- 提供商返回 SSE → 事件流向上传递

---

## 七、核心设计启示

### 1. 分层职责清晰

```
┌──────────────────────────────────────────────────┐
│  层次          │ 职责          │ 为什么需要      │
├──────────────────────────────────────────────────┤
│  应用层        │ 用户控制      │ 简单易用        │
│  agent.ts      │ 状态管理      │ 持久化、可观测  │
│  agent-loop.ts │ 循环编排      │ 协调多阶段      │
│  统一 API      │ 屏蔽差异      │ 不感知提供商    │
│  提供商适配器  │ 格式转换      │ 适配不同 API    │
└──────────────────────────────────────────────────┘
```

**启示：每一层只解决一个问题，不越界。**

### 2. 边界处转换

```
AgentMessage[]  ──►  Message[]  ──►  Anthropic/OpenAI/Google 格式
         │               │                    │
   Agent 内部      转换边界           适配器转换
```

**启示：在边界处转换，在内部统一，避免到处转换。**

### 3. 事件流贯穿

```
SSE 流  ──►  AssistantMessageEvent  ──►  AgentEvent  ──►  应用层订阅者
     │                │                    │            │
提供商发射      统一 API 转换       agent-loop 发射  agent 分发
```

**启示：事件流模型贯穿整个架构，从底层到应用层统一建模。**

### 4. 状态可观测

```
AgentState:
- messages: 可访问历史
- isStreaming: 实时状态
- streamingMessage: 当前生成内容
- pendingToolCalls: 工具执行状态
```

**启示：状态实时反映运行情况，应用层可以随时观测。**

---

## 八、总结：agent-loop.ts 与 agent.ts 的角色定位

| 文件 | 本质定位 | 核心职责 | 关键设计 | 与统一 API 的关系 |
|-----|---------|---------|---------|------------------|
| **agent-loop.ts** | 编排层 | 主循环编排、消息转换、事件发射、工具执行 | 转换边界模式、事件流设计、钩子模式 | 在转换边界处调用统一 API |
| **agent.ts** | 状态管理层 | 状态管理、队列机制、事件订阅、运行控制 | 状态管理模式、队列模式、观察者模式 | 不直接调用统一 API，通过 agent-loop |

**一句话总结：**
- **agent-loop.ts** 是"桥梁"，连接 Agent 内部世界和统一 LLM API 世界，在边界处转换，在内部统一。
- **agent.ts** 是"门面"，管理状态、队列、订阅，提供简单 API，隐藏内部复杂性。

两者协作，形成从应用层到提供商的完整闭环，同时保持每一层职责清晰、边界明确、可扩展、可观测。