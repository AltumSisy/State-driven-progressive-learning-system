# L04: Agent 类 (包装层)

---

## 1. 心智模型构建

### 1.1 背景

#### 为什么需要 Agent 类？

```
agentLoop 的问题:
├─ 无状态管理: 需要外部管理 messages, tools
├─ 无队列机制: steering/follow-up 需手动实现
├─ 无订阅等待: 事件发出后不等待处理
├─ 无屏障行为: 无法在工具预检前等待状态更新
└─ 使用复杂: 需要完整配置每次调用

→ Agent 类封装这些复杂性
```

#### Agent 类的设计定位

```
Agent 类 = agentLoop 的状态化包装器

职责:
├─ 状态管理: MutableAgentState + getter/setter
├─ 队列管理: PendingMessageQueue (steering/follow-up)
├─ 生命周期: activeRun + abortController
├─ 事件分发: listeners + processEvents
└─ 方法封装: prompt/continue/reset/subscribe
```

---

### 1.2 目标

#### 核心痛点

| 痛点 | agentLoop | Agent 类 |
|------|-----------|---------|
| 状态管理 | 外部管理 | 内置 MutableAgentState |
| 队列 | 手动配置钩子 | 内置 PendingMessageQueue |
| 事件等待 | 不等待 | await 监听器完成 |
| 屏障行为 | 无 | message_end 是工具预检屏障 |
| 易用性 | 需完整配置 | prompt("text") 即可 |

---

### 1.3 专家视角 - 概念网络

```
Agent 类概念网络:

状态管理:
├─ MutableAgentState
│   ├─ 可变: systemPrompt, model, thinkingLevel
│   ├─ getter/setter: tools, messages (复制)
│   └─ 只读: isStreaming, pendingToolCalls, errorMessage
│
├─ createMutableAgentState() ← 工厂函数
│   └─ 闭包变量: tools, messages

队列管理:
├─ PendingMessageQueue
│   ├─ mode: QueueMode ("all" | "one-at-a-time")
│   ├─ messages: AgentMessage[]
│   └─ drain(): 根据模式返回消息
│
├─ steeringQueue ← 运行时注入
├─ followUpQueue ← 完成后追加
└─ nextTurnQueue ← 下一回合

运行控制:
├─ ActiveRun
│   ├─ promise: Promise<void>
│   ├─ resolve: () => void
│   └─ abortController: AbortController
│
├─ runWithLifecycle() ← 启动运行
├─ finishRun() ← 结束运行
└─ waitForIdle() ← 等待完成
```

---

## 2. 结构化学习 (SQ3R)

### 2.1 Survey - Agent 类结构

```
Agent 类结构:

┌─────────────────────────────────────────────────────────┐
│                    Agent 类                               │
│                                                           │
│  状态:                                                    │
│  ├─ _state: MutableAgentState                            │
│  ├─ steeringQueue / followUpQueue                        │
│  └─ activeRun?: ActiveRun                                │
│                                                           │
│  公开属性:                                                │
│  ├─ state: AgentState                                    │
│  ├─ steeringMode / followUpMode                          │
│  ├─ convertToLlm / transformContext                      │
│  ├─ sessionId / thinkingBudgets                         │
│  ├─ signal: AbortSignal                                  │
│  └─ beforeToolCall / afterToolCall                       │
│                                                           │
│  方法:                                                    │
│  ├─ prompt(text | messages)                              │
│  ├─ continue()                                           │
│  ├─ reset()                                              │
│  ├─ steer(message) / followUp(message)                   │
│  ├─ abort() / waitForIdle()                              │
│  └─ subscribe(listener)                                  │
│                                                           │
│  内部方法:                                                │
│  ├─ runPromptMessages()                                  │
│  ├─ runContinuation()                                    │
│  ├─ runWithLifecycle()                                   │
│  ├─ processEvents()                                      │
│  └─ createLoopConfig()                                   │
└─────────────────────────────────────────────────────────┘
```

### 2.2 Question - 关键问题驱动

**Q1**: getter/setter 复制机制的目的是什么？
**Q2**: Agent 如何等待 subscribe 监听器完成？
**Q3**: continue() 从 assistant 消息如何处理？
**Q4**: message_end 作为屏障的具体行为是什么？

### 2.3 Read - 源代码映射

| 内容 | 源文件 | 行数 |
|------|--------|------|
| AgentOptions | `agent.ts` | L96-116 |
| Agent 类定义 | `agent.ts` | L166-219 |
| createMutableAgentState | `agent.ts` | L66-93 |
| PendingMessageQueue | `agent.ts` | L118-152 |
| subscribe | `agent.ts` | L230-234 |
| state getter | `agent.ts` | L240-243 |
| steer/followUp | `agent.ts` | L264-292 |
| abort/waitForIdle | `agent.ts` | L299-310 |
| reset | `agent.ts` | L313-322 |
| prompt | `agent.ts` | L324-335 |
| continue | `agent.ts` | L337-365 |
| processEvents | `agent.ts` | L509-556 |
| defaultConvertToLlm | `agent.ts` | L31-35 |

### 2.4 Recite - 使用模板

#### 基础使用模板

