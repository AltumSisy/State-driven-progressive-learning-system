# @pi/agent Package Reference

## 概述

`@pi/agent` 是一个**通用的 Agent 运行时框架**，提供 Agent 的核心抽象和基础设施，但不包含任何特定领域的实现（如文件操作、代码编辑等）。

- **定位**: Agent 运行时 / 核心框架
- **依赖**: `@earendil-works/pi-ai` (多提供商 LLM API)
- **被依赖**: `coding-agent` (在此之上构建)

---

## 核心架构

```
┌─────────────────────────────────────────┐
│           Agent 运行时架构               │
├─────────────────────────────────────────┤
│  Agent 类 (agent.ts)                    │
│  ├─ messages[]      # 消息历史          │
│  ├─ tools Map       # 工具注册表         │
│  ├─ state           # 共享状态          │
│  ├─ prompt()        # 发送用户消息       │
│  ├─ continue()      # 继续执行循环       │
│  └─ subscribe()     # 事件订阅            │
├─────────────────────────────────────────┤
│  Agent Loop (agent-loop.ts)             │
│  ├─ runAgentLoop()  # 高级API (带屏障)    │
│  ├─ runAgentLoopContinue()               │
│  └─ runAgentLoopGen() # 低级API (生成器)  │
├─────────────────────────────────────────┤
│  消息系统                                │
│  ├─ AgentMessage (应用层)               │
│  ├─ Message (LLM层)                     │
│  └─ convertToLlm()  # 转换函数          │
├─────────────────────────────────────────┤
│  工具系统                                │
│  ├─ AgentTool 接口                       │
│  ├─ 并行/串行执行模式                    │
│  └─ before/after 钩子                    │
├─────────────────────────────────────────┤
│  事件系统 (EventEmitter)                 │
│  └─ agent_start/end, turn_start/end      │
│     message_start/update/end             │
│     tool_execution_start/update/end      │
├─────────────────────────────────────────┤
│  Harness (测试/会话支持)                  │
│  ├─ Session 管理 (JSONL/Memory)          │
│  ├─ Compaction (上下文压缩)               │
│  └─ Skills (技能加载)                    │
├─────────────────────────────────────────┤
│  @earendil-works/pi-ai                   │
│  └─ LLM API 调用 (多提供商)               │
└─────────────────────────────────────────┘
```

---

## 核心类与接口

### Agent 类

主要入口类，协调整个代理运行循环。

```typescript
class Agent {
  messages: AgentMessage[];      // 消息历史
  tools: Map<string, AgentTool>; // 工具注册表
  state: Record<string, any>;   // 共享状态（工具间共享）
  signal: AbortSignal;          // 取消信号

  // 发送用户消息，启动执行循环
  async prompt(message: string, attachments?: Attachment[]): Promise<void>;

  // 继续执行（用于流式恢复）
  async continue(message?: AgentMessage): Promise<void>;

  // 订阅事件
  subscribe(listener: AgentListener): void;

  // 工具管理
  addTool(tool: AgentTool): void;
  removeTool(name: string): void;

  // 屏障同步（高级API使用）
  waitForBarrier(): Promise<void>;
  signalBarrierComplete(): void;
}
```

### AgentMessage (应用层消息)

```typescript
type AgentMessage =
  | { role: "user"; content: string; attachments?: Attachment[]; }
  | { role: "assistant"; content: string; }
  | { role: "toolResult"; content: string; toolCallId: string; };

// 支持通过 declaration merging 扩展
declare module "@earendil-works/pi-agent-core" {
  export interface CustomAgentMessageTypes {
    custom: { role: "custom"; data: any; };
  }
}
```

### Message (LLM层消息)

```typescript
// 来自 @earendil-works/pi-ai
type Message =
  | { role: "user"; content: string; }
  | { role: "assistant"; content: string; }
  | { role: "toolResult"; content: string; toolCallId: string; };
```

### AgentTool 接口

```typescript
interface AgentTool<T = any> {
  name: string;
  description: string;
  parameters: Schema;                    // JSON Schema
  executionMode?: "parallel" | "sequential"; // 默认并行
  execute: (
    toolCallId: string,
    params: T,
    signal: AbortSignal,
    onUpdate: (partial: string) => void
  ) => Promise<ToolResult>;
}

interface ToolResult {
  result: string;           // 工具执行结果
  isError?: boolean;        // 是否出错
  terminate?: boolean;      // 是否终止循环
  attachments?: Attachment[]; // 附件（如图片）
}
```

### Agent 事件

