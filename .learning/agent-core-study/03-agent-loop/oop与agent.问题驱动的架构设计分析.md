# agent-loop.ts 与 agent.ts：问题驱动的架构设计分析

> 从"要解决什么问题"出发，抽象本质问题，推导设计原则，展示技术实现

---

## 一、表面问题 → 本质问题抽象

### 表面问题列表

应用层在使用 Agent 时遇到的具体痛点：

```
┌────────────────────────────────────────────────────────────────┐
│                     表面问题一：循环协调难                       │
├────────────────────────────────────────────────────────────────┤
│  具体痛点：                                                     │
│  - LLM 调用 → 工具执行 → 结果处理，谁来协调？                   │
│  - 工具执行完，是继续调用 LLM 还是停止？                         │
│  - 多轮对话的状态如何维护？                                      │
│  - 工具执行失败了怎么处理？                                      │
│                                                                 │
│  用户的困惑：                                                   │
│  ❌ 每次都要手动写循环逻辑                                       │
│  ❌ 不清楚何时该停止，何时该继续                                 │
│  ❌ 状态散落各处，难以维护                                        │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│                     表面问题二：消息格式混乱                     │
├────────────────────────────────────────────────────────────────┤
│  具体痛点：                                                     │
│  - Agent 内部需要额外字段（timestamp、metadata）                │
│  - LLM API 需要统一格式（Message[]）                             │
│  - 不同层次的消息格式不一样                                       │
│  - 转换时机不确定，容易出错                                       │
│                                                                 │
│  用户的困惑：                                                   │
│  ❌ 不知道何时该用 AgentMessage，何时该用 Message                │
│  ❌ 转换代码到处写，容易遗漏                                       │
│  ❌ 格式不统一，调试困难                                          │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│                     表面问题三：工具执行复杂                     │
├────────────────────────────────────────────────────────────────┤
│  具体痛点：                                                     │
│  - 工具调用有并行和顺序两种模式                                   │
│  - 需要在执行前检查参数、在执行后处理结果                         │
│  - 工具执行中途可以被中断                                         │
│  - 工具结果需要正确返回给 LLM                                     │
│                                                                 │
│  用户的困惑：                                                   │
│  ❌ 并行和顺序的选择逻辑复杂                                      │
│  ❌ 钩子逻辑不知道放在哪里                                        │
│  ❌ 中断处理容易出错                                              │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│                     表面问题四：状态不可观测                     │
├────────────────────────────────────────────────────────────────┤
│  具体痛点：                                                     │
│  - 消息历史、工具列表在哪里管理？                                 │
│  - 当前是否在生成？生成到哪了？                                   │
│  - 哪些工具正在执行？                                            │
│  - 发生错误了，错误信息在哪？                                     │
│                                                                 │
│  用户的困惑：                                                   │
│  ❌ 状态散落各处，难以统一访问                                    │
│  ❌ 不知道 agent 当前在做什么                                     │
│  ❌ UI 无法实时显示状态                                           │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│                     表面问题五：消息注入困难                     │
├────────────────────────────────────────────────────────────────┤
│  具体痛点：                                                     │
│  - 用户想在 agent 运行中途发送新指令                              │
│  - agent 完成后想自动执行后续任务                                 │
│  - 消息注入的时机不确定                                           │
│  - 多个消息如何处理（一次一个还是批量）                           │
│                                                                 │
│  用户的困惑：                                                   │
│  ❌ 不知道何时能注入消息                                          │
│  ❌ 消息注入后 agent 的行为不可预测                                │
│  ❌ 队列管理复杂                                                  │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│                     表面问题六：事件通知缺失                     │
├────────────────────────────────────────────────────────────────┤
│  具体痛点：                                                     │
│  - UI 需要实时显示生成内容                                        │
│  - 需要记录工具执行日志                                           │
│  - 需要统计 token 使用                                           │
│  - 需要监听错误发生                                               │
│                                                                 │
│  用户的困惑：                                                   │
│  ❌ 没有统一的事件通知机制                                        │
│  ❌ 不知道何时发生了什么                                           │
│  ❌ 订阅逻辑复杂                                                  │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│                     表面问题七：运行控制复杂                     │
├────────────────────────────────────────────────────────────────┤
│  具体痛点：                                                     │
│  - 如何启动一个新的 prompt？                                     │
│  - 如何中断当前运行？                                            │
│  - 如何等待运行完成？                                            │
│  - 如何防止并发运行？                                            │
│                                                                 │
│  用户的困惑：                                                   │
│  ❌ 控制逻辑复杂                                                  │
│  ❌ 中断后状态不清晰                                              │
│  ❌ 并发运行导致状态混乱                                          │
└────────────────────────────────────────────────────────────────┘
```

---

### 本质问题抽象

表面痛点只是症状，真正需要解决的是 **七个本质问题**：

