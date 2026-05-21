# 02 - 核心类型系统

## AgentMessage 类型

### 基础定义

```typescript
// 可通过声明合并扩展
interface CustomAgentMessages {
  // 应用自定义消息类型
}

// 联合类型: LLM 消息 + 自定义消息
type AgentMessage = Message | CustomAgentMessages[keyof CustomAgentMessages];
```

### 扩展自定义消息类型

```typescript
declare module "@earendil-works/pi-agent-core" {
  interface CustomAgentMessages {
    notification: {
      role: "notification";
      text: string;
      timestamp: number
    };
    artifact: {
      role: "artifact";
      id: string;
      content: string;
      timestamp: number
    };
  }
}
```

**注意**: 自定义消息必须通过 `convertToLlm` 转换或过滤，因为 LLM 只理解标准消息类型。

## 核心类型详解

### AgentState - Agent 状态

```typescript
interface AgentState {
  systemPrompt: string;           // 系统提示
  model: Model<any>;             // 当前模型
  thinkingLevel: ThinkingLevel; // 推理级别
  tools: AgentTool<any>[];       // 可用工具
  messages: AgentMessage[];      // 对话历史
  
  // 只读状态
  readonly isStreaming: boolean;
  readonly streamingMessage?: AgentMessage;
  readonly pendingToolCalls: ReadonlySet<string>;
  readonly errorMessage?: string;
}
```

### AgentTool - 工具定义

```typescript
interface AgentTool<TParameters extends TSchema = TSchema, TDetails = any> extends Tool<TParameters> {
  label: string;                                    // UI 显示标签
  prepareArguments?: (args: unknown) => Static<TParameters>; // 参数预处理
  execute: (
    toolCallId: string,                           // 工具调用 ID
    params: Static<TParameters>,                  // 验证后的参数
    signal?: AbortSignal,                         // 中止信号
    onUpdate?: AgentToolUpdateCallback<TDetails> // 进度回调
  ) => Promise<AgentToolResult<TDetails>>;
  executionMode?: ToolExecutionMode;              // 执行模式覆盖
}
```

### AgentEvent - 事件类型

```typescript
type AgentEvent =
  // Agent 生命周期
  | { type: "agent_start" }
  | { type: "agent_end"; messages: AgentMessage[] }
  
  // Turn 生命周期
  | { type: "turn_start" }
  | { type: "turn_end"; message: AgentMessage; toolResults: ToolResultMessage[] }
  
  // Message 生命周期
  | { type: "message_start"; message: AgentMessage }
  | { type: "message_update"; message: AgentMessage; assistantMessageEvent: AssistantMessageEvent }
  | { type: "message_end"; message: AgentMessage }
  
  // Tool 执行生命周期
  | { type: "tool_execution_start"; toolCallId: string; toolName: string; args: any }
  | { type: "tool_execution_update"; toolCallId: string; toolName: string; args: any; partialResult: any }
  | { type: "tool_execution_end"; toolCallId: string; toolName: string; result: any; isError: boolean };
```

### AgentContext - 上下文快照

```typescript
interface AgentContext {
  systemPrompt: string;
  messages: AgentMessage[];
  tools?: AgentTool<any>[];
}
```

### AgentLoopConfig - 循环配置

```typescript
interface AgentLoopConfig extends SimpleStreamOptions {
  model: Model<any>;
  convertToLlm: (messages: AgentMessage[]) => Message[] | Promise<Message[]>;
  transformContext?: (messages: AgentMessage[], signal?: AbortSignal) => Promise<AgentMessage[]>;
  getApiKey?: (provider: string) => Promise<string | undefined> | string | undefined;
  shouldStopAfterTurn?: (context: ShouldStopAfterTurnContext) => boolean | Promise<boolean>;
  prepareNextTurn?: (context: PrepareNextTurnContext) => AgentLoopTurnUpdate | undefined | Promise<AgentLoopTurnUpdate | undefined>;
  getSteeringMessages?: () => Promise<AgentMessage[]>;
  getFollowUpMessages?: () => Promise<AgentMessage[]>;
  toolExecution?: ToolExecutionMode;
  beforeToolCall?: (context: BeforeToolCallContext, signal?: AbortSignal) => Promise<BeforeToolCallResult | undefined>;
  afterToolCall?: (context: AfterToolCallContext, signal?: AbortSignal) => Promise<AfterToolCallResult | undefined>;
}
```

## 关键枚举类型

### ToolExecutionMode

```typescript
type ToolExecutionMode = "sequential" | "parallel";
```

| 模式 | 说明 |
|-----|------|
| `sequential` | 顺序执行，每个工具调用完成后再执行下一个 |
| `parallel` | 并发执行，工具按完成顺序触发事件，但结果消息按助手顺序 |

### QueueMode

```typescript
type QueueMode = "all" | "one-at-a-time";
```

| 模式 | 说明 |
|-----|------|
| `all` | 一次性注入所有队列消息 |
| `one-at-a-time` | 每次只注入最旧的一条消息 |

### ThinkingLevel

```typescript
type ThinkingLevel = "off" | "minimal" | "low" | "medium" | "high" | "xhigh";
```

注意: `xhigh` 仅部分模型家族支持。

## 工具结果类型

### AgentToolResult

```typescript
interface AgentToolResult<T> {
  content: (TextContent | ImageContent)[];  // 返回给模型的内容
  details: T;                             // 结构化详情（日志/UI）
  terminate?: boolean;                      // 是否终止 Agent
}
```

### BeforeToolCallResult

```typescript
interface BeforeToolCallResult {
  block?: boolean;   // 是否阻止执行
  reason?: string;   // 阻止原因
}
```

### AfterToolCallResult

```typescript
interface AfterToolCallResult {
  content?: (TextContent | ImageContent)[];
  details?: unknown;
  isError?: boolean;
  terminate?: boolean;
}
```

## 类型设计原则

1. **可扩展性**: 通过 `CustomAgentMessages` 扩展消息类型
2. **类型安全**: 使用 TypeBox 进行参数验证
3. **信号传递**: 所有异步操作接收 `AbortSignal`
4. **不可变性**: 状态更新返回新对象

## 下一步

→ [03 - Agent 类](./03-agent-class)
