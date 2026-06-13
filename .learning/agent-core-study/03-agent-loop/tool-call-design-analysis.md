# AgentLoop 工具调用的设计问题与解决方案

---

## 一、开发者关注的核心问题

```
┌─────────────────────────────────────────────────────────┐
│  1. 并发控制        - 工具间是否有依赖？如何执行？          │
│  2. 参数验证        - LLM 返回的参数可靠吗？                │
│  3. 中断取消        - 长任务如何优雅停止？                  │
│  4. 错误处理        - 工具失败会不会崩溃整个流程？          │
│  5. 流式反馈        - 用户等待时能看到进度吗？              │
│  6. 执行拦截        - 危险操作需要确认吗？                  │
│  7. 结果修改        - 工具返回能被后处理吗？                │
│  8. 终止信号        - 工具能主动告诉 loop 停吗？            │
│  9. 事件顺序        - 并行执行如何保证顺序正确？            │
│ 10. 上下文管理      - 结果如何正确加入对话？                │
└─────────────────────────────────────────────────────────┘
```

---

## 二、问题 1：并发控制

### 问题场景

```
LLM 同时调用多个工具：
  readFile("secret.txt")     → 需要读取
  writeFile("secret.txt")    → 需要写入

如果并行执行 → readFile 可能读到写入中的半截内容
```

### 解决方案：执行模式 + 工具声明

```typescript
// types.ts - 工具可以声明自己的执行需求
interface AgentTool {
  executionMode?: "sequential" | "parallel"
  // 如果这个工具需要串行，就声明 sequential
}

// agent-loop.ts - 判断逻辑
const hasSequentialToolCall = toolCalls.some(tc =>
  tools.find(t => t.name === tc.name)?.executionMode === "sequential"
)

// 只要有一个工具声明 sequential，整批都串行
if (config.toolExecution === "sequential" || hasSequentialToolCall) {
  return executeToolCallsSequential(...)
}
```

### 设计思路

```
┌─────────────────────────────────────────┐
│  设计原则：工具自声明优先                  │
│                                         │
│  工具视角：                              │
│  ├─ 我知道我自己是否安全并发              │
│  ├─ 我声明 executionMode = "sequential" │
│  └─ Loop 看到 sequential → 强制串行      │
│                                         │
│  Loop 视角：                             │
│  ├─ 默认并行（效率优先）                  │
│  ├─ 发现 sequential → 降级串行（安全优先）│
│  └─ 全局配置可强制串行                    │
└─────────────────────────────────────────┘
```

**对比传统方案：**

| 传统方案 | AgentLoop 方案 |
|---------|---------------|
| 全局串行（低效） | 默认并行 + 工具自声明 |
| 人工编排顺序 | 工具自己声明需求 |
| 无灵活配置 | 全局配置 + 单工具覆盖 |

---

## 三、问题 2：参数验证

### 问题场景

```
LLM 返回参数：
  toolCall.arguments = { path: "test.txt", mode: 123 }
  
但 schema 定义：
  mode: { type: "string", enum: ["read", "write"] }

如果直接传给工具 → 类型错误 / 运行时崩溃
```

### 解决方案：prepareArguments + validateToolArguments

```typescript
// types.ts - 工具可以提供兼容性 shim
interface AgentTool {
  prepareArguments?: (args: unknown) => Static<TParameters>
  // 做兼容性转换，比如把 123 → "read"
}

// agent-loop.ts - 两层验证
const preparedToolCall = prepareToolCallArguments(tool, toolCall)
const validatedArgs = validateToolArguments(tool, preparedToolCall)

// pi-ai 库提供的校验函数
function validateToolArguments(tool, toolCall) {
  // 1. schema 验证
  // 2. 失败 → 抛错 → 返回 ImmediateToolCallOutcome(isError=true)
}
```

### 两层设计

