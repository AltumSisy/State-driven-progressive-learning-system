---
name: agent-harness-types-learning-guide
description: AgentHarness 类型系统学习指南 - 从核心概念到外围支持
metadata:
  type: project
---

# AgentHarness 类型系统学习指南

本文档采用**由内向外、层层扩展**的方式解析 `types.ts` 的类型定义，帮助你建立完整的类型认知体系。

## 📋 类型体系全景图

```
第一层：基础工具类型
    ↓ Result 类型、Error 转换、辅助函数

第二层：核心资源类型
    ↓ Skill、PromptTemplate、Resources

第三层：执行环境类型
    ↓ FileSystem、Shell、ExecutionEnv

第四层：Session 类型体系
    ↓ Entry 类型树、Storage 接口、Session API

第五层：事件与结果类型
    ↓ AgentHarness 事件、Hook 结果、配置类型

第六层：错误处理类型
    ↓ 各子系统的 Error 类定义
```

---

## 🔧 第一层：基础工具类型

### 1.1 Result 类型 - 错误处理的优雅方式

`Result<TValue, TError>` 是一个**联合类型**，用于表示可能失败的操作：

```typescript
export type Result<TValue, TError> = 
    | { ok: true; value: TValue }    // 成功分支
    | { ok: false; error: TError };  // 失败分支
```

**设计理念**：
- 不使用 `throw`，而是将错误编码在返回值中
- 强制调用者处理失败情况（必须检查 `ok`）
- 避免 try-catch 的隐性控制流

**辅助函数**：

```typescript
// 创建成功结果
ok<TValue, TError>(value: TValue): Result<TValue, TError>
    // 示例：ok("Hello") → { ok: true, value: "Hello" }

// 创建失败结果
err<TValue, TError>(error: TError): Result<TValue, TError>
    // 示例：err(new FileError("not_found", "File missing")) → { ok: false, error: ... }

// 获取值或抛出错误（用于测试或明确边界）
getOrThrow<TValue, TError>(result: Result<TValue, TError>): TValue
    // 如果 ok=true → 返回 value
    // 如果 ok=false → 抛出 error

// 获取值或 undefined（用于可选值）
getOrUndefined<TValue extends object, TError>(result: Result<TValue, TError>): TValue | undefined
    // 仅限 object 类型，避免原始值的 truthiness bug
```

**典型用法**：

```typescript
// FileSystem 的操作全部返回 Result
async readTextFile(path: string): Promise<Result<string, FileError>> {
    try {
        const content = await fs.readFile(path, "utf-8");
        return ok(content);  // 成功
    } catch (e) {
        return err(new FileError("not_found", "File not found", path));  // 失败
    }
}

// 使用时必须检查 ok
const result = await filesystem.readTextFile("config.json");
if (!result.ok) {
    console.error("Failed:", result.error.code);
    return;
}
console.log("Content:", result.value);
```

### 1.2 toError - 错误规范化

将任意 thrown 值转换为 Error 实例：

```typescript
export function toError(error: unknown): Error {
    if (error instanceof Error) return error;
    if (typeof error === "string") return new Error(error);
    try {
        return new Error(JSON.stringify(error));
    } catch {
        return new Error(String(error));
    }
}
```

**为什么需要这个**：
- JavaScript 允许 throw 任何值（`throw "oops"` 是合法的）
- Error 子类需要 Error 作为 cause
- 统一错误处理逻辑

---

## 📚 第二层：核心资源类型

### 2.1 Skill - 技能定义

Skill 是 Agent 的**专家能力**，通常来自 `SKILL.md` 文件：

```typescript
export interface Skill {
    name: string;                    // 稳定的技能名称（用于查找）
    description: string;             // 简短描述（告诉模型何时使用）
    content: string;                 // 完整的技能指令
    filePath: string;                // 技能文件的绝对路径
    disableModelInvocation?: boolean; // 禁止模型自动调用
}
```

**技能的两种调用方式**：
```typescript
// 1. 模型自主调用（在 system prompt 中列出）
// formatSkillsForSystemPrompt 将 skills 格式化为 XML 块

// 2. 应用显式调用
harness.skill("code-review");
```

**disableModelInvocation 的用途**：
```typescript
// 某些技能只想被应用代码调用，不想让模型随意触发
const internalSkill = {
    name: "internal-debug",
    description: "Internal debugging skill",
    content: "...",
    filePath: "...",
    disableModelInvocation: true,  // 模型看不到这个技能
};
```