```typescript
const agent = new Agent({
  initialState: {
    systemPrompt: "You are helpful.",
    model: getModel("anthropic", "claude-sonnet-4"),
    tools: [myTool],
  },
});

agent.subscribe((event, signal) => {
  if (event.type === "message_update") {
    process.stdout.write(event.delta);
  }
  if (event.type === "agent_end") {
    saveSession(event.messages);
  }
});

await agent.prompt("Hello!");
await agent.waitForIdle();
```

#### 队列使用模板

```typescript
// Steering: 运行时打断
agent.prompt("Long task...");
setTimeout(() => {
  agent.steer({ role: "user", content: "Stop!", timestamp: Date.now() });
}, 5000);

// Follow-up: 完成后追加
agent.followUp({ role: "user", content: "Also summarize", timestamp: Date.now() });
```

### 2.5 Review - TODO清单

#### TODO-1: 掌握 getter/setter (🔴)
**完成检查**:
- [ ] 解释赋值复制 vs 直接修改的区别
- [ ] 写出 createMutableAgentState 的 getter/setter 实现

#### TODO-2: 掌握 prompt/continue (🔴)
**完成检查**:
- [ ] 解释 prompt 的三种输入类型处理
- [ ] 解释 continue 从 assistant 的队列处理逻辑

#### TODO-3: 掌握队列机制 (🟠)
**完成检查**:
- [ ] 列举 steer/followUp 的注入时机
- [ ] 解释 PendingMessageQueue.drain() 两种模式

#### TODO-4: 掌握事件处理 (🟠)
**完成检查**:
- [ ] 列举 processEvents 中 message_end 的两个更新
- [ ] 解释 agent_end 后 Agent 才空闲的原因

---

## 3. 对抗性测试

### 3.1 边界问题

#### 运行中调用 prompt

```typescript
// ❌ 错误: Agent 已在运行
await agent.prompt("Task 1");
await agent.prompt("Task 2");  // 抛异常: "Already processing"

// ✅ 正确: 使用 steer 或 followUp
await agent.prompt("Task 1");
agent.steer({ role: "user", content: "Task 2", timestamp: Date.now() });
await agent.waitForIdle();
```

#### continue() 前提条件

```typescript
// ❌ 错误: 最后消息是 assistant 且无队列
agent.state.messages.push({ role: "assistant", ... });
await agent.continue();  // 抛异常

// ✅ 正确: 有队列消息
agent.steer({ role: "user", content: "...", timestamp: Date.now() });
await agent.continue();  // 正常执行
```

### 3.2 反事实推理

**情境 1**: 如果 subscribe 监听器抛异常？
```typescript
agent.subscribe(async (event) => {
  throw new Error("Listener error");
});
// 结果：processEvents 中 await listener() 会抛异常
// 教训：监听器应该自己处理错误
```

**情境 2**: 如果运行中 reset？
```typescript
agent.prompt("Task...");
agent.reset();  // 清除 messages 和队列
// 结果：不影响当前运行的上下文（已创建快照）
// 教训：reset 影响下次调用
```

**情境 3**: 如果 agent_end 监听器执行长时间操作？
```typescript
agent.subscribe(async (event) => {
  if (event.type === "agent_end") {
    await longOperation();  // 10秒
  }
});
// 结果：waitForIdle() 等待 10秒才返回
// 教训：agent_end 监听器是屏障，需控制时间
```

### 3.3 漏洞注入 - 常见错误

| 错误类型 | 示例 | 后果 |
|---------|------|------|
| 运行中再 prompt | `agent.prompt()` 两次 | 抛异常 |
| continue 无队列 | 最后消息 assistant | 抛异常 |
| 监听器抛异常 | `throw new Error()` | 中断事件处理 |
| 遗漏 waitForIdle | `prompt(); save();` | save 在运行中 |

---

## 4. 思想与迁移

### 4.1 设计哲学

#### getter/setter 保护机制

```typescript
get tools() { return tools; }
set tools(next) { tools = next.slice(); }
```

**思想**: 赋值时保护（复制），使用时开放（直接修改）。

#### 屏障行为

```typescript
// Agent 类: message_end 是屏障
await emit({ type: "message_end" });
// 等待所有监听器完成后才进行工具预检

// agentLoop: 无屏障
emit({ type: "message_end" });
// 立即继续，不等待
```

**思想**: 在关键节点等待，保证状态一致性。

#### 监听器等待

```typescript
for (const listener of this.listeners) {
  await listener(event, signal);
}
```

**思想**: 事件分发是阻塞的，消费者必须完成。

### 4.2 可迁移思维

| 思想 | Agent 类应用 | 可迁移领域 |
|------|-------------|-----------|
| **getter/setter 保护** | tools/messages 复制 | 状态管理、ORM |
| **屏障行为** | message_end 等待 | 事件系统、状态机 |
| **监听器等待** | await listener() | UI框架、消息总线 |
| **队列抽象** | PendingMessageQueue | 任务队列、消息队列 |
| **生命周期管理** | activeRun + abort | 异步操作管理 |

---

## 源文件映射

| 内容 | 源文件 | 行数 |
|------|--------|------|
| agent.ts | `src/agent.ts` | ~560 |

---

## 下一步

→ [L05: 工具执行完整流程](../05-tool-system)