```
┌────────────────────────────────────────────────────────────────┐
│                     本质问题一：编排性                          │
├────────────────────────────────────────────────────────────────┤
│  问题本质：                                                     │
│  Agent 的"思考-行动-观察"循环是多阶段的协调问题                  │
│  - LLM 调用是一个阶段                                           │
│  - 工具执行是一个阶段                                           │
│  - 结果处理是一个阶段                                           │
│  - 需要决定：继续还是停止                                        │
│                                                                 │
│  核心挑战：                                                     │
│  如何让多个阶段协调执行，而不需要手动编排？                      │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│                     本质问题二：转换性                          │
├────────────────────────────────────────────────────────────────┤
│  问题本质：                                                     │
│  不同层次的消息格式是不同的"世界"                                │
│  - Agent 内部：AgentMessage[] (扩展格式)                        │
│  - LLM API：Message[] (统一格式)                                 │
│  - 提供商：Anthropic/OpenAI/Google (各异格式)                   │
│                                                                 │
│  核心挑战：                                                     │
│  如何在边界处转换，在内部统一，避免到处转换？                    │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│                     本质问题三：状态性                          │
├────────────────────────────────────────────────────────────────┤
│  问题本质：                                                     │
│  Agent 的运行状态需要持久化、可观测                              │
│  - 消息历史需要持久化                                            │
│  - 流式状态需要实时反映                                          │
│  - 工具执行状态需要跟踪                                          │
│  - 错误信息需要记录                                              │
│                                                                 │
│  核心挑战：                                                     │
│  如何让状态统一管理、实时反映、随时访问？                        │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│                     本质问题四：队列性                          │
├────────────────────────────────────────────────────────────────┤
│  问题本质：                                                     │
│  消息注入有"时机"和"数量"两个维度                                │
│  - 时机：中途注入 vs 后续注入                                    │
│  - 数量：一次一个 vs 批量处理                                    │
│  - 需要队列管理，不能直接修改正在运行的对话                      │
│                                                                 │
│  核心挑战：                                                     │
│  如何让消息在合适的时机注入，且数量可配置？                      │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│                     本质问题五：事件性                          │
├────────────────────────────────────────────────────────────────┤
│  问题本质：                                                     │
│  Agent 的生命周期是"涌现过程"，需要实时通知                      │
│  - 消息生成是逐 token 的                                         │
│  - 工具执行有开始、更新、结束                                    │
│  - 错误发生需要通知                                              │
│  - 整体有 start、turn、end                                       │
│                                                                 │
│  核心挑战：                                                     │
│  如何让所有生命周期事件实时通知订阅者？                          │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│                     本质问题六：控制性                          │
├────────────────────────────────────────────────────────────────┤
│  问题本质：                                                     │
│  Agent 的运行需要"启动、中断、等待、并发控制"                    │
│  - 启动：如何发起一个新的任务？                                  │
│  - 中断：如何取消当前运行？                                      │
│  - 等待：如何知道运行完成？                                      │
│  - 并发：如何防止多个运行同时发生？                              │
│                                                                 │
│  核心挑战：                                                     │
│  如何让运行可控，且状态清晰？                                    │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│                     本质问题七：扩展性                          │
├────────────────────────────────────────────────────────────────┤
│  问题本质：                                                     │
│  Agent 的行为需要可扩展，但不能侵入核心逻辑                      │
│  - 工具执行前后的钩子                                            │
│  - 消息转换的自定义                                              │
│  - 下轮对话的准备                                                │
│  - 停止条件的判断                                                │
│                                                                 │
│  核心挑战：                                                     │
│  如何让扩展点清晰，且不侵入核心？                                │
└────────────────────────────────────────────────────────────────┘
```

---

### 本质问题到表面问题的映射

| 表面问题 | 本质问题 | 映射关系 |
|---------|---------|---------|
| 循环协调难 | **编排性** | 手动编排 → 自动编排 |
| 消息格式混乱 | **转换性** | 到处转换 → 边界转换 |
| 工具执行复杂 | **编排性 + 扩展性** | 手动编排 + 无钩子 → 自动编排 + 钩子 |
| 状态不可观测 | **状态性** | 状态散落 → 统一管理 |
| 消息注入困难 | **队列性** | 直接修改 → 队列注入 |
| 事件通知缺失 | **事件性** | 无通知 → 实时通知 |
| 运行控制复杂 | **控制性** | 手动控制 → 自动管理 |

---

## 二、解决问题的技术方案 → 抽象核心原则

对应七个本质问题，设计遵循 **七个核心原则**：