```typescript
type AgentEvent =
  | { type: "agent_start"; }
  | { type: "agent_end"; }
  | { type: "turn_start"; }
  | { type: "turn_end"; }
  | { type: "message_start"; message: AgentMessage; }
  | { type: "message_update"; content: string; }  // 流式更新
  | { type: "message_end"; message: AgentMessage; }
  | { type: "tool_execution_start"; toolCallId: string; toolName: string; params: any; }
  | { type: "tool_execution_update"; toolCallId: string; partial: string; }
  | { type: "tool_execution_end"; toolCallId: string; result: ToolResult; };

type AgentListener = (event: AgentEvent, signal: AbortSignal) => Promise<void> | void;
```

---

## Agent 执行循环

### 高级 API（带屏障同步）

```typescript
// agent-loop.ts
export async function runAgentLoop(
  agent: Agent,
  userMessage: string,
  options?: AgentLoopOptions
): Promise<void>;

export async function runAgentLoopContinue(
  agent: Agent,
  options?: AgentLoopOptions
): Promise<void>;
```

特点：
- 使用 `waitForBarrier()` / `signalBarrierComplete()` 进行同步
- 适合简单场景，阻塞式等待完成

### 低级 API（生成器模式）

```typescript
export function* runAgentLoopGen(
  agent: Agent,
  userMessage: string,
  options?: AgentLoopOptions
): Generator<AgentLoopStep, void, unknown>;

type AgentLoopStep =
  | { type: "llm_call"; messages: Message[]; }
  | { type: "tool_calls"; toolCalls: ToolCall[]; }
  | { type: "tool_result"; toolCallId: string; result: ToolResult; }
  | { type: "message_complete"; message: AgentMessage; };
```

特点：
- 完全可观察的执行过程
- 每一步都可拦截/处理
- 无屏障同步，更灵活

### 执行流程

```
prompt(userMessage)
    │
    ▼
┌─────────────────┐
│   添加到消息历史  │
└─────────────────┘
    │
    ▼
┌─────────────────┐
│   transformContext  │  ← 应用自定义转换
│   (AgentMessage[])  │
└─────────────────┘
    │
    ▼
┌─────────────────┐
│   convertToLlm   │  ← 转换为LLM消息格式
│   (Message[])    │
└─────────────────┘
    │
    ▼
┌─────────────────┐
│   LLM 调用       │  ← 调用 @pi/ai
│   (流式响应)      │
└─────────────────┘
    │
    ▼
┌─────────────────┐
│  解析assistant消息 │
│  - 普通消息 → 结束 │
│  - 工具调用 → 继续 │
└─────────────────┘
    │
    ▼ (有工具调用)
┌─────────────────┐
│  beforeToolCall │  ← 钩子（可阻止执行）
└─────────────────┘
    │
    ▼
┌─────────────────┐
│  执行工具         │  ← 并行或串行
│  - 调用 execute  │
│  - 流式结果更新    │
└─────────────────┘
    │
    ▼
┌─────────────────┐
│  afterToolCall  │  ← 钩子（后处理）
└─────────────────┘
    │
    ▼
┌─────────────────┐
│  工具结果 → 消息  │
└─────────────────┘
    │
    ▼
   (循环回到 LLM 调用)
```

---

## 消息转换系统

### 转换流程

```typescript
// 1. AgentMessage (应用层，可扩展)
interface MyCustomMessage {
  role: "thinking";
  content: string;
  reasoning: string;
}

// 2. transformContext - 应用自定义转换
// 默认实现：identity 函数
// 可覆盖：过滤消息、修改内容、添加元数据等

const messages: AgentMessage[] = agent.transformContext(agent.messages);

// 3. convertToLlm - 转换为标准 LLM 消息
const llmMessages: Message[] = convertToLlm(messages);
// 过滤掉不支持的消息类型
// 只保留 user/assistant/toolResult
```

### 自定义消息类型扩展

```typescript
// types.ts
import "@earendil-works/pi-agent-core";

declare module "@earendil-works/pi-agent-core" {
  export interface CustomAgentMessageTypes {
    thinking: {
      role: "thinking";
      content: string;
      reasoning: string;
    };
  }
}

// 现在 AgentMessage 会自动包含 thinking 类型
```

---

## 工具系统详解

### 工具注册

```typescript
const myTool: AgentTool = {
  name: "my_tool",
  description: "工具描述",
  parameters: {
    type: "object",
    properties: {
      param1: { type: "string" },
      param2: { type: "number" }
    },
    required: ["param1"]
  },
  executionMode: "parallel", // 或 "sequential"
  execute: async (toolCallId, params, signal, onUpdate) => {
    // 流式更新
    onUpdate("处理中...");
    
    // 执行操作
    const result = await doSomething(params);
    
    // 返回结果
    return {
      result: JSON.stringify(result),
      isError: false,
      terminate: false
    };
  }
};

agent.addTool(myTool);
```

### 执行模式

```