### 2.2 PromptTemplate - 提示模板

PromptTemplate 是**参数化的提示**，可复用：

```typescript
export interface PromptTemplate {
    name: string;         // 模板名称
    description?: string; // 可选描述（用于命令列表）
    content: string;      // 模板内容（包含参数占位符）
}
```

**占位符格式**：
```typescript
// 示例模板
const template = {
    name: "explain-code",
    description: "Explain the given code snippet",
    content: "Please explain this code: {{args[0]}}",
};

// 使用
harness.promptFromTemplate("explain-code", ["function add(a, b) { return a + b; }"]);
// 实际提示: "Please explain this code: function add(a, b) { return a + b; }"
```

### 2.3 AgentHarnessResources - 资源容器

```typescript
export interface AgentHarnessResources<
    TSkill extends Skill = Skill,
    TPromptTemplate extends PromptTemplate = PromptTemplate,
> {
    promptTemplates?: TPromptTemplate[];  // 提示模板列表
    skills?: TSkill[];                    // 技能列表
}
```

**资源的管理方式**：
```typescript
// 构造时提供
const harness = new AgentHarness({
    resources: {
        skills: [skill1, skill2],
        promptTemplates: [template1],
    },
    ...
});

// 动态更新
await harness.setResources({
    skills: [skill1, skill2, skill3],  // 新增技能
    promptTemplates: [template1],
});
```

---

## 💻 第三层：执行环境类型

### 3.1 FileSystem - 文件系统接口

FileSystem 是**抽象的文件系统接口**，支持多种后端：

```typescript
export interface FileSystem {
    cwd: string;  // 当前工作目录
    
    // 路径操作
    absolutePath(path: string, signal?: AbortSignal): Promise<Result<string, FileError>>;
    joinPath(parts: string[], signal?: AbortSignal): Promise<Result<string, FileError>>;
    canonicalPath(path: string, signal?: AbortSignal): Promise<Result<string, FileError>>;
    
    // 文件读写
    readTextFile(path: string, signal?: AbortSignal): Promise<Result<string, FileError>>;
    readTextLines(path: string, options?: { maxLines?: number }): Promise<Result<string[], FileError>>;
    readBinaryFile(path: string, signal?: AbortSignal): Promise<Result<Uint8Array, FileError>>;
    writeFile(path: string, content: string | Uint8Array): Promise<Result<void, FileError>>;
    appendFile(path: string, content: string | Uint8Array): Promise<Result<void, FileError>>;
    
    // 文件信息
    fileInfo(path: string, signal?: AbortSignal): Promise<Result<FileInfo, FileError>>;
    listDir(path: string, signal?: AbortSignal): Promise<Result<FileInfo[], FileError>>;
    exists(path: string, signal?: AbortSignal): Promise<Result<boolean, FileError>>;
    
    // 目录和临时文件
    createDir(path: string, options?: { recursive?: boolean }): Promise<Result<void, FileError>>;
    remove(path: string, options?: { recursive?: boolean; force?: boolean }): Promise<Result<void, FileError>>;
    createTempDir(prefix?: string): Promise<Result<string, FileError>>;
    createTempFile(options?: { prefix?: string; suffix?: string }): Promise<Result<string, FileError>>;
    
    // 清理资源
    cleanup(): Promise<void>;
}
```

**关键设计原则**：

1. **永不抛出异常**：
```typescript
// 所有方法必须返回 Result，不能 throw
// 即使后端抛出，也要捕获并包装为 Result
```

2. **不自动跟随符号链接**：
```typescript
// fileInfo() 返回的是 symlink 本身的信息
// canonicalPath() 才会解析符号链接
```

3. **AbortSignal 支持**：
```typescript
// 所有异步操作都接受 AbortSignal
// 用于取消长时间运行的操作
```

### 3.2 FileInfo - 文件元数据

```typescript
export interface FileInfo {
    name: string;      // 文件名（basename）
    path: string;      // 绝对路径（不跟随符号链接）
    kind: FileKind;    // 类型："file" | "directory" | "symlink"
    size: number;      // 字节大小
    mtimeMs: number;   // 修改时间（毫秒）
}
```

### 3.3 Shell - Shell 执行接口

