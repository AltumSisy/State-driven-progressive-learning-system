# L06: 事件系统

---

## 1. 心智模型构建

### 1.1 背景

#### 事件系统的演进

```
早期事件处理:
├─ 回调函数: onText, onComplete, onError
├─ 问题: 回调地狱，顺序不确定
├─ 多监听器: 手动管理，容易遗漏
└─ 无状态追踪: 不知道当前状态

中期需求:
├─ 统一事件流 → AgentEvent 类型
├─ 状态同步 → processEvents 更新
├─ 多监听器 → subscribe 队列
├─ 屏障行为 → 等待监听器完成
└─ 事件顺序 → 保证顺序执行

→ agent-core 提供完整事件系统
```

---

### 1.2 目标

#### 核心痛点

| 痛点 | 回调模式 | agent-core 事件系统 |
|------|---------|-------------------|
| 类型安全 | 无类型约束 | AgentEvent 联合类型 |
| 状态同步 | 手动更新 | processEvents 自动 |
| 监听器管理 | 手动注册 | subscribe 队列 |
| 顺序保证 | 不确定 | await 线性执行 |
| 屏障行为 | 无 | message_end 等待 |

---

### 1.3 专家视角 - 概念网络

```
事件系统概念网络:

事件类型:
├─ AgentEvent (10种)
│   ├─ agent_start / agent_end ← Agent 生命周期
│   ├─ turn_start / turn_end ← Turn 生命周期
│   ├─ message_start / message_update / message_end ← 消息流
│   └─ tool_execution_start / update / end ← 工具执行
│
├─ Discriminated Union
│   └─ type 字段辨识，自动推断其他字段
│
├─ AssistantMessageEvent (来自 pi-ai)
│   ├─ text_delta
│   ├─ thinking_delta
│   ├─ tool_call_delta
│   └─ image_delta

事件处理:
├─ processEvents()
│   ├─ 状态更新: streamingMessage, pendingToolCalls, messages
│   ├─ 监听器分发: await listener(event, signal)
│   └─ 错误隔离: 监听器抛异常不影响状态
│
├─ subscribe()
│   ├─ listeners: Set<AgentEventListener>
│   └─ 返回 unsubscribe 函数
│
├─ agent_end 屏障
│   ├─ 等待所有监听器完成
│   ├─ finishRun() 才 resolve activeRun
│   └─ waitForIdle() 返回
```

---

## 2. 结构化学习 (SQ3R)

### 2.1 Survey - 事件序列概览

```
事件序列流程:

无工具调用:
┌─────────────────────────────────────────────────────────┐
│  prompt("Hello")                                         │
│                                                          │
│  agent_start                                             │
│      │                                                    │
│  turn_start                                              │
│      │                                                    │
│  message_start { user }                                  │
│  message_end                                             │
│      │                                                    │
│  message_start { assistant }                             │
│  message_update { text_delta: "Hel" }                    │
│  message_update { text_delta: "lo!" }                    │
│  message_end                                             │
│      │                                                    │
│  turn_end { toolResults: [] }                            │
│      │                                                    │
│  agent_end { messages }                                  │
└─────────────────────────────────────────────────────────┘

带工具调用:
┌─────────────────────────────────────────────────────────┐
│  prompt("Read file")                                     │
│                                                          │
│  agent_start                                             │
│  turn_start                                              │
│  message_start/end { user }                              │
│  message_start { assistant with toolCall }               │
│  message_end                                             │
│      │                                                    │
│  tool_execution_start { toolCallId, toolName }           │
│  tool_execution_end { result, isError }                  │
│      │                                                    │
│  message_start/end { toolResult }                        │
│  turn_end                                                │
│      │                                                    │
│  turn_start ← 新回合开始                                 │
│  message_start/update/end { assistant response }         │
│  turn_end                                                │
│      │                                                    │
│  agent_end { messages }                                  │
└─────────────────────────────────────────────────────────┘
```

### 2.2 Question - 关键问题驱动

**Q1**: AgentEvent 为什么使用 Discriminated Union？
**Q2**: message_end 时执行哪两个状态更新？
**Q3**: 监听器抛异常时会发生什么？
**Q4**: agent_end 屏障的具体行为是什么？

### 2.3 Read - 源代码映射

| 内容 | 源文件 | 行数 |
|------|--------|------|
| AgentEvent 定义 | `types.ts` | L403-418 |
| AssistantMessageEvent | `pi-ai` | - |
| processEvents | `agent.ts` | L509-556 |
| subscribe | `agent.ts` | L230-234 |
| waitForIdle | `agent.ts` | L299-310 |
| finishRun | `agent.ts` | L294-297 |

### 2.4 Recite - 使用模板

#### 事件监听模板

