# 事件顺序详解

---

## 一、问题本质：并发执行的顺序不确定性

```
┌──────────────────────────────────────────────────────────────┐
│  场景：LLM 同时调用 3 个工具                                   │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  assistantMessage.content = [                                │
│    { type: "toolCall", id: "tc0", name: "readFile" },        │
│    { type: "toolCall", id: "tc1", name: "searchWeb" },       │
│    { type: "toolCall", id: "tc2", name: "executeCode" },     │
│  ]                                                           │
│                                                              │
│  原始顺序：tc0 → tc1 → tc2                                    │
│                                                              │
│  并行执行：                                                   │
│  ├─ readFile()     → 执行 5 秒                                │
│  ├─ searchWeb()    → 执行 2 秒                                │
│  ├─ executeCode()  → 执行 8 秒                                │
│                                                              │
│  完成顺序：                                                   │
│  ├─ tc1 先完成（2秒）                                         │
│  ├─ tc0 后完成（5秒）                                         │
│  ├─ tc2 最后完成（8秒）                                       │
│                                                              │
│  问题：                                                      │
│  ├─ 原始顺序：tc0, tc1, tc2                                   │
│  ├─ 完成顺序：tc1, tc0, tc2                                   │
│  ├─ 两种顺序不一致                                            │
│  ├─ 用哪种顺序发送事件？                                      │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 二、两种顺序需求

### 需求 1：实时反馈（完成顺序）

```
┌──────────────────────────────────────────────────────────────┐
│  用户视角：想知道哪个工具先完成了                               │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  用户等待 8 秒期间：                                           │
│                                                              │
│  完成顺序事件流：                                              │
│                                                              │
│  时间 0s:                                                    │
│  ├─ tool_execution_start(tc0)                                │
│  ├─ tool_execution_start(tc1)                                │
│  ├─ tool_execution_start(tc2)                                │
│  ├─ UI 显示: "3 个工具正在执行..."                             │
│                                                              │
│  时间 2s:                                                    │
│  ├─ tool_execution_end(tc1)                                  │
│  ├─ UI 显示: "searchWeb 完成 ✓"                               │
│  ├─ 用户知道：至少有一个完成了                                 │
│                                                              │
│  时间 5s:                                                    │
│  ├─ tool_execution_end(tc0)                                  │
│  ├─ UI 显示: "readFile 完成 ✓"                                │
│  ├─ 用户知道：还剩一个                                         │
│                                                              │
│  时间 8s:                                                    │
│  ├─ tool_execution_end(tc2)                                  │
│  ├─ UI 显示: "executeCode 完成 ✓"                             │
│  ├─ 用户知道：全部完成                                         │
│                                                              │
│  用户体验：                                                   │
│  ├─ 看到实时进度                                              │
│  ├─ 知道哪个先完成                                            │
│  ├─ 知道还剩多少                                              │
│  ├─ 焦虑感降低                                                │
│                                                              │
│  如果按原始顺序：                                              │
│  ├─ 2s 完成 tc1，但不发送事件                                 │
│  ├─ 等到 8s 才发送所有事件                                    │
│  ├─ 用户等待期间看不到任何反馈                                 │
│  ├─ 不知道是否卡死                                            │
│  ├─ 焦虑感增加                                                │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 需求 2：对话连贯（原始顺序）

