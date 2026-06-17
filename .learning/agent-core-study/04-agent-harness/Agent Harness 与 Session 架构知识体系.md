# Agent Harness 与 Session 架构知识体系

> 本文档系统性地介绍 Agent Harness 的完整架构，从入口层到执行层，再到 Session 持久化系统的设计。

---

## 目录

1. [AgentHarness 入口层](#1-agentharness-入口层)
2. [executeTurn 执行层](#2-executeturn-执行层)
3. [AgentLoopConfig 配置层](#3-agentloopconfig-配置层)
4. [createTurnState 状态构建](#4-create-turnstate-状态构建)
5. [Session 持久化系统](#5-session-持久化系统)
6. [SessionRepo 仓库层](#6-sessionrepo-仓库层)
7. [SessionStorage 存储层](#7-sessionstorage-存储层)
8. [SessionTreeEntry 数据层](#8-sessiontreeentry-数据层)
9. [核心机制详解](#9-核心机制详解)
10. [架构总览图](#10-架构总览图)

---

## 1. AgentHarness 入口层

### 1.1 入口方法概览

AgentHarness 提供三种主要入口方法，用于触发 Agent 执行：

```typescript
class AgentHarness {
  // 基础提示入口
  async prompt(text: string, options?: { images?: ImageContent[] }): Promise<AssistantMessage>;
  
  // Skill 调用入口
  async skill(name: string, additionalInstructions?: string): Promise<AssistantMessage>;
  
  // PromptTemplate 调用入口
  async promptFromTemplate(name: string, args?: string[]): Promise<AssistantMessage>;
}
```

### 1.2 prompt()：基础对话入口

**代码位置**：`agent-harness.ts:630-643`

```typescript
async prompt(text: string, options?: { images?: ImageContent[] }): Promise<AssistantMessage> {
  // 1. 状态检查
  if (this.phase !== "idle") throw new AgentHarnessError("busy", "AgentHarness is busy");
  this.phase = "turn";
  
  // 2. 启动运行追踪
  const finishRunPromise = this.startRunPromise();
  
  try {
    // 3. 创建 Turn 状态
    const turnState = await this.createTurnState();
    
    // 4. 执行 Turn
    return await this.executeTurn(turnState, text, options);
  } catch (error) {
    this.phase = "idle";
    throw normalizeHarnessError(error, "unknown");
  } finally {
    finishRunPromise();
  }
}
```

**流程**：
```
prompt() → createTurnState() → executeTurn() → runAgentLoop() → 返回 AssistantMessage
```

### 1.3 skill()：Skill 调用入口

**代码位置**：`agent-harness.ts:645-660`

```typescript
async skill(name: string, additionalInstructions?: string): Promise<AssistantMessage> {
  if (this.phase !== "idle") throw new AgentHarnessError("busy", "AgentHarness is busy");
  this.phase = "turn";
  const finishRunPromise = this.startRunPromise();
  
  try {
    const turnState = await this.createTurnState();
    
    // 查找 Skill
    const skill = (turnState.resources.skills ?? []).find(s => s.name === name);
    if (!skill) throw new AgentHarnessError("invalid_argument", `Unknown skill: ${name}`);
    
    // 格式化 Skill 调用指令
    return await this.executeTurn(turnState, formatSkillInvocation(skill, additionalInstructions));
  } finally {
    finishRunPromise();
  }
}
```

**Skill 格式化**（`skills.ts`）：

```typescript
function formatSkillInvocation(skill: Skill, additionalInstructions?: string): string {
  return `<skill-invoke>
<name>${skill.name}</name>
<description>${skill.description}</description>
<path>${skill.filePath}</path>
${additionalInstructions ? `<additional-instructions>${additionalInstructions}</additional-instructions>` : ''}
</skill-invoke>

${skill.content}`;
}
```

### 1.4 promptFromTemplate()：模板调用入口

**代码位置**：`agent-harness.ts:662-677`

```typescript
async promptFromTemplate(name: string, args: string[] = []): Promise<AssistantMessage> {
  if (this.phase !== "idle") throw new AgentHarnessError("busy", "AgentHarness is busy");
  this.phase = "turn";
  const finishRunPromise = this.startRunPromise();
  
  try {
    const turnState = await this.createTurnState();
    
    // 查找 Template
    const template = (turnState.resources.promptTemplates ?? []).find(t => t.name === name);
    if (!template) throw new AgentHarnessError("invalid_argument", `Unknown template: ${name}`);
    
    // 格式化 Template 调用
    return await this.executeTurn(turnState, formatPromptTemplateInvocation(template, args));
  } finally {
    finishRunPromise();
  }
}
```

### 1.5 其他入口方法

```typescript
// 队列操作（在 Turn 执行期间可用）
async steer(text: string): Promise<void>;         // 添加引导消息
async followUp(text: string): Promise<void>;      // 添加后续消息
async nextTurn(text: string): Promise<void>;      // 添加下一轮消息

// 消息追加
async appendMessage(message: AgentMessage): Promise<void>;

// Compaction
async compact(customInstructions?: string): Promise<CompactionResult>;

// 树导航（时光机）
async navigateTree(targetId: string, options?): Promise<NavigateTreeResult>;
```

---

## 2. executeTurn 执行层

### 2.1 executeTurn 核心流程

**代码位置**：`agent-harness.ts:553-628`

```typescript
private async executeTurn(
  turnState: AgentHarnessTurnState,
  text: string,
  options?: { images?: ImageContent[] }
): Promise<AssistantMessage> {
  // ===== 1. 构建初始消息 =====
  let messages: AgentMessage[] = [createUserMessage(text, options?.images)];
  
  // 合入 nextTurnQueue
  if (this.nextTurnQueue.length > 0) {
    const queuedMessages = this.nextTurnQueue.splice(0);
    messages = [...queuedMessages, messages[0]!];
  }
  
  // ===== 2. 触发 before_agent_start Hook =====
  const beforeResult = await this.emitHook({
    type: "before_agent_start",
    prompt: text,
    images: options?.images,
    systemPrompt: turnState.systemPrompt,
    resources: turnState.resources,
  });
  
  // Hook 可修改 messages 和 systemPrompt
  if (beforeResult?.messages) messages = [...messages, ...beforeResult.messages];
  
  // ===== 3. 创建 AbortController =====
  const abortController = new AbortController();
  this.runAbortController = abortController;
  
  // ===== 4. 运行 AgentLoop =====
  const runResultPromise = runAgentLoop(
    messages,                                          // 输入消息
    this.createContext(turnState, beforeResult?.systemPrompt),  // AgentContext
    this.createLoopConfig(getTurnState, setTurnState),// AgentLoopConfig
    (event) => this.handleAgentEvent(event, abortController.signal),  // Event Sink
    abortController.signal,                            // AbortSignal
    this.createStreamFn(getTurnState),                // StreamFn
  );
  
  // ===== 5. 返回结果 =====
  const newMessages = await runResultPromise;
  // 找到最后一个 assistant message
  for (let i = newMessages.length - 1; i >= 0; i--) {
    if (newMessages[i]!.role === "assistant") {
      return newMessages[i]!;
    }
  }
}
```

### 2.2 执行流程图

```
┌─────────────────────────────────────────────────────────────┐
│                    executeTurn 执行流程│
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 构建消息                                                 │
│     createUserMessage(text) + nextTurnQueue│
│         ↓                                                   │
│  2. Hook:before_agent_start                                 │
│     → 可修改 messages / systemPrompt│
│         ↓                                                   │
│  3. 创建 AbortController                                    │
│     → 支持中断执行                                           │
│         ↓                                                   │
│  4. 创建 AgentContext                                       │
│     systemPrompt + messages + tools│
│         ↓                                                   │
│  5. 创建 AgentLoopConfig                                    │
│     model + hooks + queue操作│
│         ↓                                                   │
│  6. runAgentLoop()                                          │
│     → 核心执行循环                                           │
│         ↓                                                   │
│  7. handleAgentEvent()                                      │
│     → 处理事件，写入 Session                                 │
│         ↓                                                   │
│  8. 返回 AssistantMessage│
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 AgentContext 结构

```typescript
interface AgentContext {
  systemPrompt: string;      // 系统提示
  messages: AgentMessage[];  // 消息列表
  tools: AgentTool[];        // 可用工具
}
```

### 2.4 handleAgentEvent：事件处理

**代码位置**：`agent-harness.ts:510-537`

```typescript
private async handleAgentEvent(event: AgentEvent, signal?: AbortSignal): Promise<void> {
  // message_end → 写入 Session
  if (event.type === "message_end") {
    await this.session.appendMessage(event.message);
    await this.emitAny(event, signal);
    return;
  }
  
  // turn_end → flush pending writes
  if (event.type === "turn_end") {
    await this.emitAny(event, signal);
    await this.flushPendingSessionWrites();  // 写入所有待处理的 Session 操作
    await this.emitOwn({ type: "save_point", hadPendingMutations });
    return;
  }
  
  // agent_end → 结束
  if (event.type === "agent_end") {
    await this.flushPendingSessionWrites();
    this.phase = "idle";
    await this.emitAny(event, signal);
    await this.emitOwn({ type: "settled", nextTurnCount: this.nextTurnQueue.length });
    return;
  }
  
  // 其他事件直接转发
  await this.emitAny(event, signal);
}
```

### 2.5 AgentEvent 类型

```typescript
type AgentEvent =
  | { type: "agent_start" }
  | { type: "agent_end"; messages: AgentMessage[] }
  | { type: "turn_start" }
  | { type: "turn_end"; message: AssistantMessage; toolResults: ToolResultMessage[] }
  | { type: "message_start"; message: AgentMessage }
  | { type: "message_update"; assistantMessageEvent; message: AssistantMessage }
  | { type: "message_end"; message: AgentMessage }
  | { type: "tool_execution_start"; toolCallId; toolName; args }
  | { type: "tool_execution_update"; toolCallId; toolName; partialResult }
  | { type: "tool_execution_end"; toolCallId; toolName; result; isError };
```

---

## 3. AgentLoopConfig 配置层

### 3.1 AgentLoopConfig 结构

**代码位置**：`agent-harness.ts:421-470`

```typescript
interface AgentLoopConfig {
  model: Model<any>;                          // 当前模型
  reasoning?: ThinkingLevel;                  // 思考级别
  
  // ===== 消息转换 =====
  convertToLlm: (messages: AgentMessage[]) => Promise<Message[]>;
  
  // ===== Hook 配置 =====
  transformContext?: (messages, signal) => Promise<AgentMessage[]>;
  beforeToolCall?: (params, signal) => Promise<{ block?: boolean; reason?: string }>;
  afterToolCall?: (params, signal) => Promise<ToolResultPatch>;
  
  // ===== Turn 管理 =====
  prepareNextTurn?: (context) => Promise<{
    context?: AgentContext;
    model?: Model;
    thinkingLevel?: ThinkingLevel;
  }>;
  shouldStopAfterTurn?: (context) => Promise<boolean>;
  
  // ===== Queue 操作 =====
  getSteeringMessages?: () => Promise<AgentMessage[]>;
  getFollowUpMessages?: () => Promise<AgentMessage[]>;
}
```

### 3.2 createLoopConfig 实现

```typescript
private createLoopConfig(
  getTurnState: () => AgentHarnessTurnState,
  setTurnState: (state) => void
): AgentLoopConfig {
  const turnState = getTurnState();
  
  return {
    model: turnState.model,
    reasoning: turnState.thinkingLevel === "off" ? undefined : turnState.thinkingLevel,
    
    // 消息转换
    convertToLlm,
    
    // Context Hook
    transformContext: async (messages) => {
      const result = await this.emitHook({ type: "context", messages: [...messages] });
      return result?.messages ?? messages;
    },
    
    // Tool Call Hook
    beforeToolCall: async ({ toolCall, args }) => {
      const result = await this.emitHook({
        type: "tool_call",
        toolCallId: toolCall.id,
        toolName: toolCall.name,
        input: args,
      });
      return result ? { block: result.block, reason: result.reason } : undefined;
    },
    
    // Tool Result Hook
    afterToolCall: async ({ toolCall, args, result, isError }) => {
      const patch = await this.emitHook({
        type: "tool_result",
        toolCallId: toolCall.id,
        toolName: toolCall.name,
        input: args,
        content: result.content,
        details: result.details,
        isError,
      });
      return patch ? { content: patch.content, details: patch.details, isError: patch.isError } : undefined;
    },
    
    // Prepare Next Turn
    prepareNextTurn: async () => {
      await this.flushPendingSessionWrites();
      const nextTurnState = await this.createTurnState();
      setTurnState(nextTurnState);
      return {
        context: this.createContext(nextTurnState),
        model: nextTurnState.model,
        thinkingLevel: nextTurnState.thinkingLevel,
      };
    },
    
    // Queue 操作
    getSteeringMessages: async () => this.drainQueuedMessages(this.steerQueue, this.steeringQueueMode),
    getFollowUpMessages: async () => this.drainQueuedMessages(this.followUpQueue, this.followUpQueueMode),
  };
}
```

### 3.3 Queue 机制详解

#### Queue 类型

```typescript
// Harness 内部队列
private steerQueue: UserMessage[] = [];       // 引导消息队列
private followUpQueue: UserMessage[] = [];    // 后续消息队列
private nextTurnQueue: AgentMessage[] = [];   // 下一轮消息队列

// Queue 模式
type QueueMode = "one-at-a-time" | "all";

private steeringQueueMode: QueueMode;         // 引导队列模式
private followUpQueueMode: QueueMode;         // 后续队列模式
```

#### Queue 消费逻辑

```typescript
private async drainQueuedMessages(queue: AgentMessage[], mode: QueueMode): Promise<AgentMessage[]> {
  // "all" → 取出全部
  // "one-at-a-time" → 取出一个
  const messages = mode === "all" ? queue.splice(0) : queue.splice(0, 1);
  
  if (messages.length === 0) return messages;
  
  // 触发 queue_update 事件
  await this.emitQueueUpdate();
  return messages;
}
```

#### AgentLoop 中的 Queue 使用

**代码位置**：`agent-loop.ts:155-266`

```typescript
async function runLoop(...) {
  // 初始时检查 steering 消息
  let pendingMessages: AgentMessage[] = (await config.getSteeringMessages?.()) || [];
  
  // 外层循环：处理 follow-up
  while (true) {
    let hasMoreToolCalls = true;
    
    // 内层循环：处理 tool calls 和 steering
    while (hasMoreToolCalls || pendingMessages.length > 0) {
      // 注入 pending 消息
      if (pendingMessages.length > 0) {
        for (const message of pendingMessages) {
          currentContext.messages.push(message);
          newMessages.push(message);
        }
        pendingMessages = [];
      }
      
      // 流式生成 assistant 响应
      const message = await streamAssistantResponse(...);
      
      // 处理 tool calls
      const toolCalls = message.content.filter(c => c.type === "toolCall");
      if (toolCalls.length > 0) {
        const results = await executeToolCalls(...);
        // ...
      }
      
      // prepareNextTurn →刷新 TurnState
      const nextTurnSnapshot = await config.prepareNextTurn?.(...);
      
      // 检查 steering 消息
      pendingMessages = (await config.getSteeringMessages?.()) || [];
    }
    
    // Agent 准备停止，检查 follow-up 消息
    const followUpMessages = (await config.getFollowUpMessages?.()) || [];
    if (followUpMessages.length > 0) {
      pendingMessages = followUpMessages;
      continue;  // 继续外层循环
    }
    
    break;  // 无更多消息，退出
  }
}
```

---

## 4. createTurnState 状态构建

### 4.1 AgentHarnessTurnState 结构

**代码位置**：`agent-harness.ts:158-172`

```typescript
interface AgentHarnessTurnState {
  messages: AgentMessage[];                   // 当前消息列表
  resources: AgentHarnessResources;           // Skills + PromptTemplates
  streamOptions: AgentHarnessStreamOptions;   // 流式请求配置
  sessionId: string;                          // Session ID
  systemPrompt: string;                       // 系统提示
  model: Model<any>;                          // 当前模型
  thinkingLevel: ThinkingLevel;               // 思考级别
  tools: AgentTool[];                         // 全部工具
  activeTools: AgentTool[];                   // 活跃工具
}
```

### 4.2 createTurnState 实现

**代码位置**：`agent-harness.ts:331-363`

```typescript
private async createTurnState(): Promise<AgentHarnessTurnState> {
  // ===== 1. 从 Session 构建上下文 =====
  const context = await this.session.buildContext();
  // ↑ 这是 Session 的核心方法，返回 messages + state
  
  // ===== 2. 获取资源 =====
  const resources = this.getResources();
  
  // ===== 3. 获取 Session 元数据 =====
  const sessionMetadata = await this.session.getMetadata();
  
  // ===== 4. 构建工具列表 =====
  const tools = [...this.tools.values()];
  const activeTools = this.activeToolNames
    .map(name => this.tools.get(name))
    .filter(tool => tool !== undefined);
  
  // ===== 5. 构建系统提示 =====
  let systemPrompt = "You are a helpful assistant.";
  
  if (typeof this.systemPrompt === "string") {
    systemPrompt = this.systemPrompt;
  } else if (this.systemPrompt) {
    // 动态生成系统提示
    systemPrompt = await this.systemPrompt({
      env: this.env,
      session: this.session,
      model: this.model,
      thinkingLevel: this.thinkingLevel,
      activeTools,
      resources,
    });
  }
  
  // ===== 6. 返回 TurnState =====
  return {
    messages: context.messages,
    resources,
    streamOptions: cloneStreamOptions(this.streamOptions),
    sessionId: sessionMetadata.id,
    systemPrompt,
    model: this.model,
    thinkingLevel: this.thinkingLevel,
    tools,
    activeTools,
  };
}
```

### 4.3 buildContext：Session 的核心方法

```typescript
// session.ts:114-116
async buildContext(): Promise<SessionContext> {
  return buildSessionContext(await this.getBranch());
}

async getBranch(): Promise<SessionTreeEntry[]> {
  const leafId = await this.storage.getLeafId();  // 获取当前 leaf
  return this.storage.getPathToRoot(leafId);      // 从 leaf 向上追溯
}
```

### 4.4 buildSessionContext 实现

**代码位置**：`session.ts:22-80`

```typescript
function buildSessionContext(pathEntries: SessionTreeEntry[]): SessionContext {
  // ===== 1. 恢复状态 =====
  let thinkingLevel = "off";
  let model = null;
  let activeToolNames = null;
  let compaction = null;
  
  for (const entry of pathEntries) {
    if (entry.type === "thinking_level_change") {
      thinkingLevel = entry.thinkingLevel;
    } else if (entry.type === "model_change") {
      model = { provider: entry.provider, modelId: entry.modelId };
    } else if (entry.type === "active_tools_change") {
      activeToolNames = [...entry.activeToolNames];
    } else if (entry.type === "compaction") {
      compaction = entry;
    }
  }
  
  // ===== 2. 提取消息 =====
  const messages: AgentMessage[] = [];
  
  if (compaction) {
    // 有压缩 → 用摘要替代历史
    messages.push(createCompactionSummaryMessage(compaction.summary, ...));
    
    // 只保留 firstKeptEntryId 之后的消息
    const compactionIdx = pathEntries.findIndex(e => e.id === compaction.id);
    let foundFirstKept = false;
    
    for (let i = 0; i < compactionIdx; i++) {
      if (pathEntries[i]!.id === compaction.firstKeptEntryId) foundFirstKept = true;
      if (foundFirstKept) appendMessage(pathEntries[i]!);
    }
    
    // 压缩节点之后的消息全部保留
    for (let i = compactionIdx + 1; i < pathEntries.length; i++) {
      appendMessage(pathEntries[i]!);
    }
  } else {
    // 无压缩 → 全部消息
    for (const entry of pathEntries) {
      appendMessage(entry);
    }
  }
  
  // ===== 3. 返回 SessionContext =====
  return { messages, thinkingLevel, model, activeToolNames };
}
```

### 4.5 流程图

```
┌─────────────────────────────────────────────────────────────┐
│                   createTurnState 流程│
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  session.buildContext()                                     │
│      ↓                                                      │
│  session.getBranch()                                        │
│      ↓                                                      │
│  storage.getLeafId() →当前 leafId│
│      ↓                                                      │
│  storage.getPathToRoot(leafId) → 路径 Entry[]              │
│      ↓                                                      │
│  buildSessionContext(pathEntries)│
│      │                                                      │
│      ├─→ 恢复 state: thinkingLevel, model, activeToolNames │
│      │                                                      │
│      ├─→ 处理 Compaction（如果有）│
│      │                                                      │
│      └─→ 提取 messages                                      │
│      ↓                                                      │
│  返回 SessionContext { messages, ... }                      │
│      ↓                                                      │
│  构建 systemPrompt（动态或静态）│
│      ↓                                                      │
│  返回 TurnState                                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 5. Session 持久化系统

### 5.1 Session 系统概览

Session 是**会话持久化系统**，采用**树状结构**存储对话历史，支持：
- 分支（Fork）：创建新会话，复制部分历史
- 回溯（Move）：在同一会话内移动位置
- 压缩（Compaction）：用摘要替代历史，节省 token

### 5.2 三层架构

```
┌─────────────────────────────────────────────────────────────┐
│  SessionRepo（仓库层）│
│  - 管理多个 Session│
│  - create / open / list / delete / fork                     │
└─────────────────────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────────────────────┐
│  SessionStorage（存储层）│
│  - 管理单个 Session 内的所有 Entry                          │
│  - appendEntry / getEntry / getPathToRoot                   │
└─────────────────────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────────────────────┐
│  SessionTreeEntry（数据层）│
│  - 树的节点│
│  - message / compaction / leaf / ...│
└─────────────────────────────────────────────────────────────┘
```

### 5.3 Session 类

**代码位置**：`session/session.ts:82-266`

```typescript
class Session<TMetadata extends SessionMetadata = SessionMetadata> {
  private storage: SessionStorage<TMetadata>;
  
  // ===== 读取 =====
  getMetadata(): Promise<TMetadata>;
  getLeafId(): Promise<string | null>;
  getEntry(id: string): Promise<SessionTreeEntry | undefined>;
  getEntries(): Promise<SessionTreeEntry[]>;
  getBranch(fromId?: string): Promise<SessionTreeEntry[]>;
  buildContext(): Promise<SessionContext>;
  getLabel(id: string): Promise<string | undefined>;
  getSessionName(): Promise<string | undefined>;
  
  // ===== 写入 =====
  appendMessage(message: AgentMessage): Promise<string>;
  appendThinkingLevelChange(level: string): Promise<string>;
  appendModelChange(provider: string, modelId: string): Promise<string>;
  appendActiveToolsChange(toolNames: string[]): Promise<string>;
  appendCompaction(summary, firstKeptEntryId, tokensBefore, ...): Promise<string>;
  appendCustomEntry(customType: string, data?: unknown): Promise<string>;
  appendCustomMessageEntry(customType, content, display, details): Promise<string>;
  appendLabel(targetId: string, label?: string): Promise<string>;
  appendSessionName(name: string): Promise<string>;
  
  // ===== 移动 =====
  moveTo(entryId: string | null, summary?): Promise<string | undefined>;
}
```

---

## 6. SessionRepo 仓库层

### 6.1 SessionRepo 接口

**代码位置**：`types.ts:468-478`

```typescript
interface SessionRepo<
  TMetadata extends SessionMetadata,
  TCreateOptions,
  TListOptions
> {
  create(options: TCreateOptions): Promise<Session<TMetadata>>;
  open(metadata: TMetadata): Promise<Session<TMetadata>>;
  list(options?: TListOptions): Promise<TMetadata[]>;
  delete(metadata: TMetadata): Promise<void>;
  fork(source: TMetadata, options): Promise<Session<TMetadata>>;
}
```

### 6.2 两种实现

#### JsonlSessionRepo（文件持久化）

**特点**：
- 数据存储在`.jsonl` 文件
- 每行一个 JSON 对象
- 追加写入，永不修改已有内容

**文件布局**：

```
sessions-root/
  ├── --D-code-project---/          ← cwd 编码后的目录名
  │   ├── 2026-06-16T10-30-00_abc123.jsonl
  │   └── 2026-06-16T11-00-00_def456.jsonl
  ├── --E-another-project---/
      └── 2026-06-15T09-00-00_xyz789.jsonl
```

#### InMemorySessionRepo（内存存储）

**特点**：
- 数据存储在内存Map
- 用于测试或临时会话
- 无持久化

### 6.3 Repo 方法详解

#### create：创建新会话

```typescript
async create(options: JsonlSessionCreateOptions): Promise<Session> {
  // 1. 生成 ID 和时间戳
  const id = options.id ?? createSessionId();        // UUIDv7
  const createdAt = createTimestamp();
  
  // 2. 计算文件路径
  const sessionDir = await this.getSessionDir(options.cwd);
  const filePath = `${timestamp}_${id}.jsonl`;
  
  // 3. 创建 Storage（写入 header）
  const storage = await JsonlSessionStorage.create(this.fs, filePath, {
    cwd: options.cwd,
    sessionId: id,
    parentSessionPath: options.parentSessionPath,
  });
  
  // 4. 包装返回
  return new Session(storage);
}
```

#### open：打开已有会话

```typescript
async open(metadata: JsonlSessionMetadata): Promise<Session> {
  // 1. 检查文件存在
  if (!await this.fs.exists(metadata.path)) {
    throw new SessionError("not_found", `Session not found`);
  }
  
  // 2. 加载 Storage
  const storage = await JsonlSessionStorage.open(this.fs, metadata.path);
  
  // 3. 包装返回
  return new Session(storage);
}
```

#### list：列出会话

```typescript
async list(options: JsonlSessionListOptions = {}): Promise<JsonlSessionMetadata[]> {
  // 1. 确定搜索目录
  const dirs = options.cwd 
    ? [await this.getSessionDir(options.cwd)]
    : await this.listSessionDirs();
  
  // 2. 扫描 .jsonl 文件
  const sessions: JsonlSessionMetadata[] = [];
  
  for (const dir of dirs) {
    const files = await this.fs.listDir(dir);
    const jsonlFiles = files.filter(f => f.name.endsWith(".jsonl"));
    
    // 3. 解析 header（只读第一行）
    for (const file of jsonlFiles) {
      const metadata = await loadJsonlSessionMetadata(this.fs, file.path);
      sessions.push(metadata);
    }
  }
  
  // 4. 按时间降序排序
  sessions.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
  
  return sessions;
}
```

#### fork：分叉会话

```typescript
async fork(sourceMetadata, options): Promise<Session> {
  // 1. 打开源会话
  const source = await this.open(sourceMetadata);
  
  // 2. 选择要复制的 Entry
  const forkedEntries = await getEntriesToFork(source.getStorage(), options);
  
  // 3. 创建新 Storage
  const newStorage = await JsonlSessionStorage.create(..., {
    parentSessionPath: sourceMetadata.path,  // 记录来源
  });
  
  // 4. 复制 Entry
  for (const entry of forkedEntries) {
    await newStorage.appendEntry(entry);  // 保持原 id 和 parentId
  }
  
  // 5. 返回新 Session
  return new Session(newStorage);
}
```

### 6.4 Fork 的两种模式

```typescript
// repo-utils.ts:32-51
async function getEntriesToFork(storage, options): Promise<SessionTreeEntry[]> {
  if (!options.entryId) return storage.getEntries();  // 无 entryId → 复制全部
  
  const target = await storage.getEntry(options.entryId);
  
  let effectiveLeafId: string | null;
  
  if (options.position === "at") {
    // "at" → 从 target 处分叉
    effectiveLeafId = target.id;
  } else {
    // "before" → 跳过 target，回到 parentId
    if (target.type !== "message" || target.message.role !== "user") {
      throw new SessionError("invalid_fork_target", `Not a user message`);
    }
    effectiveLeafId = target.parentId;
  }
  
  return storage.getPathToRoot(effectiveLeafId);
}
```

---

## 7. SessionStorage 存储层

### 7.1 SessionStorage 接口

**代码位置**：`types.ts:440-454`

```typescript
interface SessionStorage<TMetadata extends SessionMetadata = SessionMetadata> {
  // ===== 元数据 =====
  getMetadata(): Promise<TMetadata>;
  
  // ===== Leaf 操作 =====
  getLeafId(): Promise<string | null>;
  setLeafId(leafId: string | null): Promise<void>;  // 产生 LeafEntry
  
  // ===== Entry 操作 =====
  createEntryId(): Promise<string>;
  appendEntry(entry: SessionTreeEntry): Promise<void>;
  getEntry(id: string): Promise<SessionTreeEntry | undefined>;
  findEntries(type): Promise<Entry[]>;
  getEntries(): Promise<SessionTreeEntry[]>;
  
  // ===== 树结构 =====
  getPathToRoot(leafId: string | null): Promise<SessionTreeEntry[]>;
  
  // ===== 标签 =====
  getLabel(id: string): Promise<string | undefined>;
}
```

### 7.2 InMemorySessionStorage 实现

**代码位置**：`session/memory-storage.ts:40-131`

```typescript
class InMemorySessionStorage {
  private entries: SessionTreeEntry[];
  private byId: Map<string, SessionTreeEntry>;
  private labelsById: Map<string, string>;
  private leafId: string | null;
  private metadata: TMetadata;
  
  // ===== 追加 Entry =====
  async appendEntry(entry: SessionTreeEntry): Promise<void> {
    this.entries.push(entry);
    this.byId.set(entry.id, entry);
    updateLabelCache(this.labelsById, entry);
    
    // 自动更新 leafId
    this.leafId = entry.type === "leaf" ? entry.targetId : entry.id;
  }
  
  // ===== 设置 Leaf =====
  async setLeafId(leafId: string | null): Promise<void> {
    // 创建 LeafEntry
    const entry: LeafEntry = {
      type: "leaf",
      id: generateEntryId(this.byId),
      parentId: this.leafId,       // 当前 leaf 是父！
      timestamp: new Date().toISOString(),
      targetId: leafId,
    };
    
    this.entries.push(entry);
    this.byId.set(entry.id, entry);
    this.leafId = leafId;
  }
  
  // ===== 路径追溯 =====
  async getPathToRoot(leafId: string | null): Promise<SessionTreeEntry[]> {
    if (leafId === null) return [];
    
    const path: SessionTreeEntry[] = [];
    let current = this.byId.get(leafId);
    
    while (current) {
      path.unshift(current);      // 向前插入
      if (!current.parentId) break;
      current = this.byId.get(current.parentId);
    }
    
    return path;                  // [root, ..., leaf]
  }
}
```

### 7.3 JsonlSessionStorage 实现

**代码位置**：`session/jsonl-storage.ts:161-293`

```typescript
class JsonlSessionStorage {
  private fs: FileSystem;
  private filePath: string;
  private entries: SessionTreeEntry[];
  private byId: Map<string, SessionTreeEntry>;
  private labelsById: Map<string, string>;
  private currentLeafId: string | null;
  
  // ===== 追加 Entry =====
  async appendEntry(entry: SessionTreeEntry): Promise<void> {
    // 写入文件（追加一行）
    await this.fs.appendFile(this.filePath, `${JSON.stringify(entry)}\n`);
    
    // 更新内存状态
    this.entries.push(entry);
    this.byId.set(entry.id, entry);
    updateLabelCache(this.labelsById, entry);
    this.currentLeafId = leafIdAfterEntry(entry);
  }
  
  // ===== 打开文件 =====
  static async open(fs, filePath): Promise<JsonlSessionStorage> {
    const content = await fs.readTextFile(filePath);
    const lines = content.split("\n").filter(line => line.trim());
    
    // 解析 header（第一行）
    const header = parseHeaderLine(lines[0], filePath);
    
    // 解析所有 Entry
    const entries: SessionTreeEntry[] = [];
    let leafId: string | null = null;
    
    for (let i = 1; i < lines.length; i++) {
      const entry = parseEntryLine(lines[i], filePath, i + 1);
      entries.push(entry);
      leafId = entry.type === "leaf" ? entry.targetId : entry.id;
    }
    
    return new JsonlSessionStorage(fs, filePath, header, entries, leafId);
  }
}
```

### 7.4 追加写入的优势

| 特性 | 说明 |
|------|------|
| **永不修改已有内容** | 只 append，不覆盖 |
| **数据安全** | 即使写入失败，历史数据不受影响 |
| **易于恢复** | 文件损坏时，只需解析到最后一个有效行 |
| **支持时光机** | 所有 LeafEntry 都保留，可追溯位置历史 |

---

## 8. SessionTreeEntry 数据层

### 8.1 Entry 基础结构

```typescript
interface SessionTreeEntryBase {
  type: string;              // 类型标识
  id: string;                // 8位短 UUIDv7
  parentId: string | null;   // 父节点，形成树
  timestamp: string;         // ISO 时间戳
}
```

### 8.2 全部 Entry 类型

```typescript
type SessionTreeEntry =
  | MessageEntry            // 对话消息（核心）
  | LeafEntry               // 叶子位置标记（核心）
  | CompactionEntry         // 压缩摘要（核心）
  | ThinkingLevelChangeEntry // 思考级别变更（辅助）
  | ModelChangeEntry        // 模型切换（辅助）
  | ActiveToolsChangeEntry  // 工具集变更（辅助）
  | BranchSummaryEntry      // 分支摘要（辅助）
  | CustomEntry             // 自定义数据（扩展）
  | CustomMessageEntry      // 自定义消息（扩展）
  | LabelEntry              // 标签标记（辅助）
  | SessionInfoEntry;       // 会话名称（辅助）
```

### 8.3 核心 Entry 类型

#### MessageEntry：对话消息

```typescript
interface MessageEntry extends SessionTreeEntryBase {
  type: "message";
  message: AgentMessage;     // 完整消息对象
}

interface AgentMessage {
  role: "user" | "assistant" | "toolResult" | "custom" | ...;
  content: string | Content[];
  provider?: string;         // assistant 时记录来源
  model?: string;            // assistant 时记录模型
  thinking?: ThinkingBlock;  // 思考内容
  toolCalls?: ToolCall[];    // 工具调用
  usage?: Usage;             // token 统计
}
```

**JSON 示例**：

```json
{
  "type": "message",
  "id": "a1b2c3d4",
  "parentId": null,
  "timestamp": "2026-06-16T10:30:00.000Z",
  "message": {
    "role": "user",
    "content": "帮我写个函数"
  }
}
```

#### LeafEntry：叶子位置标记

```typescript
interface LeafEntry extends SessionTreeEntryBase {
  type: "leaf";
  targetId: string | null;   // 当前 leaf 指向的 Entry
}
```

**JSON 示例**：

```json
{
  "type": "leaf",
  "id": "l1m2n3o4",
  "parentId": "a1b2c3d4",    // 前一个 LeafEntry（形成链）
  "timestamp": "2026-06-16T10:35:00.000Z",
  "targetId": "a1b2c3d4"     // 指向当前位置
}
```

#### CompactionEntry：压缩摘要

```typescript
interface CompactionEntry extends SessionTreeEntryBase {
  type: "compaction";
  summary: string;           // 历史摘要
  firstKeptEntryId: string;  // 第一个保留的 Entry ID
  tokensBefore: number;      // 压缩前 token 数
  details?: unknown;         // 文件操作统计
  fromHook?: boolean;        // 是否由 hook 触发
}
```

**JSON 示例**：

```json
{
  "type": "compaction",
  "id": "c5d6e7f8",
  "parentId": "b4c5d6e7",
  "timestamp": "2026-06-16T11:00:00.000Z",
  "summary": "## Goal\n实现登录功能\n## Progress\n- [x] 创建表结构...",
  "firstKeptEntryId": "m3n4o5p6",
  "tokensBefore": 50000,
  "details": {
    "readFiles": ["src/auth.ts"],
    "modifiedFiles": ["src/login.ts"]
  }
}
```

### 8.4 辅助 Entry 类型

#### ThinkingLevelChangeEntry

```typescript
interface ThinkingLevelChangeEntry extends SessionTreeEntryBase {
  type: "thinking_level_change";
  thinkingLevel: string;     // "off" | "low" | "medium" | "high"
}
```

#### ModelChangeEntry

```typescript
interface ModelChangeEntry extends SessionTreeEntryBase {
  type: "model_change";
  provider: string;          // "anthropic" | "openai"
  modelId: string;           // "claude-sonnet-4-6"
}
```

#### ActiveToolsChangeEntry

```typescript
interface ActiveToolsChangeEntry extends SessionTreeEntryBase {
  type: "active_tools_change";
  activeToolNames: string[]; // ["Bash", "Read", "Write"]
}
```

#### BranchSummaryEntry

```typescript
interface BranchSummaryEntry extends SessionTreeEntryBase {
  type: "branch_summary";
  fromId: string;            // 分叉起点
  summary: string;           // 被跳过路径的摘要
}
```

#### LabelEntry

```typescript
interface LabelEntry extends SessionTreeEntryBase {
  type: "label";
  targetId: string;          // 标记目标
  label?: string;            // 标签文本（undefined =删除）
}
```

### 8.5 Entry 类型分类

| 类别 | Entry 类型 | 特点 |
|------|-----------|------|
| **对话内容** | MessageEntry | 核心数据，记录用户/助手消息 |
| **位置标记** | LeafEntry | 核心机制，标记当前位置 |
| **摘要压缩** | CompactionEntry | 核心优化，替代历史 |
| **状态变更** | ThinkingLevelChangeEntry, ModelChangeEntry, ActiveToolsChangeEntry | 记录配置变化 |
| **分支摘要** | BranchSummaryEntry | moveTo 时记录摘要 |
| **标记命名** | LabelEntry, SessionInfoEntry | 辅助功能 |
| **扩展机制** | CustomEntry, CustomMessageEntry | 应用层自定义 |

---

## 9. 核心机制详解

### 9.1 LeafEntry 与时光机

#### LeafEntry 的核心作用

```
LeafEntry = 当前位置标记
→ targetId：指向当前 Entry
→ parentId：前一个 LeafEntry（形成链）
```

#### moveTo 的完整流程

```typescript
// session.ts:246-265
async moveTo(entryId: string | null, summary?): Promise<string | undefined> {
  // 1. 验证 entry 存在
  if (entryId !== null && !(await this.storage.getEntry(entryId))) {
    throw new SessionError("not_found", `Entry not found`);
  }
  
  // 2. 移动 leafId →产生 LeafEntry
  await this.storage.setLeafId(entryId);
  
  // 3. 如果有 summary，记录 BranchSummaryEntry
  if (summary) {
    return this.appendTypedEntry({
      type: "branch_summary",
      fromId: entryId ?? "root",
      summary: summary.summary,
      ...
    });
  }
}
```

#### 时光机示例

```
初始:
A → B → C → D → E
                ↑
            Leaf1 (targetId="E")

moveTo("B"):
A → B → C → D → E
    ↑       ↑
    │    Leaf1 (历史位置，还在！)
    │
    Leaf2 (targetId="B")

继续对话:
A → B → C → D → E
    ↑
    Leaf2 → F → G
            ↑
        Leaf3 (targetId="G")

moveTo("E"):（回到原位置）
A → B → C → D → E
    ↑           ↑
    Leaf2       Leaf1
    │           ↑
    F → G       Leaf4 (targetId="E")
    ↑
Leaf3

所有 Entry 都保留！可以随时回到任意历史节点。
```

#### getPathToRoot 的作用

```typescript
async getPathToRoot(leafId: string | null): Promise<SessionTreeEntry[]> {
  // 从 leaf 向上追溯，返回从根到 leaf 的路径
  
  // leafId = "G" → [A, B, F, G]
  // leafId = "E" → [A, B, C, D, E]
}
```

**关键**：buildContext 只看当前路径，被"跳过"的 Entry 不在 messages 中。

### 9.2 Fork vs moveTo

| 操作 | Session 文件 | LeafEntry | 效果 |
|------|-------------|-----------|------|
| **fork** | 新文件 | 不产生 | 创建独立新 Session |
| **moveTo** | 同一文件 | 产生新 LeafEntry | 在同一 Session 内移动位置 |

### 9.3 Compaction 压缩机制

#### Compaction 的触发时机

```typescript
// compaction.ts:196-199
function shouldCompact(contextTokens: number, contextWindow: number, settings: CompactionSettings): boolean {
  return contextTokens > contextWindow - settings.reserveTokens;
}

// 默认设置
const DEFAULT_COMPACTION_SETTINGS = {
  enabled: true,
  reserveTokens: 16384,      // 为摘要预留
  keepRecentTokens: 20000,   // 保留最近的 token
};
```

#### Compaction 流程

```typescript
// compaction.ts:542-607
function prepareCompaction(pathEntries, settings): Result<CompactionPreparation> {
  // 1. 找到上一个 Compaction（如果有）
  let prevCompactionIndex = -1;
  for (let i = pathEntries.length - 1; i >= 0; i--) {
    if (pathEntries[i].type === "compaction") {
      prevCompactionIndex = i;
      break;
    }
  }
  
  // 2. 计算压缩边界
  const tokensBefore = estimateContextTokens(...);
  const cutPoint = findCutPoint(pathEntries, boundaryStart, boundaryEnd, settings.keepRecentTokens);
  
  // 3. 提取要压缩的消息
  const messagesToSummarize = [];
  for (let i = boundaryStart; i < cutPoint.firstKeptEntryIndex; i++) {
    const msg = getMessageFromEntry(pathEntries[i]);
    if (msg) messagesToSummarize.push(msg);
  }
  
  // 4. 返回 Preparation
  return {
    firstKeptEntryId: cutPoint.firstKeptEntry.id,
    messagesToSummarize,
    tokensBefore,
    previousSummary,
    fileOps,
  };
}
```

#### Compaction 摘要生成

```typescript
// compaction.ts:456-519
async function generateSummary(
  messages, model, reserveTokens, apiKey, ...
): Promise<Result<string>> {
  // 使用 LLM 生成结构化摘要
  // 格式：
  // ## Goal
  // ## Progress
  // ### Done
  // ### In Progress
  // ## Key Decisions
  // ## Next Steps
  // ## Critical Context
}
```

#### buildSessionContext 处理 Compaction

```typescript
// session.ts:61-77
if (compaction) {
  // 用摘要替代历史
  messages.push(createCompactionSummaryMessage(compaction.summary));
  
  // 只保留 firstKeptEntryId 之后的消息
  let foundFirstKept = false;
  for (let i = 0; i < compactionIdx; i++) {
    if (entry.id === compaction.firstKeptEntryId) foundFirstKept = true;
    if (foundFirstKept) appendMessage(entry);
  }
  
  // 压缩节点之后的消息全部保留
  for (let i = compactionIdx + 1; i < pathEntries.length; i++) {
    appendMessage(pathEntries[i]);
  }
}
```

---

## 10. 架构总览图

### 10.1 完整调用链

```
用户调用
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  AgentHarness 入口层│
│├─────────────────────────────────────────────────────────────┤
│  prompt() / skill() / promptFromTemplate()│
│  steer() / followUp() / nextTurn()│
│  compact() / navigateTree()                                  │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  executeTurn 执行层│
│├─────────────────────────────────────────────────────────────┤
│  1. createTurnState() → 从 Session 构建 TurnState│
│  2. emitHook(before_agent_start)                             │
│  3. create AgentContext                                      │
│  4. create AgentLoopConfig                                   │
│  5. runAgentLoop()                                           │
│  6. handleAgentEvent() → 写入 Session│
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  AgentLoop 执行循环│
│├─────────────────────────────────────────────────────────────┤
│  外层循环: 处理 follow-up│
│  内层循环: 处理 tool calls + steering│
││
│  streamAssistantResponse() →调用 LLM│
│  executeToolCalls() → 执行工具│
│  prepareNextTurn() →刷新 TurnState│
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  createTurnState 状态构建│
│├─────────────────────────────────────────────────────────────┤
│  session.buildContext()                                       │
│      ↓                                                       │
│  session.getBranch()                                         │
│      ↓                                                       │
│  storage.getLeafId()                                         │
│      ↓                                                       │
│  storage.getPathToRoot(leafId)                               │
│      ↓                                                       │
│  buildSessionContext(pathEntries)│
│      ↓                                                       │
│  返回 TurnState { messages, systemPrompt, tools, ... }│
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Session 持久化系统│
│├─────────────────────────────────────────────────────────────┤
│  SessionRepo (仓库层)│
│      ↓                                                       │
│  SessionStorage (存储层)                                      │
│      ↓                                                       │
│  SessionTreeEntry (数据层)│
││
│  核心机制:│
│  - LeafEntry → 时光机│
│  - CompactionEntry → 压缩│
│  - Fork → 分叉│
│  - moveTo → 回溯│
└─────────────────────────────────────────────────────────────┘
```

### 10.2 Session 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                   SessionRepo（仓库层）                       │
├─────────────────────────────────────────────────────────────┤
│  职责: 管理多个 Session 的生命周期│
│├─────────────────────────────────────────────────────────────┤
│  方法:│
│  create() → 创建新 Session（写入 header）│
│  open() → 打开已有 Session（加载全部 Entry）│
│  list() → 列出 Session（只读 header）│
│  delete() → 删除 Session│
│  fork() → 分叉 Session（复制部分 Entry）│
│├─────────────────────────────────────────────────────────────┤
│  实现:│
│  JsonlSessionRepo → 文件持久化│
│  InMemorySessionRepo → 内存存储│
└─────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│                  SessionStorage（存储层）                     │
├─────────────────────────────────────────────────────────────┤
│  职责: 管理单个 Session 内的所有 Entry│
│├─────────────────────────────────────────────────────────────┤
│  方法:│
│  getLeafId() / setLeafId() → 位置管理│
│  appendEntry() →追加节点│
│  getEntry() / findEntries() → 查询节点│
│  getPathToRoot() →路径追溯│
│  getLabel() → 标签查询│
│├─────────────────────────────────────────────────────────────┤
│  实现:│
│  JsonlSessionStorage → 文件存储（追加写入）│
│  InMemorySessionStorage → 内存存储│
│├─────────────────────────────────────────────────────────────┤
│  状态:│
│  entries[] → 所有 Entry│
│  byId Map → ID → Entry 映射│
│  labelsById Map → 标签缓存│
│  leafId → 当前位置│
└─────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│                 SessionTreeEntry（数据层）                    │
├─────────────────────────────────────────────────────────────┤
│  职责: 定义树的节点结构│
│├─────────────────────────────────────────────────────────────┤
│  基础字段:│
│  type → 类型标识│
│  id → 8位短 UUIDv7│
│  parentId → 父节点（形成树）│
│  timestamp → 时间戳│
│├─────────────────────────────────────────────────────────────┤
│  核心 Entry:│
│  MessageEntry → 对话消息│
│  LeafEntry → 位置标记│
│  CompactionEntry → 压缩摘要│
│├─────────────────────────────────────────────────────────────┤
│  辅助 Entry:│
│  ThinkingLevelChangeEntry → 思考级别│
│  ModelChangeEntry → 模型切换│
│  ActiveToolsChangeEntry → 工具集│
│  BranchSummaryEntry → 分支摘要│
│  LabelEntry → 标签│
│  SessionInfoEntry → 会话名│
│├─────────────────────────────────────────────────────────────┤
│  扩展 Entry:│
│  CustomEntry → 自定义数据│
│  CustomMessageEntry → 自定义消息│
└─────────────────────────────────────────────────────────────┘
```

---

## 总结

本文档系统性地介绍了 Agent Harness 的完整架构：

1. **入口层**：prompt、skill、promptFromTemplate 三种触发方式
2. **执行层**：executeTurn → runAgentLoop → handleAgentEvent
3. **配置层**：AgentLoopConfig（Hook、Queue、Turn 管理）
4. **状态构建**：createTurnState → session.buildContext
5. **Session 系统**：三层架构（Repo → Storage → Entry）
6. **核心机制**：LeafEntry 时光机、Compaction 压缩、Fork 分叉

**设计亮点**：
- **追加写入**：永不修改已有数据，保证安全
- **LeafEntry 链**：记录位置历史，支持时光机
- **Compaction**：用摘要替代历史，优化 token
- **Fork**：创建独立新 Session，不影响原会话

---

*文档生成时间：2026-06-17*
*代码位置：`.learning/pi/packages/agent/src/harness/`*