```
┌─────────────────────────────────────────┐
│  Layer 1: prepareArguments（兼容层）     │
│                                         │
│  作用：修复 LLM 返回的"小问题"            │
│  ├─ 123 → "123"                         │
│  ├─ "read" → "READ"                     │
│  ├─ 缺少默认值 → 补上                    │
│                                         │
│  开发者职责：                            │
│  └─ "我知道 LLM 可能犯什么错，我来修"     │
│                                         │
└─────────────────────────────────────────┘
          ↓
┌─────────────────────────────────────────┐
│  Layer 2: validateToolArguments（校验层）│
│                                         │
│  作用：严格 schema 校验                  │
│  ├─ 类型匹配                             │
│  ├─ enum 检查                            │
│  ├─ required 检查                        │
│                                         │
│  Loop 职责：                             │
│  └─ "不管谁来修，最后必须符合 schema"     │
│                                         │
└─────────────────────────────────────────┘
```

### 设计思路

```
为什么两层？

1. prepareArguments 可选
   ├─ 不写 → 直接校验（严格模式）
   └─ 写了 → 先修复再校验（兼容模式）

2. 分离关注点
   ├─ prepareArguments：工具开发者负责
   │   "我知道我的工具可能收到什么奇怪参数"
   │
   └─ validateToolArguments：Loop 负责
   │   "我只接受符合 schema 的参数"
   │
   3. 错误边界清晰
      ├─ prepare 失败 → 返回错误结果，不崩溃
      └─ validate 失败 → 返回错误结果，不崩溃
```

---

## 四、问题 3：中断取消

### 问题场景

```
用户发起请求 → LLM 调用工具 → 工具执行 30 秒
用户中途取消 → 如何停止？

如果工具不响应取消：
  ├─ 浪费资源
  ├─ 用户等待
  └─ 可能执行不应该执行的操作
```

### 解决方案：AbortSignal 传递

```typescript
// agent-loop.ts - signal 传递链
runLoop(signal)
  ↓
executeToolCalls(signal)
  ↓
prepareToolCall(signal)
  ├─ beforeToolCall(context, signal)
  └─ if (signal?.aborted) → 返回立即错误结果
  ↓
executePreparedToolCall(signal)
  ↓
tool.execute(toolCallId, params, signal, onUpdate)
  ↓
finalizeExecutedToolCall(signal)
  └─ afterToolCall(context, signal)
```

### Signal 检查点分布

```
┌─────────────────────────────────────────┐
│  Check 1: prepareToolCall 结束          │
│  if (signal?.aborted) → 返回错误结果     │
│                                         │
│  Check 2: beforeToolCall 后             │
│  if (signal?.aborted) → 返回错误结果     │
│                                         │
│  Check 3: executePreparedToolCall 中    │
│  ├─ 传给 tool.execute                   │
│  ├─ 工具内部应该检查 signal             │
│  └─ 工具应该抛错或返回                    │
│                                         │
│  Check 4: finalizeExecutedToolCall      │
│  ├─ 传给 afterToolCall                  │
│  ├─ hook 应该检查 signal                │
│                                         │
│  Check 5: Sequential 每个工具后         │
│  if (signal?.aborted) break             │
│                                         │
│  Check 6: Parallel 准备阶段             │
│  if (signal?.aborted) break             │
└─────────────────────────────────────────┘
```

### 设计思路

```
AbortSignal 设计原则：

1. 传递而非检查
   ├─ Loop 不主动中断工具
   ├─ Loop 只是传递 signal
   └─ 工具自己决定如何响应

2. 多层检查
   ├─ Loop 在关键节点检查
   ├─ Hook 收到 signal 应该检查
   └─ Tool 收到 signal 应该检查

3. 快速失败
   ├─ 发现 aborted → 立即返回错误结果
   ├─ 不等待工具完成
   └─ 不尝试"优雅停止"

为什么这样设计？
  ├─ 工具类型多样（文件、网络、计算）
  ├─ Loop 不知道工具如何实现
  └─ 让工具自己决定停止策略
```

---

## 五、问题 4：错误处理

### 问题场景

```
工具执行失败：
  readFile("/nonexist.txt") → 抛错 "File not found"

如果直接抛错：
  ├─ Loop 崩溃
  ├─ 整个流程中断
  └─ 之前的工具结果丢失
```

### 解决方案：错误结果包装 + 不抛出