```typescript
agent.subscribe((event, signal) => {
  switch (event.type) {
    case "message_update":
      if (event.assistantMessageEvent.type === "text_delta") {
        process.stdout.write(event.assistantMessageEvent.delta);
      }
      break;

    case "tool_execution_start":
      console.log(`Tool ${event.toolName} starting...`);
      break;

    case "tool_execution_end":
      if (event.isError) {
        console.error(`Tool ${event.toolName} failed`);
      }
      break;

    case "agent_end":
      saveSession(event.messages);
      break;
  }
});
```

#### 多监听器模板

```typescript
const unsubscribe1 = agent.subscribe(listener1);
const unsubscribe2 = agent.subscribe(listener2);

// 取消订阅
unsubscribe1();
```

### 2.5 Review - TODO清单

#### TODO-1: 掌握事件类型 (🔴)
**完成检查**:
- [ ] 列举 10 种 AgentEvent 类型
- [ ] 解释 Discriminated Union 的优势

#### TODO-2: 掌握状态更新 (🔴)
**完成检查**:
- [ ] 列举 message_end 时执行的两个状态更新
- [ ] 解释 streamingMessage 的生命周期

#### TODO-3: 掌握监听器机制 (🟠)
**完成检查**:
- [ ] 解释监听器抛异常时的处理
- [ ] 解释 unsubscribe 的实现

#### TODO-4: 掌握屏障行为 (🟠)
**完成检查**:
- [ ] 解释 agent_end 后 Agent 空闲的原因
- [ ] 解释 waitForIdle 的等待机制

---

## 3. 对抗性测试

### 3.1 边界问题

#### 监听器执行顺序

```typescript
// 监听器按添加顺序执行，线性等待
agent.subscribe(listener1);  // 先执行
agent.subscribe(listener2);  // 后执行
// 不是并发执行，是串行 await
```

#### message_end 状态更新

```typescript
case "message_end":
  this._state.streamingMessage = undefined;  // 清除
  this._state.messages.push(event.message);  // 持久化
```

**边界**: 两个更新在同一次 message_end 中完成。

### 3.2 反事实推理

**情境 1**: 如果监听器执行长时间操作？
```typescript
agent.subscribe(async (event) => {
  if (event.type === "agent_end") {
    await saveToDatabase();  // 5秒
  }
});
// 结果：waitForIdle() 等待 5秒
// 教训：agent_end 监听器应快速完成，或异步处理
```

**情境 2**: 如果监听器抛异常？
```typescript
agent.subscribe(async () => {
  throw new Error("Listener error");
});
// 结果：processEvents 中 await listener() 抛异常
// 教训：监听器应自行捕获错误
```

**情境 3**: 如果没有订阅任何监听器？
```typescript
const agent = new Agent({...});
await agent.prompt("Hello");  // 无 subscribe
// 结果：正常工作，事件发出但无处理
// 教训：不订阅也能用，但无法追踪进度
```

### 3.3 漏洞注入 - 常见错误

| 错误类型 | 示例 | 后果 |
|---------|------|------|
| 监听器未捕获错误 | `throw new Error()` | 中断事件处理 |
| 长时间监听器 | `await sleep(10000)` | 阻塞后续流程 |
| 遗漏 agent_end 处理 | 不处理 final messages | 数据丢失 |
| 忽略 signal | 不检查中止信号 | 无法取消 |

---

## 4. 思想与迁移

### 4.1 设计哲学

#### Discriminated Union

```typescript
type AgentEvent =
  | { type: "agent_start" }
  | { type: "agent_end"; messages: AgentMessage[] };
```

**思想**: TypeScript 根据 `type` 字段自动推断其他字段，switch 语句有完整性检查。

#### 屏障行为

```typescript
// Agent 类等待监听器
for (const listener of this.listeners) {
  await listener(event, signal);  // 阻塞等待
}

// agentLoop 不等待
emit({ type: "message_end" });  // 立即继续
```

**思想**: 在关键节点等待，保证消费者处理完成。

#### 观察性分离

```
agentLoop: 观察性流 (不等待消费者)
Agent 类: 控制性流 (等待消费者完成)
```

**思想**: 分离观察和控制，让底层纯粹，上层可控。

### 4.2 可迁移思维

| 思想 | 事件系统应用 | 可迁移领域 |
|------|-------------|-----------|
| **Discriminated Union** | AgentEvent 类型 | Redux action、消息协议 |
| **屏障行为** | agent_end 等待 | 状态机、事件系统 |
| **观察性分离** | agentLoop vs Agent | 流处理、消息总线 |
| **监听器队列** | subscribe Set | 发布订阅模式 |
| **线性执行** | await listener() | 任务队列、中间件 |

---

## 源文件映射

| 内容 | 源文件 | 行数 |
|------|--------|------|
| AgentEvent 类型 | `types.ts` | L403-418 |
| processEvents | `agent.ts` | L509-556 |
| subscribe | `agent.ts` | L230-234 |

---

## 下一步

→ [L07: Harness 基础](../07-harness-base)