```
┌────────────────────────────────────────────────────────────────┐
│                 原则一：自动编排原则（解决编排性）                │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  核心思想：                                                     │
│  "把循环编排自动化，让应用层只发起任务"                          │
│                                                                 │
│  技术方案：                                                     │
│  ┌──────────────────────────────────────────────┐              │
│  │  agentLoop() 函数                            │              │
│  │  - runLoop(): 主循环逻辑                     │              │
│  │  - 自动协调 LLM → 工具 → 结果 → 继续或停止   │              │
│  │  - 应用层只需要调用一次                       │              │
│  └──────────────────────────────────────────────┘              │
│                                                                 │
│  关键技术：                                                     │
│  - 循环自动化：while (hasMoreToolCalls)                         │
│  - 条件判断：stopReason === "end_turn" → 继续                   │
│  - 事件发射：emit({ type: "turn_start/end" })                   │
│                                                                 │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│                 原则二：边界转换原则（解决转换性）                │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  核心思想：                                                     │
│  "在边界处转换，在内部统一，避免到处转换"                        │
│                                                                 │
│  技术方案：                                                     │
│  ┌──────────────────────────────────────────────┐              │
│  │  streamAssistantResponse() 函数              │              │
│  │  - AgentMessage[] (内部)                     │              │
│  │  - convertToLlm() → Message[] (边界)         │              │
│  │  - 调用统一 API                              │              │
│  │  - 结果转换回 AgentMessage[]                 │              │
│  └──────────────────────────────────────────────┘              │
│                                                                 │
│  关键技术：                                                     │
│  - 转换函数：convertToLlm(messages)                             │
│  - 时机控制：只在 LLM 调用前转换                                 │
│  - 可扩展：应用层可自定义转换逻辑                                │
│                                                                 │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│                 原则三：状态集中原则（解决状态性）                │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  核心思想：                                                     │
│  "状态集中管理，实时反映，随时访问"                              │
│                                                                 │
│  技术方案：                                                     │
│  ┌──────────────────────────────────────────────┐              │
│  │  AgentState 结构                            │              │
│  │  - messages: 消息历史                        │              │
│  │  - tools: 工具列表                           │              │
│  │  - isStreaming: 是否在生成                   │              │
│  │  - streamingMessage: 当前生成内容            │              │
│  │  - pendingToolCalls: 正在执行的工具          │              │
│  │  - errorMessage: 错误信息                    │              │
│  └──────────────────────────────────────────────┘              │
│                                                                 │
│  关键技术：                                                     │
│  - getter/setter 模式：数组副本，避免直接修改                   │
│  - 实时更新：processEvents() 同步更新状态                       │
│  - 统一访问：agent.state.messages                               │
│                                                                 │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│                 原则四：队列模式原则（解决队列性）                │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  核心思想：                                                     │
│  "消息通过队列注入，时机和数量可配置"                            │
│                                                                 │
│  技术方案：                                                     │
│  ┌──────────────────────────────────────────────┐              │
│  │  PendingMessageQueue 类                     │              │
│  │  - enqueue(): 添加消息                       │              │
│  │  - drain(): 取出消息                         │              │
│  │  - mode: "one-at-a-time" | "all"            │              │
│  │                                              │              │
│  │  两种队列：                                  │              │
│  │  - steeringQueue: 中途注入                  │              │
│  │  - followUpQueue: 后续注入                  │              │
│  └──────────────────────────────────────────────┘              │
│                                                                 │
│  关键技术：                                                     │
│  - 队列分离：steering 和 follow-up 不同时机                     │
│  - drain 策略："one-at-a-time" 或 "all"                        │
│  - 时机控制：getSteeringMessages / getFollowUpMessages         │
│                                                                 │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│                 原则五：事件发射原则（解决事件性）                │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  核心思想：                                                     │
│  "所有生命周期事件实时发射，订阅者随时监听"                      │
│                                                                 │
│  技术方案：                                                     │
│  ┌──────────────────────────────────────────────┐              │
│  │  AgentEvent 类型                            │              │
│  │  - agent_start / agent_end                  │              │
│  │  - turn_start / turn_end                    │              │
│  │  - message_start / message_update / message_end │          │
│  │  - tool_execution_start / tool_execution_end │            │
│  │                                              │              │
│  │  subscribe(listener): 订阅机制               │              │
│  └──────────────────────────────────────────────┘              │
│                                                                 │
│  关键技术：                                                     │
│  - 层次化事件：agent → turn → message → tool                   │
│  - 实时发射：流式生成时立即发射                                  │
│  - 订阅分发：processEvents() 分发给所有订阅者                   │
│                                                                 │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│                 原则六：运行控制原则（解决控制性）                │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  核心思想：                                                     │
│  "运行对象统一管理启动、中断、等待、并发控制"                    │
│                                                                 │
│  技术方案：                                                     │
│  ┌──────────────────────────────────────────────┐              │
│  │  ActiveRun 对象                             │              │
│  │  - promise: 当前运行的 Promise               │              │
│  │  - abortController: 中断控制器               │              │
│  │  - resolve: Promise 的 resolve              │              │
│  │                                              │              │
│  │  控制方法：                                  │              │
│  │  - prompt(): 启动                            │              │
│  │  - abort(): 中断                             │              │
│  │  - waitForIdle(): 等待完成                  │              │
│  │  - activeRun 检查: 防止并发                  │              │
│  └──────────────────────────────────────────────┘              │
│                                                                 │
│  关键技术：                                                     │
│  - AbortController: 中断控制                                    │
│  - Promise 管理: waitForIdle                                    │
│  - activeRun 检查: 防止并发                                     │
│                                                                 │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│                 原则七：钩子扩展原则（解决扩展性）                │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  核心思想：                                                     │
│  "扩展点清晰且不侵入核心，通过钩子机制实现"                      │
│                                                                 │
│  技术方案：                                                     │
│  ┌──────────────────────────────────────────────┐              │
│  │  AgentLoopConfig 配置                       │              │
│  │  - beforeToolCall: 工具执行前钩子            │              │
│  │  - afterToolCall: 工具执行后钩子             │              │
│  │  - convertToLlm: 自定义消息转换              │              │
│  │  - prepareNextTurn: 下轮对话准备             │              │
│  │  - shouldStopAfterTurn: 停止条件判断         │              │
│  │  - transformContext: 上下文转换              │              │
│  └──────────────────────────────────────────────┘              │
│                                                                 │
│  关键技术：                                                     │
│  - 钩子时机：before/after 在工具执行前后调用                    │
│  - 返回值控制：beforeResult?.block 可阻止执行                   │
│  - 结果修改：afterResult 可修改工具结果                         │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

---

### 原则到问题的映射

| 本质问题 | 核心原则 | 关键技术 | 解决什么 |
|---------|---------|---------|---------|
| **编排性** | 自动编排原则 | agentLoop() + runLoop() | 自动协调 LLM → 工具 → 结果 |
| **转换性** | 边界转换原则 | convertToLlm() + 边界时机 | AgentMessage → Message，在边界处 |
| **状态性** | 状态集中原则 | AgentState + getter/setter | 统一管理、实时反映 |
| **队列性** | 队列模式原则 | PendingMessageQueue + steering/followUp | 时机和数量可配置 |
| **事件性** | 事件发射原则 | AgentEvent + subscribe() | 实时通知、层次化 |
| **控制性** | 运行控制原则 | ActiveRun + AbortController | 启动、中断、等待、并发控制 |
| **扩展性** | 钩子扩展原则 | before/after 钩子 + 自定义转换 | 清晰扩展点，不侵入核心 |

---

## 三、技术方案的实现

### 实现一：自动编排原则 → agent-loop.ts

#### 核心实现：runLoop 函数

```typescript
/**
 * 主循环逻辑：自动协调 LLM → 工具 → 结果 → 继续/停止
 */
