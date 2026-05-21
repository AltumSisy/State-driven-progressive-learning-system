# 01 - 架构概览

## 包架构图

```
┌─────────────────────────────────────────────────────────┐
│                    Application Layer                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │
│  │   Agent     │  │  agentLoop  │  │ agentLoopContinue│ │
│  │   Class     │  │  (low-level)│  │   (low-level)   │  │
│  └──────┬──────┘  └─────────────┘  └─────────────────┘  │
│         │                                                │
│         ▼                                                │
│  ┌────────────────────────────────────────────────────┐  │
│  │              AgentLoopConfig Options                │  │
│  │  • model, convertToLlm, transformContext           │  │
│  │  • toolExecution, beforeToolCall, afterToolCall     │  │
│  │  • getSteeringMessages, getFollowUpMessages        │  │
│  │  • shouldStopAfterTurn, prepareNextTurn            │  │
│  └────────────────────────────────────────────────────┘  │
│                         │                                │
│                         ▼                                │
│  ┌────────────────────────────────────────────────────┐  │
│  │              AgentEvent Stream                      │  │
│  │  agent_start → turn_start → message_* → turn_end  │  │
│  │                      ↓                              │
│  │         tool_execution_* (if tools called)        │  │
│  └────────────────────────────────────────────────────┘  │
│                         │                                │
└─────────────────────────┼────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│              @earendil-works/pi-ai                       │
│              (LLM Provider Abstraction)                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │
│  │    Model    │  │streamSimple │  │  Message Types  │  │
│  └─────────────┘  └─────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## 核心组件

### 1. Agent 类 (`src/agent.ts`)

高级 API，封装了 agent-loop，提供：
- 状态管理
- 事件订阅
- Steering/Follow-up 队列
- 便捷方法 (prompt, continue, reset)

### 2. agent-loop (`src/agent-loop.ts`)

低级 API，生成事件流，支持：
- 直接使用，无需 Agent 类包装
- 更细粒度的控制
- 观察性事件流（不等待订阅者）

### 3. 类型系统 (`src/types.ts`)

定义核心类型：
- `AgentMessage`: 可扩展的消息类型
- `AgentTool`: 工具定义
- `AgentEvent`: 事件类型
- `AgentState`: 状态接口

### 4. Harness 系统 (`src/harness/`)

高级功能模块：
- **Session**: 会话持久化
- **Compaction**: 上下文压缩
- **Skills**: 技能管理
- **System Prompt**: 系统提示模板

## 两种使用模式

### 模式 A: Agent 类 (推荐)

```typescript
const agent = new Agent({
  initialState: {
    systemPrompt: "You are a helpful assistant.",
    model: getModel("anthropic", "claude-sonnet-4-20250514"),
  },
});

agent.subscribe((event) => {
  // 处理事件
});

await agent.prompt("Hello!");
```

**特点**:
- 自动等待订阅者完成
- `message_end` 作为工具预检前的屏障
- 更适合 UI 应用

### 模式 B: agentLoop (低级)

```typescript
for await (const event of agentLoop([userMessage], context, config)) {
  console.log(event.type);
}
```

**特点**:
- 观察性流（不等待处理）
- 保留事件顺序
- 需要手动处理屏障
- 更轻量

## 执行流程

```
┌─────────────┐
│   prompt()  │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ agent_start │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────┐
│                TURN LOOP                │
│  ┌─────────────┐                        │
│  │ turn_start  │                        │
│  └──────┬──────┘                        │
│         │                               │
│         ▼                               │
│  ┌─────────────────────────────────┐   │
│  │          LLM Request              │   │
│  │  ┌─────────┐  ┌───────────────┐ │   │
│  │  │message_*│  │ message_update │ │   │
│  │  │ events  │  │  (streaming)   │ │   │
│  │  └─────────┘  └───────────────┘ │   │
│  └─────────────────────────────────┘   │
│         │                               │
│         ▼                               │
│  ┌─────────────────────────────────┐   │
│  │       Tool Execution            │   │
│  │  ┌───────────────────────────┐  │   │
│  │  │ tool_execution_* events   │  │   │
│  │  │ (if tools were called)    │  │   │
│  │  └───────────────────────────┘  │   │
│  └─────────────────────────────────┘   │
│         │                               │
│         ▼                               │
│  ┌─────────────┐  ┌─────────────────┐   │
│  │  turn_end   │──┤ check steering  │   │
│  └─────────────┘  │ follow-up queues│   │
│                   └─────────────────┘   │
└─────────────────────────────────────────┘
       │
       ▼
┌─────────────┐
│  agent_end  │
└─────────────┘
```

## 下一步

→ [02 - 核心类型系统](./02-core-types)
