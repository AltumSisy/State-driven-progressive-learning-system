# Agent.ts 核心分析

> 从核心向外扩散的方式分析 Agent 类的设计

## 第一层：核心职责

### Agent 是什么？

一句话定义：

> Agent 是一个**有状态的 LLM 调用编排器**，负责管理对话历史、发出生命周期事件、执行工具、并提供运行控制 API。

它的核心契约：

```
用户 → Agent.prompt() → Agent 内部状态 → agent-loop → LLM → 事件 → 用户监听器
```

Agent 不直接调用 LLM，而是：
1. 维护状态
2. 组装配置，调用 agent-loop
3. 处理事件，更新状态，通知监听器

### 核心职责速记

Agent 三大核心职责：

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  1️⃣ 初始化配置管理                                                   │
│     • 配置组装：createLoopConfig()                                  │
│     • 配置快照：createContextSnapshot()                             │
│     • 配置拷贝：防止污染，单向数据流                                  │
│                                                                     │
│  2️⃣ 运行时可视化体现                                                 │
│     • 事件系统：processEvents()                                     │
│     • 状态同步：事件驱动更新 _state                                  │
│     • 监听器通知：subscribe() 让外部实时响应                         │
│                                                                     │
│  3️⃣ 运行时执行介入                                                   │
│     • 并发控制：activeRun 同时只有一个                               │
│     • 中止干预：abort() + signal 传播                               │
│     • 消息注入：steering/followUp 队列                               │
│     • 失败处理：handleRunFailure() 完整事件序列                      │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**口诀版**：

```
配置管好 → 快照拷贝防污染
状态可视 → 事件驱动通知外
执行介入 → 并控中止队列兜底
```

**一句话总结**：

> Agent 做三件事：**准备阶段**做好配置管理、快照隔离；**运行阶段**通过事件让状态变化可视化；**控制阶段**通过并发控制、中止干预、队列注入、失败兜底来管理执行。

---

## 第二层：状态管理

### 状态分两类

| 类型 | 内容 | 特点 |
|------|------|------|
| **持久状态** | messages、tools、systemPrompt、model | 会保存到会话，跨运行存在 |
| **运行时状态** | isStreaming、streamingMessage、pendingToolCalls、errorMessage | 只在运行期间有意义 |

### 状态的核心问题

**问题**：如何保证外部赋值不污染内部？

**解决方案**：getter/setter 拷贝

```typescript
// 内部实现
let messages = [];

return {
    get messages() { return messages; },
    set messages(next) { messages = next.slice(); },  // 赋值时拷贝！
};
```

**效果**：
- `agent.state.messages = externalArray` → 内部存储的是拷贝
- `externalArray.push(...)` → 不影响内部
- `agent.state.messages.push(...)` → 可以，这是故意的设计

### 为什么允许 getter 返回的数组可修改？

方便增量操作：

```typescript
agent.state.messages.push(newMessage);  // 比赋值整个数组更方便
```

### 深入理解：什么是"污染"？

**污染 = 两个变量指向同一个对象，改一个影响另一个**

这是 JavaScript 引用类型的问题：

```javascript
// 🔴 污染的例子
const internal = { data: [1, 2, 3] };
const external = internal.data;  // 只是引用，不是拷贝！

external.push(4);  // 改了 external

console.log(internal.data);  // [1, 2, 3, 4] ← 被污染了！
```

**两种"污染"场景**：

1. **外部赋值污染内部**：
```
外部代码                                              Agent 内部
    │                                                     │
    │  const myArray = [msg1, msg2];                     │
    │                                                     │
    │  agent.messages = myArray  ──────────────────────► │  _state.messages = myArray.slice()
    │                                                     │  (拷贝，新对象！)
    │  myArray.push(msg3)  ──────► 只改了自己的数组        │
    │                                                     │  内部不受影响
```

2. **agent-loop 污染 Agent 内部**（第七层详细解释）：
```
Agent 内部                                          agent-loop
    │                                                     │
    │  创建快照（拷贝）                                    │
    │  context.messages = _state.messages.slice()  ────► │  context.messages
    │                                                     │
    │                                                     │  context.messages.push(msg3)
    │                                                     │
    │  内部不变，等事件更新   ◄────────────────────────── │
    │                                           (不同对象！)
```

**生活比喻**：

- ❌ 污染 = 共享一个草稿本，小明写的被小红改了
- ✅ 隔离 = 各自用复印件，互不影响

**总结**：`a = b`（对象/数组）会共享引用，`a = b.slice()` 创建新数组避免污染。

---

## 第三层：事件系统

### 事件是 Agent 与外界的通信通道

事件类型（从高层到低层）：

```
agent_start           ← 运行开始
  turn_start          ← 一轮开始（一轮 = 助手回复 + 工具执行）
    message_start     ← 消息开始
    message_update    ← 消息更新（只有 assistant）
    message_end       ← 消息结束
    tool_execution_start   ← 工具开始
    tool_execution_update  ← 工具进度
    tool_execution_end     ← 工具结束
  turn_end            ← 一轮结束
agent_end             ← 运行结束（最后事件）
```

### 事件处理流程

