# L03: Agent Loop 底层机制

---

## 设计演进概述

AgentLoop 的设计不是一蹴而就的，而是从最简单的场景逐步演进，解决每个阶段遇到的问题。

**演进路径**：
```
早期（单次调用） → 中期（手动循环） → 现在（agentLoop）
```

---

## 第一阶段：早期 - 单次 LLM API 调用

### 1.1 最简单的场景

```typescript
// 最原始的调用
const response = await llm.chat({
    model: "claude-sonnet-4",
    messages: [{ role: "user", content: "Hello" }]
});

console.log(response.content);
```

**此时只有**：
- 单次请求
- 单次响应
- 无工具调用
- 无状态管理

### 1.2 面临的问题

**问题1：如何继续对话？**

```typescript
// 手动累积消息
const messages = [];
messages.push({ role: "user", content: "Hello" });
messages.push(response);

// 继续对话
messages.push({ role: "user", content: "How are you?" });
const response2 = await llm.chat({ messages });
```

**问题2：模型调用工具怎么办？**

```typescript
// 模型返回 toolCall
if (response.content.some(c => c.type === "toolCall")) {
    // 需要执行工具
    // 需要把结果返回给模型
    // 需要再次调用 LLM
    // ??? 陷入了困境
}
```

---

### 🎯 第一阶段总结

| 概念 | 早期状态 | 问题 |
|------|---------|------|
| **消息管理** | 手动累积 | 需要自己维护消息数组 |
| **工具调用** | 无处理 | 模型返回 toolCall 后怎么办？ |
| **循环机制** | 无 | 需要手动判断是否继续 |

---

## 第二阶段：中期 - 手动工具调用循环

### 2.1 循环机制的诞生

当模型返回 toolCall 时，需要循环处理：

```typescript
// 手动处理工具调用循环
let response;
const messages = [{ role: "user", content: "Hello" }];

while (true) {
    response = await llm.chat({ model, messages });
    
    const toolCalls = response.content.filter(c => c.type === "toolCall");
    if (toolCalls.length === 0) {
        break;  // 无工具调用，退出循环
    }
    
    // 执行工具
    const toolResults = await Promise.all(
        toolCalls.map(tc => executeTool(tc))
    );
    
    // 把结果返回给模型
    messages.push(response);
    messages.push({
        role: "toolResult",
        toolCallId: toolCalls[0].id,
        content: toolResults[0]
    });
    
    // 循环继续...
}
```

### 2.2 新问题涌现

这个手动循环方案暴露了更多问题：

#### 问题1：多个工具如何执行？

```typescript
// 模型可能同时返回多个 toolCall
const toolCalls = [
    { id: "1", name: "read_file", arguments: { path: "a.txt" } },
    { id: "2", name: "read_file", arguments: { path: "b.txt" } },
    { id: "3", name: "execute_shell", arguments: { cmd: "ls" } }
];

// 问题：
// - 并行执行？顺序执行？
// - 需要参数验证吗？
// - 需要在执行前做些什么吗？（权限检查？）
// - 需要在执行后做些什么吗？（审计？修改结果？）
```

#### 问题2：中途如何干预？

```typescript
// Agent 正在运行，用户突然输入新消息
while (true) {
    response = await llm.chat({ messages });
    // ...
}

// 问题：
// - 用户在 Agent 运行时输入怎么办？
// - 外部系统想中途注入指令怎么办？
// - 如何让 Agent "听"到新消息？
```

#### 问题3：错误如何处理？

```typescript
// 工具执行失败
const result = await executeTool(toolCall);
// result 可能是 Error

// 问题：
// - 如何通知外部发生了错误？
// - 如何让 Agent 知道工具失败了？
// - Agent 应该继续还是停止？
```

#### 问题4：如何知道 Agent 在做什么？

```typescript
while (true) {
    response = await llm.chat({ messages });
    // ...
}

// 问题：
// - 外部如何知道 Agent 正在执行哪个工具？
// - 如何显示进度？
// - 如何记录日志？
```

---

### 🎯 第二阶段总结

