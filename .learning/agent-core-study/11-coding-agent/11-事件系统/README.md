# 事件系统

## 学习目标

理解 Coding Agent 的事件总线机制和消息类型体系。

## 核心源文件

- `event-bus.ts` - 事件总线
- `messages.ts` - 消息类型定义

## 关键概念

### 1. EventBus 核心（event-bus.ts）

**设计目的**:
- 提供轻量级事件发布/订阅机制
- 支持事件分发和控制
- 解耦组件间通信

**核心接口**:
```typescript
interface EventBus<TEvent> {
  subscribe(listener: (event: TEvent) => void): () => void;
  emit(event: TEvent): void;
  clear(): void;
}
```

**EventBusController**:
```typescript
interface EventBusController<TEvent> {
  pause(): void;       // 暂停事件分发
  resume(): void;      // 恢复事件分发
  clear(): void;       // 清空所有监听器
}
```

**创建函数**:
```typescript
createEventBus<TEvent>(): EventBus<TEvent> & EventBusController<TEvent>
```

### 2. 事件订阅机制

**subscribe 方法**:
```typescript
subscribe(listener: (event: TEvent) => void): () => void
```

**特点**:
- 返回 unsubscribe 函数
- 支持多个监听器
- 按注册顺序调用
- 异步监听器支持

**用法**:
```typescript
const unsubscribe = eventBus.subscribe((event) => {
  // 处理事件
});

// 取消订阅
unsubscribe();
```

### 3. 事件发射机制

**emit 方法**:
```typescript
emit(event: TEvent): void
```

**执行流程**:
1. 检查是否暂停
2. 遍历所有监听器
3. 调用监听器处理事件
4. 处理异常（不中断其他监听器）

### 4. 事件控制机制

**pause/resume**:
```typescript
pause(): void    // 暂停事件分发
resume(): void   // 恢复事件分发
```

**应用场景**:
- 暂时阻止事件处理
- 批量操作时暂停
- 恢复后批量处理

**clear**:
```typescript
clear(): void    // 清空所有监听器
```

**应用场景**:
- 组件销毁时清理
- 重置事件系统
- 防止内存泄漏

### 5. 消息类型（messages.ts）

**核心消息类型**:

#### AgentMessage
基础 Agent 消息类型：
```typescript
type AgentMessage = UserMessage | AssistantMessage | ToolResultMessage;
```

#### UserMessage
用户消息：
```typescript
interface UserMessage {
  role: 'user';
  content: string | (TextContent | ImageContent)[];
  timestamp: number;
}
```

#### AssistantMessage
助手消息：
```typescript
interface AssistantMessage {
  role: 'assistant';
  content: ContentBlock[];
  stopReason: 'end' | 'stop' | 'tool_use' | 'error' | 'aborted';
  errorMessage?: string;
  usage?: UsageInfo;
  thinking?: ThinkingContent;
  timestamp: number;
  provider?: string;
  model?: string;
}
```

#### ToolResultMessage
工具结果消息：
```typescript
interface ToolResultMessage {
  role: 'toolResult';
  toolCallId: string;
  content: string;
  details?: unknown;
  isError: boolean;
  timestamp: number;
}
```

#### CustomMessage
自定义消息：
```typescript
interface CustomMessage<T = unknown> {
  role: 'custom';
  customType: string;        // 自定义类型标识
  content: T;                // 自定义内容
  display?: string;          // 显示内容
  details?: unknown;         // 详细信息
  timestamp: number;
}
```

#### BashExecutionMessage
Bash 执行消息：
```typescript
interface BashExecutionMessage {
  role: 'bashExecution';
  command: string;
  output: string;
  exitCode?: number;
  timestamp: number;
}
```

#### CompactionSummaryMessage
压缩摘要消息：
```typescript
interface CompactionSummaryMessage {
  role: 'compactionSummary';
  summary: string;
  reason: 'manual' | 'threshold' | 'overflow';
  tokensBefore: number;
  timestamp: number;
}
```

#### BranchSummaryMessage
分支摘要消息：
```typescript
interface BranchSummaryMessage {
  role: 'branchSummary';
  summary: string;
  parentBranchId: string;
  timestamp: number;
}
```