```typescript
processEvents(event) {
    // 1. 先更新内部状态
    switch (event.type) {
        case "message_end": 
            this._state.messages.push(event.message);  // 状态同步
            break;
        // ...
    }
    
    // 2. 然后通知监听器
    for (const listener of this.listeners) {
        await listener(event, signal);  // 顺序执行，等待完成
    }
}
```

### 关键设计决策

- **状态先于监听器更新**：监听器看到的是最新状态
- **监听器顺序执行**：保证事件顺序一致性
- **监听器接收 signal**：可以响应中止请求

### subscribe 的设计

```typescript
subscribe(listener), () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);  // 返回取消函数
}
```

返回取消函数是常见模式，方便一次性订阅：

```typescript
const unsub = agent.subscribe(handler);
// ... 之后
unsub();
```

### 深入理解：消息、状态、事件、监听器的关系

**常见疑惑**：有了 `_state.messages` 存储消息，为什么还需要事件和监听器？

**核心关系图**：

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Agent 内部                                  │
│                                                                     │
│   _state.messages = []    ←─────────────────────┐                   │
│         │                                        │                   │
│         │ (1) 用户调用                           │ (4) 状态更新     │
│         ▼                                        │                   │
│   agent.prompt("Hello")                           │                   │
│         │                                        │                   │
│         ▼                                        │                   │
│   ┌─────────────────┐                            │                   │
│   │   agent-loop    │ ──→ 产生事件 ──→ processEvents(event)          │
│   │   (执行层)      │                            │                   │
│   └─────────────────┘                            │                   │
│         │                                        │                   │
│         │ 事件类型:                              │                   │
│         │  - message_start                      │                   │
│         │  - message_update                     │                   │
│         │  - message_end                        │                   │
│         │  - tool_execution_start               │                   │
│         │  - ...                                │                   │
│         ▼                                        ▼                   │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │                    processEvents(event)                     │   │
│   │                                                             │   │
│   │   switch (event.type) {                                     │   │
│   │       case "message_end":                                    │   │
│   │           this._state.messages.push(event.message); ────────┘   │
│   │           break;                                             │   │
│   │   }                                                          │   │
│   │                                                             │   │
│   │   // (5) 通知所有监听器                                        │   │
│   │   for (const listener of this.listeners) {                   │   │
│   │       await listener(event, signal);  ──────────────────────┼───┼───→ 外部代码
│   │   }                                                         │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**具体例子**：

```typescript
// ============ 1. 外部代码注册监听器 ============
const agent = new Agent();

// subscribe 注册一个"监听器"
// 监听器就是一个函数，每次有事件就会调用
const unsubscribe = agent.subscribe((event, signal) => {
    console.log("收到事件:", event.type);

    if (event.type === "message_end") {
        console.log("消息完成:", event.message.content);
    }

    if (event.type === "tool_execution_start") {
        console.log("开始执行工具:", event.toolName);
    }
});

// ============ 2. 用户发起对话 ============
await agent.prompt("帮我查一下今天天气");

// ============ 3. 内部发出一系列事件 ============
// agent-loop 执行过程中发出：
// 事件 1: { type: "agent_start", ... } → listener 被调用
// 事件 2: { type: "turn_start", ... } → listener 被调用
// 事件 3: { type: "message_start", ... } → listener 被调用
// ...
// 事件 N: { type: "agent_end", ... } → listener 被调用

// ============ 4. 之后可以查看状态 ============
console.log(agent.state.messages);
// [{ role: "user", content: "帮我查一下今天天气" },
//  { role: "assistant", content: "今天天气..." }]
```

**两者的区别**：

| 概念 | 是什么 | 目的 |
|------|--------|------|
| `_state.messages` | **数据存储** | 保存对话历史，供下次 LLM 调用使用 |
| `subscribe(listener)` | **事件通知** | 让外部代码实时响应 Agent 发生的事情 |

**为什么需要 subscribe？**

如果没有 subscribe，外部代码只能事后查看结果：

```typescript
await agent.prompt("Hello");
// 只能事后查看结果
console.log(agent.state.messages);
```

有了 subscribe，外部代码可以实时响应：

```typescript
agent.subscribe((event) => {
    if (event.type === "message_update") {
        // ✅ 实时显示流式输出
        ui.updateContent(event.content);
    }
    if (event.type === "tool_execution_start") {
        // ✅ 显示工具调用进度
        ui.showSpinner(event.toolName);
    }
});
```

**类比理解**：

把 Agent 想象成一个**餐厅后厨**：

- `_state.messages` = 订单记录本（记录所有做过的菜）
- `processEvents` = 服务员（处理后厨发生的事）
- `subscribe` = 叫号器（通知顾客"您的菜好了"）
- `listener` = 顾客收到通知后做的事

---

## 第四层：运行控制

### 核心问题

**问题**：如何管理"运行"这个概念？

### 运行的定义

一次 `prompt()` 或 `continue()` 调用对应的完整生命周期。

### 运行的追踪

```typescript
type ActiveRun = {
    promise: Promise<void>;        // 运行的 promise
    resolve: () => void;           // 完成时调用
    abortController: AbortController;  // 中止控制器
};
```

### 运行的生命周期

