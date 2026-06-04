# L04: Agent 类 (包装层)

> **前置要求**: 已完成 [L03: Agent Loop 底层机制](../03-agent-loop)

---

## 📋 课程入口检查点

在进入本课之前，请确认：
- [ ] 已完成 L03 的所有 TODO
- [ ] 能用自己的话解释 "为什么 agentLoop 需要包装层"
- [ ] 能画出 agentLoop 的双层循环结构

> ⚠️ **不要跳课** - Agent 类建立在 agentLoop 之上，跳过会导致理解断层。

---

## 1. 心智模型建构 (方法1)

### 1.1 背景 - 为什么需要 Agent 类？

#### agentLoop 的局限性

```
纯 agentLoop 的问题:
├─ 无状态管理 → 每次调用需手动管理 messages, tools
├─ 无队列机制 → steering/follow-up 需手动实现
├─ 无监听器等待 → 事件发出后不等待处理完成
├─ 无屏障行为 → 无法在工具预检前等待状态更新
└─ 使用复杂 → 需完整配置每次调用

→ Agent 类包装这些复杂性
```

#### Agent 与 agentLoop 的关系

```
Agent 类 = agentLoop + 状态管理 + 队列管理 + 监听器等待

Agent.prompt():
├─ 创建上下文快照 (AgentContext)
├─ 创建 LoopConfig
├─ 调用 runAgentLoop()
├─ 处理事件 (processEvents)
├─ 更新 MutableAgentState
└─ 等待完成 (waitForIdle)
```

**设计意图**: agentLoop 是纯粹的事件生成器，Agent 类是**状态化包装器**。

---

### 1.2 目标 - 核心痛点对比

| 痛点 | 纯 agentLoop | Agent 类解决 |
|------|-------------|-------------|
| 状态管理 | 手动维护 | MutableAgentState 自动管理 |
| 队列注入 | 无标准机制 | Steering/Follow-up 队列 |
| 监听器等待 | 不等待 | waitForIdle 屏障行为 |
| 使用便捷性 | 复杂配置 | 简化 API |
| 并发安全 | 需手动处理 | activeRun 管理 |

---

### 1.3 专家视角 - 概念网络

```
Agent 概念网络:

状态层:
├─ MutableAgentState
│   ├─ _state: 内部可变状态对象
│   ├─ getter: 返回内部引用
│   ├─ setter: 复制数组 (slice)
│   └─ 直接修改: 不触发复制
│
├─ AgentState (只读视图)
│   ├─ systemPrompt: string
│   ├─ model: Model
│   ├─ tools: AgentTool[]
│   ├─ messages: AgentMessage[]
│   ├─ isStreaming: boolean (只读)
│   ├─ streamingMessage?: AgentMessage (只读)
│   └─ pendingToolCalls: ReadonlySet<string> (只读)

队列层:
├─ PendingMessageQueue
│   ├─ steeringMessages: AgentMessage[] ← 回合中注入
│   └─ followUpMessages: AgentMessage[] ← 回合后注入
│
├─ getSteeringMessages() → 清空 steering 队列
├─ getFollowUpMessages() → 清空 followUp 队列

执行层:
├─ prompt(messages): Promise<void>
│   ├─ 检查并发 (activeRun)
│   ├─ 创建上下文快照
│   ├─ 启动 agentLoop
│   ├─ processEvents 更新状态
│   └─ waitForIdle 等待完成
│
├─ continue(): Promise<void>
│   └─ 从当前状态继续 (需最后消息是 user/toolResult)
│
├─ reset(): void
│   └─ 重置状态到初始值

事件层:
├─ subscribe(listener): () => void
│   ├─ listeners: Set<AgentEventListener>
│   └─ 返回 unsubscribe 函数
│
├─ processEvents(eventStream)
│   ├─ 更新 MutableAgentState
│   ├─ await 每个监听器
│   └─ 错误隔离 (监听器抛异常不影响)

屏障层:
├─ waitForIdle(): Promise<void>
│   ├─ 等待 activeRun 完成
│   └─ 通过 finishRun 触发
│
├─ finishRun()
│   └─ activeRun = undefined
│   └─ resolve waitForIdle
```