```typescript
// agent-loop.ts - 所有错误都被包装
function createErrorToolResult(message: string): AgentToolResult {
  return {
    content: [{ type: "text", text: message }],
    details: {},
  }
}

// executePreparedToolCall - catch 错误
try {
  const result = await tool.execute(...)
  return { result, isError: false }
} catch (error) {
  // 不抛错，返回错误结果
  return {
    result: createErrorToolResult(error.message),
    isError: true
  }
}

// finalizeExecutedToolCall - catch hook 错误
try {
  const afterResult = await config.afterToolCall(...)
} catch (error) {
  result = createErrorToolResult(error.message)
  isError = true
}
```

### 错误边界

```
┌─────────────────────────────────────────┐
│  Error Boundary 1: tool.execute         │
│                                         │
│  工具抛错 → 包装成 AgentToolResult       │
│  ├─ isError = true                      │
│  ├─ content = "Error: xxx"              │
│  └─ 流程继续，不中断                      │
│                                         │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│  Error Boundary 2: prepareToolCall      │
│                                         │
│  参数校验失败 → 包装成错误结果            │
│  ├─ isError = true                      │
│  ├─ content = "Validation failed"       │
│  └─ 返回 ImmediateToolCallOutcome       │
│                                         │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│  Error Boundary 3: afterToolCall        │
│                                         │
│  Hook 抛错 → 包装成错误结果               │
│  ├─ isError = true                      │
│  ├─ content = "Hook error: xxx"         │
│  └─ 覆盖原工具结果                        │
│                                         │
└─────────────────────────────────────────┘
```

### 设计思路

```
为什么"错误也是结果"？

传统方案：
  tool.execute() 抛错
  → Loop catch
  → 决定是否继续
  
AgentLoop 方案：
  tool.execute() 抛错
  → Loop 包装成 result
  → isError = true
  → 加入对话历史
  → LLM 看到错误
  → LLM 决定是否重试/补救

优势：
  1. LLM 看到错误信息
     ├─ 可以调整策略
     ├─ 可以换工具
     └─ 可以放弃任务
  
  2. 错误是对话的一部分
     ├─ 用户能看到
     ├─ 日志能记录
     └─ UI 能渲染
  
  3. 流程不中断
     ├─ 其他工具继续执行
     └─ 整体任务可能完成
```

---

## 六、问题 5：流式反馈

### 问题场景

```
长时间工具执行：
  searchWeb("复杂查询") → 执行 20 秒

用户等待：
  ├─ 界面静止
  ├─ 不知道进度
  └─ 不知道是否卡死
```

### 解决方案：onUpdate 回调

```typescript
// types.ts - 工具可以发送更新
interface AgentTool {
  execute: (
    toolCallId,
    params,
    signal,
    onUpdate?: AgentToolUpdateCallback<TDetails>
  ) => Promise<AgentToolResult>
}

// agent-loop.ts - Loop 传递 onUpdate
const result = await tool.execute(
  toolCallId,
  params,
  signal,
  (partialResult) => {
    // 工具调用这个回调 → Loop 发送事件
    emit({
      type: "tool_execution_update",
      toolCallId,
      toolName,
      args,
      partialResult
    })
  }
)
```

### 流式更新机制

```
┌─────────────────────────────────────────┐
│  Tool 实现                              │
│                                         │
│  async execute(id, params, signal, onUpdate) {│
│    // 阶段 1                             │
│    onUpdate({ details: { stage: "init" } })│
│    await init()                         │
│                                         │
│    // 阶段 2                             │
│    onUpdate({ details: { stage: "process" } })│
│    for (item of items) {                │
│      onUpdate({ details: { progress: i/total } })│
│      await process(item)                │
│    }                                    │
│                                         │
│    // 阶段 3                             │
│    onUpdate({ details: { stage: "done" } })│
│    return finalResult                   │
│  }                                      │
└─────────────────────────────────────────┘
          ↓ onUpdate 回调
┌─────────────────────────────────────────┐
│  Loop 处理                              │
│                                         │
│  emit tool_execution_update             │
│  ├─ UI 收到事件                         │
│  ├─ 显示进度                            │
│  └─ 用户看到实时反馈                     │
│                                         │
│  注意：update 事件不阻塞执行              │
│  ├─ emit 是 async                       │
│  ├─ 但不 await                          │
│  └─ 存入数组，最后 await Promise.all     │
└─────────────────────────────────────────┘
```