### 6. Content Block 类型

**TextContent**:
```typescript
interface TextContent {
  type: 'text';
  text: string;
}
```

**ImageContent**:
```typescript
interface ImageContent {
  type: 'image';
  source: {
    type: 'base64';
    media_type: string;  // MIME 类型
    data: string;        // Base64 数据
  };
}
```

**ToolUseContent**:
```typescript
interface ToolUseContent {
  type: 'tool_use';
  id: string;
  name: string;
  input: Record<string, unknown>;
}
```

**ThinkingContent**:
```typescript
interface ThinkingContent {
  type: 'thinking';
  thinking: string;
}
```

### 7. Usage Info

**UsageInfo 接口**:
```typescript
interface UsageInfo {
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens?: number;
  cache_write_tokens?: number;
}
```

**用途**:
- Token 使用统计
- 成本计算
- 上下文管理

### 8. 事件类型体系

**AgentEvent**（来自 pi-agent-core）:
```typescript
type AgentEvent =
  | { type: 'agent_start' }
  | { type: 'agent_end'; messages: AgentMessage[] }
  | { type: 'turn_start' }
  | { type: 'turn_end'; message: AgentMessage; toolResults?: ToolResultMessage[] }
  | { type: 'message_start'; message: AgentMessage }
  | { type: 'message_update'; message: AgentMessage; assistantMessageEvent?: any }
  | { type: 'message_end'; message: AgentMessage }
  | { type: 'tool_execution_start'; toolCallId: string; toolName: string; args: any }
  | { type: 'tool_execution_update'; toolCallId: string; toolName: string; args: any; partialResult: any }
  | { type: 'tool_execution_end'; toolCallId: string; toolName: string; result: any; isError: boolean }
```

**AgentSessionEvent**（扩展 AgentEvent）:
```typescript
type AgentSessionEvent =
  | AgentEvent
  | { type: 'queue_update'; steering: string[]; followUp: string[] }
  | { type: 'compaction_start'; reason: 'manual' | 'threshold' | 'overflow' }
  | { type: 'compaction_end'; ... }
  | { type: 'auto_retry_start'; ... }
  | { type: 'auto_retry_end'; ... }
  | { type: 'session_info_changed'; name: string }
  | { type: 'thinking_level_changed'; level: ThinkingLevel }
```

### 9. ExtensionEvent（来自 extensions/types.ts）

**ExtensionEvent 类型**:
```typescript
type ExtensionEvent =
  | AgentStartEvent
  | AgentEndEvent
  | TurnStartEvent
  | TurnEndEvent
  | MessageStartEvent
  | MessageEndEvent
  | ToolCallEvent
  | ToolResultEvent
  | SessionStartEvent
  | SessionShutdownEvent
  | SessionCompactEvent
  | SessionBeforeCompactEvent
  | InputEvent
  | ModelSelectEvent
  | ThinkingLevelSelectEvent
  | ...
```

## 重点阅读

### event-bus.ts

理解事件总线：
1. **createEventBus** - 创建函数
2. **subscribe** - 订阅机制
3. **emit** - 发射机制
4. **pause/resume** - 控制机制
5. **clear** - 清理机制

### messages.ts

理解消息类型：
1. **AgentMessage** - 基础消息类型
2. **UserMessage** - 用户消息
3. **AssistantMessage** - 助手消息
4. **ToolResultMessage** - 工具结果
5. **CustomMessage** - 自定义消息
6. **Content Block** - 内容块类型
7. **UsageInfo** - 使用信息

## 关键设计模式

### 发布/订阅模式
EventBus 实现发布订阅：
- 解耦事件源和监听器
- 支持多监听器
- 灵活订阅管理

### 控制模式
事件分发控制：
- pause/resume 暂停恢复
- 批量操作优化
- 状态管理

### 类型安全模式
TypeScript 类型定义：
- 严格的类型约束
- 类型推断
- 类型检查

### 消息层次模式
多层次消息类型：
- AgentMessage 基础层
- CustomMessage 扩展层
- 特殊消息专用层