#### 核心概念定义

| 概念 | 定义 | 关键特性 |
|------|------|---------|
| MutableAgentState | 可变的 Agent 状态 | getter/setter 复制保护 |
| PendingMessageQueue | 消息注入队列 | steering(回合中) / followUp(回合后) |
| activeRun | 当前运行的 Promise | 防止并发执行 |
| waitForIdle | 空闲等待屏障 | 所有监听器完成后才 resolve |

---

## 2. 结构化学习 SQ3R (方法2)

### 2.1 Survey - Agent 类架构概览

```
Agent 类架构:

┌─────────────────────────────────────────────────────────┐
│                    Agent 类                               │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐│
│  │                  MutableAgentState                     ││
│  │  ├─ systemPrompt                                     ││
│  │  ├─ model                                            ││
│  │  ├─ tools (setter复制)                               ││
│  │  ├─ messages (setter复制)                            ││
│  │  ├─ isStreaming (只读)                               ││
│  │  ├─ streamingMessage (只读)                          ││
│  │  └─ pendingToolCalls (只读)                          ││
│  └─────────────────────────────────────────────────────┘│
│                              │                            │
│  ┌──────────────────────────▼──────────────────────────┐│
│  │                  PendingMessageQueue                 ││
│  │  ├─ steeringMessages: AgentMessage[]               ││
│  │  └─ followUpMessages: AgentMessage[]               ││
│  └─────────────────────────────────────────────────────┘│
│                              │                            │
│  ┌──────────────────────────▼──────────────────────────┐│
│  │                  Event Listeners                     ││
│  │  listeners: Set<AgentEventListener>                ││
│  └─────────────────────────────────────────────────────┘│
│                              │                            │
│  ┌──────────────────────────▼──────────────────────────┐│
│  │                  Execution Control                   ││
│  │  ├─ prompt() / continue() / reset()                  ││
│  │  ├─ activeRun?: Promise<void>                        ││
│  │  └─ waitForIdle()                                    ││
│  └─────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────┘

调用流程:
prompt() → createContext → runAgentLoop → processEvents → waitForIdle
                                          ↓
                                    更新 MutableAgentState
                                    分发事件给 listeners
```

### 2.2 Question - 关键问题驱动

**Q1**: MutableAgentState 的 getter/setter 为什么采用不同的复制策略？
**Q2**: steering 和 followUp 队列的注入时机有什么区别？
**Q3**: waitForIdle 如何确保所有监听器都已完成？
**Q4**: 为什么需要 activeRun 来防止并发执行？

### 2.3 Read - 源代码映射

| 内容 | 源文件 | 行数 | 说明 |
|------|--------|------|------|
| Agent 类定义 | `agent.ts` | L166-219 | 主类结构 |
| MutableAgentState | `agent.ts` | L221-293 | 状态管理 |
| getter/setter 实现 | `agent.ts` | L240-293 | 复制机制 |
| PendingMessageQueue | `agent.ts` | L295-318 | 队列管理 |
| prompt() 方法 | `agent.ts` | L320-357 | 主要入口 |
| continue() 方法 | `agent.ts` | L359-385 | 继续模式 |
| reset() 方法 | `agent.ts` | L387-400 | 重置状态 |
| processEvents() | `agent.ts` | L509-556 | 事件处理 |
| subscribe() | `agent.ts` | L230-234 | 订阅机制 |
| waitForIdle() | `agent.ts` | L299-310 | 等待屏障 |
| activeRun 管理 | `agent.ts` | L292-297 | 并发控制 |

### 2.4 Recite - 使用模板

#### 基础使用模板

```typescript
import { Agent } from "@earendil-works/pi-agent-core";
import { getModel } from "@earendil-works/pi-ai";

const agent = new Agent({
  initialState: {
    systemPrompt: "You are a helpful assistant.",
    model: getModel("anthropic", "claude-sonnet-4-20250514"),
    tools: [],
    messages: [],
  },
});

// 订阅事件
agent.subscribe((event, signal) => {
  if (event.type === "message_update") {
    // 处理消息更新
  }
  if (event.type === "agent_end") {
    // 处理完成
  }
});

// 发送消息
await agent.prompt("Hello!");
```

