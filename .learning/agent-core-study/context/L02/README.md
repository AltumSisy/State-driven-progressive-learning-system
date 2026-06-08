# L02 Context: 类型系统完整解析

> 基于 `pi/agent/src/types.ts` 源码的深度学习

---

## 一、AgentState — 代理的"状态卡"

### 1.1 三块记忆法

| 分类 | 属性 | 特性 |
|------|------|------|
| **配置 (怎么干活)** | `systemPrompt`, `model`, `thinkingLevel` | 直接赋值修改 |
| **对话内容 (记着什么)** | `tools`, `messages` | setter 时浅拷贝 |
| **运行状态 (正在干嘛)** | `isStreaming`, `streamingMessage`, `pendingToolCalls`, `errorMessage` | 只读，框架维护 |

> 记忆口诀：**配置、对话、运行中，三块记住不头痛。**

### 1.2 Getter/Setter 防御性拷贝机制

```typescript
// 闭包私有变量
let tools = initialState?.tools?.slice() ?? [];

// getter/setter
get tools() { return tools; }           // 暴露内部引用
set tools(next) { tools = next.slice(); } // 赋值时复制
```

**浅拷贝的设计意图**：

| 操作 | 浅拷贝结果 | 深拷贝结果 |
|------|-----------|-----------|
| 外部修改工具对象属性 | Agent 同步看到修改 ✅ | Agent 看不到 ❌（状态分裂） |
| 外部向原数组 push 新工具 | Agent 不受影响（安全隔离数组） | 不受影响（但浪费性能） |
| 外部替换整个数组 | 通过 setter 复制后隔离 ✅ | 隔离但每个对象都复制（昂贵） |

**结论**：浅拷贝是**精准防御** — 只防御数组被替换，同时允许共享对象变更。

### 1.3 只读属性详解

| 属性 | 含义 | 框架更新时机 |
|------|------|-------------|
| `isStreaming` | 是否正在处理 | LLM调用开始→true，agent_end监听器完成→false |
| `streamingMessage` | 当前流式响应的部分消息 | 流式生成中实时更新 |
| `pendingToolCalls` | 正在执行的工具调用ID集合 | 工具开始→add，工具结束→remove |
| `errorMessage` | 最近一次失败/中止的错误信息 | 错误发生时设置 |

---

## 二、AgentTool — 代理的"技能卡"

### 2.1 五要素法

| 字段 | 来源 | 作用 |
|------|------|------|
| `name` | 继承 Tool | 工具标识 |
| `description` | 继承 Tool | 工具描述 |
| `parameters` | 继承 Tool | TypeBox schema |
| `label` | agent-core 新增 | UI 显示标签 |
| `prepareArguments` | agent-core 新增 | 兼容性 shim（参数预处理） |
| `execute` | agent-core 新增 | 核心执行函数 |
| `executionMode` | agent-core 新增 | 并发模式覆盖 |

> 记忆口诀：**名标预执模，干活传四宝（ID、参数、信号、回调）。**

### 2.2 execute 参数详解

```typescript
execute: (
  toolCallId: string,       // 本次调用的唯一ID（关联事件、取消）
  params: Static<TSchema>,  // TypeBox 验证后的类型安全参数
  signal?: AbortSignal,     // 取消信号（用户停止、超时）
  onUpdate?: Callback,      // 进度回调（流式返回中间结果）
) => Promise<AgentToolResult>
```

### 2.3 泛型参数化解释

```typescript
interface AgentTool<TParameters extends TSchema = TSchema, TDetails = any>
```

| 写法 | 通俗含义 |
|------|---------|
| `<TParameters extends TSchema>` | 参数类型必须能被 JSON Schema 描述 |
| `= TSchema` | 默认值，不指定时使用通用 schema |
| `<TDetails = any>` | 返回详情的类型，默认 any |

**类型安全示例**：
```typescript
interface WeatherParams { city: string; unit?: 'celsius' | 'fahrenheit'; }

const weatherTool: AgentTool<WeatherParams, { requestId: string }> = {
  execute: async (id, params, signal, onUpdate) => {
    console.log(params.city);  // 类型自动推断！
    return { content: '...', details: { requestId: '123' } };
  }
};
```

### 2.4 prepareArguments vs schema 验证

| 阶段 | 函数 | 作用 |
|------|------|------|
| 1 | `prepareArguments` | 兼容性 shim，处理模型传参不标准 |
| 2 | TypeBox schema | 正式验证，确保参数符合定义 |

**常见误区**：`prepareArguments` 不是验证器，是容错预处理！

---

## 三、AgentLoopConfig — 主循环的"规则书"

### 3.1 八大钩子（按执行顺序）

