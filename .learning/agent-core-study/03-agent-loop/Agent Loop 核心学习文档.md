# Agent Loop 核心学习文档

> 基于 `pi/packages/agent/src/agent-loop.ts` 源码分析

---

## 一、核心功能架构

```
┌─────────────────────────────────────────────────────────────┐
│                    AGENT LOOP 架构图                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   入口层                                                      │
│   ├─ agentLoop()           → 新会话启动（添加prompts）         │
│   └─ agentLoopContinue()   → 继续会话（不添加新消息）          │
│                                                             │
│   ↓                                                         │
│   调度层: runAgentLoop / runAgentLoopContinue                │
│                                                             │
│   ↓                                                         │
│   核心层: runLoop()  【双层循环架构】                          │
│   ┌─────────────────────────────────────────────────────┐    │
│   │  外层循环: 处理 follow-up 消息（用户在等待时输入）    │    │
│   │  ────────────────────────────────────────────────   │    │
│   │  内层循环: 处理 tool calls + steering messages      │    │
│   │                                                      │    │
│   │   ┌─ streamAssistantResponse()  ← LLM交互边界        │    │
│   │   │    (AgentMessage[] → Message[] 转换)            │    │
│   │   │                                                 │    │
│   │   └─ executeToolCalls()                             │    │
│   │        ├─ executeToolCallsSequential()               │    │
│   │        └─ executeToolCallsParallel()                │    │
│   │             ├─ prepareToolCall()      准备阶段        │    │
│   │             ├─ executePreparedToolCall() 执行阶段      │    │
│   │             └─ finalizeExecutedToolCall() 收尾阶段     │    │
│   └─────────────────────────────────────────────────────┘    │
│                                                             │
│   事件流: EventStream<AgentEvent>                           │
│   ├─ agent_start/agent_end                                 │
│   ├─ turn_start/turn_end                                    │
│   ├─ message_start/message_update/message_end               │
│   └─ tool_execution_start/update/end                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 四大核心机制

| 机制 | 职责 | 关键代码位置 |
|------|------|-------------|
| **双层循环** | 外层处理会话延续，内层处理单轮交互 | `runLoop()` L155-269 |
| **流式转换** | 实时更新消息状态，支持打字机效果 | `streamAssistantResponse()` L275-368 |
| **边界转换** | AgentMessage ↔ Message 只在LLM调用处转换 | L293-295 |
| **工具执行策略** | 支持并行/串行两种执行模式 | `executeToolCalls()` L373-388 |

---

## 二、问题抽象与解决原则

### 问题 1：消息格式的双重身份

| 维度 | 内容 |
|------|------|
| **现象** | Agent内部使用`AgentMessage`，但LLM需要`Message[]` |
| **抽象** | **领域模型与外部协议的边界转换问题** |
| **解决** | 在`streamAssistantResponse`中统一转换，保持内部一致性 |

### 问题 2：用户输入的时机不确定性

| 维度 | 内容 |
|------|------|
| **现象** | 用户可能在Agent处理工具时输入新消息（steering） |
| **抽象** | **异步输入与同步处理流的竞态条件** |
| **解决** | `getSteeringMessages()`钩子，在工具执行后检查新消息 |

### 问题 3：工具执行的并发控制

| 维度 | 内容 |
|------|------|
| **现象** | 有些工具必须顺序执行（如文件读写），有些可以并行 |
| **抽象** | **执行策略的可配置性需求** |
| **解决** | 工具级别`executionMode` + 全局`toolExecution`配置 |

### 问题 4：流式响应的状态管理

| 维度 | 内容 |
|------|------|
| **现象** | 流式过程中需要更新部分消息内容 |
| **抽象** | **不可变状态与增量更新的平衡** |
| **解决** | `partialMessage`引用更新 + `message_update`事件 |

### 问题 5：工具生命周期的可观测性

| 维度 | 内容 |
|------|------|
| **现象** | 需要追踪工具执行的全过程用于调试和UI |
| **抽象** | **执行过程的可观测性需求** |
| **解决** | 完整的事件系统（start/update/end） |

---

## 三、核心设计原则

| 原则 | 说明 | 代码体现 |
|------|------|---------|
| **单一转换边界** | 内部统一格式，只在边界处转换 | L1注释: "Transforms to Message[] only at the LLM call boundary" |
| **事件驱动架构** | 所有状态变化通过事件通知 | `AgentEventSink`回调 + `EventStream` |
| **可配置策略** | 执行模式、钩子函数均可注入 | `AgentLoopConfig`配置对象 |
| **防御式编程** | 每个关键节点检查abort信号 | 多处`signal?.aborted`检查 |
| **三阶段工具执行** | 准备→执行→收尾，支持拦截 | `prepare/execute/finalize` |
| **引用更新模式** | 流式过程中直接更新引用 | `context.messages[context.messages.length - 1] = partialMessage` |

---

## 四、面试/分享核心要点

### 一句话定位

> **这是一个支持流式响应、双向循环、策略化工具执行的Agent运行时核心。**

### 三句话讲架构

1. **双层循环**：外层处理会话生命周期（支持用户插队输入），内层处理单轮对话（LLM↔Tool交互）
2. **边界转换**：内部使用AgentMessage，只在调用LLM时转换为Message，保持领域模型一致性
3. **策略执行**：工具支持串行/并行两种模式，通过三阶段生命周期（prepare/execute/finalize）实现可观测和可拦截

### 技术亮点（Q&A）

#### Q1: 如何处理流式响应的状态管理？

**A**: 使用partialMessage引用，通过`message_update`事件实时同步，最终用`done`事件替换为finalMessage，保证数据一致性。

```typescript
// 关键代码片段
for await (const event of response) {
  switch (event.type) {
    case "text_delta":
    case "toolcall_delta":
      partialMessage = event.partial;
      context.messages[context.messages.length - 1] = partialMessage;
      await emit({ type: "message_update", message: { ...partialMessage } });
      break;
    // ...
  }
}
```

#### Q2: 如何支持用户"插队"输入？

**A**: 通过`getSteeringMessages()`钩子，在每轮工具执行后检查新消息，将新消息加入`pendingMessages`，在内层循环头部处理。

```typescript
// 外层循环中的处理逻辑
let pendingMessages: AgentMessage[] = (await config.getSteeringMessages?.()) || [];