#### 队列使用模板

```typescript
// Steering 队列 - 回合中注入
agent.steeringMessages.push({
  role: "system",
  content: "Additional context",
});

// Follow-up 队列 - 回合后注入
agent.followUpMessages.push({
  role: "user",
  content: "Follow up question",
});
```

#### 并发控制模板

```typescript
// 检查是否在运行
if (agent.activeRun) {
  console.log("Agent is busy, please wait...");
  await agent.waitForIdle();
}

// 安全调用
await agent.prompt("New task");
```

---

### 2.5 Review - TODO清单 (渐进式披露)

#### 🔴 TODO-1: 掌握 MutableAgentState (当前激活)

**完成检查**:
- [ ] 列举 AgentState 的 5 个可变属性和 3 个只读属性
- [ ] 解释为什么 tools/messages 的 setter 要复制数组
- [ ] 解释直接修改和 setter 赋值的区别

<details>
<summary>💡 提示</summary>

```typescript
// setter 复制
agent.state.tools = [tool1, tool2];  // 内部: tools = next.slice()

// 直接修改
agent.state.tools.push(tool3);  // 直接修改内部数组，不触发复制
```
</details>

---

#### 🟡 TODO-2: 掌握队列机制 (待解锁)

**前置要求**: 完成 TODO-1

**完成检查**:
- [ ] 解释 steering 队列的注入时机（回合中）
- [ ] 解释 followUp 队列的注入时机（回合后）
- [ ] 列举两种队列的使用场景

---

#### 🟡 TODO-3: 掌握屏障行为 (待解锁)

**前置要求**: 完成 TODO-2

**完成检查**:
- [ ] 解释 waitForIdle 的触发条件
- [ ] 解释 agent_end 后如何等待监听器完成
- [ ] 解释 activeRun 的作用

---

#### 🟡 TODO-4: 掌握事件处理 (待解锁)

**前置要求**: 完成 TODO-3

**完成检查**:
- [ ] 解释 subscribe 返回的 unsubscribe 函数用法
- [ ] 解释 processEvents 中监听器错误的隔离机制
- [ ] 列举 processEvents 中更新的 3 个状态字段

---

## 3. 对抗性测试 (方法3)

### 3.1 边界问题

#### MutableAgentState 复制边界

```typescript
// ❌ 错误：期望深度修改被复制
agent.state.tools[0].name = "new_name";  // 直接修改内部
agent.state.tools = agent.state.tools;     // setter 复制，但已修改

// ✅ 正确：先复制再修改
const newTools = [...agent.state.tools];
newTools[0] = { ...newTools[0], name: "new_name" };
agent.state.tools = newTools;
```

**边界**: setter 只复制数组引用，不深度复制对象。

#### 并发执行边界

```typescript
// ❌ 错误：并发调用
agent.prompt("Task 1");  // 不 await
agent.prompt("Task 2");  // 报错：已有 activeRun

// ✅ 正确：串行调用
await agent.prompt("Task 1");
await agent.prompt("Task 2");

// ✅ 正确：检查后再调用
if (!agent.activeRun) {
  await agent.prompt("Task");
}
```

### 3.2 反事实推理

**情境 1**: 如果 continue() 时最后消息是 assistant？
```typescript
agent.state.messages = [
  { role: "user", content: "Hi" },
  { role: "assistant", content: "Hello" },
];
await agent.continue();  // ❌ 抛异常
// 结果：错误提示"最后消息必须是 user 或 toolResult"
// 教训：continue 的前提条件必须满足
```

**情境 2**: 如果监听器执行长时间操作？
```typescript
agent.subscribe(async (event) => {
  if (event.type === "agent_end") {
    await saveToDatabase();  // 5秒
  }
});
await agent.prompt("Hello");  // 等待 5秒+
// 结果：prompt 返回被延迟
// 教训：监听器应快速完成，或异步处理
```

**情境 3**: 如果 reset() 在运行中调用？
```typescript
agent.prompt("Long task");  // 启动
agent.reset();               // 重置状态
// 结果：reset 不影响正在运行的 loop
// 教训：reset 只重置状态，不取消运行
```