```
prompt() 被调用
│
├─ 检查 activeRun 是否存在 → 存在则报错（并发控制）
│
├─ 创建 activeRun
├─ 设置 isStreaming = true
│
├─ 执行 agent-loop（通过 runWithLifecycle）
│   │
│   ├─ 成功 → 直接到 finally
│   └─ 失败 → handleRunFailure → 发出完整事件序列
│
└─ finishRun()
    ├─ 设置 isStreaming = false
    ├─ resolve() ← waitForIdle() 收到通知
    └─ activeRun = undefined
```

### 并发控制

```typescript
async prompt(...) {
    if (this.activeRun) {
        throw new Error("Agent is already processing...");
    }
    // 只有空闲时才能开始
}
```

### 等待完成

```typescript
waitForIdle(): Promise<void> {
    return this.activeRun?.promise ?? Promise.resolve();
}
```

调用者可以：

```typescript
agent.prompt("Hello");
await agent.waitForIdle();  // 等待完成
// 或者直接
await agent.prompt("Hello");  // prompt 本身也返回 promise
```

### 中止传播

```typescript
abort(): void {
    this.activeRun?.abortController.abort();
}

get signal(): AbortSignal | undefined {
    return this.activeRun?.abortController.signal;
}
```

signal 传递给：
- agent-loop（传给 LLM 调用）
- 工具执行
- 事件监听器

### 深入理解：运行控制的本质

**核心问题**：如何管理"一次 prompt"这个概念？

**一次"运行"的生命周期**：

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           一次运行 (Run)                                │
│                                                                         │
│   prompt() 被调用                                                        │
│        │                                                                │
│        ▼                                                                │
│   ┌──────────────────┐                                                  │
│   │ 1. 初始检查       │  ← 并发控制：已有运行？报错！                          │
│   └────────┬─────────┘                                                  │
│            │                                                            │
│            ▼                                                            │
│   ┌──────────────────┐                                                  │
│   │ 2. 创建 activeRun │  ← 创建追踪对象                                   │
│   │    {             │                                                  │
│   │      promise,    │     用于 waitForIdle()                           │
│   │      resolve,    │     运行结束时调用                                  │
│   │      abortCtrl   │     用于 abort()                                 │
│   │    }             │                                                  │
│   └────────┬─────────┘                                                  │
│            │                                                            │
│            ▼                                                            │
│   ┌──────────────────┐                                                  │
│   │ 3. 执行 agent-loop│  ← 实际工作                                       │
│   └────────┬─────────┘                                                  │
│            │                                                            │
│            ├──────────→ 成功 ─┐                                         │
│            │                  │                                         │
│            ├──────────→ 失败 ─┤                                         │
│            │                  │                                         │
│            └──────────→ 中止 ─┤                                         │
│                               │                                         │
│                               ▼                                         │
│   ┌──────────────────┐                                                  │
│   │ 4. finishRun()   │  ← 统一收尾                                       │
│   │   - isStreaming=false                                                │
│   │   - resolve()    │     通知 waitForIdle 的等待者                      │
│   │   - activeRun=undefined  清除追踪对象                                  │
│   └──────────────────┘                                                  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**为什么需要 activeRun？**

没有 activeRun 会怎样？

```typescript
// ❌ 问题 1：无法防止并发
agent.prompt("Hello");  // 开始运行
agent.prompt("World");  // 同时又调用！状态会混乱

// ❌ 问题 2：无法中止
agent.prompt("Hello");
// 用户想取消...但是没有 abortController，怎么取消？

// ❌ 问题 3：无法等待完成
agent.prompt("Hello");
await agent.waitForIdle();  // 怎么知道运行结束了？
```

有了 activeRun：

```typescript
type ActiveRun = {
    promise: Promise<void>;        // waitForIdle 可以等待这个
    resolve: () => void;           // 运行结束时调用，通知等待者
    abortController: AbortController;  // abort() 可以中止
};
```

**功能对照表**：

| 功能点 | 对应代码 | 说明 |
|--------|---------|------|
| 初始状态 | `if (activeRun) throw Error` | 并发控制 |
| 执行 | `runAgentLoop(...)` | 调用执行层 |
| 中止干预 | `abortController.abort()` | 传播到 LLM 调用和工具执行 |
| 成功处理 | 正常结束 → `finishRun()` | 清理状态 |
| 失败处理 | `handleRunFailure()` | 发出完整事件序列 |
| 结束回收 | `finishRun()` | resolve promise、清除 activeRun |

**简单类比**：

把"运行"想象成一次**外卖配送**：

```
activeRun = {
    promise:      "配送承诺"（顾客可以等配送完成）
    resolve:      "送达通知"（配送完成时调用）
    abortCtrl:    "取消按钮"（顾客可以取消订单）
}

// 配送开始
if (activeRun) throw Error("已有配送进行中");

activeRun = { promise, resolve, abortCtrl };

try {
    await 配送();  // 执行
} finally {
    resolve();         // 通知等待的顾客
    activeRun = undefined;  // 清除配送记录
}
```

**总结**：运行控制就是把一次 `prompt()` 调用当做一个**完整的生命周期单位**来管理。

---

## 第五层：消息队列

### 核心问题

**问题**：用户想在运行过程中"引导" agent，或在完成后追加任务。

### 两种队列

| 队列 | 注入时机 | 用途 |
|------|----------|------|
| **Steering** | 助手 turn 结束后，下一轮 LLM 调用前 | 运行时干预 |
| **Follow-up** | agent 即将停止时（无工具调用、无 steering） | 任务追加 |

### 队列模式