| 概念 | 中期状态 | 新问题 |
|------|---------|--------|
| **循环机制** | 手动循环 | 需要处理多种退出条件 |
| **工具执行** | 简单 Promise.all | 并行/顺序？验证？钩子？ |
| **中途干预** | 无机制 | 如何中途注入消息？ |
| **错误处理** | 无机制 | 失败怎么办？通知谁？ |
| **可观察性** | 无机制 | 外部如何知道进度？ |

---

## 第三阶段：现在 - 完整 agentLoop 设计

### 3.1 设计总览

针对第二阶段的5个问题，agentLoop 做出了系统性设计：

| 问题 | 设计决策 | 源码位置 |
|------|---------|---------|
| **工具执行模式** | parallel（默认）+ sequential（可选） | `executeToolCalls()` L373-388 |
| **工具生命周期** | 三阶段：prepare → execute → finalize | L562-626 → L628-663 → L665-708 |
| **中途干预** | steering（回合内）+ follow-up（回合后） | `getSteeringMessages()` / `getFollowUpMessages()` |
| **可观察性** | AgentEvent 事件流 | `EventStream<AgentEvent>` |
| **扩展性** | 8大Hook系统 | beforeToolCall / afterToolCall / ... |

---

### 3.2 核心架构设计

#### 设计决策：无状态事件生成器

```typescript
// agentLoop 返回 EventStream，不是 Promise
function agentLoop(
    prompts: AgentMessage[],
    context: AgentContext,
    config: AgentLoopConfig,
    signal?: AbortSignal,
): EventStream<AgentEvent, AgentMessage[]>
```

**为什么这样设计？**

```
┌────────────────────────────────────────────────────┐
│                    Agent 类                         │
│  职责：状态管理 + 队列管理 + subscribe               │
│                                                     │
│  ┌──────────────────────────────────────────────┐ │
│  │               agentLoop                       │ │
│  │  职责：纯粹事件生成，无状态                     │ │
│  │                                               │ │
│  │  输入: prompts + context + config             │ │
│  │  输出: EventStream                            │ │
│  └──────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────┘
```

**好处**：
- **可测试性**：无状态函数易于单元测试
- **可组合性**：事件流可被多个消费者处理
- **职责分离**：生成和处理分离

---

### 3.3 双层循环设计

#### 问题：为什么需要两层循环？

如果只有一层循环：

```typescript
// 单层循环的问题
while (hasToolCalls || hasSteering || hasFollowUp) {
    // steering 可能产生新的 toolCalls
    // toolCalls 可能产生新的 steering
    // followUp 可能产生新的 toolCalls
    // → 可能无限循环
    // → 无法区分"当前任务"和"后续任务"
}
```

#### 解决方案：双层循环

```typescript
// Outer Loop: 处理后续任务（follow-up）
while (true) {
    // Inner Loop: 处理当前任务（工具 + steering）
    while (hasMoreToolCalls || pendingMessages.length > 0) {
        // ...
    }
    
    // 检查 follow-up
    const followUpMessages = await config.getFollowUpMessages?.();
    if (followUpMessages.length > 0) {
        pendingMessages = followUpMessages;
        continue;  // 重新进入 Inner Loop
    }
    break;  // 无消息，退出
}
```

**语义分离**：
- **Inner Loop** = 当前回合的任务闭环
- **Outer Loop** = 多回合的任务调度

---

### 3.4 队列注入设计

#### 问题：中途如何干预？

```typescript
// Agent 正在运行，用户突然输入
while (true) {
    response = await llm.chat({ messages });
    // 用户输入怎么办？
}
```

#### 解决方案：两个队列

| 队列 | 注入时机 | 用途 | 源码位置 |
|------|---------|------|---------|
| **Steering** | 回合开始时（Inner） | 实时干预当前回合 | L182-189, L253 |
| **Follow-up** | 回合结束后（Outer） | 触发新回合 | L257-262 |

**典型场景**：
```
用户实时输入 → Steering Queue → 中途干预
后台任务完成 → Follow-up Queue → 触发继续
定时任务 → Follow-up Queue → 定期检查
```

---