### 3.3 漏洞注入 - 常见错误

| 错误类型 | 示例 | 后果 | 修复 |
|---------|------|------|------|
| 并发调用 | `prompt(); prompt()` | 第二个报错 | await 第一个 |
| 深度修改期望复制 | `tools[0].name = x` | 未触发复制 | 复制后再赋值 |
| 长时间监听器 | `await sleep(10)` | 阻塞返回 | 异步处理 |
| continue 前提不满足 | 最后消息是 assistant | 抛异常 | 检查消息顺序 |
| 忽略 abort 信号 | 不检查 `signal.aborted` | 无法取消 | 检查并提前返回 |

---

## 4. 思想与迁移

### 4.1 设计哲学

#### 包装器模式

```
agentLoop (底层) → Agent (包装层) → 应用代码

底层：纯函数，无状态，事件流
包装层：状态管理，队列，屏障
应用层：简单调用，订阅事件
```

**思想**: 分层封装，每层解决特定问题。

#### 防御性复制

```typescript
set tools(next) { this._state.tools = next.slice(); }
set messages(next) { this._state.messages = next.slice(); }
```

**思想**: 防止外部修改污染内部状态，同时允许原地修改。

#### 屏障同步

```typescript
// Agent 类等待监听器
for (const listener of this.listeners) {
  await listener(event, signal);  // 阻塞等待
}

// agentLoop 不等待
emit({ type: "message_end" });  // 立即继续
```

**思想**: 在关键节点等待，保证消费者处理完成。

### 4.2 可迁移思维

| 思想 | Agent 类应用 | 可迁移领域 |
|------|-------------|-----------|
| **包装器模式** | Agent 包装 agentLoop | 框架设计、API封装 |
| **防御性复制** | getter/setter 复制 | 状态管理、不变性 |
| **屏障同步** | waitForIdle | 状态机、事件系统 |
| **队列注入** | steering/followUp | 消息队列、任务调度 |
| **并发控制** | activeRun | 资源池、连接管理 |

---

## 📝 费曼检验 (必须完成)

在继续下一课之前，请用自己的话解释：

### 问题 1: MutableAgentState
> 不要复制原文，像教别人一样解释：
> "为什么 Agent.state.tools 的 setter 要复制数组？直接返回引用有什么问题？"

你的解释：_______________________________________________

### 问题 2: 队列机制
> "steering 和 followUp 队列分别在什么时候被消费？为什么需要两种队列？"

你的解释：_______________________________________________

### 问题 3: 屏障行为
> "waitForIdle 为什么能确保所有监听器都已完成？activeRun 是什么时候被清空的？"

你的解释：_______________________________________________

---

<details>
<summary>✅ 检查你的理解</summary>

**问题 1 参考答案**:
- setter 复制数组是为了防止外部修改影响内部状态
- 如果返回引用，外部 `tools.push()` 会直接修改内部，破坏封装
- 同时允许原地修改 `agent.state.tools.push()` 用于快速更新

**问题 2 参考答案**:
- steering: 在回合开始时注入（内层循环）
- followUp: 在回合结束后注入（外层循环）
- 分离允许回合中干预 vs 回合后追问的不同场景

**问题 3 参考答案**:
- waitForIdle 等待 activeRun Promise 完成
- processEvents 中 await 每个监听器，保证顺序执行
- agent_end 时调用 finishRun() 清空 activeRun，触发 resolve
</details>

---

## 源文件映射

| 学习内容 | 源文件 | 行数 |
|---------|--------|------|
| Agent 类定义 | `src/agent.ts` | ~560 |
| MutableAgentState | `src/agent.ts` | L221-293 |
| PendingMessageQueue | `src/agent.ts` | L295-318 |
| prompt/continue/reset | `src/agent.ts` | L320-400 |
| processEvents | `src/agent.ts` | L509-556 |

---

## 下一步

完成费曼检验后，解锁下一课：

→ [L05: 工具执行完整流程](../05-tool-system)

---

## 💾 学习记录

完成时间: ___________

自我评估 (1-5): ___

脆弱点记录:
- _________________________________

备注:
- _________________________________