### 设计思路

```
为什么 onUpdate 是回调而非 Promise？

1. 主动推送
   ├─ Tool 决定何时发送更新
   ├─ Loop 不需要轮询
   └─ 实时性更好

2. 非阻塞
   ├─ emit 不阻塞 tool 执行
   ├─ Tool 可以连续发送多次
   └─ 最后批量 await

3. 结构化数据
   ├─ onUpdate(partialResult)
   ├─ partialResult 包含 details
   ├─ details 类型由 Tool 定义
   └─ UI 可以根据 details 渲染

4. 可选
   ├─ Tool 不必须实现 onUpdate
   ├─ 没有 onUpdate → 无进度
   └─ 有 onUpdate → 有进度
```

---

## 七、问题 6：执行拦截

### 问题场景

```
危险工具调用：
  deleteFile("/important.txt")
  
如果直接执行：
  ├─ 文件被删
  ├─ 无法恢复
  └─ 用户可能后悔
```

### 解决方案：beforeToolCall Hook

```typescript
// types.ts - Hook 可以拦截
interface BeforeToolCallResult {
  block?: boolean      // 是否阻止执行
  reason?: string      // 阻止原因
}

interface AgentLoopConfig {
  beforeToolCall?: (
    context: BeforeToolCallContext,
    signal?: AbortSignal
  ) => Promise<BeforeToolCallResult | undefined>
}

// agent-loop.ts - 拦截逻辑
if (config.beforeToolCall) {
  const beforeResult = await config.beforeToolCall(
    { assistantMessage, toolCall, args, context },
    signal
  )
  
  if (beforeResult?.block) {
    // 拦截 → 返回错误结果
    return {
      kind: "immediate",
      result: createErrorToolResult(
        beforeResult.reason || "Tool execution was blocked"
      ),
      isError: true
    }
  }
}
```

### 拦截场景

```
┌─────────────────────────────────────────┐
│  场景 1：危险操作确认                     │
│                                         │
│  beforeToolCall: async (context) => {   │
│    if (context.toolCall.name === "deleteFile") {│
│      const confirmed = await askUser()  │
│      if (!confirmed) {                  │
│        return { block: true, reason: "User declined" }│
│      }                                  │
│    }                                    │
│  }                                      │
│                                         │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│  场景 2：资源限制                         │
│                                         │
│  beforeToolCall: async (context) => {   │
│    if (context.toolCall.name === "searchWeb") {│
│      if (searchCount > MAX_SEARCHES) {  │
│        return { block: true, reason: "Search limit reached" }│
│      }                                  │
│      searchCount++                      │
│    }                                    │
│  }                                      │
│                                         │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│  场景 3：审计日志                         │
│                                         │
│  beforeToolCall: async (context) => {   │
│    logAudit(context)                    │
│    // 不拦截，只记录                      │
│    return undefined                     │
│  }                                      │
│                                         │
└─────────────────────────────────────────┘
```

### 设计思路

```
为什么 beforeToolCall 而非工具内部检查？

1. 分离关注点
   ├─ Tool：只知道如何执行
   ├─ Hook：知道是否应该执行
   └─ 职责清晰

2. 动态策略
   ├─ Hook 可以访问全局状态
   │   ├─ 用户权限
   │   ├─ 资源限制
   │   ├─ 运行时条件
   │
   ├─ Tool 不需要知道这些
   └─ Tool 实现更简单

3. 灵活配置
   ├─ 同一个 Tool
   ├─ 不同场景用不同 Hook
   │   ├─ 测试环境：无拦截
   │   ├─ 生产环境：严格拦截
   │
   └─ Tool 代码不变

4. 统一入口
   ├─ 所有拦截逻辑集中
   ├─ 容易维护
   └─ 容易审计
```

---

## 八、问题 7：结果修改

### 问题场景

