# L03: Agent Loop 底层机制

---

## 1. 心智模型构建

### 1.1 背景

#### 为什么需要底层 agentLoop？

```
问题演进:
├─ 早期: 直接调用 LLM API，单次请求
├─ 中期: 需要处理工具调用，手动循环
│   ├─ 问题1: 工具调用后如何继续？
│   ├─ 问题2: 多个工具如何执行？
│   ├─ 问题3: 如何处理错误？
│   └─ 问题4: 如何注入外部消息？
├─ 现在: agentLoop 提供完整循环机制
│   ├─ 双层循环 (inner/outer)
│   ├─ steering/follow-up 队列
│   ├─ 工具并行/顺序执行
│   └─ 事件流生成
```

#### Agent 类与 agentLoop 的关系

```
Agent 类 = agentLoop + 状态管理 + 队列管理 + subscribe

Agent.prompt():
├─ 创建上下文快照
├─ 创建 LoopConfig
├─ 调用 runAgentLoop()
├─ 处理事件 (processEvents)
└─ 等待完成 (waitForIdle)
```

**设计意图**: agentLoop 是纯粹的事件生成器，Agent 类是状态化包装器。

---

### 1.2 目标

#### 核心痛点

| 痛点 | 手动实现 | agentLoop 解决 |
|------|---------|---------------|
| 工具调用循环 | 手动判断 toolCalls，再调用 | 双层循环自动处理 |
| 并发工具执行 | 手动 Promise.all + 顺序管理 | executeToolCallsParallel |
| 上下文转换 | 手动 filter + transform | transformContext + convertToLlm |
| 中途注入消息 | 无标准机制 | steering/follow-up 队列 |
| 事件追踪 | 无事件体系 | AgentEvent 流 |

---

### 1.3 专家视角 - 概念网络

```
agentLoop 概念网络:

输入:
├─ prompts: AgentMessage[] ← 初始消息
├─ context: AgentContext ← 系统提示 + 历史 + 工具
├─ config: AgentLoopConfig ← 完整配置
└─ signal?: AbortSignal ← 中止信号

输出:
├─ EventStream<AgentEvent, AgentMessage[]>
│   ├─ 事件流: agent_start → ... → agent_end
│   └─ 最终值: AgentMessage[] (新增消息)

核心流程:
├─ runLoop() ← 主循环
│   ├─ 外层循环: follow-up 消息
│   └─ 内层循环: 工具调用 + steering
│
├─ streamAssistantResponse() ← LLM 调用边界
│   ├─ transformContext
│   ├─ convertToLlm
│   └─ streamSimple
│
└─ executeToolCalls() ← 工具执行
    ├─ prepareToolCall
    ├─ executePreparedToolCall
    └─ finalizeExecutedToolCall
```

---

## 2. 结构化学习 (SQ3R)

### 2.1 Survey - 循环流程概览

```
agentLoop 执行流程:

┌─────────────────────────────────────────────────────────┐
│                    OUTER LOOP                             │
│  (follow-up messages)                                     │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐│
│  │                  INNER LOOP                          ││
│  │  (tool calls + steering)                             ││
│  │                                                       ││
│  │  1. emit turn_start                                   ││
│  │  2. inject pending (steering) messages               ││
│  │  3. streamAssistantResponse() → assistantMessage     ││
│  │  4. [error/aborted?] → agent_end                     ││
│  │  5. [toolCalls?] → executeToolCalls()                ││
│  │  6. emit turn_end                                     ││
│  │  7. prepareNextTurn? → 更换 context/model            ││
│  │  8. shouldStopAfterTurn? → agent_end                 ││
│  │  9. getSteeringMessages() → pending                  ││
│  │  [continue or exit inner]                             ││
│  └─────────────────────────────────────────────────────┘│
│                                                           │
│  getFollowUpMessages()                                    │
│  [continue or exit outer]                                 │
└─────────────────────────────────────────────────────────┘

emit agent_end { messages: AgentMessage[] }
```

### 2.2 Question - 关键问题驱动

