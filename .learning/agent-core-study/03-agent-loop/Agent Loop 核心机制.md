---
name: agent-loop-core-analysis
description: Agent Loop 核心机制深度解析 - 消息流转、工具执行、事件系统
metadata:
  type: reference
---

# Agent Loop 核心机制学习文档

## 一、核心功能点拆解

### 1.1 双入口设计

```
agentLoop()        → 新对话开始，添加新消息到上下文
agentLoopContinue() → 从现有上下文继续，用于重试场景
```

**记忆口诀：一个入口两种模式 —— 新建或继续**

### 1.2 双层循环架构

```
外层循环 (while true)
├── 处理 follow-up messages（循环后的额外消息）
└── 内层循环 (while hasMoreToolCalls || pendingMessages)
    ├── 处理 steering messages（转向消息）
    ├── 流式获取 assistant 响应
    ├── 执行工具调用
    └── 检查终止条件
```

**记忆口诀：外层管消息队列，内层管执行流程**

### 1.3 三种消息注入机制

| 机制 | 触发时机 | 用途 |
|------|----------|------|
| `prompts` | 启动时 | 初始用户输入 |
| `steeringMessages` | 每个 turn 开始前 | 中途干预方向 |
| `followUpMessages` | 循环结束时 | 延续对话 |

### 1.4 工具执行两种模式

```typescript
// 并行执行（默认）
executeToolCallsParallel() → Promise.all() 同时执行

// 串行执行
executeToolCallsSequential() → for...of 顺序执行
```

触发条件：
- `config.toolExecution === "sequential"`
- 任一工具的 `executionMode === "sequential"`

### 1.5 工具执行三阶段

```
prepareToolCall()
├── 参数验证
├── beforeToolCall 钩子
└── 返回 prepared/immediate

executePreparedToolCall()
├── tool.execute()
└── 发送 partial update 事件

finalizeExecutedToolCall()
├── afterToolCall 钩子
└── 修改/增强结果
```

---

## 二、遇到的问题 → 抽象提炼

### 问题 1：重试时如何保持上下文？

**场景**：LLM 返回错误，需要重试但不能丢失已执行的工具结果。

**抽象**：状态连续性问题 —— 如何在不重新开始的情况下继续执行？

**解决原则**：
- 分离"新建"和"继续"两种入口
- 继续时验证最后一消息不是 assistant（必须是 user 或 toolResult）
- 保持 context.messages 不变，只追加新消息

### 问题 2：流式响应如何实时更新？

**场景**：LLM 流式返回 token，需要实时显示进度。

**抽象**：部分状态管理 —— 如何在数据不完整时管理状态？

**解决原则**：
- 使用 `partial` message 表示不完整状态
- 每次事件到来时替换 `context.messages[-1]`
- 区分 `message_start`（初始）、`message_update`（增量）、`message_end`（完整）

```typescript
// 关键模式：就地更新
context.messages[context.messages.length - 1] = partialMessage;
```

### 问题 3：工具调用何时并行、何时串行？

**场景**：读取文件的工具可以并行，但创建 git commit 的工具需要串行。

**抽象**：依赖关系建模 —— 如何表达工具间的依赖？

**解决原则**：
- 工具级别配置 `executionMode`
- 混合模式检测：任一 sequential → 全部串行
- 保持结果顺序与调用顺序一致

### 问题 4：如何在循环中注入外部指令？

**场景**：用户在 agent 执行过程中输入新指令，需要改变方向。

**抽象**：控制流中断 —— 如何在不可中断的操作中注入控制？

**解决原则**：
- **Steering messages**：在每个 turn 之前检查，用于改变方向
- **Follow-up messages**：在循环结束时检查，用于延续任务
- 分离"注入点"和"执行点"

```typescript
// 注入点设计
pendingMessages = (await config.getSteeringMessages?.()) || [];
// 执行点设计
for (const message of pendingMessages) {
    currentContext.messages.push(message);
}
```

### 问题 5：API Key 过期怎么办？

**场景**：长时间运行的 agent，API key 可能中途过期。

