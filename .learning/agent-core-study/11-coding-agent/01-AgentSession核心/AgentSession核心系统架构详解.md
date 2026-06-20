# AgentSession 核心系统架构详解

> 本文档系统性地介绍 AgentSession 及其关联组件的完整架构，从入口类到支持层的分层解析。

---

## 目录

1. [系统概览](#一系统概览)
2. [AgentSession 入口类](#二agentsession-入口类)
3. [SessionManager 会话管理器](#三sessionmanager-会话管理器)
4. [AgentSessionServices 服务层](#四agentsessionservices-服务层)
5. [AgentSessionRuntime 运行时管理器](#五agentsessionruntime-运行时管理器)
6. [SessionCwd 工作目录管理](#六sessioncwd-工作目录管理)
7. [架构关系图](#七架构关系图)
8. [学习路径建议](#八学习路径建议)

---

## 一、系统概览

### 1.1 核心文件列表

| 文件 | 行数 | 职责 |
|------|------|------|
| `agent-session.ts` | 3086 | **入口类** - 会话核心抽象 |
| `session-manager.ts` | 1459 | 会话持久化管理器 |
| `agent-session-services.ts` | 199 | cwd绑定的服务抽象层 |
| `agent-session-runtime.ts` | 420 | 运行时生命周期管理器 |
| `session-cwd.ts` | 60 | 工作目录验证辅助 |

### 1.2 架构分层

```
┌─────────────────────────────────────────────────────────────────────┐
│                    应用层 (Modes)                                    │
│                    interactive / print / rpc                         │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                AgentSessionRuntime (运行时管理器)                     │
│  ─────────────────────────────────────────────────────────────────  │
│  管理 session/services 生命周期                                      │
│  实现: switchSession / newSession / fork / importFromJsonl           │
└─────────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌──────────────────────────┐    ┌──────────────────────────────┐
│      AgentSession        │    │     AgentSessionServices     │
│  ─────────────────────   │    │  ──────────────────────────  │
│  会话核心抽象 (入口)      │    │  cwd 绑定的基础设施服务        │
│                          │    │                              │
│  - agent (pi-agent-core) │    │  - cwd / agentDir            │
│  - sessionManager        │◄───│  - authStorage               │
│  - prompt/steer/followUp │    │  - settingsManager           │
│  - compact               │    │  - modelRegistry             │
│  - subscribe             │    │  - resourceLoader            │
└──────────────────────────┘    └──────────────────────────────┘
              │
              ▼
┌──────────────────────────┐
│      SessionManager      │
│  ─────────────────────   │
│  会话持久化管理器         │
│                          │
│  - JSONL 文件存储        │
│  - 树状 Entry 结构       │
│  - Leaf 指针管理         │
│  - 分支/压缩支持         │
└──────────────────────────┘
```

---

## 二、AgentSession 入口类

**源文件**: `agent-session.ts` (3086行)

### 2.1 类定义与核心属性

```typescript
export class AgentSession {
  // ===== 核心实例属性 (readonly) =====
  readonly agent: Agent;                    // pi-agent-core 的 Agent 实例
  readonly sessionManager: SessionManager;  // 会话管理器
  readonly settingsManager: SettingsManager;// 设置管理器
  
  // ===== 服务层属性 =====
  readonly modelRegistry: ModelRegistry;    // 模型注册表
  readonly resourceLoader: ResourceLoader;  // 资源加载器
  readonly extensionRunner: ExtensionRunner;// 扩展运行器
  
  // ===== 状态属性 (getter) =====
  get state(): AgentState;                  // Agent 状态
  get model(): Model | undefined;           // 当前模型
  get thinkingLevel(): ThinkingLevel;       // 思维级别
  get isStreaming(): boolean;               // 是否流式输出
  get systemPrompt(): string;               // 系统提示词
  get messages(): AgentMessage[];           // 消息列表
  
  // ===== 会话属性 (getter) =====
  get sessionFile(): string | undefined;    // 会话文件路径
  get sessionId(): string;                  // 会话ID
  get sessionName(): string | undefined;    // 会话名称
  get scopedModels(): ReadonlyArray<...>;   // scoped模型列表
  get promptTemplates(): ReadonlyArray<...>; // 提示模板
}
```

### 2.2 配置接口

```typescript
export interface AgentSessionConfig {
  agent: Agent;                              // 核心 Agent 实例
  sessionManager: SessionManager;            // 会话管理器
  settingsManager: SettingsManager;          // 设置管理器
  cwd: string;                               // 工作目录
  
  // 模型配置
  scopedModels?: Array<{ model: Model; thinkingLevel?: ThinkingLevel }>;
  
  // 资源与工具
  resourceLoader: ResourceLoader;            // 资源加载器
  customTools?: ToolDefinition[];            // 自定义工具
  initialActiveToolNames?: string[];         // 初始激活工具
  allowedToolNames?: string[];               // 工具白名单
  baseToolsOverride?: Record<string, AgentTool>; // 工具覆盖
  
  // 模型与扩展
  modelRegistry: ModelRegistry;              // 模型注册表
  extensionRunnerRef?: { current?: ExtensionRunner };
  sessionStartEvent?: SessionStartEvent;
}
```

### 2.3 核心方法分类

#### 消息传递方法

```typescript
// 发送用户提示
async prompt(text: string, options?: PromptOptions): Promise<void>;

// 中断式消息（立即插入执行）
async steer(text: string, images?: ImageContent[]): Promise<void>;

// 后续式消息（等待执行完成）
async followUp(text: string, images?: ImageContent[]): Promise<void>;

// 自定义消息
async sendCustomMessage<T>(message, options?): Promise<void>;

// 用户消息（总是触发 turn）
async sendUserMessage(content, options?): Promise<void>;
```

#### 模型管理方法

```typescript
// 设置模型
async setModel(model: Model): Promise<void>;

// 循环切换模型
async cycleModel(direction?: "forward" | "backward"): Promise<ModelCycleResult | undefined>;

// 设置思维级别
setThinkingLevel(level: ThinkingLevel): void;

// 循环切换思维级别
cycleThinkingLevel(): ThinkingLevel | undefined;
```

#### 压缩方法

```typescript
// 手动压缩
async compact(customInstructions?: string): Promise<CompactionResult>;

// 中止压缩
abortCompaction(): void;
abortBranchSummary(): void;

// 设置自动压缩
setAutoCompactionEnabled(enabled: boolean): void;
```

#### 会话管理方法

```typescript
// 设置会话名称
setSessionName(name: string): void;

// 设置 scoped 模型
setScopedModels(scopedModels): void;

// 树形导航
async navigateTree(targetId, options?): Promise<NavigateTreeResult>;

// 获取 fork 用户消息
getUserMessagesForForking(): Array<{ entryId: string; text: string }>;

// 统计与导出
getSessionStats(): SessionStats;
getContextUsage(): ContextUsage | undefined;
async exportToHtml(outputPath?: string): Promise<string>;
exportToJsonl(outputPath?: string): string;
```

#### Bash 执行方法

```typescript
async executeBash(command, onChunk?, options?): Promise<BashResult>;
recordBashResult(command, result, options?): void;
abortBash(): void;
```

#### 事件订阅方法

```typescript
// 订阅事件
subscribe(listener: AgentSessionEventListener): () => void;

// 销毁会话
dispose(): void;
```

### 2.4 事件类型

```typescript
export type AgentSessionEvent =
  // Agent 事件（继承）
  | { type: 'agent_start' }
  | { type: 'agent_end'; messages: AgentMessage[]; willRetry: boolean }
  | { type: 'turn_start' }
  | { type: 'turn_end'; message: AgentMessage; toolResults?: ToolResultMessage[] }
  | { type: 'message_start'; message: AgentMessage }
  | { type: 'message_update'; message: AgentMessage; assistantMessageEvent?: any }
  | { type: 'message_end'; message: AgentMessage }
  | { type: 'tool_execution_start'; toolCallId: string; toolName: string; args: any }
  | { type: 'tool_execution_update'; toolCallId: string; toolName: string; partialResult: any }
  | { type: 'tool_execution_end'; toolCallId: string; toolName: string; result: any; isError: boolean }
  
  // Session 扩展事件
  | { type: 'queue_update'; steering: readonly string[]; followUp: readonly string[] }
  | { type: 'compaction_start'; reason: 'manual' | 'threshold' | 'overflow' }
  | { type: 'compaction_end'; reason: ...; result?: CompactionResult; aborted: boolean; willRetry: boolean }
  | { type: 'session_info_changed'; name: string | undefined }
  | { type: 'thinking_level_changed'; level: ThinkingLevel }
  | { type: 'auto_retry_start'; attempt: number; maxAttempts: number; delayMs: number; errorMessage: string }
  | { type: 'auto_retry_end'; success: boolean; attempt: number; finalError?: string };
```

### 2.5 构造函数流程

```typescript
constructor(config: AgentSessionConfig) {
  // 1. 保存核心实例
  this.agent = config.agent;
  this.sessionManager = config.sessionManager;
  this.settingsManager = config.settingsManager;
  
  // 2. 初始化私有状态
  this._scopedModels = config.scopedModels ?? [];
  this._resourceLoader = config.resourceLoader;
  this._cwd = config.cwd;
  this._modelRegistry = config.modelRegistry;
  
  // 3. 订阅 Agent 事件（内部处理）
  this._unsubscribeAgent = this.agent.subscribe(this._handleAgentEvent);
  
  // 4. 安装工具钩子
  this._installAgentToolHooks();
  
  // 5. 构建运行时（工具注册、扩展绑定）
  this._buildRuntime({
    activeToolNames: this._initialActiveToolNames,
    includeAllExtensionTools: true,
  });
}
```

### 2.6 内部事件处理流程

```typescript
private _handleAgentEvent = async (event: AgentEvent): Promise<void> => {
  // 1. 处理队列消息移除（message_start + user）
  if (event.type === "message_start" && event.message.role === "user") {
    // 从 steering 或 followUp 队列移除
    // 发送 queue_update 事件
  }
  
  // 2. 发送给扩展系统
  await this._emitExtensionEvent(event);
  
  // 3. 发送给用户监听器
  this._emit(event);
  
  // 4. 会话持久化（message_end）
  if (event.type === "message_end") {
    // 根据消息类型持久化到 SessionManager
    this.sessionManager.appendMessage(event.message);
  }
};
```

---

## 三、SessionManager 会话管理器

**源文件**: `session-manager.ts` (1459行)

### 3.1 设计理念

SessionManager 采用 **追加写入树状结构** 设计：

- **追加写入**: 永不修改已有数据，只追加新 Entry
- **树状结构**: 每个 Entry 有 `id` 和 `parentId`，形成树
- **Leaf 指针**: 跟踪当前位置，支持分支和回溯
- **JSONL 存储**: 每行一个 JSON 对象，易于解析和恢复

### 3.2 Entry 类型体系

```typescript
// 基础结构
interface SessionEntryBase {
  type: string;              // 类型标识
  id: string;                // 8位短 UUID
  parentId: string | null;   // 父节点，形成树
  timestamp: string;         // ISO 时间戳
}

// 全部 Entry 类型
type SessionEntry =
  | SessionMessageEntry          // 对话消息（核心）
  | ThinkingLevelChangeEntry     // 思维级别变更
  | ModelChangeEntry             // 模型切换
  | CompactionEntry              // 压缩摘要（核心）
  | BranchSummaryEntry           // 分支摘要
  | CustomEntry                  // 自定义数据（扩展）
  | CustomMessageEntry           // 自定义消息（扩展）
  | LabelEntry                   // 标签标记
  | SessionInfoEntry;            // 会话名称
```

### 3.3 核心 Entry 结构详解

#### SessionMessageEntry - 对话消息

```typescript
interface SessionMessageEntry extends SessionEntryBase {
  type: "message";
  message: AgentMessage;     // 完整消息对象
}

// AgentMessage 可能的角色
type AgentMessageRole = "user" | "assistant" | "toolResult" | "custom" | "bashExecution";
```

#### CompactionEntry - 压缩摘要

```typescript
interface CompactionEntry extends SessionEntryBase {
  type: "compaction";
  summary: string;           // LLM 生成的摘要
  firstKeptEntryId: string;  // 第一个保留的 Entry ID
  tokensBefore: number;      // 压缩前 token 数
  details?: unknown;         // 扩展数据（如文件操作统计）
  fromHook?: boolean;        // 是否由扩展生成
}
```

#### BranchSummaryEntry - 分支摘要

```typescript
interface BranchSummaryEntry extends SessionEntryBase {
  type: "branch_summary";
  fromId: string;            // 分叉起点
  summary: string;           // 被跳过路径的摘要
  details?: unknown;
  fromHook?: boolean;
}
```

### 3.4 SessionHeader 结构

```typescript
interface SessionHeader {
  type: "session";
  version?: number;          // 当前版本: 3
  id: string;                // UUIDv7
  timestamp: string;         // 创建时间
  cwd: string;               // 工作目录
  parentSession?: string;    // fork 来源（如果有）
}
```

### 3.5 SessionManager 类核心方法

```typescript
export class SessionManager {
  // ===== 工厂方法 =====
  static create(cwd: string, sessionDir?: string): SessionManager;
  static open(path: string, sessionDir?: string, cwdOverride?: string): SessionManager;
  static continueRecent(cwd: string, sessionDir?: string): SessionManager;
  static inMemory(cwd?: string): SessionManager;
  static forkFrom(sourcePath: string, targetCwd: string, sessionDir?: string): SessionManager;
  static async list(cwd: string, sessionDir?: string, onProgress?): Promise<SessionInfo[]>;
  static async listAll(onProgress?): Promise<SessionInfo[]>;
  
  // ===== 状态查询 =====
  getCwd(): string;
  getSessionDir(): string;
  getSessionId(): string;
  getSessionFile(): string | undefined;
  getSessionName(): string | undefined;
  isPersisted(): boolean;
  
  // ===== Entry 查询 =====
  getLeafId(): string | null;
  getLeafEntry(): SessionEntry | undefined;
  getEntry(id: string): SessionEntry | undefined;
  getChildren(parentId: string): SessionEntry[];
  getLabel(id: string): string | undefined;
  getHeader(): SessionHeader | null;
  getEntries(): SessionEntry[];
  getTree(): SessionTreeNode[];
  getBranch(fromId?: string): SessionEntry[];
  
  // ===== Entry 追加 =====
  appendMessage(message: Message | CustomMessage | BashExecutionMessage): string;
  appendThinkingLevelChange(thinkingLevel: string): string;
  appendModelChange(provider: string, modelId: string): string;
  appendCompaction(summary, firstKeptEntryId, tokensBefore, details?, fromHook?): string;
  appendCustomEntry(customType: string, data?: unknown): string;
  appendCustomMessageEntry(customType, content, display, details?): string;
  appendSessionInfo(name: string): string;
  appendLabelChange(targetId: string, label?: string): string;
  
  // ===== 分支操作 =====
  branch(branchFromId: string): void;             // 移动 leaf 指针
  resetLeaf(): void;                              // 重置 leaf 到 null
  branchWithSummary(branchFromId, summary, details?, fromHook?): string;
  createBranchedSession(leafId: string): string | undefined;
  
  // ===== 上下文构建 =====
  buildSessionContext(): SessionContext;
  
  // ===== 会话切换 =====
  newSession(options?: NewSessionOptions): string | undefined;
  setSessionFile(sessionFile: string): void;
}
```

### 3.6 buildSessionContext 核心逻辑

```typescript
function buildSessionContext(entries: SessionEntry[], leafId?: string, byId?: Map): SessionContext {
  // 1. 从 leaf 向上追溯到 root，收集路径
  const path: SessionEntry[] = [];
  let current = leaf;
  while (current) {
    path.unshift(current);  // 向前插入
    current = current.parentId ? byId.get(current.parentId) : undefined;
  }
  
  // 2. 提取状态（thinkingLevel、model）
  // 3. 查找压缩 Entry
  // 4. 构建消息列表
  
  if (compaction) {
    // 有压缩：用摘要替代历史
    messages.push(createCompactionSummaryMessage(compaction.summary));
    
    // 只保留 firstKeptEntryId 之后的消息
    // + 压缩节点之后的消息
  } else {
    // 无压缩：全部消息
  }
  
  return { messages, thinkingLevel, model };
}
```

### 3.7 持久化机制

```typescript
// 文件路径格式
// ~/.pi/agent/sessions/--D-code-project--/2026-06-19T10-30-00_abc123.jsonl

// 写入时机
_persist(entry: SessionEntry): void {
  // 只有在有 assistant 消息后才开始写入
  // 首次写入时批量写入所有已有 Entry
  // 之后追加写入单个 Entry
}
```

### 3.8 版本迁移

```typescript
const CURRENT_SESSION_VERSION = 3;

// v1 → v2: 添加 id/parentId 树结构
function migrateV1ToV2(entries: FileEntry[]): void;

// v2 → v3: hookMessage role → custom role
function migrateV2ToV3(entries: FileEntry[]): void;
```

---

## 四、AgentSessionServices 服务层

**源文件**: `agent-session-services.ts` (199行)

### 4.1 服务集合接口

```typescript
export interface AgentSessionServices {
  cwd: string;                    // 工作目录（绑定点）
  agentDir: string;               // Agent 配置目录
  authStorage: AuthStorage;       // 认证存储
  settingsManager: SettingsManager;// 设置管理器
  modelRegistry: ModelRegistry;   // 模型注册表
  resourceLoader: ResourceLoader; // 资源加载器
  diagnostics: AgentSessionRuntimeDiagnostic[]; // 启动诊断信息
}
```

### 4.2 创建服务

```typescript
export interface CreateAgentSessionServicesOptions {
  cwd: string;
  agentDir?: string;              // 默认 ~/.pi/agent
  authStorage?: AuthStorage;
  settingsManager?: SettingsManager;
  modelRegistry?: ModelRegistry;
  extensionFlagValues?: Map<string, boolean | string>;
  resourceLoaderOptions?: Omit<DefaultResourceLoaderOptions, "cwd" | "agentDir" | "settingsManager">;
}

export async function createAgentSessionServices(options): Promise<AgentSessionServices> {
  // 1. 创建/获取各组件实例
  const cwd = options.cwd;
  const agentDir = options.agentDir ?? getAgentDir();
  const authStorage = options.authStorage ?? AuthStorage.create(join(agentDir, "auth.json"));
  const settingsManager = options.settingsManager ?? SettingsManager.create(cwd, agentDir);
  const modelRegistry = options.modelRegistry ?? ModelRegistry.create(authStorage, join(agentDir, "models.json"));
  
  // 2. 创建资源加载器
  const resourceLoader = new DefaultResourceLoader({ cwd, agentDir, settingsManager });
  await resourceLoader.reload();
  
  // 3. 处理扩展 Provider 注册
  // 4. 处理扩展 Flag 值
  // 5. 收集诊断信息
  
  return { cwd, agentDir, authStorage, settingsManager, modelRegistry, resourceLoader, diagnostics };
}
```

### 4.3 从服务创建 AgentSession

```typescript
export interface CreateAgentSessionFromServicesOptions {
  services: AgentSessionServices;
  sessionManager: SessionManager;
  sessionStartEvent?: SessionStartEvent;
  model?: Model;
  thinkingLevel?: ThinkingLevel;
  scopedModels?: Array<{ model: Model; thinkingLevel?: ThinkingLevel }>;
  tools?: string[];
  noTools?: boolean;
  customTools?: ToolDefinition[];
}

export async function createAgentSessionFromServices(options): Promise<CreateAgentSessionResult> {
  // 使用已创建的服务构建 AgentSession
  return createAgentSession({
    cwd: options.services.cwd,
    agentDir: options.services.agentDir,
    authStorage: options.services.authStorage,
    settingsManager: options.services.settingsManager,
    modelRegistry: options.services.modelRegistry,
    resourceLoader: options.services.resourceLoader,
    sessionManager: options.sessionManager,
    model: options.model,
    thinkingLevel: options.thinkingLevel,
    scopedModels: options.scopedModels,
    tools: options.tools,
    noTools: options.noTools,
    customTools: options.customTools,
    sessionStartEvent: options.sessionStartEvent,
  });
}
```

### 4.4 诊断信息类型

```typescript
export interface AgentSessionRuntimeDiagnostic {
  type: "info" | "warning" | "error";
  message: string;
}

// 示例诊断信息：
// - Unknown option: --someFlag
// - Extension "..." error: ...
// - Extension flag "--..." requires a value
```

---

## 五、AgentSessionRuntime 运行时管理器

**源文件**: `agent-session-runtime.ts` (420行)

### 5.1 设计职责

AgentSessionRuntime 是 **会话生命周期的顶层管理者**：

- 拥有当前的 `AgentSession` 和 `AgentSessionServices`
- 实现会话切换操作（switch/new/fork/import）
- 管理 teardown → apply → finishReplacement 流程
- 存储运行时工厂以复用

### 5.2 类定义

```typescript
export class AgentSessionRuntime {
  private _session: AgentSession;
  private _services: AgentSessionServices;
  private readonly createRuntime: CreateAgentSessionRuntimeFactory;
  private _diagnostics: AgentSessionRuntimeDiagnostic[];
  private _modelFallbackMessage?: string;
  
  // 回调
  private rebindSession?: (session: AgentSession) => Promise<void>;
  private beforeSessionInvalidate?: () => void;
  
  // ===== 属性访问 =====
  get services(): AgentSessionServices;
  get session(): AgentSession;
  get cwd(): string;
  get diagnostics(): readonly AgentSessionRuntimeDiagnostic[];
  get modelFallbackMessage(): string | undefined;
  
  // ===== 会话切换方法 =====
  async switchSession(sessionPath, options?): Promise<{ cancelled: boolean }>;
  async newSession(options?): Promise<{ cancelled: boolean }>;
  async fork(entryId, options?): Promise<{ cancelled: boolean; selectedText?: string }>;
  async importFromJsonl(inputPath, cwdOverride?): Promise<{ cancelled: boolean }>;
  
  // ===== 销毁 =====
  async dispose(): Promise<void>;
}
```

### 5.3 会话切换流程

```typescript
// 通用流程
async switchSession(sessionPath, options?) {
  // 1. 发送 before_switch 事件（可取消）
  const beforeResult = await this.emitBeforeSwitch("resume", sessionPath);
  if (beforeResult.cancelled) return beforeResult;
  
  // 2. 创建/打开目标 SessionManager
  const sessionManager = SessionManager.open(sessionPath, ...);
  
  // 3. 验证 cwd 存在
  assertSessionCwdExists(sessionManager, this.cwd);
  
  // 4. Teardown 当前会话
  await this.teardownCurrent("resume", sessionManager.getSessionFile());
  // ↓ 发送 session_shutdown 事件
  // ↓ 执行 beforeSessionInvalidate 回调
  // ↓ 调用 session.dispose()
  
  // 5. Apply 新运行时
  this.apply(await this.createRuntime({
    cwd: sessionManager.getCwd(),
    agentDir: this.services.agentDir,
    sessionManager,
    sessionStartEvent: { type: "session_start", reason: "resume", previousSessionFile },
  }));
  // ↓ 更新 _session, _services, _diagnostics
  
  // 6. Finish 替换
  await this.finishSessionReplacement(options?.withSession);
  // ↓ 执行 rebindSession 回调
  // ↓ 执行 withSession 回调（传入 ReplacedSessionContext）
  
  return { cancelled: false };
}
```

### 5.4 各操作对比

| 操作 | SessionManager 方法 | Shutdown Reason | Start Reason |
|------|--------------------|-----------------|--------------|
| `switchSession` | `SessionManager.open()` | `"resume"` | `"resume"` |
| `newSession` | `SessionManager.create()` | `"new"` | `"new"` |
| `fork` | `createBranchedSession()` | `"fork"` | `"fork"` |
| `importFromJsonl` | `SessionManager.open()` | `"resume"` | `"resume"` |
| `dispose` | - | `"quit"` | - |

### 5.5 Teardown 流程详解

```typescript
private async teardownCurrent(reason: SessionShutdownEvent["reason"], targetSessionFile?: string): Promise<void> {
  // 1. 发送 session_shutdown 事件给扩展
  await emitSessionShutdownEvent(this.session.extensionRunner, {
    type: "session_shutdown",
    reason,
    targetSessionFile,
  });
  
  // 2. 执行同步回调（UI teardown）
  this.beforeSessionInvalidate?.();
  
  // 3. 销毁当前会话
  this.session.dispose();
}
```

### 5.6 工厂函数

```typescript
export type CreateAgentSessionRuntimeFactory = (options: {
  cwd: string;
  agentDir: string;
  sessionManager: SessionManager;
  sessionStartEvent?: SessionStartEvent;
}) => Promise<CreateAgentSessionRuntimeResult>;

export interface CreateAgentSessionRuntimeResult extends CreateAgentSessionResult {
  services: AgentSessionServices;
  diagnostics: AgentSessionRuntimeDiagnostic[];
}

// 创建初始运行时
export async function createAgentSessionRuntime(
  createRuntime: CreateAgentSessionRuntimeFactory,
  options: { cwd, agentDir, sessionManager, sessionStartEvent? },
): Promise<AgentSessionRuntime> {
  assertSessionCwdExists(options.sessionManager, options.cwd);
  const result = await createRuntime(options);
  return new AgentSessionRuntime(
    result.session,
    result.services,
    createRuntime,
    result.diagnostics,
    result.modelFallbackMessage,
  );
}
```

---

## 六、SessionCwd 工作目录管理

**源文件**: `session-cwd.ts` (60行)

### 6.1 设计目的

处理会话工作目录不存在的情况：

- 会话文件中记录的 `cwd` 可能已被删除/移动
- 需要验证并提供友好的错误提示
- 支持 cwd 覆盖选项

### 6.2 核心接口

```typescript
export interface SessionCwdIssue {
  sessionFile?: string;       // 会话文件路径
  sessionCwd: string;         // 会话记录的 cwd（不存在）
  fallbackCwd: string;        // 当前 cwd（替代）
}

export class MissingSessionCwdError extends Error {
  readonly issue: SessionCwdIssue;
}
```

### 6.3 核心函数

```typescript
// 检查 cwd 是否存在问题
export function getMissingSessionCwdIssue(
  sessionManager: SessionCwdSource,
  fallbackCwd: string,
): SessionCwdIssue | undefined;

// 格式化错误消息
export function formatMissingSessionCwdError(issue: SessionCwdIssue): string;
export function formatMissingSessionCwdPrompt(issue: SessionCwdIssue): string;

// 断言 cwd 存在（否则抛出 MissingSessionCwdError）
export function assertSessionCwdExists(sessionManager: SessionCwdSource, fallbackCwd: string): void;
```

### 6.4 使用场景

```typescript
// 在 switchSession 和 importFromJsonl 中使用
async switchSession(sessionPath, options?) {
  const sessionManager = SessionManager.open(sessionPath, ...);
  
  // 验证 cwd 存在
  assertSessionCwdExists(sessionManager, this.cwd);
  // ↑ 如果 cwd 不存在，抛出 MissingSessionCwdError
  
  // ...
}
```

---

## 七、架构关系图

### 7.1 组件依赖关系

```
┌─────────────────────────────────────────────────────────────────────┐
│                        AgentSessionRuntime                           │
│  ─────────────────────────────────────────────────────────────────  │
│                                                                     │
│  拥有并管理:                                                         │
│  ┌─────────────────┐         ┌─────────────────────┐              │
│  │   _session      │         │    _services        │              │
│  │   AgentSession  │◄────────│ AgentSessionServices│              │
│  └─────────────────┘         └─────────────────────┘              │
│         │                           │                              │
│         │ 依赖                      │ 包含                          │
│         ▼                           ▼                              │
│  ┌─────────────────┐         ┌─────────────────────┐              │
│  │ sessionManager  │         │ settingsManager     │              │
│  │ SessionManager  │         │ modelRegistry       │              │
│  └─────────────────┘         │ resourceLoader      │              │
│         │                    │ authStorage         │              │
│         │ 持久化              └─────────────────────┘              │
│         ▼                                                          │
│  ┌─────────────────────────────────────────────────┐              │
│  │              JSONL Session File                  │              │
│  │  ~/.pi/agent/sessions/--cwd--/session.jsonl     │              │
│  └─────────────────────────────────────────────────┘              │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 7.2 数据流向

```
用户输入 (prompt/steer/followUp)
         │
         ▼
    AgentSession
         │
         ├──────────────────┬─────────────────────┐
         │                  │                     │
         ▼                  ▼                     ▼
    Agent (pi-core)    SessionManager      ExtensionRunner
         │                  │                     │
         │ LLM请求           │ 持久化               │ 扩展处理
         ▼                  ▼                     ▼
    Claude API        JSONL文件            扩展回调
         │                  │                     │
         │ 响应              │                     │
         ▼                  │                     │
    AgentEvent ─────────────┼─────────────────────┘
         │                  │
         ▼                  ▼
    _handleAgentEvent   appendMessage()
         │
         ├─→ 扩展系统 (_emitExtensionEvent)
         ├─→ 用户监听器 (_emit)
         └─→ 会话持久化 (sessionManager.appendMessage)
```

### 7.3 会话切换流程

```
switchSession(sessionPath)
         │
         ├─→ emitBeforeSwitch("resume") ──→ 扩展可取消
         │
         ├─→ SessionManager.open(sessionPath)
         │
         ├─→ assertSessionCwdExists() ──→ cwd 不存在则抛错
         │
         ├─→ teardownCurrent("resume")
         │       │
         │       ├─→ emitSessionShutdownEvent()
         │       ├─→ beforeSessionInvalidate?.()
         │       └─→ session.dispose()
         │
         ├─→ createRuntime({ cwd, agentDir, sessionManager })
         │       │
         │       ├─→ createAgentSessionServices()
         │       └─→ createAgentSessionFromServices()
         │
         ├─→ apply(result) ──→ 更新 _session, _services
         │
         └─→ finishSessionReplacement(withSession)
                 │
                 ├─→ rebindSession?.()
                 └─→ withSession(createReplacedSessionContext())
```

---

## 八、学习路径建议

### 8.1 建议阅读顺序

1. **SessionManager** (`session-manager.ts`)
   - 先理解 Entry 类型体系
   - 理解树状结构和 Leaf 指针
   - 理解 buildSessionContext 的逻辑
   - 理解 JSONL 文件格式

2. **AgentSessionServices** (`agent-session-services.ts`)
   - 理解服务集合的概念
   - 理解 cwd 绑定的含义
   - 理解各服务组件的作用

3. **AgentSession** (`agent-session.ts`)
   - 理解配置接口 AgentSessionConfig
   - 理解构造函数初始化流程
   - 理解核心方法（prompt/steer/followUp）
   - 理解事件处理流程 _handleAgentEvent

4. **AgentSessionRuntime** (`agent-session-runtime.ts`)
   - 理解生命周期管理职责
   - 理解 teardown → apply → finishReplacement 流程
   - 理解各会话切换操作的差异

5. **SessionCwd** (`session-cwd.ts`)
   - 理解 cwd 验证机制
   - 理解错误处理方式

### 8.2 源码分段阅读建议

#### session-manager.ts

| 行号 | 内容 | 重点 |
|------|------|------|
| 27-150 | Entry 类型定义 | 理解各 Entry 结构 |
| 300-420 | buildSessionContext | 理解上下文构建逻辑 |
| 706-810 | SessionManager 类基础 | 理解初始化和索引构建 |
| 871-1000 | append 方法 | 理解各种 Entry 的追加 |
| 1071-1089 | getBranch/buildSessionContext | 理解树遍历 |
| 1162-1300 | branch 方法 | 理解分支操作 |
| 1306-1458 | 工厂方法 | 理解会话创建/打开 |

#### agent-session.ts

| 行号 | 内容 | 重点 |
|------|------|------|
| 122-150 | AgentSessionEvent 类型 | 理解事件体系 |
| 155-183 | AgentSessionConfig 接口 | 理解配置结构 |
| 251-342 | 构造函数 | 理解初始化流程 |
| 468-539 | _handleAgentEvent | 理解事件处理 |
| 722-811 | 状态访问 getter | 理解状态属性 |
| 961-1111 | prompt() 方法 | 理解消息发送 |
| 1610-2026 | 压缩系统 | 理解 compact/_checkCompaction |
| 2422-2521 | 自动重试 | 理解 _isRetryableError/_prepareRetry |
| 2343-2395 | _buildRuntime | 理解运行时构建 |

#### agent-session-runtime.ts

| 行号 | 内容 | 重点 |
|------|------|------|
| 29-34 | Factory 类型定义 | 理解工厂模式 |
| 67-124 | AgentSessionRuntime 类 | 理解属性和回调 |
| 160-184 | teardownCurrent/apply/finish | 理销毁和应用流程 |
| 186-243 | switchSession/newSession | 理解会话切换 |
| 245-330 | fork | 理解分叉流程 |
| 392-410 | createAgentSessionRuntime | 理解运行时创建 |

### 8.3 关键设计模式

#### 追加写入模式
SessionManager 永不修改已有 Entry，只追加。保证数据安全和可恢复。

#### Leaf 指针模式
通过移动 leafId 实现分支和回溯，不删除历史。

#### 事件转发模式
AgentSession 订阅 Agent 事件，三路转发：扩展系统 → 用户监听器 → 内部处理。

#### 服务分离模式
AgentSessionServices 独立于 AgentSession，支持 cwd 变化时复用。

#### 运行时管理模式
AgentSessionRuntime 管理生命周期，实现会话切换的标准化流程。

---

## 总结

AgentSession 核心系统采用分层设计：

1. **入口层**: `AgentSession` - 会话核心抽象，提供所有运行时 API
2. **持久化层**: `SessionManager` - JSONL 文件存储，树状 Entry 结构
3. **服务层**: `AgentSessionServices` - cwd 绑定的基础设施服务集合
4. **运行时层**: `AgentSessionRuntime` - 生命周期管理，会话切换操作
5. **辅助层**: `SessionCwd` - 工作目录验证

核心设计理念：
- **追加写入**: 数据永不修改，保证安全
- **树状结构**: Entry 通过 id/parentId 形成树，支持分支
- **事件驱动**: 通过事件连接各组件
- **cwd 绑定**: 服务随工作目录重新创建
- **分离关注点**: 持久化、服务、运行时各司其职

---

*文档生成时间: 2026-06-19*
*源文件位置: `.learning/agent-core-study/pi/coding-agent/src/core/`*