```
工具返回结果：
  readFile("/large.txt") → 返回 10000 行

问题：
  ├─ 结果太长 → LLM 处理不了
  ├─ 格式不对 → UI 显示不了
  ├─ 敏感信息 → 不应该暴露
```

### 解决方案：afterToolCall Hook

```typescript
// types.ts - Hook 可以修改结果
interface AfterToolCallResult {
  content?: (TextContent | ImageContent)[]  // 替换内容
  details?: unknown                         // 替换 details
  isError?: boolean                         // 替换错误标志
  terminate?: boolean                       // 设置终止信号
}

// agent-loop.ts - 修改逻辑
if (config.afterToolCall) {
  const afterResult = await config.afterToolCall(
    { assistantMessage, toolCall, args, result, isError, context },
    signal
  )
  
  if (afterResult) {
    result = {
      content: afterResult.content ?? result.content,
      details: afterResult.details ?? result.details,
      terminate: afterResult.terminate ?? result.terminate,
    }
    isError = afterResult.isError ?? isError
  }
}
```

### 修改场景

```
┌─────────────────────────────────────────┐
│  场景 1：内容裁剪                         │
│                                         │
│  afterToolCall: async (context) => {    │
│    if (context.toolCall.name === "readFile") {│
│      const lines = context.result.content│
│      if (lines.length > 100) {          │
│        return {                         │
│          content: lines.slice(0, 100),  │
│          details: { truncated: true }   │
│        }                                │
│      }                                  │
│    }                                    │
│  }                                      │
│                                         │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│  场景 2：错误恢复                         │
│                                         │
│  afterToolCall: async (context) => {    │
│    if (context.isError) {               │
│      // 尝试恢复                         │
│      const fixed = await tryRecover()   │
│      if (fixed) {                       │
│        return {                         │
│          isError: false,                │
│          content: fixed                 │
│        }                                │
│      }                                  │
│      // 给建议                           │
│      return {                           │
│        content: "Error. Try: ..."       │
│      }                                  │
│    }                                    │
│  }                                      │
│                                         │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│  场景 3：敏感过滤                         │
│                                         │
│  afterToolCall: async (context) => {    │
│    const filtered = filterSecrets(      │
│      context.result.content             │
│    )                                    │
│    return { content: filtered }         │
│  }                                      │
│                                         │
└─────────────────────────────────────────┘
```

### 设计思路

```
替换而非合并

为什么 AfterToolCallResult 是替换语义？

1. 明确意图
   ├─ content?: 替换全部内容
   ├─ 不提供 → 保持原样
   ├─ 提供 → 完全替换
   │
   └─ 不存在"部分修改"的歧义

2. 防止意外
   ├─ 如果是合并
   │   ├─ 原内容: [a, b, c]
   │   ├─ hook 返回: [d]
   │   └─ 合并: [a, b, c, d] ← 可能不是想要
   │
   └─ 替换语义
   │   ├─ 原内容: [a, b, c]
   │   ├─ hook 返回: [d]
   │   └─ 结果: [d] ← 明确意图

3. 简化实现
   ├─ 不需要 deep merge
   ├─ 不需要合并策略
   └─ 逻辑清晰

对比：
  合并语义 → 复杂、歧义、难调试
  替换语义 → 简单、明确、易理解
```

---

## 九、问题 8：终止信号

### 问题场景

```
工具执行完成：
  shutdown() → 系统关闭

问题：
  ├─ 工具执行成功
  ├─ 但 Loop 不知道应该停止
  └─ 继续调用 LLM → 浪费资源 / 无意义
```

### 解决方案：terminate 标志

```typescript
// types.ts - 工具可以返回终止信号
interface AgentToolResult {
  content: (TextContent | ImageContent)[]
  details: T
  terminate?: boolean  // 终止信号
}

// agent-loop.ts - 检查逻辑
function shouldTerminateToolBatch(finalizedCalls) {
  return finalizedCalls.length > 0 
    && finalizedCalls.every(f => f.result.terminate === true)
}

// 如果所有工具都返回 terminate=true
const executedToolBatch = await executeToolCalls(...)
hasMoreToolCalls = !executedToolBatch.terminate
// → hasMoreToolCalls = false
// → 内层循环结束
```