```
┌──────────────────────────────────────────────────────────────┐
│  LLM 视角：需要按原始顺序理解工具结果                           │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  对话历史：                                                   │
│                                                              │
│  [0] user: "帮我分析这个项目的依赖"                           │
│  [1] assistant: "好的，我来：                                 │
│        1. readFile(package.json)                             │
│        2. searchWeb(最新版本)                                 │
│        3. executeCode(分析依赖)"                             │
│  [2] toolResult(tc0): "package.json 内容..."                 │
│  [3] toolResult(tc1): "搜索结果..."                           │
│  [4] toolResult(tc2): "分析结果..."                           │
│                                                              │
│  LLM 读取：                                                   │
│  ├─ 看到 assistant 的规划顺序                                 │
│  ├─ 看到 toolResult 按规划顺序返回                            │
│  ├─ 可以按顺序理解                                            │
│  ├─ 可以引用 "第 1 步的结果"                                  │
│                                                              │
│  如果按完成顺序：                                              │
│  [2] toolResult(tc1): "搜索结果..."                           │
│  [3] toolResult(tc0): "package.json 内容..."                 │
│  [4] toolResult(tc2): "分析结果..."                           │
│                                                              │
│  LLM 困惑：                                                   │
│  ├─ assistant 说 "先 readFile"                               │
│  ├─ 但第一个结果是 searchWeb                                  │
│  ├─ 顺序不匹配                                                │
│  ├─ 可能理解错误                                              │
│  ├─ 可能引用错误                                              │
│                                                              │
│  UI 渲染：                                                   │
│  ├─ assistant 说 "1. readFile, 2. searchWeb, 3. executeCode" │
│  ├─ 结果应该对应显示                                          │
│  ├─ 结果[0] 对应步骤 1                                        │
│  ├─ 结果[1] 对应步骤 2                                        │
│  ├─ 结果[2] 对应步骤 3                                        │
│  ├─ 用户可以对照理解                                          │
│                                                              │
│  如果按完成顺序：                                              │
│  ├─ 结果[0] 是步骤 2                                          │
│  ├─ 结果[1] 是步骤 1                                          │
│  ├─ 用户对照困难                                              │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 三、两种顺序的具体含义

```
┌──────────────────────────────────────────────────────────────┐
│  事件类型                    │  顺序需求      │  用途           │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  tool_execution_start        │  原始顺序      │  开始执行       │
│  ├─ 准备阶段串行              │               │  按顺序启动     │
│  ├─ 按代码顺序 for 循环       │               │               │
│                                                              │
│  tool_execution_update       │  实时发送      │  流式更新       │
│  ├─ 工具调用时立即发送        │               │  不关心顺序     │
│  ├─ 不阻塞执行               │               │               │
│                                                              │
│  tool_execution_end          │  完成顺序      │  进度反馈       │
│  ├─ 完成时立即发送            │  （实时性）    │  用户知道进度   │
│  ├─ 不等待其他工具            │               │               │
│                                                              │
│  message_start/end           │  原始顺序      │  对话历史       │
│  (toolResult 消息)           │  （连贯性）    │  LLM 理解       │
│  ├─ Promise.all 完成后        │               │  UI 渲染       │
│  ├─ 按数组顺序遍历            │               │               │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 四、代码实现机制

### Parallel 模式完整流程

```typescript
// executeToolCallsParallel 核心逻辑

async function executeToolCallsParallel(
  currentContext,
  assistantMessage,
  toolCalls,
  config,
  signal,
  emit
) {
  // ┌─────────────────────────────────────────────┐
  // │  Step 1: 准备阶段（串行，按原始顺序）          │
  // └─────────────────────────────────────────────┘
  
  const finalizedCalls: FinalizedToolCallEntry[] = []
  
  // for 循环 = 原始顺序
  for (const toolCall of toolCalls) {
    // 发送 start 事件（原始顺序）
    await emit({
      type: "tool_execution_start",
      toolCallId: toolCall.id,
      toolName: toolCall.name,
      args: toolCall.arguments
    })
    
    // 准备（串行）
    const preparation = await prepareToolCall(...)
    
    // 立即结果 → 直接加入数组
    if (preparation.kind === "immediate") {
      const finalized = { toolCall, result, isError }
      // 发送 end 事件（立即，不等待）
      await emitToolExecutionEnd(finalized, emit)
      finalizedCalls.push(finalized)
      if (signal?.aborted) break
      continue
    }
    
    // 需执行 → 加入异步函数
    // 注意：这里 push 的是函数，不是结果
    finalizedCalls.push(async () => {
      // ┌─────────────────────────────────────────────┐
      // │  Step 2: 执行阶段（并行）                     │
      // └─────────────────────────────────────────────┘
      
      const executed = await executePreparedToolCall(...)
      const finalized = await finalizeExecutedToolCall(...)
      
      // ┌─────────────────────────────────────────────┐
      // │  Step 3: 发送 end 事件（完成顺序）            │
      // └─────────────────────────────────────────────┘
      
      // 完成时立即发送，不等待其他工具
      await emitToolExecutionEnd(finalized, emit)
      
      return finalized
    })
    
    if (signal?.aborted) break
  }
  
  // ┌─────────────────────────────────────────────┐
  // │  Step 4: 并行执行（Promise.all）              │
  // └─────────────────────────────────────────────┘
  
  // Promise.all：
  // ├─ 并行执行所有异步函数
  // ├─ 返回数组按原数组顺序排列
  // ├─ 即使 tc1 先完成，结果[1] = tc1 的结果
  const orderedFinalizedCalls = await Promise.all(
    finalizedCalls.map(entry => 
      typeof entry === "function" ? entry() : Promise.resolve(entry)
    )
  )
  
  // ┌─────────────────────────────────────────────┐
  // │  Step 5: 发送消息事件（原始顺序）              │
  // └─────────────────────────────────────────────┘
  
  const messages: ToolResultMessage[] = []
  
  // for 循环 = 数组顺序 = 原始顺序
  for (const finalized of orderedFinalizedCalls) {
    // 创建 toolResult 消息
    const toolResultMessage = createToolResultMessage(finalized)
    
    // 发送 message 事件（原始顺序）
    await emitToolResultMessage(toolResultMessage, emit)
    
    messages.push(toolResultMessage)
  }
  
  return {
    messages,
    terminate: shouldTerminateToolBatch(orderedFinalizedCalls)
  }
}
```