```typescript
type QueueMode = "all" | "one-at-a-time";
```

- `"all"`：一次性清空所有消息
- `"one-at-a-time"`：每次只取一条（交互场景）

### 队列实现

```typescript
class PendingMessageQueue {
    private messages: AgentMessage[] = [];
    public mode: QueueMode;
    
    enqueue(message), void { this.messages.push(message); }
    
    drain(): AgentMessage[] {
        if (this.mode === "all") {
            // 一次性清空
            const drained = this.messages.slice();
            this.messages = [];
            return drained;
        }
        // 只取第一条
        const first = this.messages[0];
        this.messages = this.messages.slice(1);
        return [first];
    }
}
```

### 队列如何注入到 agent-loop？

通过配置函数：

```typescript
createLoopConfig() {
    return {
        getSteeringMessages: async () => this.steeringQueue.drain(),
        getFollowUpMessages: async () => this.followUpQueue.drain(),
    };
}
```

agent-loop 在适当时机调用这些函数，获取队列消息。

### continue() 如何处理队列？

```typescript
async continue() {
    const lastMessage = this._state.messages[...];

    if (lastMessage.role === "assistant") {
        // 最后是 assistant，必须通过队列注入
        const steering = this.steeringQueue.drain();
        if (steering.length > 0) {
            await this.runPromptMessages(steering, { skipInitialSteeringPoll: true });
            return;
        }
        // ...
    }

    // 最后是 user/toolResult，直接继续
    await this.runContinuation();
}
```

### 深入理解：prompt() vs continue() 与队列的关系

**核心区别**：

```
prompt()   → 发起新对话（用户提供新输入）
continue() → 继续现有对话（无新输入，或从队列取）
```

**continue() 的"继续"是什么意思？取决于最后一条消息的角色**：

```
情况 A: 最后是 user/toolResult
        → Agent 还没处理这条消息，直接调用 LLM
        → 不需要队列！

情况 B: 最后是 assistant
        → Agent 已经回复完，"停下来"了
        → 要继续，必须有新输入
        → 新输入从哪来？→ 队列！
```

**图解两种情况**：

```
┌─────────────────────────────────────────────────────────────────────┐
│                     情况 A：最后是 user/toolResult                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   messages: [user: "hello", assistant: "hi", user: "how are you?"]  │
│                                                                  ↑  │
│                                                         最后一条是 user │
│                                                                     │
│   continue() 做什么？                                                │
│   → Agent 还没回复这条消息                                            │
│   → 直接调用 LLM 处理                                                 │
│   → 不需要队列！                                                      │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                     情况 B：最后是 assistant                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   messages: [user: "hello", assistant: "hi, how can I help?"]       │
│                                                                  ↑  │
│                                                      最后一条是 assistant│
│                                                                     │
│   continue() 做什么？                                                │
│   → Agent 已经回复完，在"等待"新输入                                   │
│   → 不能直接调用 LLM（没有新输入）                                      │
│   → 检查队列有没有消息！                                               │
│                                                                     │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │ steeringQueue 有消息？                                       │   │
│   │                                                             │   │
│   │   YES → 取出消息，作为新的 user 输入继续                        │   │
│   │          await runPromptMessages(steering)                  │   │
│   │                                                             │   │
│   │   NO  → 没什么可继续的，可能抛错或返回                           │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**具体使用场景**：

场景 1 - prompt() + steering 队列：

```typescript
// 用户发起对话
agent.prompt("帮我分析这段代码");

// 运行过程中，用户想"引导"agent
agent.steeringQueue.enqueue({
    role: "user",
    content: "重点关注性能问题"
});

// Agent 在下一个 turn 会收到这个 steering 消息
```

场景 2 - continue() + steering 队列：

```typescript
// Agent 完成回复后
// messages: [user: "hello", assistant: "hi, how can I help?"]

// 外部代码加入 steering 消息
agent.steeringQueue.enqueue({
    role: "user",
    content: "Actually, tell me a joke"
});

// 调用 continue()
agent.continue();
// → 检测到最后是 assistant
// → 检查 steeringQueue，发现消息
// → 用队列消息继续运行
```

**流程对比**：

```
prompt() 流程：
┌────────────────────────────────────────────────────────────────┐
│                                                                │
│   用户输入 → agent-loop 开始                                    │
│                  │                                             │
│                  ▼                                             │
│            ┌──────────┐                                        │
│            │ LLM turn │                                        │
│            └────┬─────┘                                        │
│                 │                                              │
│                 ▼                                              │
│        steeringQueue 有消息？                                   │
│         /          \                                           │
│       YES          NO                                          │
│        │            │                                          │
│        ▼            ▼                                          │
│   注入 steering   工具调用？                                    │
│   继续 turn        /      \                                     │
│                   YES      NO                                  │
│                    │        │                                  │
│                    ▼        ▼                                  │
│               执行工具   followUpQueue 有消息？                  │
│                    │        /          \                        │
│                    │      YES          NO                        │
│                    │       │            │                        │
│                    │       ▼            ▼                        │
│                    │   注入 followUp   agent_end                  │
│                    │   继续 turn                                  │
│                    │                                             │
└────────────────────────────────────────────────────────────────┘

