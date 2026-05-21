# 04 - Agent 循环

## 概述

`agentLoop` 和 `agentLoopContinue` 是低级 API，生成 `AgentEvent` 异步迭代器。它们提供比 `Agent` 类更细粒度的控制。

## 核心函数

### agentLoop

```typescript
import { agentLoop } from "@earendil-works/pi-agent-core";

const stream = agentLoop(
  prompts: AgentMessage[],           // 初始提示消息
  context: AgentContext,             // 初始上下文
  config: AgentLoopConfig            // 循环配置
): AsyncIterable<AgentEvent>;

// 使用
for await (const event of agentLoop([userMessage], context, config)) {
  console.log(event.type);
}
```

### agentLoopContinue

```typescript
import { agentLoopContinue } from "@earendil-works/pi-agent-core";

// 从现有上下文继续（不添加新消息）
const stream = agentLoopContinue(
  context: AgentContext,
  config: AgentLoopConfig
): AsyncIterable<AgentEvent>;
```

## AgentLoopConfig 详解

```typescript
interface AgentLoopConfig extends SimpleStreamOptions {
  // 必需
  model: Model<any>;
  convertToLlm: (messages: AgentMessage[]) => Message[] | Promise<Message[]>;
  
  // 可选: 上下文转换
  transformContext?: (messages: AgentMessage[], signal?: AbortSignal) => Promise<AgentMessage[]>;
  
  // 可选: 动态 API Key
  getApiKey?: (provider: string) => Promise<string | undefined> | string | undefined;
  
  // 可选: Turn 停止检查
  shouldStopAfterTurn?: (context: ShouldStopAfterTurnContext) => boolean | Promise<boolean>;
  
  // 可选: 准备下一 Turn
  prepareNextTurn?: (context: PrepareNextTurnContext) => AgentLoopTurnUpdate | undefined | Promise<...>;
  
  // 可选: Steering 消息源
  getSteeringMessages?: () => Promise<AgentMessage[]>;
  
  // 可选: Follow-up 消息源
  getFollowUpMessages?: () => Promise<AgentMessage[]>;
  
  // 可选: 工具执行模式
  toolExecution?: "parallel" | "sequential";  // 默认: "parallel"
  
  // 可选: 工具钩子
  beforeToolCall?: (context: BeforeToolCallContext, signal?: AbortSignal) => Promise<BeforeToolCallResult | undefined>;
  afterToolCall?: (context: AfterToolCallContext, signal?: AbortSignal) => Promise<AfterToolCallResult | undefined>;
}
```

## 循环执行流程

```
agentLoop(prompts, context, config)
│
├─ 添加 prompts 到 context.messages
│
├─ 触发 agent_start
│
├─ ╔═══════════════════════════════════════╗
│  ║           TURN LOOP (循环)            ║
│  ╠═══════════════════════════════════════╣
│  ║                                       ║
│  ║  ┌─ transformContext(context.messages) ║
│  ║  ├─ convertToLlm(transformed)         ║
│  ║  ├─ trigger turn_start                ║
│  ║  │                                     ║
│  ║  ├─ stream LLM response               ║
│  ║  │  ├─ trigger message_start          ║
│  ║  │  ├─ trigger message_update (stream)║
│  ║  │  └─ trigger message_end             ║
│  ║  │                                     ║
│  ║  ├─ IF has tool calls:                ║
│  ║  │   ├─ beforeToolCall (preflight)    ║
│  ║  │   ├─ execute tools                 ║
│  ║  │   │  ├─ trigger tool_execution_*   ║
│  ║  │   ├─ afterToolCall                ║
│  ║  │   ├─ add tool result messages      ║
│  ║  │   └─ trigger message_start/end     ║
│  ║  │                                     ║
│  ║  ├─ trigger turn_end                  ║
│  ║  │                                     ║
│  ║  ├─ shouldStopAfterTurn?              ║
│  ║  │   └─ true → break                  ║
│  ║  │                                     ║
│  ║  ├─ prepareNextTurn?                  ║
│  ║  │   └─ update context/model           ║
│  ║  │                                     ║
│  ║  ├─ getSteeringMessages?              ║
│  ║  │   └─ add to context, continue loop ║
│  ║  │                                     ║
│  ║  ├─ getFollowUpMessages?              ║
│  ║  │   └─ add to context, continue loop ║
│  ║  │                                     ║
│  ║  └─ continue loop (next turn)         ║
│  ╚═══════════════════════════════════════╝
│
├─ 触发 agent_end
│
└─ 流结束
```

