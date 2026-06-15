---
name: agent-harness-learning-guide
description: AgentHarness 核心组件学习指南 - 由浅入深的分层介绍
metadata:
  type: project
---

# AgentHarness 核心组件学习指南

本文档采用**由浅入深、层层扩散**的方式介绍 `AgentHarness` 的架构，从核心概念到实现细节，帮助你建立完整的认知框架。

## 📋 学习路线图

```
第一层：核心概念与整体定位
    ↓
第二层：核心执行流程（prompt/skill → executeTurn → runAgentLoop）
    ↓
第三层：状态管理与上下文构建（TurnState、Session、Queue）
    ↓
第四层：事件与 Hook 系统（监听器机制）
    ↓
第五层：辅助功能（压缩、树导航、工具管理）
```

---

## 🔍 第一层：核心概念与整体定位

### 1.1 AgentHarness 是什么？

**一句话定义**：AgentHarness 是 Agent 执行的**编排器**和**生命周期管理者**。

类比理解：
- **Agent Loop** 是"发动机" - 负责实际的推理和工具调用循环
- **Session** 是"日志系统" - 负责记录和持久化对话历史
- **AgentHarness** 是"驾驶员" - 负责协调发动机和日志系统，处理用户指令

### 1.2 核心职责

```
┌─────────────────────────────────────────────────────────┐
│                    AgentHarness                          │
├─────────────────────────────────────────────────────────┤
│  1. 接收用户指令 (prompt/skill/promptFromTemplate)      │
│  2. 构建执行上下文 (TurnState + Session Context)        │
│  3. 启动 Agent Loop 执行                                │
│  4. 管理 Session 写入（消息持久化）                      │
│  5. 处理队列消息（steer/followUp/nextTurn）             │
│  6. 发射事件通知（订阅机制）                            │
│  7. 提供辅助功能（compact/navigateTree）               │
└─────────────────────────────────────────────────────────┘
```

### 1.3 在系统中的位置

```
用户层:     用户输入 → prompt()/skill()/...
                ↓
编排层:     AgentHarness ← 你要学习的主角
                ↓
执行层:     Agent Loop (runAgentLoop)
                ↓
数据层:     Session (消息存储) + Model (LLM 调用)
```

---

## 🚀 第二层：核心执行流程

### 2.1 三大入口方法

AgentHarness 提供三个主要入口，对应不同的用户交互方式：

```typescript
// 1. 直接提示 - 最基础的交互方式
async prompt(text: string, options?: { images?: ImageContent[] }): Promise<AssistantMessage>

// 2. 技能调用 - 预定义的专家能力
async skill(name: string, additionalInstructions?: string): Promise<AssistantMessage>

// 3. 模板提示 - 参数化的提示模板
async promptFromTemplate(name: string, args: string[] = []): Promise<AssistantMessage>
```

**它们的共同模式**：
```typescript
async [methodName](...args): Promise<AssistantMessage> {
    // 1. 状态检查（必须是 idle）
    if (this.phase !== "idle") throw new AgentHarnessError("busy", "...");
    
    // 2. 进入 turn 阶段
    this.phase = "turn";
    const finishRunPromise = this.startRunPromise();
    
    try {
        // 3. 创建 TurnState
        const turnState = await this.createTurnState();
        
        // 4. 执行回合（核心！）
        return await this.executeTurn(turnState, [preparedInput]);
    } finally {
        // 5. 清理
        finishRunPromise();
    }
}
```

### 2.2 executeTurn - 回合执行的核心

`executeTurn` 是真正执行对话回合的方法，位于 `agent-harness.ts:553-628`。

**核心流程**：

```typescript
private async executeTurn(turnState, text, options): Promise<AssistantMessage> {
    // ① 准备消息队列
    let messages = [createUserMessage(text, options?.images)];
    
    // 如果有 nextTurnQueue，合并队列消息
    if (this.nextTurnQueue.length > 0) {
        const queuedMessages = this.nextTurnQueue.splice(0);
        messages = [...queuedMessages, messages[0]!];
    }
    
    // ② 触发 before_agent_start hook
    const beforeResult = await this.emitHook({
        type: "before_agent_start",
        prompt: text,
        images: options?.images,
        systemPrompt: turnState.systemPrompt,
        resources: turnState.resources,
    });
    
    // ③ 创建 AbortController（用于中断控制）
    const abortController = new AbortController();
    this.runAbortController = abortController;
    
    // ④ 运行 Agent Loop！
    const runResultPromise = runAgentLoop(
        messages,                    // 输入消息
        this.createContext(turnState), // 上下文
        this.createLoopConfig(...),   // Loop 配置
        (event) => this.handleAgentEvent(event, signal), // 事件处理器
        abortController.signal,       // 中断信号
        this.createStreamFn(...),     // LLM 调用函数
    );
    
    // ⑤ 处理结果
    const newMessages = await runResultPromise;
    // 找到最后一条 assistant 消息返回
    
    // ⑥ 清理
    await this.flushPendingSessionWrites();
    this.runAbortController = undefined;
}
```