### 3.5 边界分离设计

#### 问题：应用层想扩展消息类型

```typescript
// 应用层想定义自己的消息类型
type MyCustomMessage = {
    role: "custom";
    data: any;
};

// 但 LLM 只接受标准类型
// user, assistant, toolResult
```

#### 解决方案：AgentMessage ↔ Message 边界

```typescript
// 应用层：可扩展
type AgentMessage = Message | CustomAgentMessages[keyof CustomAgentMessages];

// LLM层：标准
type Message = UserMessage | AssistantMessage | ToolResultMessage;

// 转换边界：只在 LLM 调用时发生
async function streamAssistantResponse(...) {
    // Step 1: AgentMessage[] → AgentMessage[] (可选)
    let messages = await config.transformContext?.(context.messages);
    
    // Step 2: AgentMessage[] → Message[] (必须)
    const llmMessages = await config.convertToLlm(messages);
    
    // Step 3: 调用 LLM
    await streamSimple(model, llmContext, ...);
}
```

**好处**：
- 应用层可以扩展（自定义消息类型）
- LLM 层保持标准（兼容所有模型）
- 转换集中在一个地方（易于维护）

---

### 3.6 工具执行三阶段设计

#### 问题：工具执行需要哪些控制点？

```typescript
// 工具执行的生命周期
executeTool(toolCall)

// 需要：
// 1. 参数验证（防止无效参数）
// 2. 执行前检查（权限、审计）
// 3. 执行（实际工作）
// 4. 执行后处理（修改结果、审计）
```

#### 解决方案：三阶段

```typescript
// 阶段1: 预检（顺序）
const prepared = await prepareToolCall(...);
// → prepareArguments（兼容性 shim）
// → validateToolArguments（TypeBox 验证）
// → beforeToolCall（钩子，可阻止执行）

// 阶段2: 执行（并行）
const executed = await executePreparedToolCall(prepared, signal, emit);
// → tool.execute(...)
// → 发送 tool_execution_update 事件

// 阶段3: 结果处理（顺序）
const finalized = await finalizeExecutedToolCall(...);
// → afterToolCall（钩子，可修改结果）
// → 生成 ToolResultMessage
```

**为什么三阶段？**
- **安全性**：预检确保参数有效
- **效率**：多个工具并行执行
- **一致性**：结果顺序与模型期望一致

---

### 3.7 并行 vs 顺序执行设计

#### 问题：多个工具如何执行？

```typescript
const toolCalls = [
    { name: "read_file", ... },
    { name: "read_file", ... },
    { name: "execute_shell", ... }  // 危险操作
];

// 并行执行？
// → 效率高，但 execute_shell 可能在 read_file 之前执行
// → 可能不符合预期

// 顺序执行？
// → 安全，但效率低
```

#### 解决方案：默认并行，可选顺序

```typescript
// 判断逻辑
const hasSequentialToolCall = toolCalls.some(
    (tc) => context.tools?.find((t) => t.name === tc.name)?.executionMode === "sequential"
);

if (config.toolExecution === "sequential" || hasSequentialToolCall) {
    return executeToolCallsSequential(...);
}
return executeToolCallsParallel(...);
```

**设计意图**：
- 默认并行（效率优先）
- 工具可声明 sequential（安全控制）
- 配置可强制顺序（全局控制）

---

### 3.8 Hook 系统设计

#### 问题：如何提供扩展点？

```typescript
// 工具执行前想检查权限
// 工具执行后想审计结果
// 回合结束后想决定是否停止
```

#### 解决方案：8大Hook

| Hook | 时机 | 用途 | 源码位置 |
|------|------|------|---------|
| `beforeToolCall` | 工具执行前 | 检查权限、阻止执行 | L581-605 |
| `afterToolCall` | 工具执行后 | 修改结果、审计 | L676-700 |
| `shouldStopAfterTurn` | 回合结束后 | 决定是否停止 | L241-251 |
| `prepareNextTurn` | 回合结束后 | 调整下回合参数 | L226-239 |
| `getSteeringMessages` | 回合开始时 | 获取实时干预消息 | L167, L253 |
| `getFollowUpMessages` | 外层循环检查 | 获取后续任务消息 | L257 |
| `transformContext` | LLM调用前 | 变换消息数组 | L284-286 |
| `convertToLlm` | LLM调用边界 | 类型转换 | L289 |
| `getApiKey` | LLM调用前 | OAuth token 刷新 | L301-302 |