## 关键钩子详解

### shouldStopAfterTurn

在 turn 结束后调用，决定是否停止循环：

```typescript
shouldStopAfterTurn: async ({ message, toolResults, context, newMessages }) => {
  // 示例: 在上下文太满前停止
  return estimateTokens(context.messages) > MAX_TOKENS;
}
```

**执行时机**:
- 在 `turn_end` 触发后
- 在检查 steering/follow-up 队列前
- 返回 `true` 会触发 `agent_end` 并退出

### prepareNextTurn

在下一 turn 开始前调用，可修改上下文：

```typescript
prepareNextTurn: async ({ message, toolResults, context, newMessages }) => {
  // 示例: 切换到更强的模型
  if (needsComplexReasoning(context)) {
    return {
      context: { ...context, systemPrompt: "Complex reasoning mode" },
      model: getModel("anthropic", "claude-opus-4-20250514"),
      thinkingLevel: "high"
    };
  }
}
```

### beforeToolCall

在工具执行前调用，可阻止执行：

```typescript
beforeToolCall: async ({ toolCall, args, context }, signal) => {
  // 示例: 阻止危险命令
  if (toolCall.name === "bash") {
    const cmd = args.command;
    if (cmd.includes("rm -rf /")) {
      return { block: true, reason: "Dangerous command blocked" };
    }
  }
  
  // 返回 undefined 或 {} 表示允许执行
}
```

### afterToolCall

在工具执行后调用，可修改结果：

```typescript
afterToolCall: async ({ toolCall, result, isError, context }, signal) => {
  // 示例: 标记已审计
  if (!isError) {
    return {
      details: { ...result.details, audited: true }
    };
  }
  
  // 示例: 终止 Agent
  if (toolCall.name === "notify_done") {
    return { terminate: true };
  }
}
```

## 与 Agent 类的对比

```typescript
// ===== 使用 Agent 类 =====
const agent = new Agent({ initialState, ... });
agent.subscribe(handler);
await agent.prompt("Hello");

// ===== 使用 agentLoop =====
const context = { systemPrompt: "...", messages: [], tools: [] };
const config = { model, convertToLlm: ... };

for await (const event of agentLoop([userMessage], context, config)) {
  await handler(event);  // 需要自己 await
}
```

| 方面 | Agent 类 | agentLoop |
|-----|---------|-----------|
| 事件处理 | 自动等待订阅者 | 观察者模式 |
| 队列管理 | 内置 | 通过 getSteeringMessages/getFollowUpMessages |
| 状态修改 | 自动管理 | 手动管理 |
| 使用复杂度 | 低 | 高 |
| 控制粒度 | 中等 | 高 |

## 最佳实践

### 批处理场景

```typescript
// 适合批量处理，无需订阅管理
async function batchProcess(items: string[]) {
  const results = [];
  
  for (const item of items) {
    const events = [];
    for await (const event of agentLoop(
      [{ role: "user", content: item, timestamp: Date.now() }],
      context,
      config
    )) {
      events.push(event);
      if (event.type === "agent_end") {
        results.push(event.messages);
      }
    }
  }
  
  return results;
}
```

### 自定义队列

```typescript
// 实现自定义 steering/follow-up 逻辑
const steeringQueue: AgentMessage[] = [];
const followUpQueue: AgentMessage[] = [];

const config: AgentLoopConfig = {
  model,
  convertToLlm,
  getSteeringMessages: async () => {
    const messages = steeringQueue.slice();
    steeringQueue.length = 0;
    return messages;
  },
  getFollowUpMessages: async () => {
    if (steeringQueue.length > 0) return []; // Steering 优先
    const messages = followUpQueue.slice();
    followUpQueue.length = 0;
    return messages;
  },
};
```

### 上下文管理

```typescript
// 使用 shouldStopAfterTurn 进行上下文压缩
shouldStopAfterTurn: async ({ context, newMessages }) => {
  const tokenCount = estimateTokens(context.messages);
  
  if (tokenCount > COMPACTION_THRESHOLD) {
    // 触发压缩
    context.messages = await compactContext(context.messages);
    return false; // 不停止，继续
  }
  
  return false;
}
```

## 下一步

→ [05 - 工具系统](./05-tool-system)