continue() 流程：
┌────────────────────────────────────────────────────────────────┐
│                                                                │
│   检查最后一条消息角色                                           │
│         /              \                                       │
│   assistant           user/toolResult                          │
│        │                     │                                 │
│        ▼                     ▼                                 │
│   steeringQueue?       直接 runContinuation()                   │
│     /      \                                                   │
│   有消息   无消息                                               │
│     │       │                                                  │
│     ▼       ▼                                                  │
│   继续    报错                                                  │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

**总结**：

| 方法 | 队列作用 | 使用场景 |
|------|---------|---------|
| `prompt()` | 队列在 agent-loop 内部自动处理 | 发起新对话 |
| `continue()` | 队列是"继续"的必要条件（当最后是 assistant 时） | 恢复已停止的对话 |

`continue()` 检查队列的本质是：**Agent 已经"停下来"了，要让它继续动，必须给它新的"燃料"（消息）**。

---

## 第六层：配置组装

### 核心问题

**问题**：Agent 如何把自身配置传递给 agent-loop？

### 配置组装函数

```typescript
createLoopConfig(options): AgentLoopConfig {
    return {
        // 模型配置
        model: this._state.model,
        reasoning: this._state.thinkingLevel === "off" ? undefined : this._state.thinkingLevel,
        
        // 传递给底层
        sessionId: this.sessionId,
        transport: this.transport,
        thinkingBudgets: this.thinkingBudgets,
        onPayload: this.onPayload,
        onResponse: this.onResponse,
        
        // 工具相关
        toolExecution: this.toolExecution,
        beforeToolCall: this.beforeToolCall,
        afterToolCall: this.afterToolCall,
        
        // 消息处理
        convertToLlm: this.convertToLlm,
        transformContext: this.transformContext,
        getApiKey: this.getApiKey,
        
        // 队列（函数形式）
        getSteeringMessages: async () => this.steeringQueue.drain(),
        getFollowUpMessages: async () => this.followUpQueue.drain(),
    };
}
```

### 为什么队列用函数形式？

因为 agent-loop 需要在运行过程中多次调用，而不是只在开始时获取一次。

### 深入理解：配置分类记忆

**口诀：模型传工具，队列用函数**

**四大类配置**：

```
┌────────────────┐  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐
│   1️⃣ 模型配置   │  │   2️⃣ 传递配置   │  │   3️⃣ 工具配置   │  │   4️⃣ 队列配置   │
│                │  │                │  │                │  │                │
│  model         │  │  sessionId     │  │  toolExecution │  │  getSteering   │
│  reasoning     │  │  transport     │  │  beforeTool    │  │  getFollowUp   │
│                │  │  onPayload     │  │  afterTool     │  │                │
│                │  │  onResponse    │  │                │  │                │
└────────────────┘  └────────────────┘  └────────────────┘  └────────────────┘
      ↓                    ↓                    ↓                    ↓
   "用什么模型"         "怎么通信"          "怎么执行工具"        "怎么注入消息"
```

**为什么队列用函数？**

```typescript
// ❌ 值形式：只在创建配置时调用一次
steeringMessages: this.steeringQueue.drain()
// agent-loop 无法感知队列变化

// ✅ 函数形式：agent-loop 可以多次调用
getSteeringMessages: async () => this.steeringQueue.drain()
// 每次调用都能拿到最新队列内容
```

**一图总览**：

```
Agent 内部状态
      │
      │  createLoopConfig()
      │
      ▼
┌─────────────────────────────────────────────────────┐
│                   AgentLoopConfig                   │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │
│  │ 模型        │  │ 传递        │  │ 工具        │  │
│  │ ────────    │  │ ────────    │  │ ────────    │  │
│  │ model       │  │ sessionId   │  │ toolExec    │  │
│  │ reasoning   │  │ transport   │  │ beforeTool  │  │
│  │             │  │ onPayload   │  │ afterTool   │  │
│  │ (直接值)    │  │ onResponse  │  │             │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  │
│                           │                         │
│                           ▼                         │
│                    ┌─────────────┐                  │
│                    │ 队列        │                  │
│                    │ ────────    │                  │
│                    │ getSteering │                  │
│                    │ getFollowUp │                  │
│                    │             │                  │
│                    │ (函数!)     │                  │
│                    └─────────────┘                  │
│                                                     │
└─────────────────────────────────────────────────────┘
      │
      │  传给
      ▼
┌─────────────┐
│ agent-loop  │
└─────────────┘
```

**快速记忆表**：

| 我是谁 | 我给什么 | 我怎么给 |
|--------|---------|---------|
| 模型配置 | 用什么模型 | 值 |
| 传递配置 | 怎么通信 | 引用 |
| 工具配置 | 怎么执行 | 钩子函数 |
| 队列配置 | 怎么注入 | **取值函数** |

---

## 第七层：上下文隔离

### 核心问题

**问题**：agent-loop 会修改 context（添加消息），如何防止污染 Agent 内部状态？

### 解决方案

创建快照：

```typescript
createContextSnapshot(): AgentContext {
    return {
        systemPrompt: this._state.systemPrompt,
        messages: this._state.messages.slice(),  // 拷贝！
        tools: this._state.tools.slice(),        // 拷贝！
    };
}
```

agent-loop 修改的是快照，不影响 Agent 内部。

### Agent 的 messages 怎么更新？

通过事件：