### 终止场景

```
┌─────────────────────────────────────────┐
│  场景 1：shutdown 工具                   │
│                                         │
│  shutdownTool.execute = async () => {   │
│    await shutdownSystem()               │
│    return {                             │
│      content: "System shutdown",        │
│      details: {},                       │
│      terminate: true                    │
│    }                                    │
│  }                                      │
│                                         │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│  场景 2：任务完成标志                     │
│                                         │
│  taskDoneTool.execute = async () => {   │
│    return {                             │
│      content: "Task completed",         │
│      details: {},                       │
│      terminate: true                    │
│    }                                    │
│  }                                      │
│                                         │
└─────────────────────────────────────────┘
```

### 设计局限性

```
问题：为什么 terminate 需要"所有工具都返回"？

┌─────────────────────────────────────────┐
│  多工具调用场景                          │
│                                         │
│  toolCalls = [                          │
│    readFile(),      → terminate: false  │
│    shutdown(),      → terminate: true   │
│  ]                                      │
│                                         │
│  检查：                                  │
│  ├─ readFile.terminate = false          │
│  ├─ shutdown.terminate = true           │
│  └─ every() → false                     │
│  └─ hasMoreToolCalls = true             │
│  └─ 循环继续                             │
│                                         │
│  结果：                                  │
│  shutdown 信号被 readFile 稀释           │
│  Loop 不知道应该停止                      │
│                                         │
└─────────────────────────────────────────┘
```

### 为什么设计成"全部终止"？

```
设计思路：

1. 防止误终止
   ├─ 如果是"任一终止"
   │   ├─ 一个工具返回 terminate
   │   ├─ 其他工具还在执行重要操作
   │   ├─ Loop 就停止
   │   └─ 重要操作被忽略
   │
   └─ "全部终止"更安全
   │   ├─ 所有工具都同意停止
   │   ├─ 才真正停止
   │   └─ 防止意外

2. 但实际有缺陷
   ├─ LLM 可能同时调用多个工具
   │   ├─ 一个是 terminate 工具
   │   ├─ 一个是普通工具
   │   └─ terminate 被稀释
   │
   ├─ LLM 不一定单独调用 terminate 工具
   │   ├─ 不确定性高
   │   ├─ terminate 机制不可靠
   │
   └─ 建议：使用 shouldStopAfterTurn
   │   ├─ 更可靠
   │   ├─ Loop 主动判断
   │   ├─ 不依赖 LLM
```

---

## 十、问题 9：事件顺序

### 问题场景

```
并行执行：
  toolCalls = [tc0, tc1, tc2]
  
完成顺序：
  tc1 先完成 → emit tool_execution_end(tc1)
  tc0 后完成 → emit tool_execution_end(tc0)
  tc2 最后完成 → emit tool_execution_end(tc2)

问题：
  ├─ tool_execution_end 按完成顺序
  ├─ message_start/end 应该按什么顺序？
  │   ├─ 完成顺序？→ 对话混乱
  │   ├─ 原始顺序？→ 需要等待
```

### 解决方案：完成顺序 + 原始顺序分离

```typescript
// agent-loop.ts - Parallel 模式
const finalizedCalls: FinalizedToolCallEntry[] = []

// 准备阶段
for (const toolCall of toolCalls) {
  // ...
  finalizedCalls.push(async () => {
    const executed = await executePreparedToolCall(...)
    const finalized = await finalizeExecutedToolCall(...)
    // 完成 → 立即发送 tool_execution_end
    await emitToolExecutionEnd(finalized, emit)
    return finalized
  })
}

// Promise.all → 按完成顺序返回 finalizedCalls
// 但数组顺序保持原始顺序

const orderedFinalizedCalls = await Promise.all(
  finalizedCalls.map(entry => ...)
)

// 按原始顺序发送 message 事件
for (const finalized of orderedFinalizedCalls) {
  const toolResultMessage = createToolResultMessage(finalized)
  await emitToolResultMessage(toolResultMessage, emit)
  messages.push(toolResultMessage)
}
```