async function runLoop(
    initialContext: AgentContext,
    newMessages: AgentMessage[],
    initialConfig: AgentLoopConfig,
    signal: AbortSignal | undefined,
    emit: AgentEventSink,
    streamFn?: StreamFn,
): Promise<void> {
    let currentContext = initialContext;
    let config = initialConfig;
    let firstTurn = true;
    let pendingMessages: AgentMessage[] = [];
    
    // 👇 外层循环：处理 follow-up 消息
    while (true) {
        let hasMoreToolCalls = true;
        
        // 👇 内层循环：处理工具调用和 steering 消息
        while (hasMoreToolCalls || pendingMessages.length > 0) {
            // 1. 处理 pending 消息
            if (pendingMessages.length > 0) {
                for (const message of pendingMessages) {
                    emit({ type: "message_start", message });
                    currentContext.messages.push(message);
                }
                pendingMessages = [];
            }
            
            // 2. 👇 调用 LLM (关键：自动编排)
            const assistantMessage = await streamAssistantResponse(
                currentContext, config, signal, emit, streamFn
            );
            newMessages.push(assistantMessage);
            
            // 3. 检查是否需要停止
            if (assistantMessage.stopReason === "error" || 
                assistantMessage.stopReason === "aborted") {
                emit({ type: "agent_end", messages: newMessages });
                return;  // 👈 自动停止
            }
            
            // 4. 👇 检查工具调用 (关键：自动决定是否继续)
            const toolCalls = assistantMessage.content.filter(c => c.type === "toolCall");
            const toolResults: ToolResultMessage[] = [];
            hasMoreToolCalls = false;
            
            if (toolCalls.length > 0) {
                // 5. 👇 执行工具 (关键：自动编排)
                const executedBatch = await executeToolCalls(
                    currentContext, assistantMessage, config, signal, emit
                );
                toolResults.push(...executedBatch.messages);
                hasMoreToolCalls = !executedBatch.terminate;  // 👈 自动判断
                
                // 6. 将工具结果加入消息列表
                for (const result of toolResults) {
                    currentContext.messages.push(result);
                    newMessages.push(result);
                }
            }
            
            // 7. 发射 turn_end 事件
            emit({ type: "turn_end", message: assistantMessage, toolResults });
            
            // 8. 检查自定义停止条件
            if (await config.shouldStopAfterTurn?.({ message, toolResults, context })) {
                emit({ type: "agent_end", messages: newMessages });
                return;  // 👈 自定义停止
            }
            
            // 9. 检查 steering 消息
            pendingMessages = (await config.getSteeringMessages?.()) || [];
        }
        
        // 👇 检查 follow-up 消息 (外层循环继续的条件)
        const followUpMessages = (await config.getFollowUpMessages?.()) || [];
        if (followUpMessages.length > 0) {
            pendingMessages = followUpMessages;
            continue;  // 👈 自动继续
        }
        
        // 没有更多消息，退出
        break;
    }
    
    emit({ type: "agent_end", messages: newMessages });
}
```

**设计要点：**

| 设计点 | 解决的问题 | 如何实现 |
|--------|-----------|---------|
| 内层循环 | **工具调用循环** | `while (hasMoreToolCalls)` |
| 外层循环 | **follow-up 消息** | `while (true)` + 检查队列 |
| 自动停止 | **何时停止** | stopReason === "error" / custom condition |
| 自动继续 | **何时继续** | hasMoreToolCalls = true / follow-up messages |
| 事件发射 | **生命周期通知** | emit() 在每个关键点 |

---

### 实现二：边界转换原则 → streamAssistantResponse 函数

```typescript
/**
 * 消息转换边界：AgentMessage[] → Message[] → 调用 LLM → AgentMessage
 */
async function streamAssistantResponse(
    context: AgentContext,
    config: AgentLoopConfig,
    signal: AbortSignal | undefined,
    emit: AgentEventSink,
    streamFn?: StreamFn,
): Promise<AssistantMessage> {
    // 1. 👇 应用内部转换 (可选)
    let messages = context.messages;  // AgentMessage[]
    if (config.transformContext) {
        messages = await config.transformContext(messages, signal);
    }
    
    // 2. 👇 关键转换边界：AgentMessage[] → Message[]
    const llmMessages = await config.convertToLlm(messages);
    
    // 3. 👇 构造统一 LLM context
    const llmContext: Context = {
        systemPrompt: context.systemPrompt,
        messages: llmMessages,  // 👈 Message[] (统一格式)
        tools: context.tools,
    };
    
    // 4. 👇 调用统一 API (不关心是哪个提供商)
    const streamFunction = streamFn || streamSimple;
    const response = await streamFunction(config.model, llmContext, {
        ...config,
        apiKey: await config.getApiKey?.(config.model.provider) || config.apiKey,
        signal,
    });
    
    // 5. 👇 处理流式事件，实时发射
    let partialMessage: AssistantMessage | null = null;
    
    for await (const event of response) {
        switch (event.type) {
            case "start":
                partialMessage = event.partial;
                emit({ type: "message_start", message: partialMessage });
                break;
            
            case "text_delta":
                partialMessage = event.partial;
                emit({ type: "message_update", message: partialMessage });
                break;
            
            case "done":
                const finalMessage = await response.result();
                emit({ type: "message_end", message: finalMessage });
                return finalMessage;  // 👈 AssistantMessage (内部格式)
        }
    }
}
```

**设计要点：**

| 设计点 | 解决的问题 | 如何实现 |
|--------|-----------|---------|
| 转换时机 | **何时转换** | 只在 LLM 调用前 |
| 转换函数 | **如何转换** | `convertToLlm(messages)` |
| 统一格式 | **屏蔽差异** | `Message[]` 是统一格式 |
| 流式处理 | **实时发射** | `for await (event)` + emit |
| 结果格式 | **内部格式** | `AssistantMessage` |

---

### 实现三：状态集中原则 → Agent 类

```typescript
/**
 * 状态集中管理：MutableAgentState + getter/setter
 */
function createMutableAgentState(initialState?) {
    let tools = initialState?.tools?.slice() ?? [];
    let messages = initialState?.messages?.slice() ?? [];
    
    return {
        systemPrompt: initialState?.systemPrompt ?? "",
        model: initialState?.model ?? DEFAULT_MODEL,
        thinkingLevel: initialState?.thinkingLevel ?? "off",
        
        // 👇 getter 返回副本，setter 接受并复制
        get tools() { return tools; },
        set tools(nextTools) { tools = nextTools.slice(); },
        
        get messages() { return messages; },
        set messages(nextMessages) { messages = nextMessages.slice(); },
        
        // 👇 流式状态：实时反映
        isStreaming: false,
        streamingMessage: undefined,
        pendingToolCalls: new Set<string>(),
        errorMessage: undefined,
    };
}