```typescript
export interface Shell {
    exec(
        command: string,
        options?: ExecutionEnvExecOptions,
    ): Promise<Result<{ stdout: string; stderr: string; exitCode: number }, ExecutionError>>;
    
    cleanup(): Promise<void>;
}

export interface ExecutionEnvExecOptions {
    cwd?: string;                    // 工作目录
    env?: Record<string, string>;    // 环境变量
    timeout?: number;                // 超时（秒）
    abortSignal?: AbortSignal;       // 中断信号
    onStdout?: (chunk: string) => void;  // stdout 流式回调
    onStderr?: (chunk: string) => void;  // stderr 流式回调
}
```

**流式输出支持**：
```typescript
// 实时获取命令输出
const result = await shell.exec("npm install", {
    onStdout: (chunk) => console.log("OUT:", chunk),
    onStderr: (chunk) => console.error("ERR:", chunk),
});
```

### 3.4 ExecutionEnv - 执行环境组合

```typescript
// ExecutionEnv 组合了 FileSystem 和 Shell
export interface ExecutionEnv extends FileSystem, Shell {}
```

**为什么这样设计**：
- FileSystem 和 Shell 是**独立能力**
- ExecutionEnv 是**完整环境**
- AgentHarness 需要 ExecutionEnv（既有文件操作，又有命令执行）

---

## 🗂️ 第四层：Session 类型体系

### 4.1 SessionTreeEntry - 会话树的节点类型

Session 是一个**树形结构**，每个节点是一个 `SessionTreeEntry`：

```typescript
export type SessionTreeEntry =
    | MessageEntry              // 消息节点
    | ThinkingLevelChangeEntry  // 思考级别变化
    | ModelChangeEntry          // 模型变化
    | ActiveToolsChangeEntry    // 活跃工具变化
    | CompactionEntry           // 压缩摘要
    | BranchSummaryEntry        // 分支摘要
    | CustomEntry               // 自定义数据
    | CustomMessageEntry        // 自定义消息
    | LabelEntry                // 标签
    | SessionInfoEntry          // 会话信息
    | LeafEntry;                // 叶子指针
```

**所有 Entry 的共同结构**：

```typescript
export interface SessionTreeEntryBase {
    type: string;               // Entry 类型标识
    id: string;                 // 唯一 ID
    parentId: string | null;    // 父节点 ID（树结构）
    timestamp: string;          // 时间戳（ISO 字符串）
}
```

### 4.2 Entry 类型详解

#### MessageEntry - 最核心的 Entry

```typescript
export interface MessageEntry extends SessionTreeEntryBase {
    type: "message";
    message: AgentMessage;  // 用户或助手消息
}
```

#### ConfigChange Entries - 配置变更

```typescript
// 思考级别变化
export interface ThinkingLevelChangeEntry extends SessionTreeEntryBase {
    type: "thinking_level_change";
    thinkingLevel: string;
}

// 模型变化
export interface ModelChangeEntry extends SessionTreeEntryBase {
    type: "model_change";
    provider: string;
    modelId: string;
}

// 活跃工具变化
export interface ActiveToolsChangeEntry extends SessionTreeEntryBase {
    type: "active_tools_change";
    activeToolNames: string[];
}
```

**为什么需要这些 Entry**：
```typescript
// Session 是树形历史，需要记录所有变更
// rebuildContext() 会沿着树重建完整状态
// 遇到 ModelChangeEntry → 改变当前 model
// 遇到 ActiveToolsChangeEntry → 改变当前 activeTools
```

#### CompactionEntry - 压缩摘要

```typescript
export interface CompactionEntry<T = unknown> extends SessionTreeEntryBase {
    type: "compaction";
    summary: string;              // 摘要文本
    firstKeptEntryId: string;     // 第一个保留的 Entry ID
    tokensBefore: number;         // 压缩前的 token 数
    details?: T;                  // 额外细节（文件操作等）
    fromHook?: boolean;           // 是否来自 Hook
}
```

**压缩的意义**：
```typescript
// 当对话历史过长时：
// 1. 用 LLM 生成摘要
// 2. 替换早期历史为 CompactionEntry
// 3. rebuildContext() 遇到 CompactionEntry → 插入摘要消息
```

#### BranchSummaryEntry - 分支摘要