**Q1**: 为什么需要双层循环 (inner/outer)？
**Q2**: steering 和 follow-up 的注入时机有什么区别？
**Q3**: streamAssistantResponse 中消息转换的完整流程是什么？
**Q4**: shouldStopAfterTurn 和 terminate 的触发时机有什么区别？

### 2.3 Read - 源代码映射

| 内容 | 源文件 | 行数 |
|------|--------|------|
| agentLoop 函数 | `agent-loop.ts` | L31-54 |
| agentLoopContinue 函数 | `agent-loop.ts` | L64-93 |
| runAgentLoop 函数 | `agent-loop.ts` | L95-118 |
| runAgentLoopContinue 函数 | `agent-loop.ts` | L120-143 |
| runLoop 主循环 | `agent-loop.ts` | L155-269 |
| streamAssistantResponse | `agent-loop.ts` | L275-368 |
| executeToolCalls | `agent-loop.ts` | L373-388 |
| executeToolCallsSequential | `agent-loop.ts` | L395-449 |
| executeToolCallsParallel | `agent-loop.ts` | L451-516 |
| prepareToolCall | `agent-loop.ts` | L562-626 |
| executePreparedToolCall | `agent-loop.ts` | L628-663 |
| finalizeExecutedToolCall | `agent-loop.ts` | L665-708 |
| shouldTerminateToolBatch | `agent-loop.ts` | L544-546 |

### 2.4 Recite - 使用模板

#### 低级 API 使用模板

```typescript
import { agentLoop } from "@earendil-works/pi-agent-core";

const context: AgentContext = {
  systemPrompt: "You are helpful.",
  messages: [],
  tools: [],
};

const config: AgentLoopConfig = {
  model: getModel("anthropic", "claude-sonnet-4"),
  convertToLlm: (msgs) => msgs.filter(m => 
    ["user", "assistant", "toolResult"].includes(m.role)
  ),
  toolExecution: "parallel",
};

const userMessage = { role: "user", content: "Hello", timestamp: Date.now() };

for await (const event of agentLoop([userMessage], context, config)) {
  console.log(event.type);
}
```

#### 继续模式模板

```typescript
import { agentLoopContinue } from "@earendil-works/pi-agent-core";

// 从现有上下文继续
for await (const event of agentLoopContinue(context, config)) {
  console.log(event.type);
}

// 注意: 最后消息必须是 user 或 toolResult
```

### 2.5 Review - TODO清单 (渐进式披露)

> 📋 **渐进式学习**: 一次只显示一个TODO，完成后才解锁下一个。

#### 🔴 TODO-1: 掌握双层循环 (当前激活)

**完成检查**:
- [ ] 画出外层循环和内层循环的职责
- [ ] 解释 steering 和 follow-up 的注入时机区别

<details>
<summary>💡 提示</summary>

内层循环: 处理工具调用和 steering 消息
外层循环: 处理 follow-up 消息

steering: 回合开始时注入（内层）
followUp: 回合结束后注入（外层）
</details>

---

#### 🟡 TODO-2: 掌握 LLM 调用边界 (待解锁)

**前置要求**: 完成 TODO-1

**完成检查**:
- [ ] 列举 streamAssistantResponse 的消息转换三步
- [ ] 解释 getApiKey 的作用 (OAuth token 刷新)

---

#### 🟡 TODO-3: 掌握工具执行模式 (待解锁)

**前置要求**: 完成 TODO-2

**完成检查**:
- [ ] 列举并行执行的三阶段 (预检、执行、结果)
- [ ] 解释 terminate 的触发条件

---

## 📝 费曼检验 (必须完成)

在继续下一课之前，请用自己的话解释：

### 问题 1: 双层循环
> "为什么需要双层循环（inner/outer）？如果只有一层循环会怎样？"

你的解释：_______________________________________________

### 问题 2: 工具执行
> "并行执行的三阶段是什么？为什么要先预检再执行？"

你的解释：_______________________________________________

### 问题 3: 终止机制
> "terminate 什么情况下会生效？为什么是批级别的？"

你的解释：_______________________________________________