class Agent {
    private _state: MutableAgentState;
    
    // 👇 统一访问：agent.state.messages
    get state(): AgentState {
        return this._state;
    }
    
    // 👇 实时更新：processEvents 同步更新状态
    private async processEvents(event: AgentEvent): Promise<void> {
        switch (event.type) {
            case "message_start":
                this._state.streamingMessage = event.message;
                break;
            
            case "message_update":
                this._state.streamingMessage = event.message;
                break;
            
            case "message_end":
                this._state.streamingMessage = undefined;
                this._state.messages.push(event.message);  // 👈 持久化
                break;
            
            case "tool_execution_start":
                this._state.pendingToolCalls.add(event.toolCallId);  // 👈 实时反映
                break;
            
            case "tool_execution_end":
                this._state.pendingToolCalls.delete(event.toolCallId);
                break;
        }
        
        // 👇 分发给订阅者
        const signal = this.activeRun?.abortController.signal;
        for (const listener of this.listeners) {
            await listener(event, signal);
        }
    }
}
```

**设计要点：**

| 设计点 | 解决的问题 | 如何实现 |
|--------|-----------|---------|
| getter/setter | **避免直接修改** | 数组副本 |
| 流式状态 | **实时反映** | `isStreaming`、`streamingMessage` |
| 工具状态 | **跟踪执行** | `pendingToolCalls` Set |
| 持久化 | **消息历史** | `messages.push(event.message)` |
| 统一访问 | **随时访问** | `agent.state.messages` |

---

### 实现四：队列模式原则 → PendingMessageQueue

```typescript
/**
 * 消息队列：时机和数量可配置
 */
class PendingMessageQueue {
    private messages: AgentMessage[] = [];
    public mode: QueueMode;  // "one-at-a-time" | "all"
    
    constructor(mode: QueueMode) {
        this.mode = mode;
    }
    
    // 👇 添加消息
    enqueue(message: AgentMessage): void {
        this.messages.push(message);
    }
    
    // 👇 取出消息：根据 mode 决定数量
    drain(): AgentMessage[] {
        if (this.mode === "all") {
            // 👈 批量取出
            const drained = this.messages.slice();
            this.messages = [];
            return drained;
        }
        
        // 👈 一次一个
        const first = this.messages[0];
        if (!first) return [];
        this.messages = this.messages.slice(1);
        return [first];
    }
    
    clear(): void {
        this.messages = [];
    }
}

class Agent {
    private readonly steeringQueue: PendingMessageQueue;
    private readonly followUpQueue: PendingMessageQueue;
    
    constructor(options: AgentOptions) {
        // 👇 时机分离：steering 和 follow-up
        this.steeringQueue = new PendingMessageQueue(options.steeringMode ?? "one-at-a-time");
        this.followUpQueue = new PendingMessageQueue(options.followUpMode ?? "one-at-a-time");
    }
    
    // 👇 steering: 中途注入
    steer(message: AgentMessage): void {
        this.steeringQueue.enqueue(message);
    }
    
    // 👇 follow-up: 后续注入
    followUp(message: AgentMessage): void {
        this.followUpQueue.enqueue(message);
    }
    
    // 👇 配置到 agent-loop
    private createLoopConfig(): AgentLoopConfig {
        return {
            ...
            getSteeringMessages: async () => this.steeringQueue.drain(),
            getFollowUpMessages: async () => this.followUpQueue.drain(),
        };
    }
}
```

**设计要点：**

| 设计点 | 解决的问题 | 如何实现 |
|--------|-----------|---------|
| 队列分离 | **时机不同** | steeringQueue vs followUpQueue |
| drain 策略 | **数量不同** | "one-at-a-time" vs "all" |
| enqueue | **添加消息** | `queue.enqueue(message)` |
| drain | **取出消息** | `queue.drain()` |
| 时机控制 | **何时取出** | agent-loop 的 getSteeringMessages/getFollowUpMessages |

---

### 实现五：事件发射原则 → AgentEvent + subscribe

```typescript
/**
 * 事件发射：层次化、实时通知
 */
type AgentEvent =
    | { type: "agent_start" }
    | { type: "turn_start" }
    | { type: "message_start"; message: AgentMessage }
    | { type: "message_update"; message: AgentMessage }
    | { type: "message_end"; message: AgentMessage }
    | { type: "tool_execution_start"; toolCallId, toolName, args }
    | { type: "tool_execution_end"; toolCallId, toolName, result }
    | { type: "turn_end"; message: AssistantMessage; toolResults: ToolResultMessage[] }
    | { type: "agent_end"; messages: AgentMessage[] };

class Agent {
    private readonly listeners = new Set<(event: AgentEvent, signal: AbortSignal) => Promise<void> | void>();
    
    // 👇 订阅机制
    subscribe(listener: (event: AgentEvent, signal: AbortSignal) => Promise<void> | void): () => void {
        this.listeners.add(listener);
        // 👈 返回 unsubscribe 函数
        return () => this.listeners.delete(listener);
    }
    
    // 👇 实时发射：processEvents 分发
    private async processEvents(event: AgentEvent): Promise<void> {
        // 1. 更新状态
        switch (event.type) {
            case "message_start":
                this._state.streamingMessage = event.message;
                break;
            ...
        }
        
        // 2. 👇 分发给所有订阅者
        const signal = this.activeRun?.abortController.signal;
        for (const listener of this.listeners) {
            await listener(event, signal);  // 👈 异步等待
        }
    }
}