**关键洞察**：
- `executeTurn` 不直接调用 LLM，而是调用 `runAgentLoop`
- `runAgentLoop` 才是真正的循环执行器（多轮工具调用）
- `executeTurn` 只是准备输入、配置上下文、处理输出

### 2.3 runAgentLoop - Agent Loop 的调用

`runAgentLoop` 来自 `../agent-loop.ts`，是独立的执行引擎。

AgentHarness 通过 `createLoopConfig` 为 Agent Loop 提供配置：

```typescript
private createLoopConfig(getTurnState, setTurnState): AgentLoopConfig {
    return {
        model: turnState.model,
        reasoning: turnState.thinkingLevel === "off" ? undefined : turnState.thinkingLevel,
        convertToLlm,  // 消息转换函数
        
        // Hook 集成点
        transformContext: async (messages) => {
            const result = await this.emitHook({ type: "context", messages });
            return result?.messages ?? messages;
        },
        
        beforeToolCall: async ({ toolCall, args }) => {
            const result = await this.emitHook({ type: "tool_call", ... });
            return result ? { block: result.block, reason: result.reason } : undefined;
        },
        
        afterToolCall: async ({ toolCall, args, result, isError }) => {
            const patch = await this.emitHook({ type: "tool_result", ... });
            return patch ? { content: patch.content, ... } : undefined;
        },
        
        // 队列消息获取
        getSteeringMessages: async () => this.drainQueuedMessages(this.steerQueue, ...),
        getFollowUpMessages: async () => this.drainQueuedMessages(this.followUpQueue, ...),
        
        // 准备下一回合
        prepareNextTurn: async () => {
            await this.flushPendingSessionWrites();
            const nextTurnState = await this.createTurnState();
            setTurnState(nextTurnState);
            return { context, model, thinkingLevel };
        },
    };
}
```

**理解要点**：
- AgentHarness 不实现 Agent Loop，而是**配置**它
- 通过 hooks 机制，Harness 在 Loop 的关键节点插入自己的逻辑
- Loop 和 Harness 是**松耦合**的 - Loop 只需要配置接口

---

## 🗂️ 第三层：状态管理与上下文构建

### 3.1 TurnState - 回合状态

`TurnState` 是一个回合执行所需的完整状态快照：

```typescript
interface AgentHarnessTurnState {
    messages: AgentMessage[];          // 当前对话历史
    resources: AgentHarnessResources;  // 技能和模板资源
    streamOptions: AgentHarnessStreamOptions; // LLM 调用选项
    sessionId: string;                 // 会话ID
    systemPrompt: string;              // 系统提示词
    model: Model<any>;                 // 当前模型
    thinkingLevel: ThinkingLevel;      // 思考级别
    tools: TTool[];                    // 所有工具
    activeTools: TTool[];              // 活跃工具
}
```

**创建流程** (`createTurnState` 方法，行 331-363)：

```typescript
private async createTurnState(): Promise<AgentHarnessTurnState> {
    // 1. 从 Session 构建上下文（消息历史）
    const context = await this.session.buildContext();
    
    // 2. 获取资源和会话元数据
    const resources = this.getResources();
    const sessionMetadata = await this.session.getMetadata();
    
    // 3. 准备工具列表
    const tools = [...this.tools.values()];
    const activeTools = this.activeToolNames
        .map((name) => this.tools.get(name))
        .filter((tool): tool is TTool => tool !== undefined);
    
    // 4. 动态生成系统提示词
    let systemPrompt = "You are a helpful assistant.";
    if (typeof this.systemPrompt === "string") {
        systemPrompt = this.systemPrompt;
    } else if (this.systemPrompt) {
        // 支持函数式系统提示词（可以根据上下文动态生成）
        systemPrompt = await this.systemPrompt({
            env: this.env,
            session: this.session,
            model: this.model,
            thinkingLevel: this.thinkingLevel,
            activeTools,
            resources,
        });
    }
    
    return { messages, resources, streamOptions, sessionId, systemPrompt, model, thinkingLevel, tools, activeTools };
}
```