## 学习建议

### 阅读顺序

1. **event-bus.ts** - 理解事件总线机制
2. **messages.ts** - 理解消息类型定义

### 重点理解

1. **订阅机制** - subscribe 返回 unsubscribe
2. **发射机制** - emit 如何分发事件
3. **控制机制** - pause/resume 的作用
4. **消息类型** - 各种消息结构
5. **Content Block** - 内容块类型
6. **事件层次** - AgentEvent vs AgentSessionEvent vs ExtensionEvent

## 在 AgentSession 中的应用

### 内部事件总线
```typescript
class AgentSession {
  private _eventListeners: AgentSessionEventListener[] = [];
  
  subscribe(listener: AgentSessionEventListener): () => void {
    this._eventListeners.push(listener);
    return () => {
      const index = this._eventListeners.indexOf(listener);
      if (index !== -1) {
        this._eventListeners.splice(index, 1);
      }
    };
  }
  
  private _emit(event: AgentSessionEvent): void {
    for (const l of this._eventListeners) {
      l(event);
    }
  }
}
```

### Agent 事件转发
```typescript
this._unsubscribeAgent = this.agent.subscribe(this._handleAgentEvent);

private _handleAgentEvent = async (event: AgentEvent): Promise<void> => {
  // 处理 Agent 事件
  // 发送给扩展
  await this._emitExtensionEvent(event);
  
  // 发送给用户监听器
  this._emit(event);
};
```

### 扩展事件系统
ExtensionRunner 有自己的事件系统：
```typescript
class ExtensionRunner {
  emit(event: ExtensionEvent): Promise<any> {
    // 分发给扩展
  }
}
```

### 消息创建和发送
```typescript
// 创建用户消息
const userMessage: UserMessage = {
  role: 'user',
  content: [{ type: 'text', text: 'Hello' }],
  timestamp: Date.now()
};

// 发送消息
await agent.prompt(userMessage);
```

### 自定义消息发送
```typescript
await session.sendCustomMessage({
  customType: 'notification',
  content: { message: 'Build completed' },
  display: 'Build completed successfully'
});
```

## 实际应用场景

### 1. UI 事件监听
UI 监听会话事件：
```typescript
session.subscribe((event) => {
  if (event.type === 'message_start') {
    // 显示消息开始
  } else if (event.type === 'message_end') {
    // 显示消息结束
  }
});
```

### 2. 工具执行跟踪
跟踪工具执行：
```typescript
session.subscribe((event) => {
  if (event.type === 'tool_execution_start') {
    console.log(`Tool ${event.toolName} started`);
  } else if (event.type === 'tool_execution_end') {
    console.log(`Tool ${event.toolName} ended`);
  }
});
```

### 3. 压缩状态监听
监听压缩状态：
```typescript
session.subscribe((event) => {
  if (event.type === 'compaction_start') {
    // 显示压缩进度
  } else if (event.type === 'compaction_end') {
    // 显示压缩结果
  }
});
```

### 4. 错误处理监听
监听错误：
```typescript
session.subscribe((event) => {
  if (event.type === 'agent_end') {
    const lastMsg = event.messages[event.messages.length - 1];
    if (lastMsg.role === 'assistant' && lastMsg.stopReason === 'error') {
      // 处理错误
    }
  }
});
```

### 5. 队列状态监听
监听消息队列：
```typescript
session.subscribe((event) => {
  if (event.type === 'queue_update') {
    console.log(`Steering: ${event.steering.length}`);
    console.log(`FollowUp: ${event.followUp.length}`);
  }
});
```

## 扩展思考

### 性能考虑
- 多监听器的性能影响
- 异步监听器的顺序
- 事件分发优化

### 错误处理
- 监听器错误不中断其他监听器
- 错误日志和追踪
- 错误恢复机制

### 内存管理
- 监听器清理防止内存泄漏
- unsubscribe 必须调用
- 组件销毁时的清理

### 事件顺序
- 监听器调用顺序
- 异步监听器顺序
- 事件优先级

### 扩展事件
- 如何添加新事件类型
- 如何扩展事件系统
- 如何保持向后兼容