```typescript
export interface BranchSummaryEntry<T = unknown> extends SessionTreeEntryBase {
    type: "branch_summary";
    fromId: string;      // 原叶子 ID
    summary: string;     // 摘要文本
    details?: T;         // 额外细节
    fromHook?: boolean;  // 是否来自 Hook
}
```

**分支摘要的场景**：
```typescript
// navigateTree() 切换分支时可选生成摘要
// 类似 git 的 squash merge
```

#### Custom Entries - 扩展机制

```typescript
// 自定义数据（不影响对话）
export interface CustomEntry<T = unknown> extends SessionTreeEntryBase {
    type: "custom";
    customType: string;  // 自定义类型标识
    data?: T;            // 自定义数据
}

// 自定义消息（显示为对话，但不是真实消息）
export interface CustomMessageEntry<T = unknown> extends SessionTreeEntryBase {
    type: "custom_message";
    customType: string;
    content: string | (TextContent | ImageContent)[];  // 消息内容
    details?: T;
    display: boolean;  // 是否显示给模型
}
```

**用途举例**：
```typescript
// CustomEntry: 记录应用特定的状态
await session.appendCustomEntry("app_state", { theme: "dark" });

// CustomMessageEntry: 插入虚拟对话
await session.appendCustomMessageEntry("system_note", "User changed theme", true);
```

#### LeafEntry - 叶子指针

```typescript
export interface LeafEntry extends SessionTreeEntryBase {
    type: "leaf";
    targetId: string | null;  // 当前叶子节点的 ID
}
```

**为什么需要 LeafEntry**：
```typescript
// Session 是树，可以有多个分支
// LeafEntry 指向当前活跃的分支叶子
// 支持分支切换（navigateTree）
```

### 4.3 SessionContext - 重建的上下文

```typescript
export interface SessionContext {
    messages: AgentMessage[];                       // 消息历史
    thinkingLevel: string;                          // 当前思考级别
    model: { provider: string; modelId: string } | null;  // 当前模型
    activeToolNames: string[] | null;               // 当前活跃工具
}
```

**buildContext() 的重建逻辑**：
```typescript
// 从 leaf → root 逆向遍历树
// 收集所有 Entry
// 根据 Entry 类型重建当前状态：
//   MessageEntry → 加入 messages
//   ModelChangeEntry → 更新 model
//   CompactionEntry → 插入摘要消息
//   ...
```

### 4.4 SessionStorage - 存储接口

```typescript
export interface SessionStorage<TMetadata extends SessionMetadata = SessionMetadata> {
    getMetadata(): Promise<TMetadata>;       // 获取元数据
    getLeafId(): Promise<string | null>;     // 获取叶子 ID
    setLeafId(leafId: string | null): Promise<void>;  // 设置叶子 ID
    createEntryId(): Promise<string>;        // 创建新 Entry ID
    appendEntry(entry: SessionTreeEntry): Promise<void>;  // 添加 Entry
    getEntry(id: string): Promise<SessionTreeEntry | undefined>;  // 获取 Entry
    findEntries<TType>(type: TType): Promise<Array<Extract<...>>>;  // 查找特定类型
    getLabel(id: string): Promise<string | undefined>;  // 获取标签
    getPathToRoot(leafId: string | null): Promise<SessionTreeEntry[]>;  // 获取路径
    getEntries(): Promise<SessionTreeEntry[]>;  // 获取所有 Entry
}
```

### 4.5 SessionRepo - 会话仓库

```typescript
export interface SessionRepo<
    TMetadata extends SessionMetadata = SessionMetadata,
    TCreateOptions extends SessionCreateOptions = SessionCreateOptions,
    TListOptions = void,
> {
    create(options: TCreateOptions): Promise<Session<TMetadata>>;   // 创建会话
    open(metadata: TMetadata): Promise<Session<TMetadata>>;         // 打开会话
    list(options?: TListOptions): Promise<TMetadata[]>;             // 列出会话
    delete(metadata: TMetadata): Promise<void>;                     // 删除会话
    fork(source: TMetadata, options: SessionForkOptions): Promise<Session<TMetadata>>;  // Fork 会话
}
```

**Fork 操作详解**：
```typescript
export interface SessionForkOptions {
    entryId?: string;       // Fork 起点 Entry ID
    position?: "before" | "at";  // Fork 位置
    id?: string;            // 新会话 ID
}

// 示例
await repo.fork(session.metadata, {
    entryId: "msg-123",     // 从 msg-123 处 fork
    position: "at",         // 包含 msg-123
    id: "new-session-id",
});
```