### 关键点解析

```
┌──────────────────────────────────────────────────────────────┐
│  finalizedCalls 数组的设计                                     │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  数组结构：                                                   │
│                                                              │
│  finalizedCalls = [                                          │
│    async () => { ... tc0 执行逻辑 ... },    // index 0       │
│    async () => { ... tc1 执行逻辑 ... },    // index 1       │
│    async () => { ... tc2 执行逻辑 ... },    // index 2       │
│  ]                                                           │
│                                                              │
│  数组顺序 = 原始顺序                                          │
│  ├─ finalizedCalls[0] 对应 tc0                               │
│  ├─ finalizedCalls[1] 对应 tc1                               │
│  ├─ finalizedCalls[2] 对应 tc2                               │
│                                                              │
│  Promise.all 行为：                                           │
│                                                              │
│  const results = await Promise.all(                          │
│    finalizedCalls.map(fn => fn())                            │
│  )                                                           │
│                                                              │
│  ├─ 并行执行所有 fn()                                         │
│  ├─ tc1 的 fn() 先返回                                       │
│  ├─ tc0 的 fn() 后返回                                       │
│  ├─ tc2 的 fn() 最后返回                                     │
│                                                              │
│  但 results 数组保持原顺序：                                  │
│  ├─ results[0] = tc0 的结果                                  │
│  ├─ results[1] = tc1 的结果                                  │
│  ├─ results[2] = tc2 的结果                                  │
│                                                              │
│  原因：Promise.all 返回数组顺序与输入数组一致                  │
│  ├─ 输入数组 [fn0, fn1, fn2]                                 │
│  ├─ 输出数组 [result0, result1, result2]                     │
│  ├─ 即使 fn1 先完成                                          │
│  ├─ result1 仍在 index 1                                     │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 五、时间线示例

```
时间线：Parallel 模式下的事件发送

时间 0s:
├─ for 循环开始
├─ emit tool_execution_start(tc0)  ← 原始顺序
├─ prepareToolCall(tc0)
├─ finalizedCalls.push(async () => tc0)
├─ emit tool_execution_start(tc1)  ← 原始顺序
├─ prepareToolCall(tc1)
├─ finalizedCalls.push(async () => tc1)
├─ emit tool_execution_start(tc2)  ← 原始顺序
├─ prepareToolCall(tc2)
├─ finalizedCalls.push(async () => tc2)
├─ for 循环结束
├─ Promise.all 开始

时间 1s:
├─ tc1 执行中...

时间 2s:
├─ tc1 完成
├─ emit tool_execution_end(tc1)    ← 完成顺序（先完成先发送）
├─ 返回 finalized(tc1)
├─ tc0 执行中...
├─ tc2 执行中...

时间 5s:
├─ tc0 完成
├─ emit tool_execution_end(tc0)    ← 完成顺序（先完成先发送）
├─ 返回 finalized(tc0)
├─ tc2 执行中...

时间 8s:
├─ tc2 完成
├─ emit tool_execution_end(tc2)    ← 完成顺序（先完成先发送）
├─ 返回 finalized(tc2)
├─ Promise.all 结束