**抽象**：凭证生命周期管理 —— 动态资源获取。

**解决原则**：
- 每次调用前通过 `getApiKey()` 动态获取
- 回退机制：`resolvedApiKey = await getApiKey() || config.apiKey`

---

## 三、面试/分享核心讲述点

### 开场：一句话概括

> "Agent Loop 是一个**事件驱动的对话循环**，它管理 LLM 和工具之间的交互，通过**双层循环**处理用户干预，通过**三阶段执行**保证工具调用的可控性。"

### 核心架构图（手绘风格）

```
用户输入
   │
   ▼
┌─────────────────────────────────┐
│  agentLoop / agentLoopContinue  │
└─────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────┐
│  外层循环：follow-up 消息检查     │◄────────┐
└─────────────────────────────────┘         │
   │                                        │
   ▼                                        │
┌─────────────────────────────────┐         │
│  内层循环：工具调用执行           │         │
│  ├─ steering messages 注入      │         │
│  ├─ 流式 assistant 响应          │         │
│  ├─ 工具执行（并行/串行）          │         │
│  └─ 终止条件检查                  │         │
└─────────────────────────────────┘         │
   │                                        │
   ▼                                        │
有 follow-up？ ───── 是 ────────────────────┘
   │
   否
   ▼
 结束
```

### 面试高频问题

#### Q1: 为什么需要双层循环？

**回答要点**：
1. **内层循环**：处理 LLM → 工具 → LLM 的自动循环（如：调用工具后又产生新工具调用）
2. **外层循环**：处理 agent "想停下来"但外部有新任务的情况（如：用户在等待时输入了新指令）
3. **设计思想**：分离"自主循环"和"外部驱动"，让 agent 既有自主性又能被干预

#### Q2: 工具执行的 prepare/execute/finalize 三阶段解决了什么问题？

**回答要点**：
```
prepare    → 验证 + 钩子干预（可以阻止执行）
execute    → 真正执行 + 实时更新
finalize   → 结果增强（可以修改返回内容）
```

1. **解耦**：把验证、执行、后处理分离
2. **可扩展**：通过钩子实现权限控制、日志、监控
3. **可测试**：每个阶段可单独测试
4. **错误隔离**：一个阶段的错误不影响其他阶段的清理

#### Q3: 流式响应如何保证消息完整性？

**回答要点**：
1. **partial message 模式**：始终在 context 中维护一个"当前正在构建"的消息
2. **事件驱动更新**：每次收到 delta 就替换 partial
3. **最终一致性**：`response.result()` 返回完整消息，确保最后状态正确
4. **边界处理**：处理 `start` → `update*` → `end` 和直接 `done` 两种路径

```typescript
// 两种路径
case "start":
    context.messages.push(partial);  // 添加占位
case "done":
    context.messages[-1] = final;    // 替换为完整
```

#### Q4: 如果让你设计一个 Agent Loop，你会怎么做？

**回答框架**：

1. **状态管理**
   - Context 对象：messages + tools + systemPrompt
   - 不变性：只追加不修改（除了流式更新的 partial）

2. **事件系统**
   - 事件类型：`*_start` / `*_delta` / `*_end`
   - 好处：UI 可以响应，测试可以断言

3. **控制流**
   - 双层循环：内层自主，外层响应外部
   - 终止条件：`stopReason` / `shouldStopAfterTurn` / `toolResult.terminate`

4. **扩展点**
   - 钩子：`beforeToolCall` / `afterToolCall`
   - 转换：`transformContext` / `convertToLlm`
   - 动态配置：`getApiKey` / `prepareNextTurn`

### 白板演示代码

```typescript
// 核心循环的简化版（面试可画）
async function runLoop(context, config) {
    while (true) {  // 外层：follow-up
        while (hasMoreWork) {  // 内层：工具调用
            // 1. 注入 steering
            const steering = await config.getSteeringMessages?.();
            context.messages.push(...steering);

            // 2. 获取响应
            const message = await streamLLM(context);

            // 3. 执行工具
            const results = await executeTools(message.toolCalls);

            // 4. 检查终止
            if (shouldStop(message, results)) break;
        }

        // 5. 检查 follow-up
        const followUp = await config.getFollowUpMessages?.();
        if (!followUp.length) break;
        context.messages.push(...followUp);
    }
}
```