// 👇 agent-loop 实时发射
async function runLoop(...) {
    emit({ type: "agent_start" });
    emit({ type: "turn_start" });
    
    const message = await streamAssistantResponse(...);
    emit({ type: "message_end", message });
    
    const toolResults = await executeToolCalls(...);
    emit({ type: "turn_end", message, toolResults });
    
    emit({ type: "agent_end", messages: newMessages });
}
```

**设计要点：**

| 设计点 | 解决的问题 | 如何实现 |
|--------|-----------|---------|
| 层次化事件 | **生命周期清晰** | agent → turn → message → tool |
| 实时发射 | **立即通知** | emit() 在每个关键点 |
| 订阅机制 | **监听者管理** | Set + subscribe/unsubscribe |
| 信号传递 | **中断控制** | AbortSignal 传给订阅者 |
| 异步等待 | **订阅者完成** | `await listener(event, signal)` |

---

### 实现六：运行控制原则 → ActiveRun

```typescript
/**
 * 运行控制：启动、中断、等待、并发控制
 */
type ActiveRun = {
    promise: Promise<void>;           // 当前运行的 Promise
    resolve: () => void;              // Promise 的 resolve 函数
    abortController: AbortController; // 中断控制器
};

class Agent {
    private activeRun?: ActiveRun;
    
    // 👇 启动：创建 activeRun
    private async runWithLifecycle(executor: (signal: AbortSignal) => Promise<void>): Promise<void> {
        // 1. 检查并发
        if (this.activeRun) {
            throw new Error("Agent is already processing.");
        }
        
        // 2. 👇 创建 activeRun
        const abortController = new AbortController();
        let resolvePromise = () => {};
        const promise = new Promise<void>((resolve) => {
            resolvePromise = resolve;
        });
        this.activeRun = { promise, resolve: resolvePromise, abortController };
        
        // 3. 设置流式状态
        this._state.isStreaming = true;
        
        try {
            // 4. 👇 执行任务
            await executor(abortController.signal);
        } catch (error) {
            await this.handleRunFailure(error, abortController.signal.aborted);
        } finally {
            // 5. 👇 清理 activeRun
            this.finishRun();
        }
    }
    
    // 👇 中断：调用 abortController.abort()
    abort(): void {
        this.activeRun?.abortController.abort();
    }
    
    // 👇 等待：返回 activeRun.promise
    waitForIdle(): Promise<void> {
        return this.activeRun?.promise ?? Promise.resolve();
    }
    
    // 👇 清理
    private finishRun(): void {
        this._state.isStreaming = false;
        this._state.streamingMessage = undefined;
        this.activeRun?.resolve();  // 👈 resolve Promise
        this.activeRun = undefined;
    }
    
    // 👇 启动入口：prompt()
    async prompt(input: string | AgentMessage | AgentMessage[]): Promise<void> {
        if (this.activeRun) {
            throw new Error("Agent is already processing. Use steer() or followUp().");
        }
        
        const messages = this.normalizePromptInput(input);
        await this.runWithLifecycle(async (signal) => {
            await runAgentLoop(messages, this.createContextSnapshot(), this.createLoopConfig(), 
                (event) => this.processEvents(event), signal, this.streamFn);
        });
    }
}
```

**设计要点：**

| 设计点 | 解决的问题 | 如何实现 |
|--------|-----------|---------|
| ActiveRun | **运行对象** | promise + resolve + abortController |
| 并发检查 | **防止并发** | if (this.activeRun) throw |
| 中断控制 | **AbortController** | abortController.abort() |
| 等待完成 | **waitForIdle** | activeRun.promise |
| 状态清理 | **finishRun** | resolve + isStreaming = false |
| 启动入口 | **prompt()** | runWithLifecycle |

---

### 实现七：钩子扩展原则 → AgentLoopConfig

```typescript
/**
 * 钩子扩展：清晰的扩展点，不侵入核心
 */
type AgentLoopConfig = {
    model: Model;
    
    // 👇 工具执行前钩子
    beforeToolCall?: (context: BeforeToolCallContext, signal?: AbortSignal) => Promise<BeforeToolCallResult | undefined>;
    
    // 👇 工具执行后钩子
    afterToolCall?: (context: AfterToolCallContext, signal?: AbortSignal) => Promise<AfterToolCallResult | undefined>;
    
    // 👇 自定义消息转换
    convertToLlm?: (messages: AgentMessage[]) => Message[] | Promise<Message[]>;
    
    // 👇 上下文转换
    transformContext?: (messages: AgentMessage[], signal?: AbortSignal) => Promise<AgentMessage[]>;
    
    // 👇 下轮对话准备
    prepareNextTurn?: (signal?: AbortSignal) => Promise<AgentLoopTurnUpdate | undefined>;
    
    // 👇 停止条件判断
    shouldStopAfterTurn?: (context: StopContext) => Promise<boolean>;
};

// 👇 agent-loop 中调用钩子
async function prepareToolCall(...) {
    // 1. 参数准备
    const preparedToolCall = prepareToolCallArguments(tool, toolCall);
    const validatedArgs = validateToolArguments(tool, preparedToolCall);
    
    // 2. 👇 beforeToolCall 钩子
    if (config.beforeToolCall) {
        const beforeResult = await config.beforeToolCall(
            { assistantMessage, toolCall, args: validatedArgs, context },
            signal
        );
        
        // 👈 阻止执行
        if (beforeResult?.block) {
            return {
                kind: "immediate",
                result: createErrorToolResult(beforeResult.reason || "Blocked"),
                isError: true
            };
        }
    }
    
    // 3. 返回准备好的工具调用
    return { kind: "prepared", toolCall, tool, args: validatedArgs };
}