时间 8s+:
├─ orderedFinalizedCalls = [tc0结果, tc1结果, tc2结果]  ← 原始顺序
├─ for 循环遍历（按数组顺序）
├─ emit message_start(tc0结果)     ← 原始顺序
├─ emit message_end(tc0结果)       ← 原始顺序
├─ emit message_start(tc1结果)     ← 原始顺序
├─ emit message_end(tc1结果)       ← 原始顺序
├─ emit message_start(tc2结果)     ← 原始顺序
├─ emit message_end(tc2结果)       ← 原始顺序
```

---

## 六、对比 Sequential 模式

```
┌──────────────────────────────────────────────────────────────┐
│  Sequential 模式：顺序天然一致                                  │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  时间线：                                                     │
│                                                              │
│  时间 0s:                                                    │
│  ├─ emit tool_execution_start(tc0)                           │
│  ├─ execute tc0                                              │
│                                                              │
│  时间 5s:                                                    │
│  ├─ emit tool_execution_end(tc0)                             │
│  ├─ emit message_start/end(tc0)                              │
│  ├─ emit tool_execution_start(tc1)                           │
│  ├─ execute tc1                                              │
│                                                              │
│  时间 7s:                                                    │
│  ├─ emit tool_execution_end(tc1)                             │
│  ├─ emit message_start/end(tc1)                              │
│  ├─ emit tool_execution_start(tc2)                           │
│  ├─ execute tc2                                              │
│                                                              │
│  时间 15s:                                                   │
│  ├─ emit tool_execution_end(tc2)                             │
│  ├─ emit message_start/end(tc2)                              │
│                                                              │
│  特点：                                                      │
│  ├─ 串行执行                                                  │
│  ├─ 完成顺序 = 原始顺序                                       │
│  ├─ 无顺序冲突                                                │
│  ├─ 但总时间更长（5+2+8=15s）                                 │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 七、设计本质：分离两种需求

```
┌──────────────────────────────────────────────────────────────┐
│  设计思路：不同用途需要不同顺序                                 │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  需求分离：                                                   │
│                                                              │
│  ├─ 进度反馈需求                                              │
│  │   ├─ 用户想知道实时状态                                    │
│  │   ├─ 哪个先完成？                                          │
│  │   ├─ 还剩多少？                                            │
│  │   ├─ 用完成顺序                                            │
│  │   ├─ tool_execution_end                                   │
│  │   ├─ 实时性优先                                            │
│  │                                                           │
│  ├─ 对话连贯需求                                              │
│  │   ├─ LLM 需要按顺序理解                                    │
│  │   ├─ assistant 的规划顺序                                  │
│  │   ├─ toolResult 对应步骤                                   │
│  │   ├─ 用原始顺序                                            │
│  │   ├─ message_start/end                                    │
│  │   ├─ 连贯性优先                                            │
│  │                                                           │
│  为什么不能统一？                                              │
│  │                                                           │
│  ├─ 如果统一用完成顺序                                        │
│  │   ├─ 对话历史顺序错乱                                      │
│  │   ├─ LLM 理解困难                                         │
│  │   ├─ UI 渲染困难                                          │
│  │                                                           │
│  ├─ 如果统一用原始顺序                                        │
│  │   ├─ 进度反馈延迟                                          │
│  │   ├─ 用户等待无反馈                                        │
│  │   ├─ 焦虑感增加                                            │
│  │                                                           │
│  ├─ 分离是最好的选择                                          │
│  │   ├─ 不同事件满足不同需求                                  │
│  │   ├─ tool_execution_end → 进度                            │
│  │   ├─ message_start/end → 对话                             │
│  │   ├─ 各取所需                                              │
│  │                                                           │
└──────────────────────────────────────────────────────────────┘
```

---

## 八、实现技巧：Promise.all 的特性

```
┌──────────────────────────────────────────────────────────────┐
│  Promise.all 的关键特性                                        │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  特性：返回数组顺序与输入数组一致                               │
│                                                              │
│  示例：                                                      │
│                                                              │
│  const promises = [                                          │
│    new Promise(resolve => setTimeout(() => resolve('A'), 3000)),│
│    new Promise(resolve => setTimeout(() => resolve('B'), 1000)),│
│    new Promise(resolve => setTimeout(() => resolve('C'), 2000)),│
│  ]                                                           │
│                                                              │
│  完成顺序：B(1s) → C(2s) → A(3s)                              │
│                                                              │
│  const results = await Promise.all(promises)                 │
│                                                              │
│  results = ['A', 'B', 'C']                                   │
│  ├─ results[0] = 'A'                                         │
│  ├─ results[1] = 'B'                                         │
│  ├─ results[2] = 'C'                                         │
│                                                              │
│  ├─ 虽然 'B' 先完成                                          │
│  ├─ 但 'B' 仍在 index 1                                      │
│  ├─ 顺序与 promises 数组一致                                  │
│                                                              │
│  利用这个特性：                                                │
│  │                                                           │
│  ├─ finalizedCalls 数组按原始顺序排列                         │
│  │   ├─ [tc0函数, tc1函数, tc2函数]                          │
│  │                                                           │
│  ├─ Promise.all 并行执行                                     │
│  │   ├─ tc1 先完成                                           │
│  │   ├─ 但在内部立即 emit tool_execution_end                 │
│  │   ├─ 用户看到完成顺序                                      │
│  │                                                           │
│  ├─ Promise.all 返回保持原始顺序                              │
│  │   ├─ [tc0结果, tc1结果, tc2结果]                          │
│  │   ├─ 遍历发送 message_start/end                           │
│  │   ├─ LLM 看到原始顺序                                      │
│  │                                                           │
└──────────────────────────────────────────────────────────────┘
```