---

## 四、设计模式提炼

### 4.1 事件流模式

**定义**：将异步操作建模为事件序列，消费者通过事件类型响应。

**实现要点**：
```typescript
type AgentEvent =
  | { type: "agent_start" }
  | { type: "turn_start" }
  | { type: "message_start"; message: AgentMessage }
  | { type: "message_update"; assistantMessageEvent: StreamEvent }
  | { type: "message_end"; message: AgentMessage }
  | { type: "tool_execution_start"; ... }
  | { type: "tool_execution_end"; ... }
  | { type: "turn_end"; ... }
  | { type: "agent_end"; messages: AgentMessage[] };
```

**好处**：
- UI 可以细粒度响应
- 易于测试和调试
- 支持中间状态持久化

### 4.2 钩子链模式

**定义**：在操作前后插入自定义逻辑。

**钩子点**：
- `beforeToolCall`：权限检查、参数修改、阻止执行
- `afterToolCall`：结果修改、日志、清理
- `prepareNextTurn`：上下文压缩、模型切换
- `transformContext`：消息过滤、重排序

### 4.3 延迟执行模式

**定义**：将异步操作表示为函数，按需执行。

**示例**：
```typescript
type FinalizedToolCallEntry =
  | FinalizedToolCallOutcome           // 立即结果
  | (() => Promise<FinalizedToolCallOutcome>);  // 延迟执行

// 并行执行时收集函数
finalizedCalls.push(async () => { ... });

// 最后统一执行
const results = await Promise.all(
    finalizedCalls.map(entry => typeof entry === 'function' ? entry() : entry)
);
```

**好处**：
- 统一处理立即结果和异步操作
- 支持并行优化
- 保持顺序一致性

---

## 五、记忆卡片

### 卡片 1：双入口
- `agentLoop`：新建对话
- `agentLoopContinue`：继续对话（最后一消息必须是 user/toolResult）

### 卡片 2：双层循环
- 外层：`follow-up` 消息（延续任务）
- 内层：`toolCalls` + `steering` 消息（自主执行）

### 卡片 3：三阶段工具执行
- `prepare`：验证 + 钩子（可阻止）
- `execute`：执行 + 实时更新
- `finalize`：结果增强

### 卡片 4：三种消息注入
- `prompts`：启动时
- `steering`：每 turn 前
- `follow-up`：循环结束时

### 卡片 5：两种工具执行
- `parallel`：Promise.all（默认）
- `sequential`：for...of（工具配置或全局配置）

---

## 六、延伸思考

### 如果要支持工具间的依赖关系？

当前设计只有"全部并行"或"全部串行"。如果要支持"工具A必须在工具B之前完成"：

```typescript
// 可能的扩展
type ToolDependency = {
  tool: string;
  dependsOn: string[];
};

// 拓扑排序后执行
async function executeWithDependencies(toolCalls, dependencies) {
  const graph = buildDependencyGraph(toolCalls, dependencies);
  const sorted = topologicalSort(graph);
  // 分层执行（每层内的工具并行）
  for (const layer of sorted) {
    await Promise.all(layer.map(executeTool));
  }
}
```

### 如果要支持 checkpoint/restore？

当前 context 只在内存中。如果要支持断点续传：

```typescript
type Checkpoint = {
  context: AgentContext;
  newMessages: AgentMessage[];
  turnNumber: number;
};

// 每次循环后保存
await config.saveCheckpoint?.({
  context: currentContext,
  newMessages,
  turnNumber,
});

// 启动时恢复
const checkpoint = await config.loadCheckpoint?.();
if (checkpoint) {
  currentContext = checkpoint.context;
  // ...
}
```

---

## 相关链接

- [[agent-tool-design]] - Agent Tool 类型系统设计
- [[agent-state-management]] - Agent 状态管理策略
- [[stream-processing-patterns]] - 流式处理模式