---

## 📡 第五层：事件与结果类型

### 5.1 AgentHarnessOwnEvent - 自身事件

AgentHarness 发出的自身事件（区别于 Agent Loop 的 AgentEvent）：

```typescript
export type AgentHarnessOwnEvent<TSkill, TPromptTemplate> =
    | QueueUpdateEvent           // 队列更新
    | SavePointEvent             // 保存点
    | AbortEvent                 // 中断
    | SettledEvent               // 执行结束
    | BeforeAgentStartEvent      // Agent 启动前
    | ContextEvent               // 上下文构建
    | BeforeProviderRequestEvent // Provider 请求前
    | BeforeProviderPayloadEvent // Provider payload 前
    | AfterProviderResponseEvent // Provider 响应后
    | ToolCallEvent              // 工具调用
    | ToolResultEvent            // 工具结果
    | SessionBeforeCompactEvent  // 压缩前
    | SessionCompactEvent        // 压缩完成
    | SessionBeforeTreeEvent     // 树导航前
    | SessionTreeEvent           // 树导航完成
    | ModelUpdateEvent           // 模型更新
    | ThinkingLevelUpdateEvent   // 思考级别更新
    | ResourcesUpdateEvent       // 资源更新
    | ToolsUpdateEvent;          // 工具更新
```

### 5.2 事件分类

**① 状态通知事件**（只观察，不干预）：

```typescript
// 队列更新
export interface QueueUpdateEvent {
    type: "queue_update";
    steer: AgentMessage[];
    followUp: AgentMessage[];
    nextTurn: AgentMessage[];
}

// 保存点（回合结束后的同步点）
export interface SavePointEvent {
    type: "save_point";
    hadPendingMutations: boolean;  // 是否有待写入的变更
}

// Agent 结束
export interface SettledEvent {
    type: "settled";
    nextTurnCount: number;  // nextTurnQueue 的消息数
}

// 中断完成
export interface AbortEvent {
    type: "abort";
    clearedSteer: AgentMessage[];     // 清空的 steer 消息
    clearedFollowUp: AgentMessage[];  // 清空的 followUp 消息
}
```

**② Hook 事件**（可以返回结果，影响流程）：

```typescript
// Agent 启动前（可以注入消息）
export interface BeforeAgentStartEvent {
    type: "before_agent_start";
    prompt: string;
    images?: ImageContent[];
    systemPrompt: string;
    resources: AgentHarnessResources;
}

// 上下文构建（可以修改消息）
export interface ContextEvent {
    type: "context";
    messages: AgentMessage[];
}

// Provider 请求前（可以修改请求选项）
export interface BeforeProviderRequestEvent {
    type: "before_provider_request";
    model: Model<any>;
    sessionId: string;
    streamOptions: AgentHarnessStreamOptions;
}

// Provider payload 前（可以修改请求 payload）
export interface BeforeProviderPayloadEvent {
    type: "before_provider_payload";
    model: Model<any>;
    payload: unknown;
}

// 工具调用前（可以阻止调用）
export interface ToolCallEvent {
    type: "tool_call";
    toolCallId: string;
    toolName: string;
    input: Record<string, unknown>;
}

// 工具结果（可以修改结果）
export interface ToolResultEvent {
    type: "tool_result";
    toolCallId: string;
    toolName: string;
    input: Record<string, unknown>;
    content: Array<TextContent | ImageContent>;
    details: unknown;
    isError: boolean;
}
```

**③ Session 事件**（压缩和树导航）：

```typescript
// 压缩前（可以提供自定义摘要）
export interface SessionBeforeCompactEvent {
    type: "session_before_compact";
    preparation: CompactionPreparation;  // 压缩准备结果
    branchEntries: SessionTreeEntry[];   // 分支所有 Entry
    customInstructions?: string;
    signal: AbortSignal;
}

// 压缩完成
export interface SessionCompactEvent {
    type: "session_compact";
    compactionEntry: CompactionEntry;
    fromHook: boolean;  // 是否来自 Hook
}

// 树导航前（可以提供自定义摘要）
export interface SessionBeforeTreeEvent {
    type: "session_before_tree";
    preparation: TreePreparation;
    signal: AbortSignal;
}

// 树导航完成
export interface SessionTreeEvent {
    type: "session_tree";
    newLeafId: string | null;
    oldLeafId: string | null;
    summaryEntry?: BranchSummaryEntry;
    fromHook?: boolean;
}
```