while (hasMoreToolCalls || pendingMessages.length > 0) {
  if (pendingMessages.length > 0) {
    // 处理用户插队消息
    for (const message of pendingMessages) {
      currentContext.messages.push(message);
    }
    pendingMessages = [];
  }
  // ...继续正常流程
}
```

#### Q3: 工具执行如何做到既灵活又可控？

**A**: 三层机制：

1. **全局配置** `sequential/parallel`
2. **工具级别** `executionMode`
3. **before/after钩子** 支持拦截和修改结果

```typescript
// 配置接口
interface AgentLoopConfig {
  toolExecution?: "sequential" | "parallel";
  beforeToolCall?: (context: ToolCallContext, signal?: AbortSignal) => Promise<{ block?: boolean; reason?: string } | void>;
  afterToolCall?: (context: ToolCallContext, signal?: AbortSignal) => Promise<Partial<ToolResult> | void>;
}
```

### 设计价值

| 价值 | 说明 |
|------|------|
| **可测试性** | 事件流可完全mock，不依赖真实LLM |
| **可观测性** | 完整事件生命周期，支持实时UI更新 |
| **可扩展性** | 配置驱动，钩子函数支持自定义行为 |

---

## 五、记忆口诀

```
双层循环管会话，边界转换是关键
流式更新用引用，工具执行分三段
事件驱动全链路，配置钩子够灵活
```

---

## 六、附录：AgentEvent 完整类型

```typescript
export type AgentEvent =
  // Agent生命周期
  | { type: "agent_start" }
  | { type: "agent_end"; messages: AgentMessage[] }
  
  // Turn生命周期 - 一轮 = 助手响应 + 工具调用/结果
  | { type: "turn_start" }
  | { type: "turn_end"; message: AgentMessage; toolResults: ToolResultMessage[] }
  
  // Message生命周期
  | { type: "message_start"; message: AgentMessage }
  | { type: "message_update"; message: AgentMessage; assistantMessageEvent: AssistantMessageEvent }
  | { type: "message_end"; message: AgentMessage }
  
  // Tool执行生命周期
  | { type: "tool_execution_start"; toolCallId: string; toolName: string; args: any }
  | { type: "tool_execution_update"; toolCallId: string; toolName: string; args: any; partialResult: any }
  | { type: "tool_execution_end"; toolCallId: string; toolName: string; result: any; isError: boolean };
```

---

## 七、关键函数速查

| 函数 | 行号 | 职责 |
|------|------|------|
| `agentLoop` | L31-54 | 新会话入口 |
| `agentLoopContinue` | L64-93 | 继续会话入口 |
| `runAgentLoop` | L95-118 | 新会话调度 |
| `runAgentLoopContinue` | L120-143 | 继续会话调度 |
| `runLoop` | L155-269 | **核心主循环** |
| `streamAssistantResponse` | L275-368 | 流式LLM响应 |
| `executeToolCalls` | L373-388 | 工具执行分发 |
| `executeToolCallsSequential` | L395-449 | 串行执行 |
| `executeToolCallsParallel` | L451-516 | 并行执行 |
| `prepareToolCall` | L562-626 | 工具准备阶段 |
| `executePreparedToolCall` | L628-663 | 工具执行阶段 |
| `finalizeExecutedToolCall` | L665-708 | 工具收尾阶段 |
| `shouldTerminateToolBatch` | L544-546 | 终止条件判断 |

---

*文档生成时间: 2026-06-09*  
*源码路径: `pi/packages/agent/src/agent-loop.ts`*