### 3.2 Session 管理

AgentHarness 通过 `Session` 对象管理对话历史：

**写入时机**：
```typescript
// 立即写入（idle 状态）
if (this.phase === "idle") {
    await this.session.appendMessage(message);
}

// 延迟写入（执行中状态）
else {
    this.pendingSessionWrites.push({ type: "message", message });
}
```

**延迟写入机制** (`pendingSessionWrites`)：
- 执行过程中不能直接写入 Session（会破坏当前状态）
- 放入 `pendingSessionWrites` 队列
- 在 `flushPendingSessionWrites()` 时批量写入

**支持的写入类型**：
```typescript
type PendingSessionWrite = 
    | { type: "message"; message: AgentMessage }
    | { type: "model_change"; provider: string; modelId: string }
    | { type: "thinking_level_change"; thinkingLevel: ThinkingLevel }
    | { type: "active_tools_change"; activeToolNames: string[] }
    | { type: "custom"; customType: string; data: unknown }
    | { type: "custom_message"; customType: string; content: ... }
    | { type: "label"; targetId: string; label: string }
    | { type: "session_info"; name?: string }
    | { type: "leaf"; targetId: string };
```

### 3.3 队列系统

AgentHarness 有三个消息队列，用于不同的交互场景：

```
┌─────────────────────────────────────────────────────┐
│  steerQueue (steering) - 实时干预                   │
│  用途：在执行中插入用户指令，改变 agent 行为        │
│ 时机：Agent Loop 会每轮检查                         │
│  模式：one-at-a-time 或 all                         │
└─────────────────────────────────────────────────────┘
           ↓ Agent Loop 获取: getSteeringMessages()

┌─────────────────────────────────────────────────────┐
│  followUpQueue (follow-up) - 后续追问               │
│  用途：在当前回合结束后继续对话                     │
│ 时机：Agent Loop 完成后检查                         │
│  模式：one-at-a-time 或 all                         │
└─────────────────────────────────────────────────────┘
           ↓ Agent Loop 获取: getFollowUpMessages()

┌─────────────────────────────────────────────────────┐
│  nextTurnQueue (next turn) - 下回合预加载           │
│  用途：提前准备下一个回合的输入                     │
│ 时机：在 executeTurn 开始时合并                     │
└─────────────────────────────────────────────────────┘
```

**队列操作方法**：
```typescript
// 添加 steering 消息（必须执行中）
async steer(text: string, options?: { images?: ImageContent[] }): Promise<void> {
    if (this.phase === "idle") throw new AgentHarnessError("invalid_state", "Cannot steer while idle");
    this.steerQueue.push(createUserMessage(text, options?.images));
    await this.emitQueueUpdate();
}

// 添加 follow-up 消息（必须执行中）
async followUp(text: string, options?: { images?: ImageContent[] }): Promise<void> {
    if (this.phase === "idle") throw new AgentHarnessError("invalid_state", "Cannot follow up while idle");
    this.followUpQueue.push(createUserMessage(text, options?.images));
    await this.emitQueueUpdate();
}

// 添加 next-turn 消息（任何时刻）
async nextTurn(text: string, options?: { images?: ImageContent[] }): Promise<void> {
    this.nextTurnQueue.push(createUserMessage(text, options?.images));
    await this.emitQueueUpdate();
}
```

---

## 📡 第四层：事件与 Hook 系统

### 4.1 事件系统架构

AgentHarness 有一个灵活的事件系统，支持两种模式：

```
模式 1: subscribe() - 订阅所有事件
    → listener(event, signal)
    → 用于日志、监控等全局观察

模式 2: on() - 监听特定事件类型
    → handler(event)
    → 可以返回结果，影响执行流程（Hook）
```

**事件类型分类**：