**④ 配置变更事件**：

```typescript
// 模型更新
export interface ModelUpdateEvent {
    type: "model_update";
    model: Model<any>;
    previousModel: Model<any> | undefined;
    source: "set" | "restore";
}

// 思考级别更新
export interface ThinkingLevelUpdateEvent {
    type: "thinking_level_update";
    level: ThinkingLevel;
    previousLevel: ThinkingLevel;
}

// 工具更新
export interface ToolsUpdateEvent {
    type: "tools_update";
    toolNames: string[];
    previousToolNames: string[];
    activeToolNames: string[];
    previousActiveToolNames: string[];
    source: "set" | "restore";
}

// 资源更新
export interface ResourcesUpdateEvent {
    type: "resources_update";
    resources: AgentHarnessResources;
    previousResources: AgentHarnessResources;
}
```

### 5.3 HookResult 类型

Hook 事件可以返回结果，影响执行流程：

```typescript
export type AgentHarnessEventResultMap = {
    before_agent_start: BeforeAgentStartResult | undefined;
    context: ContextResult | undefined;
    before_provider_request: BeforeProviderRequestResult | undefined;
    before_provider_payload: BeforeProviderPayloadResult | undefined;
    after_provider_response: undefined;  // 不能返回结果
    tool_call: ToolCallResult | undefined;
    tool_result: ToolResultPatch | undefined;
    session_before_compact: SessionBeforeCompactResult | undefined;
    session_compact: undefined;  // 不能返回结果
    session_before_tree: SessionBeforeTreeResult | undefined;
    session_tree: undefined;  // 不能返回结果
    model_update: undefined;
    thinking_level_update: undefined;
    resources_update: undefined;
    tools_update: undefined;
    queue_update: undefined;
    save_point: undefined;
    abort: undefined;
    settled: undefined;
};
```

**关键 Result 类型详解**：

```typescript
// BeforeAgentStartResult - 注入消息
export interface BeforeAgentStartResult {
    messages?: AgentMessage[];    // 额外的消息（插入到对话中）
    systemPrompt?: string;        // 替换系统提示词
}

// ContextResult - 修改上下文
export interface ContextResult {
    messages: AgentMessage[];     // 替换的消息历史
}

// BeforeProviderRequestResult - 修改请求选项
export interface BeforeProviderRequestResult {
    streamOptions?: AgentHarnessStreamOptionsPatch;  // 流选项补丁
}

// BeforeProviderPayloadResult - 修改 payload
export interface BeforeProviderPayloadResult {
    payload: unknown;            // 替换的 payload
}

// ToolCallResult - 阻止或允许工具调用
export interface ToolCallResult {
    block?: boolean;             // 是否阻止
    reason?: string;             // 阻止原因（给模型的提示）
}

// ToolResultPatch - 修改工具结果
export interface ToolResultPatch {
    content?: Array<TextContent | ImageContent>;  // 替换内容
    details?: unknown;           // 替换细节
    isError?: boolean;           // 标记为错误
    terminate?: boolean;         // 终止 Agent Loop
}

// SessionBeforeCompactResult - 自定义压缩
export interface SessionBeforeCompactResult {
    cancel?: boolean;            // 取消压缩
    compaction?: CompactResult;  // 提供自定义摘要
}

// SessionBeforeTreeResult - 自定义树导航
export interface SessionBeforeTreeResult {
    cancel?: boolean;            // 取消导航
    summary?: { summary: string; details?: unknown };  // 提供自定义摘要
    customInstructions?: string; // 自定义指令
    replaceInstructions?: boolean;
    label?: string;
}
```

### 5.4 AgentHarnessOptions - 构造选项

```typescript
export interface AgentHarnessOptions<TSkill, TPromptTemplate, TTool> {
    env: ExecutionEnv;           // 执行环境（必须）
    session: Session;            // 会话（必须）
    tools?: TTool[];             // 工具列表
    resources?: AgentHarnessResources;  // 资源
    systemPrompt?: string | ((context) => string | Promise<string>);  // 系统提示词
    getApiKeyAndHeaders?: (model) => Promise<{ apiKey: string; headers?: Record<string, string> } | undefined>;  // API Key 获取
    streamOptions?: AgentHarnessStreamOptions;  // 流选项
    model: Model<any>;           // 模型（必须）
    thinkingLevel?: ThinkingLevel;  // 思考级别
    activeToolNames?: string[];  // 活跃工具名称
    steeringMode?: QueueMode;    // Steering 队列模式
    followUpMode?: QueueMode;    // FollowUp 队列模式
}
```