### 两种顺序的意义

```
┌─────────────────────────────────────────┐
│  tool_execution_end 顺序                │
│                                         │
│  按完成先后                              │
│  ├─ 用户看到实时进度                     │
│  ├─ 知道哪个先完成                       │
│  └─ UI 可以动态更新                      │
│                                         │
│  示例：                                  │
│  tc1 完成 → emit → UI 显示 "工具1完成"   │
│  tc0 完成 → emit → UI 显示 "工具0完成"   │
│                                         │
│  意义：实时反馈                          │
│                                         │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│  message_start/end 顺序                 │
│                                         │
│  按原始 toolCall 顺序                    │
│  ├─ 对话历史保持顺序                     │
│  ├─ LLM 按顺序阅读                       │
│  └─ UI 按顺序渲染                        │
│                                         │
│  示例：                                  │
│  emit message(tc0) → 加入对话            │
│  emit message(tc1) → 加入对话            │
│  emit message(tc2) → 加入对话            │
│                                         │
│  意义：对话连贯                          │
│                                         │
└─────────────────────────────────────────┘
```

### 设计思路

```
为什么两种顺序？

1. 不同用途
   ├─ tool_execution_end：进度反馈
   │   ├─ 用户关心实时性
   │   ├─ 不关心顺序
   │
   └─ message_start/end：对话历史
   │   ├─ LLM 关心顺序
   │   ├─ 用户关心顺序
   │   ├─ UI 渲染需要顺序

2. 实现
   ├─ tool_execution_end：完成时立即 emit
   │   ├─ 不等待其他工具
   │   ├─ 实时性优先
   │
   └─ message_start/end：Promise.all 完成后
   │   ├─ 按原始顺序遍历
   │   ├─ 连贯性优先

3. 类型标记
   ├─ finalizedCalls 数组顺序 = 原始顺序
   │   ├─ tc0 在 index 0
   │   ├─ tc1 在 index 1
   │   ├─ tc2 在 index 2
   │
   └─ Promise.all 返回保持数组顺序
   │   ├─ 即使 tc1 先完成
   │   ├─ 结果[1] = tc1 的结果
   │   ├─ 遍历按 index → 按原始顺序
```

---

## 十一、问题 10：上下文管理

### 问题场景

```
工具结果：
  readFile → result
  
问题：
  ├─ result 加入哪个 context？
  ├─ currentContext？newMessages？
  ├─ 顺序如何？
  ├─ 如果中途停止，结果还在吗？
```

### 解决方案：双 Context 管理

```typescript
// agent-loop.ts - 两个 context
let currentContext = initialContext  // LLM 看到的完整对话
const newMessages: AgentMessage[] = []  // 本次 run 新增的消息

// 工具结果加入两个
currentContext.messages.push(result)  // LLM 下轮能看到
newMessages.push(result)              // 返回给调用者

// agent_end 时返回 newMessages
await emit({ type: "agent_end", messages: newMessages })
return newMessages
```

### 双 Context 意义

```
┌─────────────────────────────────────────┐
│  currentContext                         │
│                                         │
│  作用：运行时对话                         │
│  ├─ 包含所有历史消息                     │
│  ├─ 包含本次新增消息                     │
│  ├─ LLM 调用时使用                      │
│  ├─ 不断增长                            │
│                                         │
│  示例：                                  │
│  [历史消息] + [新prompt] + [LLM回复] + [工具结果]│
│                                         │
│  意义：                                  │
│  ├─ LLM 看到完整上下文                   │
│  ├─ 可以引用之前内容                     │
│                                         │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│  newMessages                            │
│                                         │
│  作用：本次 run 的产出                    │
│  ├─ 只包含本次新增的消息                 │
│  ├─ 不包含历史消息                       │
│  ├─ 返回给调用者                         │
│                                         │
│  示例：                                  │
│  [新prompt] + [LLM回复] + [工具结果]     │
│                                         │
│  意义：                                  │
│  ├─ 调用者知道本次产生了什么             │
│  ├─ 可以保存到数据库                     │
│  ├─ 可以追加到持久化 context             │
│                                         │
└─────────────────────────────────────────┘
```

