# 06 - 事件流

## 概述

Agent 通过事件流与外部通信。理解事件序列对构建响应式 UI 至关重要。

## 事件类型概览

| 事件 | 触发时机 | 数据 |
|-----|---------|------|
| `agent_start` | Agent 开始处理 | - |
| `agent_end` | Agent 完成 | `messages: AgentMessage[]` |
| `turn_start` | 新 Turn 开始 | - |
| `turn_end` | Turn 完成 | `message`, `toolResults` |
| `message_start` | 消息开始 | `message` |
| `message_update` | 消息更新（仅助手） | `message`, `assistantMessageEvent` |
| `message_end` | 消息完成 | `message` |
| `tool_execution_start` | 工具开始 | `toolCallId`, `toolName`, `args` |
| `tool_execution_update` | 工具进度 | `toolCallId`, `toolName`, `args`, `partialResult` |
| `tool_execution_end` | 工具完成 | `toolCallId`, `toolName`, `result`, `isError` |

## Prompt 事件序列

### 无工具调用

```
agent_start
│
├─ turn_start
│  │
│  ├─ message_start   { role: "user" }
│  ├─ message_end
│  │
│  ├─ message_start   { role: "assistant" }
│  ├─ message_update  { type: "text_delta", delta: "Hello" }
│  ├─ message_update  { type: "text_delta", delta: "!" }
│  ├─ message_end
│  │
│  └─ turn_end        { message: assistantMessage, toolResults: [] }
│
└─ agent_end          { messages: [...] }
```

### 带工具调用

```
agent_start
│
├─ turn_start
│  │
│  ├─ message_start   { role: "user" }
│  ├─ message_end
│  │
│  ├─ message_start   { role: "assistant", content: [toolCall] }
│  ├─ message_end     // 助手消息包含工具调用
│  │
│  ├─ tool_execution_start  { toolCallId, toolName, args }
│  ├─ tool_execution_update { partialResult }
│  ├─ tool_execution_end    { result, isError }
│  │
│  ├─ message_start   { role: "toolResult" }
│  ├─ message_end
│  │
│  └─ turn_end        { message, toolResults }
│
├─ turn_start         // 下一 Turn
│  │
│  ├─ message_start   { role: "assistant" }  // 对工具结果的响应
│  ├─ message_update
│  ├─ message_end
│  │
│  └─ turn_end
│
└─ agent_end
```

## Continue 事件序列

```typescript
// 从现有上下文继续
await agent.continue();
```

序列类似，但没有初始 user message：

```
agent_start
│
├─ turn_start
│  │
│  ├─ message_start   { role: "assistant" }
│  ├─ message_update
│  ├─ message_end
│  │
│  └─ turn_end
│
└─ agent_end
```

**注意**: 最后一条消息必须是 `user` 或 `toolResult`。

## Steering 事件序列

当 Agent 运行时发送 steering 消息：

```
agent_start
│
├─ turn_start
│  ├─ ...
│  └─ turn_end
│
├─ turn_start         // Steering 触发的 Turn
│  ├─ message_start   { role: "user" }  // steering 消息
│  ├─ message_end
│  ├─ message_start   { role: "assistant" }
│  ├─ ...
│  └─ turn_end
│
└─ agent_end
```

## Follow-up 事件序列

当 Agent 完成后有 follow-up 消息：

```
agent_start
│
├─ turn_start
│  └─ ...
│  └─ turn_end
│
├─ turn_start         // Follow-up 触发的 Turn
│  ├─ message_start   { role: "user" }  // follow-up 消息
│  ├─ message_end
│  ├─ message_start   { role: "assistant" }
│  ├─ ...
│  └─ turn_end
│
└─ agent_end
```

## 多工具调用事件序列

### Parallel 模式（默认）

```
// 3 个工具并发执行
├─ tool_execution_start  { toolCallId: A }
├─ tool_execution_start  { toolCallId: B }
├─ tool_execution_start  { toolCallId: C }
│
├─ tool_execution_end    { toolCallId: B }  // B 先完成
├─ tool_execution_end    { toolCallId: A }  // A 后完成
├─ tool_execution_end    { toolCallId: C }  // C 最后
│
// 结果消息按助手原始顺序
├─ message_start         { toolResult: A }
├─ message_end
├─ message_start         { toolResult: B }
├─ message_end
├─ message_start         { toolResult: C }
├─ message_end
```

### Sequential 模式

```
├─ tool_execution_start  { toolCallId: A }
├─ tool_execution_end    { toolCallId: A }
├─ message_start         { toolResult: A }
├─ message_end
│
├─ tool_execution_start  { toolCallId: B }
├─ tool_execution_end    { toolCallId: B }
├─ message_start         { toolResult: B }
├─ message_end
│
├─ tool_execution_start  { toolCallId: C }
├─ tool_execution_end    { toolCallId: C }
├─ message_start         { toolResult: C }
├─ message_end
```

## message_update 详解