| 钩子 | 执行时机 | 作用 | 记忆点 |
|------|---------|------|--------|
| `model` | 循环开始 | 指定使用的模型 | 必填 |
| `convertToLlm` | 每次LLM调用前 | 内部消息→LLM格式 | **翻译官** |
| `transformContext` | convertToLlm之前 | 上下文裁剪/注入 | **整理官** |
| `getApiKey` | LLM调用时 | 动态获取API Key | **钥匙官** |
| `beforeToolCall` | 工具执行前 | 可阻止执行 | **拦截官** |
| `afterToolCall` | 工具执行后 | 可覆写结果 | **修改官** |
| `shouldStopAfterTurn` | turn结束后 | 决定是否停止 | **刹车官** |
| `prepareNextTurn` | 下一轮前 | 调整配置 | **调参官** |
| `getSteeringMessages` | 下一轮开始前 | 注入引导消息 | **方向盘** |
| `getFollowUpMessages` | 无工具无引导时 | 注入后续消息 | **加餐官** |

### 3.2 钩子返回值语义

| 钩子 | 返回值 | 语义 |
|------|--------|------|
| `beforeToolCall` | `{ block: true, reason: "..." }` | 阻止执行，发出 error tool result |
| `afterToolCall` | `{ content: [...], details: {...} }` | **字段级替换**，无深度合并 |
| `shouldStopAfterTurn` | `true` | 优雅停止，不再发起下一轮 |
| `prepareNextTurn` | `{ model, thinkingLevel }` | 替换下一轮配置 |

**afterToolCallResult 关键**：返回的字段会**完全替换**原字段，需手动展开：
```typescript
afterToolCall: async ({ result }) => {
  return {
    details: { ...result.details, audited: true },  // 手动合并
  };
}
```

### 3.3 工具执行模式

| 模式 | 行为 | 适用场景 |
|------|------|---------|
| `sequential` | 一个一个执行 | 写操作、独占资源 |
| `parallel` | 预检顺序→执行并发→结果原序 | 只读、独立操作 |

**parallel 详细流程**：
1. 预检阶段：prepareArguments → schema验证 → beforeToolCall（顺序）
2. 执行阶段：execute（并发）
3. 结果阶段：tool_execution_end 按完成顺序，ToolResult 消息按原序

---

## 四、辅助类型速查

| 类型 | 一句话作用 |
|------|-----------|
| `StreamFn` | 安全流式函数，不抛异常，错误编码在流内 |
| `ToolExecutionMode` | `"sequential" | "parallel"` |
| `QueueMode` | `"all" | "one-at-a-time"` — 队列消耗策略 |
| `AgentToolCall` | 消息中工具调用块的结构 |
| `BeforeToolCallResult` | `{ block?: boolean, reason?: string }` |
| `ThinkingLevel` | 6级：off → minimal → low → medium → high → xhigh |

**xhigh 注意**：仅部分模型支持 extended thinking，需检查 `model.metadata`。

---

## 五、三者关系总览

| 概念 | 作用 | 存放位置 |
|------|------|----------|
| `AgentState` | 代理的**当前瞬时状态** | 运行时不断变化 |
| `AgentTool` | 定义**单个技能** | 放在 `AgentState.tools` 数组 |
| `AgentLoopConfig` | 定义**主循环行为规则** | 代理创建时传入，通常不变 |

简单说：
- **State** = 这一刻的"是什么"
- **Tool** = 技能卡
- **LoopConfig** = 工作流程规则书

---

## 六、常见错误清单

| 错误类型 | 后果 | 正确做法 |
|---------|------|---------|
| 遗漏 `parameters` | TypeBox 验证失败 | 使用 `Type.Object({})` 空 schema |
| 混淆 `prepareArguments` | 当成验证器用 | 它是兼容性 shim，验证在之后 |
| `afterToolCallResult` 深度合并期望 | 丢失原值 | 手动 `{ ...result.details, new }` |
| `xhigh` 不检查模型 | 部分模型忽略/报错 | 检查 `getModelThinkingLevel(model)` |
| 直接 push 到 tools/messages | 污染内部状态 | 推荐整体替换 `state.tools = [...]` |
| 钩子函数抛异常 | 中断底层循环 | 必须安全返回 fallback 值 |

---

## 七、源码映射

| 内容 | 文件 | 行数 |
|------|------|------|
| AgentState | `types.ts` | L317-342 |
| AgentTool | `types.ts` | L361-384 |
| AgentToolResult | `types.ts` | L344-355 |
| AgentLoopConfig | `types.ts` | L135-277 |
| AgentEvent | `types.ts` | L403-418 |
| ThinkingLevel | `types.ts` | L284 |
| ToolExecutionMode | `types.ts` | L36 |
| QueueMode | `types.ts` | L44 |
| BeforeToolCallResult | `types.ts` | L55-58 |
| AfterToolCallResult | `types.ts` | L72-81 |