### 设计思路

```
为什么两个 context？

1. 分离关注点
   ├─ currentContext：运行时
   │   ├─ Loop 内部使用
   │   ├─ LLM 调用使用
   │   ├─ 动态增长
   │
   └─ newMessages：返回值
   │   ├─ Loop 外部使用
   │   ├─ 调用者关心
   │   ├─ 本次产出

2. 调用者灵活
   ├─ 调用者收到 newMessages
   │   ├─ 可以追加到持久化 context
   │   ├─ 可以保存到数据库
   │   ├─ 可以不保存（临时运行）
   │
   └─ 不需要"整个历史"
   │   ├─ 调用者可能已有历史
   │   ├─ 只需要新增部分

3. 继续运行
   ├─ agentLoopContinue 不需要 prompt
   │   ├─ context 已有消息
   │   ├─ 继续运行
   │
   │   └─ newMessages 只包含新产生部分
   │       ├─ 不包含之前的
   │       ├─ 不会重复
```

---

## 十二、设计原则总结

```
┌─────────────────────────────────────────────────────────────┐
│  AgentLoop 工具调用设计原则                                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 分离关注点                                               │
│     ├─ Tool：只知道如何执行                                  │
│     ├─ Hook：知道是否执行 / 如何处理                         │
│     ├─ Loop：知道何时执行 / 如何编排                         │
│     └─ 各司其职                                              │
│                                                             │
│  2. 错误即结果                                               │
│     ├─ 错误包装成 AgentToolResult                            │
│     ├─ isError 标记                                          │
│     ├─ 流程不中断                                            │
│     ├─ LLM 看到错误                                          │
│     └─ LLM 决定下一步                                        │
│                                                             │
│  3. 传递而非控制                                             │
│     ├─ AbortSignal 传递给所有层级                            │
│     ├─ Loop 不主动中断                                       │
│     ├─ Tool / Hook 自己响应                                  │
│     └─ 各层自主决定                                          │
│                                                             │
│  4. 替换而非合并                                             │
│     ├─ AfterToolCallResult 替换语义                          │
│     ├─ 明确意图                                              │
│     ├─ 防止歧义                                              │
│     └─ 简化实现                                              │
│                                                             │
│  5. 工具自声明                                               │
│     ├─ executionMode 由工具声明                              │
│     ├─ 工具知道自己是否安全并发                              │
│     ├─ Loop 根据声明调整                                     │
│     └─ 灵活 + 安全                                           │
│                                                             │
│  6. 双重验证                                                 │
│     ├─ prepareArguments：兼容层（可选）                      │
│     ├─ validateToolArguments：校验层（强制）                 │
│     ├─ 先修复后校验                                          │
│     └─ 最终符合 schema                                       │
│                                                             │
│  7. 流式非阻塞                                               │
│     ├─ onUpdate 回调                                         │
│     ├─ emit 不阻塞执行                                       │
│     ├─ 批量 await                                            │
│     ├─ 实时反馈                                              │
│                                                             │
│  8. 顺序分离                                                 │
│     ├─ tool_execution_end：完成顺序（实时性）                │
│     ├─ message_start/end：原始顺序（连贯性）                 │
│     ├─ 不同用途                                              │
│     ├─ 各有意义                                              │
│                                                             │
│  9. 双 Context                                               │
│     ├─ currentContext：运行时完整对话                        │
│     ├─ newMessages：本次产出                                 │
│     ├─ 分离关注点                                            │
│     ├─ 调用者灵活                                            │
│                                                             │
│  10. 拦截统一入口                                            │
│      ├─ beforeToolCall 集中拦截逻辑                         │
│      ├─ 容易维护                                            │
│      ├─ 容易审计                                            │
│      ├─ 工具实现简单                                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 一句话总结

```
开发者关注的问题：
  并发/参数/中断/错误/反馈/拦截/修改/终止/顺序/上下文

核心设计原则：
  分离关注点 + 错误即结果 + 传递而非控制 + 替换而非合并
  + 工具自声明 + 双重验证 + 流式非阻塞 + 顺序分离 + 双Context + 拦截统一入口
```