```typescript
processEvents(event) {
    switch (event.type) {
        case "message_end":
            this._state.messages.push(event.message);  // 通过事件更新
            break;
    }
}
```

### 单向数据流

```
Agent 内部状态 → 快照 → agent-loop（修改快照） → 事件 → Agent 内部状态
```

### 深入理解：为什么需要上下文隔离？

**常见疑惑**：是多个 agent-loop 同时运行，每个有自己的 context 吗？

**答案**：不是！Agent 同时只有一个 agent-loop 在运行（由 activeRun 控制）。

```
❌ 错误理解：
┌─────────────────────────────────────────────────────┐
│                       Agent                         │
│                                                     │
│    state.messages = [...]                          │
│                                                     │
│    ┌─────────────┐  ┌─────────────┐  ┌─────────────┐│
│    │ agent-loop │  │ agent-loop │  │ agent-loop ││
│    │   (运行中)  │  │   (运行中)  │  │   (运行中)  ││
│    └─────────────┘  └─────────────┘  └─────────────┘│
│          │               │               │          │
│          └───────────────┴───────────────┘          │
│                          │                          │
│                    都读取 state                      │
└─────────────────────────────────────────────────────┘

✅ 正确理解：
┌─────────────────────────────────────────────────────┐
│                       Agent                         │
│                                                     │
│    state.messages = [...]                          │
│                                                     │
│    activeRun = { ... }  ← 同时只有一个！             │
│                                                     │
│    ┌─────────────────┐                              │
│    │   agent-loop    │  ← 同一时间只有一个在运行      │
│    │    (运行中)      │                              │
│    └─────────────────┘                              │
│           │                                         │
│           ▼                                         │
│    context snapshot (拷贝)                          │
└─────────────────────────────────────────────────────┘
```

**那为什么要上下文隔离？**

不是为了"多个 agent-loop"，而是为了 **单向数据流**：

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │                      Agent                               │   │
│   │                                                          │   │
│   │   _state.messages = [msg1, msg2]                         │   │
│   │                                                          │   │
│   └──────────────────────────┬──────────────────────────────┘   │
│                              │                                  │
│                    (1) createContextSnapshot()                   │
│                              │                                  │
│                              ▼                                  │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │                  context snapshot                        │   │
│   │                                                          │   │
│   │   messages = [msg1, msg2]  ← 拷贝，不是引用！              │   │
│   │                                                          │   │
│   └──────────────────────────┬──────────────────────────────┘   │
│                              │                                  │
│                              │ 传递给                           │
│                              ▼                                  │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │                    agent-loop                            │   │
│   │                                                          │   │
│   │   执行过程中往 context 添加消息：                          │   │
│   │   context.messages.push(msg3)                             │   │
│   │   context.messages.push(msg4)                             │   │
│   │                                                          │   │
│   │   发出事件：                                               │   │
│   │   emit("message_end", { message: msg3 })                 │   │
│   │   emit("message_end", { message: msg4 })                 │   │
│   │                                                          │   │
│   └──────────────────────────┬──────────────────────────────┘   │
│                              │                                  │
│                    (2) 事件驱动更新                              │
│                              │                                  │
│                              ▼                                  │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │                      Agent                               │   │
│   │                                                          │   │
│   │   processEvents(event) {                                 │   │
│   │       if (event.type === "message_end") {                │   │
│   │           _state.messages.push(event.message);  ← 更新！  │   │
│   │       }                                                  │   │
│   │   }                                                      │   │
│   │                                                          │   │
│   │   // 现在 _state.messages = [msg1, msg2, msg3, msg4]     │   │
│   │                                                          │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**为什么不直接让 agent-loop 修改 Agent 状态？**

```
❌ 不好的设计：直接修改
┌─────────────────┐
│     Agent       │
│                 │
│  messages ◄─────┼───── agent-loop 直接修改
│                 │
└─────────────────┘

问题：
- 难以追踪状态变化
- 没有统一的事件通知
- UI 无法响应变化
- 难以调试

✅ 好的设计：单向数据流
┌─────────────────┐
│     Agent       │
│                 │
│  messages       │
│     ▲           │
│     │           │
│  processEvents  │◄──── 事件
│                 │
└─────────────────┘
        │
        │ snapshot (拷贝)
        ▼
┌─────────────────┐
│   agent-loop    │
│                 │
│  context        │
│  (可修改)        │
│                 │
└─────────────────┘

优点：
- 状态变化都有事件
- UI 可监听事件
- 易于调试和追踪
- 数据流向清晰
```

**总结**：

| 你的理解 | 实际情况 |
|---------|---------|
| 多个 agent-loop 同时运行 | ❌ 同时只有一个（由 activeRun 控制） |
| agent-loop 复用 Agent 状态 | ✅ 通过快照，不是直接引用 |
| agent-loop 可调整自己的 context | ✅ context 是拷贝，随便改 |
| 不影响 Agent | ✅ Agent 通过事件更新，不直接共享 |

**一句话**：上下文隔离是为了实现 **单向数据流**，而不是为了支持多个 agent-loop 同时运行。Agent 通过快照传递状态，agent-loop 修改快照，通过事件通知 Agent 更新状态。

### 补充：continue() 的完整状态处理

**问题**：continue() 时，systemPrompt、之前的 messages、sessionId、tools 怎么处理？

