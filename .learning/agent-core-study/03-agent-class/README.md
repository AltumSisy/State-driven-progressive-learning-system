# 03 - Agent 类

## 类概述

`Agent` 类是围绕低级 `agent-loop` 的状态化包装器，提供：
- 状态管理
- 生命周期事件
- 工具执行
- Steering 和 Follow-up 队列

## 构造函数选项

```typescript
const agent = new Agent({
  // 初始状态
  initialState: {
    systemPrompt: string,
    model: Model<any>,
    thinkingLevel: "off" | "minimal" | "low" | "medium" | "high" | "xhigh",
    tools: AgentTool<any>[],
    messages: AgentMessage[],
  },
  
  // 核心配置
  convertToLlm?: (messages) => messages.filter(...),  // 消息转换
  transformContext?: async (messages, signal) => pruneOldMessages(messages),  // 上下文转换
  
  // 队列模式
  steeringMode?: "one-at-a-time" | "all",   // 默认: "one-at-a-time"
  followUpMode?: "one-at-a-time" | "all",   // 默认: "one-at-a-time"
  
  // 流和传输
  streamFn?: StreamFn,                      // 自定义流函数
  sessionId?: string,                       // 会话 ID（用于缓存）
  thinkingBudgets?: ThinkingBudgets,        // 思考预算
  transport?: Transport,                     // 传输方式
  maxRetryDelayMs?: number,                 // 最大重试延迟
  
  // 工具钩子
  toolExecution?: "parallel" | "sequential", // 工具执行模式
  beforeToolCall?: async (context, signal) => { block?: boolean, reason?: string },
  afterToolCall?: async (context, signal) => { content?, details?, isError?, terminate? },
  prepareNextTurn?: async (signal) => { context?, model?, thinkingLevel? },
  
  // 回调
  onPayload?: (payload) => void,            // 收到 payload 时
  onResponse?: (response) => void,          // 收到响应时
  getApiKey?: async (provider) => key,     // 动态 API key 获取
});
```

## 状态管理

### 读取状态

```typescript
// 状态属性
agent.state.systemPrompt      // 系统提示
agent.state.model              // 当前模型
agent.state.thinkingLevel      // 思考级别
agent.state.tools              // 工具列表
agent.state.messages           // 消息历史
agent.state.isStreaming        // 是否正在流式传输
agent.state.streamingMessage   // 当前流式消息
agent.state.pendingToolCalls   // 待处理工具调用
agent.state.errorMessage       // 错误信息
```

### 修改状态

```typescript
// 这些赋值会复制顶层数组
agent.state.systemPrompt = "New prompt";
agent.state.model = getModel("openai", "gpt-4o");
agent.state.thinkingLevel = "medium";
agent.state.tools = [myTool];       // 复制数组
agent.state.messages = newMessages; // 复制数组

// 直接修改返回的数组会修改当前状态
agent.state.messages.push(message);
```

## 核心方法

### prompt() - 发送消息

```typescript
// 文本提示
await agent.prompt("Hello!");

// 带图片
await agent.prompt("What's in this image?", [
  { type: "image", data: base64Data, mimeType: "image/jpeg" }
]);

// AgentMessage 直接
await agent.prompt({
  role: "user",
  content: "Hello",
  timestamp: Date.now()
});

// 批量消息
await agent.prompt([
  { role: "user", content: "Hello", timestamp: Date.now() },
  { role: "user", content: "World", timestamp: Date.now() }
]);
```

### continue() - 继续对话

```typescript
// 从当前上下文继续，不添加新消息
// 最后一条消息必须是 user 或 toolResult
await agent.continue();
```

### reset() - 重置状态

```typescript
// 清除消息历史、运行时状态和队列
agent.reset();
```

## 事件订阅

```typescript
const unsubscribe = agent.subscribe(async (event, signal) => {
  switch (event.type) {
    case "agent_start":
      console.log("Agent started");
      break;
    case "message_update":
      if (event.assistantMessageEvent.type === "text_delta") {
        process.stdout.write(event.assistantMessageEvent.delta);
      }
      break;
    case "agent_end":
      console.log("Agent finished");
      await flushSessionState(signal);  // 最终屏障工作
      break;
  }
});

// 取消订阅
unsubscribe();
```

**重要特性**:
- 监听器按注册顺序 `await`
- `agent_end` 监听器完成后 Agent 才进入空闲状态
- 监听器接收当前运行的中止信号

## Steering 和 Follow-up

### Steering（转向）

在 Agent 运行时注入消息，打断当前流程：

```typescript
// 在 Agent 运行时发送转向消息
agent.steer({
  role: "user",
  content: "Stop! Do this instead.",
  timestamp: Date.now(),
});

// 模式设置
agent.steeringMode = "one-at-a-time";  // 或 "all"

// 清除队列
agent.clearSteeringQueue();
```

### Follow-up（后续）

在 Agent 完成后继续执行：

```typescript
// 在 Agent 完成后继续
agent.followUp({
  role: "user",
  content: "Also summarize the result.",
  timestamp: Date.now(),
});

// 模式设置
agent.followUpMode = "one-at-a-time";  // 或 "all"

// 清除队列
agent.clearFollowUpQueue();
```

### 队列控制

```typescript
// 清除所有队列
agent.clearAllQueues();

// 检查是否有队列消息
if (agent.hasQueuedMessages()) {
  // ...
}
```

## 流程控制

### 中止和等待

```typescript
// 中止当前运行
agent.abort();

// 等待当前运行完成
await agent.waitForIdle();

// 获取当前中止信号
const signal = agent.signal;
if (signal?.aborted) {
  // ...
}
```

## 内部实现

### PendingMessageQueue 类

```typescript
class PendingMessageQueue {
  mode: QueueMode;  // "all" | "one-at-a-time"
  
  enqueue(message: AgentMessage): void;
  hasItems(): boolean;
  drain(): AgentMessage[];  // 根据模式返回消息
  clear(): void;
}
```

### 状态管理

```typescript
// 内部可变状态
interface MutableAgentState extends AgentState {
  isStreaming: boolean;
  streamingMessage?: AgentMessage;
  pendingToolCalls: Set<string>;
  errorMessage?: string;
}

// 创建初始状态
function createMutableAgentState(initialState?): MutableAgentState {
  // messages 和 tools 使用 getter/setter 复制数组
}
```

## 与 agentLoop 的区别

| 特性 | Agent 类 | agentLoop |
|-----|---------|-----------|
| 事件处理 | 等待订阅者完成 | 观察性流 |
| 屏障行为 | `message_end` 是工具预检的屏障 | 无屏障 |
| 状态管理 | 内置 | 外部管理 |
| 队列 | 内置 Steering/Follow-up | 通过配置 |
| 使用场景 | UI 应用 | 批处理/低级控制 |

## 最佳实践

1. **使用 `waitForIdle()`** 确保 Agent 完成后再进行其他操作
2. **在 `agent_end` 中做屏障工作** 如刷新会话状态
3. **错误处理** 在 `afterToolCall` 中修改错误状态
4. **Steering 用于打断** Follow-up 用于追加任务
5. **状态修改** 直接修改数组后赋值会复制，原地修改不会

## 下一步

→ [04 - Agent 循环](./04-agent-loop)