**设计哲学**：
- 通过 Hook 提供扩展点，而非继承
- 组合优于继承

---

### 3.9 事件流设计

#### 问题：外部如何知道 Agent 在做什么？

```typescript
while (true) {
    response = await llm.chat({ messages });
    // 外部如何知道：
    // - 正在执行哪个工具？
    // - 工具执行进度？
    // - 是否出错？
}
```

#### 解决方案：AgentEvent 事件流

```typescript
// 10种事件类型
type AgentEvent =
    | { type: "agent_start" }
    | { type: "agent_end"; messages: AgentMessage[] }
    | { type: "turn_start" }
    | { type: "turn_end"; message: AssistantMessage; toolResults: ToolResultMessage[] }
    | { type: "message_start"; message: AgentMessage }
    | { type: "message_update"; assistantMessageEvent; message }
    | { type: "message_end"; message: AgentMessage }
    | { type: "tool_execution_start"; toolCallId; toolName; args }
    | { type: "tool_execution_update"; toolCallId; partialResult }
    | { type: "tool_execution_end"; toolCallId; result; isError }
```

**消费方式**：
```typescript
for await (const event of agentLoop(...)) {
    switch (event.type) {
        case "tool_execution_start":
            console.log(`开始执行: ${event.toolName}`);
            break;
        case "tool_execution_end":
            console.log(`执行完成`);
            break;
    }
}
```

---

### 3.10 终止机制设计

#### 问题：何时停止 Agent？

```typescript
// 可能的停止条件：
// 1. 工具返回 terminate（停止后续 LLM 调用）
// 2. 回合结束后 shouldStopAfterTurn 返回 true
// 3. LLM 调用出错
// 4. 用户取消（AbortSignal）
```

#### 解决方案：多层终止机制

```typescript
// 层级1: 工具级 terminate
// 所有工具都返回 terminate: true 时才生效
function shouldTerminateToolBatch(finalizedCalls) {
    return finalizedCalls.length > 0 && 
           finalizedCalls.every(f => f.result.terminate === true);
}

// 层级2: 回合级 shouldStopAfterTurn
if (await config.shouldStopAfterTurn?.({ message, toolResults, ... })) {
    await emit({ type: "agent_end", messages });
    return;
}

// 层级3: 错误/取消
if (message.stopReason === "error" || message.stopReason === "aborted") {
    await emit({ type: "agent_end", messages });
    return;
}
```

**设计意图**：
- terminate 是批级别的（所有工具同意）
- shouldStopAfterTurn 是回合级别的
- error/aborted 是立即终止

---

### 🎯 第三阶段总结

| 概念 | 现在状态 | 设计决策 |
|------|---------|---------|
| **核心架构** | 无状态事件生成器 | 状态交给上层 Agent 类 |
| **循环机制** | 双层循环（inner + outer） | 职责分离：当前 vs 后续 |
| **工具执行** | 三阶段 + 并行/顺序 | 安全 → 效率 → 一致性 |
| **消息类型** | AgentMessage ↔ Message 边界 | 应用层扩展 + LLM标准 |
| **中途干预** | steering + follow-up 队列 | 回合内 + 回合后 |
| **可观察性** | AgentEvent 事件流 | 生成器模式 |
| **扩展性** | 8大Hook | 组合优于继承 |
| **终止机制** | 三层终止 | 工具级 → 回合级 → 立即 |

---

## 演进全景图