仅用于 assistant 消息，包含 `assistantMessageEvent`：

```typescript
interface AssistantMessageEvent {
  // 类型决定 data 内容
  type: "text_delta" | "thinking_delta" | "signature_delta" | 
        "toolCall_start" | "toolCall_delta" | "toolCall_end" |
        "toolResult" | "stop" | "error";
}

// 示例事件序列
├─ message_start
├─ message_update { type: "thinking_delta", delta: "..." }  // 推理内容
├─ message_update { type: "text_delta", delta: "Based on" }    // 文本增量
├─ message_update { type: "text_delta", delta: " my analysis" }
├─ message_update { type: "toolCall_start", toolCall: {...} } // 工具调用开始
├─ message_update { type: "toolCall_end" }
├─ message_end
```

## 订阅处理

### Agent 类订阅

```typescript
agent.subscribe(async (event, signal) => {
  // Agent 会 await 这个 Promise
  await handleEvent(event);
});

// 取消订阅
const unsubscribe = agent.subscribe(...);
unsubscribe();
```

**重要特性**:
- 监听器按注册顺序 `await`
- `agent_end` 监听器完成后 Agent 才空闲
- 监听器接收中止信号

### agentLoop 处理

```typescript
for await (const event of agentLoop(...)) {
  // 不会等待你的处理
  handleEvent(event);
}
```

**区别**: `agentLoop` 是观察性流，不等待你的事件处理。

## UI 更新模式

### 消息列表更新

```typescript
agent.subscribe((event) => {
  switch (event.type) {
    case "message_start":
      ui.addMessage(event.message);
      break;
    case "message_update":
      if (event.assistantMessageEvent.type === "text_delta") {
        ui.appendToLastMessage(event.assistantMessageEvent.delta);
      }
      break;
    case "message_end":
      ui.finalizeMessage(event.message);
      break;
  }
});
```

### 工具执行更新

```typescript
agent.subscribe((event) => {
  switch (event.type) {
    case "tool_execution_start":
      ui.showToolIndicator(event.toolCallId, event.toolName);
      break;
    case "tool_execution_update":
      ui.updateToolProgress(event.toolCallId, event.partialResult);
      break;
    case "tool_execution_end":
      if (event.isError) {
        ui.showToolError(event.toolCallId, event.result);
      } else {
        ui.showToolSuccess(event.toolCallId, event.result);
      }
      break;
  }
});
```

### 状态指示器

```typescript
agent.subscribe((event) => {
  switch (event.type) {
    case "agent_start":
      ui.setStatus("Running");
      break;
    case "turn_start":
      ui.setStatus("Thinking...");
      break;
    case "tool_execution_start":
      ui.setStatus(`Running ${event.toolName}...`);
      break;
    case "agent_end":
      ui.setStatus("Idle");
      break;
  }
});
```

## 完整事件处理示例

```typescript
const agent = new Agent({
  initialState: { /* ... */ }
});

// 消息存储
const messages: AgentMessage[] = [];
const streamingContent = new Map<string, string>();
const pendingTools = new Set<string>();

agent.subscribe(async (event, signal) => {
  switch (event.type) {
    case "agent_start":
      console.log("Agent started");
      break;
      
    case "message_start":
      messages.push(event.message);
      if (event.message.role === "assistant") {
        streamingContent.set(event.message.id || "latest", "");
      }
      break;
      
    case "message_update": {
      const { assistantMessageEvent } = event;
      if (assistantMessageEvent.type === "text_delta") {
        const current = streamingContent.get("latest") || "";
        streamingContent.set("latest", current + assistantMessageEvent.delta);
        ui.updateStreamingText(streamingContent.get("latest")!);
      }
      break;
    }
      
    case "message_end":
      ui.finalizeMessage(event.message);
      break;
      
    case "tool_execution_start":
      pendingTools.add(event.toolCallId);
      ui.showToolRunning(event.toolCallId, event.toolName);
      break;
      
    case "tool_execution_end":
      pendingTools.delete(event.toolCallId);
      if (event.isError) {
        ui.showToolError(event.toolCallId, event.result);
      } else {
        ui.showToolComplete(event.toolCallId, event.result);
      }
      break;
      
    case "turn_end":
      console.log(`Turn completed with ${event.toolResults.length} tool results`);
      break;
      
    case "agent_end":
      console.log("Agent completed");
      await saveSession(event.messages);  // 屏障工作
      break;
  }
});

// 运行 Agent
await agent.prompt("Hello!");
await agent.waitForIdle();  // 确保所有事件处理完成
```

## 事件时序保证

1. **agent_start** 是第一个事件
2. **agent_end** 是最后一个事件
3. **turn_start** 在 **turn_end** 之前
4. **message_start** 在 **message_end** 之前
5. **tool_execution_start** 在 **tool_execution_end** 之前
6. **message_end** 在对应的 **tool_execution_start** 之前（助手消息包含工具调用时）

## 下一步

→ [07 - Harness 系统](./07-harness)