async function finalizeExecutedToolCall(...) {
    let result = executed.result;
    let isError = executed.isError;
    
    // 👇 afterToolCall 钩子
    if (config.afterToolCall) {
        const afterResult = await config.afterToolCall(
            { assistantMessage, toolCall: prepared.toolCall, args: prepared.args, result, isError, context },
            signal
        );
        
        // 👈 修改结果
        if (afterResult) {
            result = {
                content: afterResult.content ?? result.content,
                details: afterResult.details ?? result.details,
                terminate: afterResult.terminate ?? result.terminate,
            };
            isError = afterResult.isError ?? isError;
        }
    }
    
    return { toolCall: prepared.toolCall, result, isError };
}
```

**设计要点：**

| 设计点 | 解决的问题 | 如何实现 |
|--------|-----------|---------|
| before 钩子 | **执行前检查** | beforeResult?.block 阻止 |
| after 钩子 | **结果修改** | afterResult 修改 content/details |
| 消息转换 | **自定义转换** | convertToLlm(messages) |
| 上下文转换 | **历史压缩** | transformContext(messages) |
| 停止条件 | **自定义停止** | shouldStopAfterTurn() |
| 下轮准备 | **状态更新** | prepareNextTurn() |

---

## 四、完整最小实现示例

### 最小 agent-loop.ts 实现

```typescript
// ==================== 1. 类型定义 ====================
type AgentMessage = {
    role: "user" | "assistant" | "toolResult";
    content: any[];
    timestamp: number;
};

type AgentEvent =
    | { type: "agent_start" }
    | { type: "message_start"; message: AgentMessage }
    | { type: "message_end"; message: AgentMessage }
    | { type: "turn_end"; message: AgentMessage; toolResults: AgentMessage[] }
    | { type: "agent_end"; messages: AgentMessage[] };

type AgentContext = {
    messages: AgentMessage[];
    tools: any[];
};

type AgentConfig = {
    model: any;
    convertToLlm: (messages: AgentMessage[]) => any[];
};

type EmitFn = (event: AgentEvent) => Promise<void>;

// ==================== 2. agentLoop 函数 ====================
export function agentLoop(
    prompts: AgentMessage[],
    context: AgentContext,
    config: AgentConfig,
    emit: EmitFn,
    streamFn: (model: any, messages: any[]) => Promise<any>,
): Promise<AgentMessage[]> {
    return runLoop(prompts, context, config, emit, streamFn);
}

// ==================== 3. runLoop 主循环 ====================
async function runLoop(
    prompts: AgentMessage[],
    context: AgentContext,
    config: AgentConfig,
    emit: EmitFn,
    streamFn: (model: any, messages: any[]) => Promise<any>,
): Promise<AgentMessage[]> {
    const newMessages: AgentMessage[] = [...prompts];
    context.messages.push(...prompts);
    
    // 👇 发射开始事件
    await emit({ type: "agent_start" });
    for (const prompt of prompts) {
        await emit({ type: "message_start", message: prompt });
        await emit({ type: "message_end", message: prompt });
    }
    
    // 👇 主循环
    let hasMoreToolCalls = true;
    while (hasMoreToolCalls) {
        // 1. 👇 消息转换边界：AgentMessage[] → Message[]
        const llmMessages = config.convertToLlm(context.messages);
        
        // 2. 👇 调用 LLM
        await emit({ type: "message_start", message: { role: "assistant", content: [], timestamp: Date.now() } });
        const assistantMessage = await streamFn(config.model, llmMessages);
        await emit({ type: "message_end", message: assistantMessage });
        
        newMessages.push(assistantMessage);
        context.messages.push(assistantMessage);
        
        // 3. 👇 检查工具调用
        const toolCalls = assistantMessage.content.filter(c => c.type === "toolCall");
        const toolResults: AgentMessage[] = [];
        hasMoreToolCalls = false;
        
        if (toolCalls.length > 0) {
            // 4. 👇 执行工具
            for (const toolCall of toolCalls) {
                const tool = context.tools.find(t => t.name === toolCall.name);
                const result = await tool?.execute(toolCall.id, toolCall.arguments);
                
                const toolResultMessage = {
                    role: "toolResult",
                    toolCallId: toolCall.id,
                    content: result?.content || [],
                    timestamp: Date.now(),
                };
                
                toolResults.push(toolResultMessage);
                context.messages.push(toolResultMessage);
                newMessages.push(toolResultMessage);
            }
            
            hasMoreToolCalls = true;  // 👈 继续循环
        }
        
        // 5. 👇 发射 turn_end
        await emit({ type: "turn_end", message: assistantMessage, toolResults });
    }
    
    // 👇 发射结束事件
    await emit({ type: "agent_end", messages: newMessages });
    return newMessages;
}
```

---

### 最小 agent.ts 实现

```typescript
// ==================== 1. 状态定义 ====================
type AgentState = {
    messages: AgentMessage[];
    tools: any[];
    isStreaming: boolean;
    streamingMessage?: AgentMessage;
};

function createState(initialState?: Partial<AgentState>): AgentState {
    return {
        messages: initialState?.messages?.slice() ?? [],
        tools: initialState?.tools?.slice() ?? [],
        isStreaming: false,
        streamingMessage: undefined,
    };
}

// ==================== 2. Agent 类 ====================
export class Agent {
    private _state: AgentState;
    private listeners = new Set<(event: AgentEvent) => Promise<void>>();
    private activeRun?: {
        promise: Promise<void>;
        resolve: () => void;
        abortController: AbortController;
    };
    
    constructor(initialState?: Partial<AgentState>) {
        this._state = createState(initialState);
    }
    
    // 👇 状态访问
    get state(): AgentState {
        return this._state;
    }
    
    // 👇 订阅
    subscribe(listener: (event: AgentEvent) => Promise<void>): () => void {
        this.listeners.add(listener);
        return () => this.listeners.delete(listener);
    }
    
    // 👇 启动 prompt
    async prompt(input: string | AgentMessage): Promise<void> {
        if (this.activeRun) {
            throw new Error("Agent is already processing.");
        }
        
        const message = typeof input === "string"
            ? { role: "user", content: [{ type: "text", text: input }], timestamp: Date.now() }
            : input;
        
        // 👇 创建 activeRun
        const abortController = new AbortController();
        let resolvePromise = () => {};
        const promise = new Promise<void>((resolve) => {
            resolvePromise = resolve;
        });
        this.activeRun = { promise, resolve: resolvePromise, abortController };
        
        this._state.isStreaming = true;
        
        try {
            await agentLoop(
                [message],
                { messages: this._state.messages.slice(), tools: this._state.tools },
                { model: { id: "claude-3-opus" }, convertToLlm: (msgs) => msgs },
                (event) => this.processEvents(event),
                async (model, messages) => {
                    // 👇 模拟 LLM 调用
                    return { role: "assistant", content: [{ type: "text", text: "Hello" }], timestamp: Date.now() };
                }
            );
        } finally {
            // 👇 清理
            this._state.isStreaming = false;
            this.activeRun?.resolve();
            this.activeRun = undefined;
        }
    }
    