<details>
<summary>✅ 检查你的理解</summary>

**问题 1 参考答案**:
- 内层处理当前任务（工具+steering）
- 外层处理后续任务（follow-up）
- 分离职责，防止无限递归

**问题 2 参考答案**:
- 三阶段: prepare（预检）→ execute（执行）→ finalize（后处理）
- 预检确保参数有效，钩子检查通过

**问题 3 参考答案**:
- 所有工具都返回 terminate: true 时才生效
- 防止单个工具意外终止整个流程
</details>

---

## 3. 对抗性测试

### 3.1 边界问题

#### agentLoopContinue 的前提条件

```typescript
// ❌ 错误: 最后消息是 assistant
context.messages = [
  { role: "user", content: "Hi" },
  { role: "assistant", content: "Hello" },
];
agentLoopContinue(context, config);  // 抛异常

// ✅ 正确: 最后消息是 user 或 toolResult
context.messages.push({ role: "toolResult", ... });
agentLoopContinue(context, config);
```

#### 契约函数不能抛异常

```typescript
// ❌ 错误
transformContext: async (msgs) => {
  if (invalid) throw new Error();
}

// ✅ 正确
transformContext: async (msgs) => {
  if (invalid) return msgs;  // 回退
}
```

### 3.2 反事实推理

**情境 1**: 如果没有 getSteeringMessages？
```typescript
config.getSteeringMessages = undefined;
// 结果：runLoop 使用默认 () => []
// 教训：无 steering 功能，不能中途注入
```

**情境 2**: 如果所有工具都返回 terminate？
```typescript
// 工具1: { ..., terminate: true }
// 工具2: { ..., terminate: true }
// 结果：shouldTerminateToolBatch 返回 true，跳过后续 LLM 调用
// 教训：terminate 是批级别的，所有工具同意才生效
```

**情境 3**: 如果 shouldStopAfterTurn 返回 true？
```typescript
shouldStopAfterTurn: () => true;
// 结果：在 turn_end 后直接 emit agent_end
// 教训：跳过 steering/follow-up 检查
```

### 3.3 漏洞注入 - 常见错误

| 错误类型 | 示例 | 后果 |
|---------|------|------|
| continueFrom assistant | 最后消息是助手 | 抛异常 |
| 契约函数抛异常 | `throw new Error()` | 中断循环 |
| 忽略 signal | 不检查中止信号 | 无法取消 |
| 遗漏 getSteeringMessages | steering 消息丢失 | 无法中途干预 |

---

## 4. 思想与迁移

### 4.1 设计哲学

#### 双层循环设计

```
Inner Loop: 处理当前任务
├─ 工具调用执行
├─ steering 消息注入
└─ 直到无工具调用、无 steering

Outer Loop: 处理后续任务
├─ follow-up 消息注入
├─ 触发新的 inner loop
└─ 直到无 follow-up
```

**思想**: 分离当前任务和后续任务的调度。

#### 观察性流

```typescript
for await (const event of agentLoop(...)) {
  handleEvent(event);  // 不等待
}
```

**思想**: 生成器模式，消费者自行决定如何处理。

#### 契约式编程

```typescript
convertToLlm: (messages) => Message[]
// 契约: 不能抛异常，必须返回有效值
```

**思想**: 信任调用者，不做防御性检查。

### 4.2 可迁移思维

| 思想 | agentLoop 应用 | 可迁移领域 |
|------|---------------|-----------|
| **双层循环** | inner(当前) + outer(后续) | 任务调度、消息处理 |
| **观察性流** | AsyncGenerator | 流处理、事件系统 |
| **契约式编程** | 契约函数不抛异常 | API设计、服务边界 |
| **Hook 系统** | beforeToolCall/afterToolCall | 中间件、拦截器 |
| **队列注入** | steering/follow-up | 消息队列、任务队列 |

---

## 源文件映射

| 内容 | 源文件 | 行数 |
|------|--------|------|
| agent-loop.ts | `src/agent-loop.ts` | ~740 |

---

## 下一步

→ [L04: Agent 类 (包装层)](./04-agent-loop)