```typescript
// ① 自身事件（AgentHarness 发出）
type AgentHarnessOwnEvent = 
    | { type: "queue_update"; steer: UserMessage[]; followUp: UserMessage[]; nextTurn: AgentMessage[] }
    | { type: "save_point"; hadPendingMutations: boolean }
    | { type: "settled"; nextTurnCount: number }
    | { type: "abort"; clearedSteer: UserMessage[]; clearedFollowUp: UserMessage[] }
    | { type: "model_update"; model: Model<any>; previousModel: Model<any>; source: "set" }
    | { type: "thinking_level_update"; level: ThinkingLevel; previousLevel: ThinkingLevel }
    | { type: "tools_update"; ... }
    | { type: "resources_update"; ... }
    | { type: "after_provider_response"; status: number; headers: Record<string, string> }
    | { type: "session_compact"; compactionEntry: CompactionEntry; fromHook: boolean }
    | { type: "session_tree"; newLeafId: string; oldLeafId: string; ... };

// ② Hook 事件（可以返回结果影响流程）
type AgentHarnessHookEvent = 
    | { type: "before_agent_start"; prompt: string; images?: ImageContent[]; ... }
    | { type: "context"; messages: AgentMessage[] }
    | { type: "tool_call"; toolCallId: string; toolName: string; input: Record<string, unknown> }
    | { type: "tool_result"; toolCallId: string; toolName: string; input: Record<string, unknown>; content: string; ... }
    | { type: "before_provider_request"; model: Model<any>; sessionId: string; streamOptions: ... }
    | { type: "before_provider_payload"; model: Model<any>; payload: unknown }
    | { type: "session_before_compact"; preparation: ...; branchEntries: ...; ... }
    | { type: "session_before_tree"; preparation: ...; signal: AbortSignal };

// ③ Agent 事件（来自 Agent Loop）
type AgentEvent = 
    | { type: "message_start"; message: AgentMessage }
    | { type: "message_end"; message: AgentMessage }
    | { type: "turn_end"; message: AgentMessage; toolResults: ToolResult[] }
    | { type: "agent_end"; messages: AgentMessage[] }
    | { type: "text_delta"; delta: string }
    | { type: "tool_call_delta"; ... };
```

### 4.2 事件发射机制

**三类 emit 方法**：

```typescript
// ① emitOwn - 发射自身事件（只通知订阅者）
private async emitOwn(event: AgentHarnessOwnEvent, signal?: AbortSignal): Promise<void> {
    for (const listener of this.getHandlers(SUBSCRIBER_EVENT_TYPE) ?? []) {
        await listener(event, signal);
    }
}

// ② emitAny - 发射任意事件（只通知订阅者）
private async emitAny(event: AgentHarnessEvent, signal?: AbortSignal): Promise<void> {
    for (const listener of this.getHandlers(SUBSCRIBER_EVENT_TYPE) ?? []) {
        await listener(event, signal);
    }
}

// ③ emitHook - 发射 Hook 事件（收集处理结果）
private async emitHook<TType extends keyof AgentHarnessEventResultMap>(
    event: Extract<AgentHarnessOwnEvent, { type: TType }>,
): Promise<AgentHarnessEventResultMap[TType] | undefined> {
    const handlers = this.getHandlers(event.type as TType);
    if (!handlers || handlers.size === 0) return undefined;
    
    let lastResult: AgentHarnessEventResultMap[TType] | undefined;
    for (const handler of handlers) {
        const result = await handler(event);
        if (result !== undefined) {
            lastResult = result;
        }
    }
    return lastResult;
}
```

### 4.3 Hook 的应用场景

**before_agent_start** - 在 agent 启动前注入额外消息：
```typescript
harness.on("before_agent_start", async (event) => {
    // 可以注入额外的系统消息
    return {
        messages: [
            { role: "user", content: [{ type: "text", text: "Remember to be concise" }] }
        ]
    };
});
```

**tool_call** - 阻止特定工具调用：
```typescript
harness.on("tool_call", async (event) => {
    if (event.toolName === "dangerous_tool") {
        return {
            block: true,
            reason: "This tool is disabled for safety reasons"
        };
    }
    return undefined;  // 允许调用
});
```

**tool_result** - 修改工具返回结果：
```typescript
harness.on("tool_result", async (event) => {
    if (event.toolName === "read_file") {
        // 可以过滤敏感内容
        return {
            content: event.content.replace(/API_KEY=.*/g, "API_KEY=<redacted>"),
            details: event.details,
            isError: event.isError,
        };
    }
    return undefined;  // 使用原始结果
});
```

**before_provider_request** - 动态修改请求选项：
```typescript
harness.on("before_provider_request", async (event) => {
    // 可以动态添加 headers 或修改 timeout
    return {
        streamOptions: {
            headers: { "X-Custom-Header": "value" },
            timeoutMs: 60000,
        }
    };
});
```

---

## 🔧 第五层：辅助功能

### 5.1 Compact（压缩）

**目的**：当对话历史过长时，用 LLM 生成摘要，替换早期历史。

**流程** (`compact` 方法，行 708-762)：