    // 👇 中断
    abort(): void {
        this.activeRun?.abortController.abort();
    }
    
    // 👇 等待完成
    waitForIdle(): Promise<void> {
        return this.activeRun?.promise ?? Promise.resolve();
    }
    
    // 👇 处理事件
    private async processEvents(event: AgentEvent): Promise<void> {
        // 1. 更新状态
        switch (event.type) {
            case "message_end":
                this._state.messages.push(event.message);
                break;
        }
        
        // 2. 分发给订阅者
        for (const listener of this.listeners) {
            await listener(event);
        }
    }
}
```

---

### 使用示例

```typescript
// ==================== 创建 Agent ====================
const agent = new Agent({
    tools: [{
        name: "search",
        execute: async (id, args) => {
            return { content: [{ type: "text", text: `Search result for ${args.query}` }] };
        }
    }]
});

// ==================== 订阅事件 ====================
agent.subscribe(async (event) => {
    switch (event.type) {
        case "message_end":
            console.log("Message:", event.message.content);
            break;
        case "agent_end":
            console.log("Agent finished with", event.messages.length, "messages");
            break;
    }
});

// ==================== 发起 prompt ====================
await agent.prompt("Hello, can you search for 'weather'?");

// ==================== 观察状态 ====================
console.log("Messages:", agent.state.messages);
console.log("Is streaming:", agent.state.isStreaming);

// ==================== 中断 ====================
// agent.abort();

// ==================== 等待完成 ====================
await agent.waitForIdle();
```

---

## 五、总结：问题 → 原则 → 实现 → 最小示例

### 三条主线

```
┌─────────────────────────────────────────────────────────────────┐
│  表面问题         本质问题         核心原则         实现         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  循环协调难  ───►  编排性  ───►  自动编排原则  ───►  agentLoop() │
│                                                                 │
│  消息格式混乱 ───►  转换性  ───►  边界转换原则 ───►  convertToLlm │
│                                                                 │
│  状态不可观测 ───►  状态性  ───►  状态集中原则 ───►  AgentState  │
│                                                                 │
│  消息注入困难 ───►  队列性  ───►  队列模式原则 ───►  PendingQueue│
│                                                                 │
│  事件通知缺失 ───►  事件性  ───►  事件发射原则 ───►  AgentEvent │
│                                                                 │
│  运行控制复杂 ───►  控制性  ───►  运行控制原则 ───►  ActiveRun │
│                                                                 │
│  工具执行复杂 ───►  扩展性  ───►  钠子扩展原则 ───►  before/after│
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 核心启示

**1. 问题驱动设计**

```
表面痛点 → 本质问题 → 核心原则 → 技术实现
```

- 不要只解决表面症状，找到本质问题
- 一个本质问题对应一个核心原则
- 一个核心原则指导多个技术实现

**2. 分层职责清晰**

```
agent-loop.ts: 编排层 → 解决编排性、转换性、扩展性
agent.ts: 状态管理层 → 解决状态性、队列性、事件性、控制性
```

- 每一层只解决一类问题
- 不越界，不混杂

**3. 边界转换原则**

```
AgentMessage[]  ──►  Message[]  ──►  统一 API
         │               │
    Agent 内部      边界转换
```

- 在边界处转换，在内部统一
- 避免到处转换

**4. 自动化 vs 可扩展**

```
自动编排: agentLoop() 自动协调循环
可扩展: 钩子机制 (before/after) 不侵入核心
```

- 核心逻辑自动化，减少手动编排
- 扩展点清晰，通过钩子实现

---

## 六、与统一多提供商 LLM API 的关系

### agent-loop.ts 与统一 API 的连接点

```
┌─────────────────────────────────────────────────────────────────┐
│  agent-loop.ts         统一 LLM API          提供商适配器       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  AgentMessage[]  ──►  Message[]  ──►  Anthropic/OpenAI/Google   │
│         │               │                    │                  │
│    Agent 内部      统一抽象层          适配器转换               │
│                                                                 │
│  边界转换原则     异构性 → 统一抽象层    适配器模式              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**关键连接点：**

| agent-loop.ts | 统一 API | 连接方式 |
|---------------|---------|---------|
| AgentMessage[] | Message[] | convertToLlm() 在边界处转换 |
| streamAssistantResponse() | streamSimple() | 调用统一 API |
| AssistantMessageEvent | AgentEvent | 事件流向上传递 |

**agent.ts 不直接调用统一 API，通过 agent-loop 间接调用。**

---

## 七、设计模式总结

| 模式 | 解决的本质问题 | 应用场景 |
|-----|---------------|---------|
| **编排模式** | 编排性 | agentLoop() 自动协调循环 |
| **转换边界模式** | 转换性 | convertToLlm() 在边界处转换 |
| **状态管理模式** | 状态性 | AgentState 统一管理 |
| **队列模式** | 队列性 | PendingMessageQueue 时机控制 |
| **事件发射模式** | 事件性 | AgentEvent 实时通知 |
| **运行对象模式** | 控制性 | ActiveRun 启动/中断/等待 |
| **钠子模式** | 扩展性 | before/after 钩子 |

**一句话总结：**

- **agent-loop.ts** 解决"如何协调循环"的问题，通过 **自动编排原则** 和 **边界转换原则**，让应用层只发起任务，不手动编排。

- **agent.ts** 解决"如何管理状态和控制运行"的问题，通过 **状态集中原则**、**队列模式原则**、**事件发射原则**、**运行控制原则**，让状态可观测、消息可注入、事件可订阅、运行可控制。