---

## 九、事件顺序完整流程图

```
┌──────────────────────────────────────────────────────────────┐
│  Parallel 模式事件发送完整流程                                  │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  assistantMessage (原始顺序)                                  │
│  ├─ toolCall[tc0]                                            │
│  ├─ toolCall[tc1]                                            │
│  ├─ toolCall[tc2]                                            │
│                                                              │
│  ↓                                                           │
│                                                              │
│  for 循环（串行，原始顺序）                                    │
│  ├─ emit tool_execution_start(tc0)  ──────────────────┐      │
│  ├─ prepare(tc0)                                       │      │
│  ├─ finalizedCalls.push(async () => tc0)               │      │
│  ├─ emit tool_execution_start(tc1)  ──────────────────┤ 原始 │
│  ├─ prepare(tc1)                                       │ 顺序 │
│  ├─ finalizedCalls.push(async () => tc1)               │      │
│  ├─ emit tool_execution_start(tc2)  ──────────────────┤      │
│  ├─ prepare(tc2)                                       │      │
│  ├─ finalizedCalls.push(async () => tc2)               │      │
│                                                        │      │
│  ↓                                                     │      │
│                                                        │      │
│  Promise.all（并行）                                   │      │
│  ├─ async() for tc0 开始执行                           │      │
│  ├─ async() for tc1 开始执行                           │      │
│  ├─ async() for tc2 开始执行                           │      │
│                                                        │      │
│  ├─ tc1 完成（2s）                                     │      │
│  │  ├─ emit tool_execution_end(tc1) ────────────────┐│完成 │
│  │  ├─ return finalized(tc1)                        ││顺序 │
│  │                                                   ││     │
│  ├─ tc0 完成（5s）                                   ││     │
│  │  ├─ emit tool_execution_end(tc0) ────────────────┤│     │
│  │  ├─ return finalized(tc0)                        ││     │
│  │                                                   ││     │
│  ├─ tc2 完成（8s）                                   ││     │
│  │  ├─ emit tool_execution_end(tc2) ────────────────┘│     │
│  │  ├─ return finalized(tc2)                        │      │
│  │                                                   │      │
│  ├─ Promise.all 返回                                  │      │
│  │  orderedFinalizedCalls = [tc0, tc1, tc2] ─────────┘ 原始 │
│  │                                                       顺序│
│  ↓                                                          │
│                                                             │
│  for 循环（串行，数组顺序 = 原始顺序）                        │
│  ├─ emit message_start/end(tc0结果) ──────────────────┐ 原始│
│  ├─ emit message_start/end(tc1结果) ──────────────────┤ 顺序│
│  ├─ emit message_start/end(tc2结果) ──────────────────┘    │
│                                                            │
│  messages = [tc0结果, tc1结果, tc2结果] ────────────────── 原始顺序│
│                                                            │
└──────────────────────────────────────────────────────────────┘
```

---

## 十、一句话总结

```
问题本质：
  并发执行 → 完成顺序 ≠ 原始顺序 → 顺序冲突

两种需求：
  ├─ 进度反馈：完成顺序（实时性）
  └─ 对话连贯：原始顺序（连贯性）

解决方法：
  ├─ tool_execution_end：完成时立即发送（完成顺序）
  ├─ message_start/end：Promise.all 后遍历发送（原始顺序）
  ├─ 利用 Promise.all 返回数组保持输入顺序的特性

设计本质：
  ├─ 分离两种需求
  ├─ 不同事件满足不同用途
  ├─ 不统一 → 各取所需
```