**systemPrompt 的两种形式**：

```typescript
// 静态系统提示词
const harness = new AgentHarness({
    systemPrompt: "You are a helpful assistant.",
    ...
});

// 动态系统提示词（函数）
const harness = new AgentHarness({
    systemPrompt: async (context) => {
        const { model, activeTools, resources } = context;
        let prompt = "You are a helpful assistant.";
        
        // 添加工具信息
        if (activeTools.length > 0) {
            prompt += "\n\nYou have access to these tools: " + 
                activeTools.map(t => t.name).join(", ");
        }
        
        // 添加技能信息
        if (resources.skills) {
            prompt += "\n\nYou have these skills: " + 
                resources.skills.map(s => s.name).join(", ");
        }
        
        return prompt;
    },
    ...
});
```

---

## 🚨 第六层：错误处理类型

### 6.1 错误类型分类

整个系统有清晰的错误层级：

```
AgentHarnessError (顶层)
    ├─ FileError (文件操作)
    ├─ ExecutionError (Shell 执行)
    ├─ CompactionError (压缩)
    ├─ BranchSummaryError (分支摘要)
    └─ SessionError (Session 操作)
```

### 6.2 Error Code 设计

每个 Error 类型都有**稳定的错误码**：

```typescript
// FileError 的错误码
export type FileErrorCode =
    | "aborted"           // 操作被中断
    | "not_found"         // 文件不存在
    | "permission_denied" // 权限不足
    | "not_directory"     // 不是目录
    | "is_directory"      // 是目录
    | "invalid"           // 无效路径
    | "not_supported"     // 操作不支持
    | "unknown";          // 未知错误

// ExecutionError 的错误码
export type ExecutionErrorCode =
    | "aborted"           // 命令被中断
    | "timeout"           // 超时
    | "shell_unavailable" // Shell 不可用
    | "spawn_error"       // 启动失败
    | "callback_error"    // 回调错误
    | "unknown";

// SessionError 的错误码
export type SessionErrorCode =
    | "not_found"          // Entry 不存在
    | "invalid_session"    // 无效会话
    | "invalid_entry"      // 无效 Entry
    | "invalid_fork_target" // 无效 Fork 目标
    | "storage"            // 存储错误
    | "unknown";
```

**稳定错误码的意义**：
```typescript
// 错误码是跨后端的稳定标识
// 无论底层是 Node.js fs 还是浏览器 File API
// 错误码都一样，方便统一处理

const result = await filesystem.readTextFile("config.json");
if (!result.ok) {
    if (result.error.code === "not_found") {
        // 统一处理文件不存在
        console.log("File not found, creating default...");
    } else if (result.error.code === "permission_denied") {
        // 统一处理权限错误
        console.error("Permission denied");
    }
}
```

### 6.3 Error 类构造

所有 Error 类都支持 `cause` 链：

```typescript
export class FileError extends Error {
    public code: FileErrorCode;
    public path?: string;  // 相关路径（可选）

    constructor(code: FileErrorCode, message: string, path?: string, cause?: Error) {
        super(message, cause === undefined ? undefined : { cause });
        this.name = "FileError";
        this.code = code;
        this.path = path;
    }
}

// 使用示例
const nodeError = new Error("ENOENT: no such file or directory");
const fileError = new FileError(
    "not_found",
    "File not found: config.json",
    "/path/to/config.json",
    nodeError,  // 保留原始 Node.js 错误
);
```

### 6.4 AgentHarnessError - 顶层错误

```typescript
export type AgentHarnessErrorCode =
    | "busy"              // Harness 正忙
    | "invalid_state"     // 无效状态（如 idle 时 steer）
    | "invalid_argument"  // 无效参数
    | "session"           // Session 错误
    | "hook"              // Hook 错误
    | "auth"              // 认证错误
    | "compaction"        // 压缩错误
    | "branch_summary"    // 分支摘要错误
    | "unknown";          // 未知错误

export class AgentHarnessError extends Error {
    public code: AgentHarnessErrorCode;

    constructor(code: AgentHarnessErrorCode, message: string, cause?: Error) {
        super(message, cause === undefined ? undefined : { cause });
        this.name = "AgentHarnessError";
        this.code = code;
    }
}
```