**答案**：全部继承，只是根据最后一条消息角色决定是否需要队列消息。

**两种路径的状态处理**：

**路径 A：最后是 user/toolResult → 直接继续**

```
_state.messages = [user: "hello", toolResult: "..."]
                                              ↑
                                         最后一条

continue() 做什么？
→ 创建快照（继承所有状态）
→ 直接调用 agent-loop
→ 不添加任何新消息
```

**路径 B：最后是 assistant → 需要队列消息**

```
_state.messages = [user: "hello", assistant: "hi, how can..."]
                                                       ↑
                                                  最后一条

continue() 做什么？
→ 检查 steeringQueue
→ 有消息：创建快照 + 添加队列消息
→ 无消息：报错 "Nothing to continue"
```

**状态处理总结表**：

| 状态 | prompt() | continue() | 处理方式 |
|------|----------|------------|---------|
| `systemPrompt` | 继承 | 继承 | 不变 |
| `messages` | 新输入 | 继承 + 可能加 steering | 通过快照 |
| `tools` | 继承 | 继承 | 不变 |
| `sessionId` | 继承 | 继承 | 不变 |
| `model` | 继承 | 继承 | 不变 |
| `steeringQueue` | agent-loop 内处理 | 作为启动消息 | 函数形式 |
| `followUpQueue` | agent-loop 内处理 | agent-loop 内处理 | 函数形式 |

**完整流程图**：

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           continue() 执行流程                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   ┌──────────────────────────────────────────────────────────────────┐  │
│   │  Agent._state                                                     │  │
│   │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐    │  │
│   │  │systemPrompt│ │ messages   │ │   tools    │ │ sessionId  │    │  │
│   │  │  (不变)    │ │ (继承)     │ │  (不变)    │ │  (不变)    │    │  │
│   │  └────────────┘ └────────────┘ └────────────┘ └────────────┘    │  │
│   └──────────────────────────────────────────────────────────────────┘  │
│          │                    │                    │                   │
│          │                    │                    │                   │
│          ▼                    ▼                    ▼                   │
│   ┌──────────────────────────────────────────────────────────────────┐  │
│   │  createContextSnapshot()                                          │  │
│   │                                                                   │  │
│   │  {                                                                │  │
│   │    systemPrompt: "...",        // 直接引用                        │  │
│   │    messages: [...].slice(),    // 拷贝                           │  │
│   │    tools: [...].slice(),       // 拷贝                           │  │
│   │  }                                                                │  │
│   │                                                                   │  │
│   │  + 如果有 steering：messages.push(...steering)                     │  │
│   │                                                                   │  │
│   └──────────────────────────────────────────────────────────────────┘  │
│                              │                                          │
│                              ▼                                          │
│   ┌──────────────────────────────────────────────────────────────────┐  │
│   │  agent-loop                                                       │  │
│   │                                                                   │  │
│   │  - 使用快照作为初始 context                                        │  │
│   │  - 运行过程中往 context 添加消息                                   │  │
│   │  - 通过事件通知 Agent 更新状态                                      │  │
│   │                                                                   │  │
│   └──────────────────────────────────────────────────────────────────┘  │
│                              │                                          │
│                              │ 事件                                     │
│                              ▼                                          │
│   ┌──────────────────────────────────────────────────────────────────┐  │
│   │  Agent.processEvents(event)                                       │  │
│   │                                                                   │  │
│   │  switch (event.type) {                                           │  │
│   │    case "message_end":                                            │  │
│   │      _state.messages.push(event.message);  // 更新内部状态        │  │
│   │      break;                                                       │  │
│   │  }                                                               │  │
│   │                                                                   │  │
│   └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**一句话总结**：`continue()` 继承所有现有状态，只是根据最后一条消息的角色决定：
- **最后是 user/toolResult**：直接用现有 messages 继续运行
- **最后是 assistant**：需要从 steeringQueue 取消息才能继续

---

## 第八层：输入处理

### 核心问题

**问题**：用户输入形式多样（字符串、单个消息、消息数组、带图片），如何统一？

### normalizePromptInput

```typescript
normalizePromptInput(input, images?): AgentMessage[] {
    if (Array.isArray(input)) return input;          // 已经是数组
    if (typeof input !== "string") return [input];   // 单个 AgentMessage
    // 字符串 → 构造用户消息
    const content = [{ type: "text", text: input }];
    if (images) content.push(...images);
    return [{ role: "user", content, timestamp: Date.now() }];
}
```

### prompt 的签名重载

```typescript
async prompt(message: AgentMessage | AgentMessage[]): Promise<void>;
async prompt(input: string, images?: ImageContent[]): Promise<void>;
```

支持：
- `agent.prompt("Hello")`
- `agent.prompt("What's this?", [image])`
- `agent.prompt({ role: "user", content: "Hello", ... })`
- `agent.prompt([message1, message2])`

---

## 第九层：错误处理

### 核心问题

**问题**：运行出错时，如何保证监听器看到完整生命周期？

### handleRunFailure

```typescript
handleRunFailure(error, aborted) {
    const failureMessage = {
        role: "assistant",
        stopReason: aborted ? "aborted" : "error",
        errorMessage: error.message,
        // ...
    };
    
    // 发出完整事件序列
    await processEvents({ type: "message_start", message: failureMessage });
    await processEvents({ type: "message_end", message: failureMessage });
    await processEvents({ type: "turn_end", ... });
    await processEvents({ type: "agent_end", ... });
}
```