```
早期
├─ 单次 LLM 调用
├─ 手动消息管理
├─ 问题：如何继续对话？工具调用怎么办？
│
├─→ 中期
│   ├─ 手动循环处理 toolCalls
│   ├─ 问题：并行/顺序？中途干预？错误处理？可观察性？
│   │
│   └─→ 现在（agentLoop）
│       ├─ 双层循环（职责分离）
│       ├─ 三阶段工具执行（安全→效率→一致性）
│       ├─ 队列注入（steering + follow-up）
│       ├─ 边界分离（AgentMessage ↔ Message）
│       ├─ 事件流（可观察性）
│       ├─ Hook系统（扩展性）
│       └─ 三层终止机制
```

---

## 📝 后续深入大纲

读者可以按以下大纲深入源码细节：

### 细节1：双层循环的完整流程

- **源码位置**：`agent-loop.ts` L155-269

**深入要点**：
- [ ] Inner Loop 的详细步骤（L174-254）
- [ ] Outer Loop 的详细步骤（L169-266）
- [ ] firstTurn 的处理逻辑（L175-179）
- [ ] steering 注入时机（L182-189, L253）
- [ ] follow-up 注入时机（L257-262）
- [ ] 循环退出条件分析

---

### 细节2：LLM 调用边界

- **源码位置**：`agent-loop.ts` L275-368

**深入要点**：
- [ ] streamAssistantResponse 的三步转换
- [ ] transformContext 的作用和时机
- [ ] convertToLlm 的契约要求（不能抛异常）
- [ ] getApiKey 的 OAuth token 刷新机制（L301-302）
- [ ] 流式事件处理（AssistantMessageEvent）
- [ ] partialMessage 的实时更新机制

---

### 细节3：工具执行三阶段

- **源码位置**：`agent-loop.ts` L562-708

**深入要点**：
- [ ] prepareToolCall 预检阶段（L562-626）
  - prepareArguments 兼容性 shim
  - validateToolArguments TypeBox 验证
  - beforeToolCall 钩子（可阻止）
- [ ] executePreparedToolCall 执行阶段（L628-663）
  - execute 的四参数
  - onUpdate 进度回调
  - 错误处理
- [ ] finalizeExecutedToolCall 结果阶段（L665-708）
  - afterToolCall 钩子（可修改结果）
  - 字段级替换语义

---

### 细节4：并行 vs 顺序执行

- **源码位置**：`agent-loop.ts` L373-516

**深入要点**：
- [ ] 判断逻辑（L381-387）
- [ ] executeToolCallsParallel（L451-516）
  - 预检阶段顺序
  - 执行阶段并行（Promise.all）
  - 结果阶段顺序
  - finalizedCalls 的 thunk 设计
- [ ] executeToolCallsSequential（L395-449）
  - 完全顺序
  - 每个工具完整生命周期
- [ ] terminate 批级别终止（L544-546）

---

### 细节5：事件系统

- **源码位置**：`types.ts` L403-418 + `agent-loop.ts`

**深入要点**：
- [ ] AgentEvent 的10种类型定义
- [ ] Discriminated Union 设计好处
- [ ] EventStream 的设计（L145-150）
- [ ] emit 函数的调用时机
- [ ] 消费者如何处理事件流

---

### 细节6：终止机制

- **源码位置**：`agent-loop.ts` 多处

**深入要点**：
- [ ] terminate 批级别终止（L544-546）
- [ ] shouldStopAfterTurn 回合级终止（L241-251）
- [ ] error / aborted 立即终止（L196-200）
- [ ] 三层终止的优先级和触发条件

---

### 细节7：契约式编程

- **源码位置**：多个契约函数

**深入要点**：
- [ ] convertToLlm 契约（不能抛异常）
- [ ] transformContext 契约
- [ ] 为什么不做防御性检查
- [ ] 调用者的责任边界

---

### 细节8：入口函数分析

- **源码位置**：`agent-loop.ts` L31-143

**深入要点**：
- [ ] agentLoop vs agentLoopContinue 的区别
- [ ] agentLoopContinue 的前提条件（最后消息必须是非 assistant）
- [ ] runAgentLoop vs runAgentLoopContinue
- [ ] EventStream 的创建和结束

---

## 源文件映射

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
| AgentEvent 类型 | `types.ts` | L403-418 |

---

## 下一步

→ [L04: Agent 类（包装层）](./04-agent-class)