**错误映射逻辑**（在 agent-harness.ts 中）：

```typescript
function normalizeHarnessError(error: unknown, fallbackCode: AgentHarnessErrorCode): AgentHarnessError {
    if (error instanceof AgentHarnessError) return error;
    
    const cause = toError(error);
    
    // 将子系统错误映射为顶层错误
    if (cause instanceof SessionError) 
        return new AgentHarnessError("session", cause.message, cause);
    if (cause instanceof CompactionError) 
        return new AgentHarnessError("compaction", cause.message, cause);
    if (cause instanceof BranchSummaryError) 
        return new AgentHarnessError("branch_summary", cause.message, cause);
    
    // 其他错误使用 fallback code
    return new AgentHarnessError(fallbackCode, cause.message, cause);
}
```

---

## 🎯 类型设计洞察总结

### 洞察 1：Result 模式优于 try-catch

```typescript
// 传统 try-catch（隐性控制流）
try {
    const content = await fs.readFile(path);
    // 成功处理
} catch (error) {
    // 错误处理
}

// Result 模式（显式处理）
const result = await filesystem.readTextFile(path);
if (!result.ok) {
    // 错误处理（必须显式检查）
    return;
}
// 成功处理（自动保证 ok=true）
```

**优势**：
- 强制处理错误（编译器/类型系统会提醒）
- 错误处理是值的一部分，不是控制流
- 避免 try-catch 的嵌套地狱

### 洞察 2：Session 是树而非列表

```typescript
// 不是简单的消息列表
messages: AgentMessage[]

// 而是树形结构
SessionTreeEntry (每个节点可以有多个子节点)
    ├─ MessageEntry (消息节点)
    ├─ ModelChangeEntry (配置变更)
    ├─ CompactionEntry (压缩摘要)
    └─ LeafEntry (指向当前叶子)
```

**树的意义**：
- 支持分支（用户可以回到历史节点）
- 支持配置变更记录（rebuildContext 时重建状态）
- 支持 Fork（从任意节点创建新会话）

### 洞察 3：Entry 类型是类型安全的 Union

```typescript
// 使用 Union + Extract 实现类型安全查找
export type SessionTreeEntry = MessageEntry | ModelChangeEntry | ...;

// findEntries 的返回类型自动推断
const messages = await storage.findEntries("message");  
// 类型自动推断为 MessageEntry[]

const modelChanges = await storage.findEntries("model_change");
// 类型自动推断为 ModelChangeEntry[]
```

### 洞察 4：事件和 Hook 的分离

```typescript
// 状态通知事件 - 只观察
QueueUpdateEvent, SavePointEvent, AbortEvent, SettledEvent
    → subscribe() 监听
    → 不能返回结果

// Hook 事件 - 可干预
BeforeAgentStartEvent, ContextEvent, ToolCallEvent, ...
    → on() 监听
    → 可以返回结果影响流程
```

### 洞察 5：泛型的策略性使用

```typescript
// 顶层使用默认泛型（简化使用）
export interface AgentHarnessResources<
    TSkill extends Skill = Skill,
    TPromptTemplate extends PromptTemplate = PromptTemplate,
> {
    skills?: TSkill[];
    promptTemplates?: TPromptTemplate[];
}

// 大多数情况使用默认
const resources: AgentHarnessResources = {
    skills: [skill1],
};

// 特殊情况自定义类型
interface CustomSkill extends Skill {
    customField: string;
}
const resources: AgentHarnessResources<CustomSkill> = {
    skills: [customSkill1],
};
```

---

## 📚 延伸学习建议

学习完类型系统后，建议继续学习：

1. **[[session-implementation]]** - 理解 Session 的具体实现（JsonlSessionStorage）
2. **[[filesystem-implementation]]** - 理解 FileSystem 的不同后端实现
3. **[[compaction-implementation]]** - 理解压缩算法的具体实现
4. **[[event-flow]]** - 跟踪一次完整执行的事件流

---

**下一步行动**：
- 用 TypeScript 类型检查器验证 Result 模式的强制检查
- 查看 Session 的实际 JSONL 存储格式
- 实现 FileSystem 的一个 Mock 版本，理解接口契约