### 为什么这样设计？

UI 可能依赖事件更新界面。如果只发出 `agent_end`：
- UI 不知道发生了什么错误
- 可能显示不正确的状态

完整序列保证：
- UI 显示一条"错误消息"
- UI 知道 agent 已停止
- 状态一致

---

## 第十层：辅助工具

### 默认值

```typescript
// 默认消息转换
defaultConvertToLlm(messages) {
    return messages.filter(m => 
        m.role === "user" || m.role === "assistant" || m.role === "toolResult"
    );
}

// 默认模型（出错时使用）
DEFAULT_MODEL = { id: "unknown", ... };

// 空用量（出错时使用）
EMPTY_USAGE = { input: 0, output: 0, ... };
```

### 为什么需要这些？

保证 Agent 在最小配置下也能安全运行，出错时能生成合理的失败消息。

---

## 整体架构图

```
┌────────────────────────────────────────────────────────────────────┐
│                         Agent 类                                    │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │                    核心职责                                   │ │
│  │  有状态的 LLM 调用编排器                                      │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                              │                                     │
│                              ▼                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │
│  │   状态管理   │  │   事件系统   │  │   运行控制   │            │
│  │              │  │              │  │              │            │
│  │ 持久状态     │  │ subscribe()  │  │ activeRun    │            │
│  │ 运行时状态   │  │ processEvents│  │ abort()      │            │
│  │ getter拷贝   │  │ 监听器顺序   │  │ waitForIdle  │            │
│  └──────────────┘  └──────────────┘  └──────────────┘            │
│         │                 │                 │                     │
│         └─────────────────┼─────────────────┘                     │
│                           │                                       │
│                           ▼                                       │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │                    消息队列                                   │ │
│  │                                                              │ │
│  │  Steering Queue（运行时干预）    Follow-up Queue（任务追加）  │ │
│  │  QueueMode: "all" / "one-at-a-time"                          │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                           │                                       │
│                           ▼                                       │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │                    配置组装                                   │ │
│  │                                                              │ │
│  │  createLoopConfig() → AgentLoopConfig                        │ │
│  │  createContextSnapshot() → AgentContext                      │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                           │                                       │
│                           ▼                                       │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │                    辅助工具                                   │ │
│  │                                                              │ │
│  │  normalizePromptInput()  defaultConvertToLlm()               │ │
│  │  DEFAULT_MODEL  EMPTY_USAGE  handleRunFailure()              │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼ 调用
                    ┌─────────────────┐
                    │   agent-loop    │
                    │   (执行层)      │
                    └─────────────────┘
                              │
                              ▼ 调用
                    ┌─────────────────┐
                    │    pi-ai        │
                    │  (LLM 通信层)   │
                    └─────────────────┘
```

---

## 关键设计决策总结

| 问题 | 解决方案 | 层级 |
|------|----------|------|
| 状态一致性 | getter/setter 拷贝数组 | 状态管理 |
| 并发控制 | activeRun + 检查 | 运行控制 |
| 中止传播 | AbortController + signal 传递 | 运行控制 |
| 运行时干预 | Steering Queue + drain 函数 | 消息队列 |
| 任务追加 | Follow-up Queue + 时机控制 | 消息队列 |
| 状态同步 | 事件驱动更新 | 事件系统 |
| 上下文隔离 | 快照拷贝 | 配置组装 |
| 错误恢复 | 完整事件序列 | 错误处理 |

---

## 数据流总结

### 正常流程

```
用户调用 prompt()
    │
    ├─→ 检查 activeRun（并发控制）
    │
    ├─→ normalizePromptInput（输入标准化）
    │
    ├─→ runWithLifecycle
    │       │
    │       ├─→ 创建 activeRun
    │       ├─→ 设置 isStreaming = true
    │       │
    │       ├─→ createContextSnapshot（上下文隔离）
    │       ├─→ createLoopConfig（配置组装）
    │       │
    │       ├─→ runAgentLoop（调用执行层）
    │       │       │
    │       │       ├─→ 发出事件
    │       │       │
    │       │       └─→ processEvents
    │       │               │
    │       │               ├─→ 更新内部状态
    │       │               └─→ 通知监听器
    │       │
    │       └─→ finishRun
    │               │
    │               ├─→ 设置 isStreaming = false
    │               ├─→ resolve()（通知 waitForIdle）
    │               └─→ 清除 activeRun
    │
    └─→ 返回
```

### 错误流程

```
runAgentLoop 抛出异常
    │
    └─→ handleRunFailure
            │
            ├─→ 创建失败消息
            ├─→ 发出完整事件序列
            │       message_start → message_end → turn_end → agent_end
            │
            └─→ finally: finishRun
```

### 队列注入流程

```
agent-loop 内层循环结束
    │
    ├─→ 检查 steeringQueue.drain()
    │       │
    │       ├─→ 有消息 → 注入，继续内层循环
    │       └─→ 无消息 → 继续
    │
    ├─→ 工具调用执行完毕
    │
    └─→ 检查 followUpQueue.drain()
            │
            ├─→ 有消息 → 注入，继续外层循环
            └─→ 无消息 → emit agent_end，退出
```