```
① 准备压缩
    → prepareCompaction(branchEntries, settings)
    → 确定哪些条目需要压缩

② Hook 介入
    → emitHook("session_before_compact")
    → 允许外部提供自定义摘要

③ 执行压缩
    → 如果 hook 提供了摘要 → 直接使用
    → 否则 → compact(preparation, model, ...)
    → 调用 LLM 生成摘要

④ 写入 Session
    → session.appendCompaction(summary, firstKeptEntryId, ...)
    → 记录压缩事件

⑤ 发射事件
    → emitOwn("session_compact")
```

### 5.2 NavigateTree（树导航）

**目的**：在对话树的分支间切换，可选择性生成摘要。

**流程** (`navigateTree` 方法，行 764-862)：

```
① 检查目标
    → 如果目标已是当前叶子 → 返回
    → 如果目标不存在 → 错误

② 收集条目
    → collectEntriesForBranchSummary(session, oldLeafId, targetId)
    → 找到需要摘要的条目

③ Hook 介入
    → emitHook("session_before_tree")
    → 允许取消或提供自定义摘要

④ 生成摘要（可选）
    → 如果需要且 hook 未提供
    → generateBranchSummary(entries, model, ...)

⑤ 移动叶子
    → session.moveTo(newLeafId, summary?)
    → 更新会话状态

⑥ 发射事件
    → emitOwn("session_tree")
```

**树导航的两种场景**：
```typescript
// 场景 1：切换到已存在的消息
await harness.navigateTree("msg-123");

// 场景 2：切换并生成摘要（类似 git 的 squash）
await harness.navigateTree("msg-123", { summarize: true });
```

### 5.3 工具管理

**动态工具切换**：
```typescript
// 设置全部工具
await harness.setTools([tool1, tool2, tool3]);

// 只改变活跃工具（不改变工具池）
await harness.setActiveTools(["tool1", "tool3"]);

// 获取当前工具
const allTools = harness.getTools();
const activeTools = harness.getActiveTools();
```

**工具验证机制**：
```typescript
// 构造时验证
constructor(options) {
    this.validateUniqueNames(tools.map(t => t.name), "Duplicate tool name(s)");
    this.validateToolNames(activeToolNames);
}

// setTools/setActiveTools 时验证
private validateToolNames(toolNames: string[], tools: Map<string, TTool> = this.tools): void {
    this.validateUniqueNames(toolNames, "Duplicate active tool name(s)");
    const missing = toolNames.filter((name) => !tools.has(name));
    if (missing.length > 0) throw new AgentHarnessError("invalid_argument", `Unknown tool(s): ${missing.join(", ")}`);
}
```

---

## 🎯 核心设计洞察总结

### 洞察 1：编排器模式

AgentHarness 不执行具体任务，而是**编排**各个子系统：

```
AgentHarness = 协调器
    ↓
协调 Session（存储）
协调 AgentLoop（执行）
协调 Hooks（扩展）
协调 Queues（交互）
```

### 洞察 2：状态隔离

通过 `TurnState` 实现状态隔离：

```
每回合开始 → 创建新 TurnState
    → 包含该回合需要的所有信息
    → 避免执行过程中状态变化影响当前回合
```

### 洞察 3：延迟写入

通过 `pendingSessionWrites` 实现安全写入：

```
执行中 → 暂存写入请求
回合结束 → flushPendingSessionWrites()
    → 批量写入
    → 避免破坏当前上下文
```

### 洞察 4：Hook 插件化

通过 Hook 系统实现插件化扩展：

```
关键节点 → emitHook
    → 外部处理器返回结果
    → 影响执行流程
    → 不修改 Harness 核心代码
```

### 洞察 5：队列分层

三种队列对应三种交互模式：

```
steerQueue → 实时干预（立即生效）
followUpQueue → 后续追问（回合后生效）
nextTurnQueue → 预加载（下回合生效）
```

---

## 📚 延伸学习建议

学习完 AgentHarness 后，建议继续学习：

1. **[[agent-loop]]** - 理解 Loop 如何使用 Harness 提供的配置
2. **[[session]]** - 理解 Session 的存储结构和 buildContext 机制
3. **[[compaction]]** - 深入压缩算法和摘要生成
4. **[[types-harness]]** - 理解所有类型定义的完整结构

---

**下一步行动**：
- 用调试器跟踪一次完整的 `prompt()` 调用
- 实现一个简单的 Hook 监听器，观察事件流
- 尝试使用 `steer()` 在执行中干预 agent 行为