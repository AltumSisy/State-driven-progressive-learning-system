# SessionManager 知识点详解

> 本文档深入解析 SessionManager 的核心设计，包括 Entry 类型体系、树状结构、上下文构建、JSONL 文件格式等关键知识点。

---

## 概述：SessionManager 是什么？

### 核心定位

SessionManager 是 Claude Code CLI 的**会话持久化引擎**，负责管理用户与 AI 之间的完整对话历史。

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      SessionManager 在系统中的位置                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   用户输入                    AI 响应                                    │
│      ↓                           ↓                                      │
│   ┌─────────────────────────────────────────────────────────────────┐  │
│   │                     AgentSession                                │  │
│   │   • 协调用户交互与 AI 调用                                        │  │
│   │   • 管理 agent state (messages, model, thinkingLevel)           │  │
│   │   • 处理 compaction、树形导航                                     │  │
│   └─────────────────────────────────────────────────────────────────┘  │
│                           ↓                                             │
│   ┌─────────────────────────────────────────────────────────────────┐  │
│   │                     SessionManager                               │  │
│   │   • 持久化对话历史到 JSONL 文件                                    │  │
│   │   • 维护树状结构，支持时光机回溯                                    │  │
│   │   • 构建 LLM 上下文 (buildSessionContext)                         │  │
│   │   • 管理 compaction 摘要                                          │  │
│   └─────────────────────────────────────────────────────────────────┘  │
│                           ↓                                             │
│   ┌─────────────────────────────────────────────────────────────────┐  │
│   │                     JSONL 文件                                   │  │
│   │   ~/.pi/agent/sessions/<encoded-cwd>/<timestamp>_<uuid>.jsonl   │  │
│   └─────────────────────────────────────────────────────────────────┘  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 解决的核心问题

| 问题 | SessionManager 的解决方案 |
|------|---------------------------|
| **对话持久化** | 追加写入 JSONL 文件，每次消息都即时保存 |
| **历史回溯（时光机）** | 树状结构 + leaf 指针，支持回到任意历史节点重新开始 |
| **上下文压缩** | CompactionEntry 摘要历史，节省 token |
| **跨会话复用** | forkFrom() 支持跨项目复制会话历史 |
| **分支管理** | 树状结构支持多分支，一个文件存储多条对话路径 |

### 核心职责

1. **持久化层**
   - 所有对话 Entry 追加写入 JSONL 文件
   - 支持 session 恢复、跨进程继续对话
   - 文件损坏时自动迁移到最新版本

2. **数据结构层**
   - 维护 `id` / `parentId` 树状结构
   - 管理 `leafId` 当前位置指针
   - 维护 `byId` 快速查找索引

3. **上下文构建层**
   - `buildSessionContext()` 从 leaf 到 root 遍历
   - 处理 compaction 摘要替换历史
   - 提取当前 thinkingLevel、model 配置

4. **操作层**
   - `branch()` / `branchWithSummary()` 时光机操作
   - `createBranchedSession()` 提取路径为独立会话
   - 静态工厂方法创建/打开/列出会话

### 设计理念

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         SessionManager 设计理念                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  1. 追加写入模式                                                         │
│     ┌─────────────────────────────────────────────────────────────┐    │
│     │ • 永不修改已有 Entry                                          │    │
│     │ • 只追加新 Entry                                               │    │
│     │ • 写入失败不影响历史                                            │    │
│     │ • 支持时光机：所有历史保留                                      │    │
│     └─────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  2. 树状结构模式                                                         │
│     ┌─────────────────────────────────────────────────────────────┐    │
│     │ • Entry 通过 id/parentId 形成树                               │    │
│     │ • leafId 指向当前位置                                          │    │
│     │ • branch() 移动指针，创建新分支                                │    │
│     │ • 一个文件存储多条对话路径                                      │    │
│     └─────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  3. 上下文构建模式                                                       │
│     ┌─────────────────────────────────────────────────────────────┐    │
│     │ • 从 leaf 回溯到 root                                          │    │
│     │ • CompactionEntry 替换早期历史                                 │    │
│     │ • BranchSummaryEntry 注入跳过路径的摘要                        │    │
│     │ • 输出：messages + thinkingLevel + model                      │    │
│     └─────────────────────────────────────────────────────────────┘    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 与 AgentSession 的关系

| 组件 | 职责 | 关系 |
|------|------|------|
| **AgentSession** | 协调交互、调用 AI、处理用户命令 | 使用 SessionManager |
| **SessionManager** | 持久化、树结构、上下文构建 | 被 AgentSession 调用 |
| **AgentHarness** | 抽象框架层 | pi/agent 系统的接口定义 |

**AgentSession 调用 SessionManager 的场景**：

```typescript
// 发送消息时 → appendMessage()
await sessionManager.appendMessage(userMessage);

// AI 响应时 → appendMessage()
await sessionManager.appendMessage(assistantMessage);

// 构建 LLM 上下文时 → buildSessionContext()
const context = sessionManager.buildSessionContext();
agent.state.messages = context.messages;

// 树形导航时 → branch() / branchWithSummary()
sessionManager.branch(targetId);
// 或
sessionManager.branchWithSummary(targetId, summary);

// Fork 会话时 → createBranchedSession()
const newPath = sessionManager.createBranchedSession(leafId);

// Compaction 时 → appendCompaction()
await sessionManager.appendCompaction(summary, firstKeptEntryId, tokensBefore);
```

---

## 目录

1. [Entry 类型体系](#一entry-类型体系)
2. [树状结构与 Leaf 指针](#二树状结构与-leaf-指针)
3. [buildSessionContext 上下文构建](#三buildsessioncontext-上下文构建)
4. [JSONL 文件格式](#四jsonl-文件格式)
5. [SessionManager 类详解](#五sessionmanager-类详解)
6. [版本迁移机制](#六版本迁移机制)
7. [核心设计模式总结](#七核心设计模式总结)

---

## 一、Entry 类型体系

### 1.1 Entry 基础结构

所有 Entry 都继承自 `SessionEntryBase`：

```typescript
// 源码位置: session-manager.ts:43-48
export interface SessionEntryBase {
  type: string;              // 类型标识（必填）
  id: string;                // 8位短 UUID（必填）
  parentId: string | null;   // 父节点 ID，null 表示根节点
  timestamp: string;         // ISO 时间戳
}
```

**关键知识点**：

| 字段 | 说明 |
|------|------|
| `id` | 8位短 UUID，通过 `generateId()` 生成，碰撞检测确保唯一 |
| `parentId` | 形成树结构的关键，指向父 Entry |
| `timestamp` | ISO 8601 格式，用于排序和恢复时间顺序 |

### 1.2 八种 Entry 类型详解

#### ① SessionMessageEntry - 对话消息

```typescript
// 源码位置: session-manager.ts:50-53
export interface SessionMessageEntry extends SessionEntryBase {
  type: "message";
  message: AgentMessage;
}
```

**AgentMessage 可能的角色**：

```typescript
type AgentMessageRole = 
  | "user"          // 用户消息
  | "assistant"     // AI 助手消息
  | "toolResult"    // 工具执行结果
  | "custom"        // 自定义消息（扩展）
  | "bashExecution";// Bash 命令执行记录
```

**JSON 示例**：

```json
{
  "type": "message",
  "id": "a1b2c3d4",
  "parentId": null,
  "timestamp": "2026-06-19T10:30:00.000Z",
  "message": {
    "role": "user",
    "content": "帮我写一个函数"
  }
}
```

---

#### ② ThinkingLevelChangeEntry - 思维级别变更

```typescript
// 源码位置: session-manager.ts:55-58
export interface ThinkingLevelChangeEntry extends SessionEntryBase {
  type: "thinking_level_change";
  thinkingLevel: string;     // "off" | "minimal" | "low" | "medium" | "high"
}
```

**作用**：记录思维级别的切换历史，`buildSessionContext` 会从路径中提取最新的思维级别。

---

#### ③ ModelChangeEntry - 模型切换

```typescript
// 源码位置: session-manager.ts:60-64
export interface ModelChangeEntry extends SessionEntryBase {
  type: "model_change";
  provider: string;          // "anthropic" | "openai" | ...
  modelId: string;           // "claude-sonnet-4-6" | ...
}
```

**注意**：模型信息也可能从 assistant message 中提取（provider/model 字段）。

---

#### ④ CompactionEntry - 压缩摘要（核心）

```typescript
// 源码位置: session-manager.ts:66-75
export interface CompactionEntry<T = unknown> extends SessionEntryBase {
  type: "compaction";
  summary: string;           // LLM 生成的摘要文本
  firstKeptEntryId: string;  // 第一个保留的 Entry ID
  tokensBefore: number;      // 压缩前的 token 数
  details?: T;               // 扩展数据（如文件操作统计）
  fromHook?: boolean;        // 是否由扩展生成
}
```

**关键知识点**：

| 字段 | 说明 |
|------|------|
| `summary` | LLM 生成的结构化摘要，包含 Goal/Progress/Key Decisions 等 |
| `firstKeptEntryId` | 压缩边界，从该 Entry 开始保留原始消息 |
| `tokensBefore` | 记录压缩前的上下文大小，用于统计 |
| `fromHook` | 区分系统生成和扩展生成，向后兼容用 undefined/false 表示系统生成 |

**JSON 示例**：

```json
{
  "type": "compaction",
  "id": "c5d6e7f8",
  "parentId": "b4c5d6e7",
  "timestamp": "2026-06-19T11:00:00.000Z",
  "summary": "## Goal\n实现登录功能\n## Progress\n- [x] 创建表结构...",
  "firstKeptEntryId": "m3n4o5p6",
  "tokensBefore": 50000,
  "details": {
    "readFiles": ["src/auth.ts"],
    "modifiedFiles": ["src/login.ts"]
  }
}
```

---

#### ⑤ BranchSummaryEntry - 分支摘要

```typescript
// 源码位置: session-manager.ts:77-85
export interface BranchSummaryEntry<T = unknown> extends SessionEntryBase {
  type: "branch_summary";
  fromId: string;            // 分叉起点（"root" 表示从根分叉）
  summary: string;           // 被跳过路径的摘要
  details?: T;               // 扩展数据（不发送给 LLM）
  fromHook?: boolean;        // 是否由扩展生成
}
```

**使用场景**：当用户在树形导航时选择跳过某条路径，系统会生成 BranchSummaryEntry 记录被跳过的内容。

---

#### ⑥ CustomEntry - 自定义数据（扩展）

```typescript
// 源码位置: session-manager.ts:97-101
export interface CustomEntry<T = unknown> extends SessionEntryBase {
  type: "custom";
  customType: string;        // 扩展标识符，用于过滤
  data?: T;                  // 扩展自定义数据
}
```

**重要说明**：

- **不参与 LLM 上下文**：`buildSessionContext` 会忽略此类型
- **用途**：扩展在会话 reload 时扫描 entries，根据 `customType` 恢复内部状态

---

#### ⑦ LabelEntry - 标签标记

```typescript
// 源码位置: session-manager.ts:104-108
export interface LabelEntry extends SessionEntryBase {
  type: "label";
  targetId: string;          // 标记的目标 Entry
  label: string | undefined; // 标签文本（undefined 表示删除）
}
```

**设计要点**：

- LabelEntry 不改变树的父子结构
- `targetId` 指向被标记的 Entry
- `label` 为 `undefined` 时表示删除标签
- 标签缓存通过 `labelsById` Map 维护

---

#### ⑧ SessionInfoEntry - 会话名称

```typescript
// 源码位置: session-manager.ts:111-114
export interface SessionInfoEntry extends SessionEntryBase {
  type: "session_info";
  name?: string;             // 用户定义的会话名称（空字符串表示清除）
}
```

**获取逻辑**：从 entries 倒序查找最新的 `session_info` Entry。

---

#### ⑨ CustomMessageEntry - 自定义消息（扩展）

```typescript
// 源码位置: session-manager.ts:128-134
export interface CustomMessageEntry<T = unknown> extends SessionEntryBase {
  type: "custom_message";
  customType: string;        // 扩展标识符
  content: string | (TextContent | ImageContent)[]; // 消息内容
  details?: T;               // 扩展元数据（不发送给 LLM）
  display: boolean;          // TUI 显示控制
}
```

**重要区分**：

| 特性 | CustomEntry | CustomMessageEntry |
|------|-------------|-------------------|
| 参与 LLM 上下文 | ❌ 否 | ✅ 是 |
| 用途 | 扩展状态持久化 | 向 LLM 注入消息 |
| content 字段 | ❌ 无 | ✅ 有 |
| display 字段 | ❌ 无 | ✅ 有（控制 TUI 显示） |

---

### 1.3 Entry 类型分类总结

| 类别 | Entry 类型 | 特点 | 参与 LLM 上下文 |
|------|-----------|------|----------------|
| **对话内容** | SessionMessageEntry | 核心数据 | ✅ |
| **摘要压缩** | CompactionEntry | 替代历史 | ✅（作为摘要消息） |
| **分支摘要** | BranchSummaryEntry | 跳过路径摘要 | ✅（作为摘要消息） |
| **状态变更** | ThinkingLevelChangeEntry, ModelChangeEntry | 配置变化 | ❌（提取状态） |
| **扩展注入** | CustomMessageEntry | 扩展消息 | ✅ |
| **扩展存储** | CustomEntry | 扩展状态 | ❌ |
| **标记命名** | LabelEntry, SessionInfoEntry | 辅助功能 | ❌ |

---

### 1.4 SessionHeader 结构

```typescript
// 源码位置: session-manager.ts:29-36
export interface SessionHeader {
  type: "session";
  version?: number;          // 当前版本: 3，v1 sessions 没有 version
  id: string;                // UUIDv7 格式的会话 ID
  timestamp: string;         // 创建时间
  cwd: string;               // 工作目录
  parentSession?: string;    // fork 来源（如果有）
}
```

**JSON 示例**：

```json
{
  "type": "session",
  "version": 3,
  "id": "0123456789abcdef",
  "timestamp": "2026-06-19T10:30:00.000Z",
  "cwd": "/home/user/project",
  "parentSession": "/path/to/source/session.jsonl"
}
```

---

## 二、树状结构与 Leaf 指针

### 2.1 树状结构原理

SessionManager 采用 **追加写入树状结构**：

```
Entry 通过 id 和 parentId 形成树:
- parentId = null → 根节点
- parentId = "xxx" → 父节点为 xxx Entry
- 每次追加，新 Entry 成为当前 leaf 的子节点
```

**树结构示例**：

```
初始状态 (leafId = null):
  空

追加 Entry A (parentId = null, leafId = "A"):
  A (root)
  ↑ leaf

追加 Entry B (parentId = "A", leafId = "B"):
  A → B
       ↑ leaf

追加 Entry C (parentId = "B", leafId = "C"):
  A → B → C
            ↑ leaf

执行 branch("B") (leafId = "B"):
  A → B → C
       ↑ leaf (移动到这里)

追加 Entry D (parentId = "B", leafId = "D"):
  A → B → C (被跳过)
       ↓
       D (新分支)
       ↑ leaf

最终树结构:
  A → B → C
       ↓
       D
       ↑ leaf

getBranch() 返回: [A, B, D]（从 root 到 leaf 的路径）
```

### 2.2 Leaf 指针的作用

```typescript
// 源码位置: session-manager.ts:717
private leafId: string | null = null;
```

**Leaf 指针的含义**：

| leafId 值 | 含义 |
|-----------|------|
| `null` | 树的起点，无任何 Entry |
| `"xxx"` | 当前位置在 Entry xxx |
| 最后 Entry 的 id | 默认位置（最新消息） |

**Leaf 指针的操作**：

```typescript
// 源码位置: session-manager.ts:1162-1176

// 分支：移动 leaf 指针到指定 Entry
branch(branchFromId: string): void {
  this.leafId = branchFromId;
}

// 重置：回到起点，用于重新编辑第一条消息
resetLeaf(): void {
  this.leafId = null;
}
```

### 2.3 树遍历：getBranch()

```typescript
// 源码位置: session-manager.ts:1071-1080
getBranch(fromId?: string): SessionEntry[] {
  const path: SessionEntry[] = [];
  const startId = fromId ?? this.leafId;
  let current = startId ? this.byId.get(startId) : undefined;
  
  // 从 leaf 向 root 回溯
  while (current) {
    path.unshift(current);   // 向前插入，保证 root 在前
    current = current.parentId ? this.byId.get(current.parentId) : undefined;
  }
  
  return path;  // [root, ..., leaf]
}
```

**关键算法**：从 leaf 向 root 回溯，使用 `unshift` 保证顺序。

### 2.4 树结构可视化：getTree()

```typescript
// 源码位置: session-manager.ts:1112-1150
export interface SessionTreeNode {
  entry: SessionEntry;
  children: SessionTreeNode[];
  label?: string;            // 解析后的标签
  labelTimestamp?: string;
}

getTree(): SessionTreeNode[] {
  // 1. 创建节点 Map
  // 2. 构建父子关系
  // 3. 处理孤儿节点（parentId 无效）
  // 4. 按时间戳排序 children
}
```

---

## 三、buildSessionContext 上下文构建

### 3.1 函数签名

```typescript
// 源码位置: session-manager.ts:314-318
export function buildSessionContext(
  entries: SessionEntry[],
  leafId?: string | null,
  byId?: Map<string, SessionEntry>,
): SessionContext
```

### 3.2 返回结构

```typescript
// 源码位置: session-manager.ts:161-165
export interface SessionContext {
  messages: AgentMessage[];                           // 发送给 LLM 的消息列表
  thinkingLevel: string;                              // 当前思维级别
  model: { provider: string; modelId: string } | null;// 当前模型信息
}
```

### 3.3 构建流程详解

#### Step 1: 构建 ID 索引

```typescript
// 源码位置: session-manager.ts:319-325
if (!byId) {
  byId = new Map<string, SessionEntry>();
  for (const entry of entries) {
    byId.set(entry.id, entry);
  }
}
```

#### Step 2: 确定 Leaf Entry

```typescript
// 源码位置: session-manager.ts:327-343
let leaf: SessionEntry | undefined;

if (leafId === null) {
  // 显式 null → 无消息（导航到第一条消息之前）
  return { messages: [], thinkingLevel: "off", model: null };
}

if (leafId) {
  leaf = byId.get(leafId);  // 指定 leaf
}

if (!leaf) {
  leaf = entries[entries.length - 1];  // 默认：最后一个 Entry
}

if (!leaf) {
  return { messages: [], thinkingLevel: "off", model: null };  // 空 session
}
```

#### Step 3: 从 Leaf 回溯到 Root

```typescript
// 源码位置: session-manager.ts:345-351
const path: SessionEntry[] = [];
let current: SessionEntry | undefined = leaf;

while (current) {
  path.unshift(current);   // 向前插入
  current = current.parentId ? byId.get(current.parentId) : undefined;
}
// 结果: [root, ..., leaf]
```

#### Step 4: 提取状态和压缩 Entry

```typescript
// 源码位置: session-manager.ts:353-368
let thinkingLevel = "off";
let model: { provider: string; modelId: string } | null = null;
let compaction: CompactionEntry | null = null;

for (const entry of path) {
  if (entry.type === "thinking_level_change") {
    thinkingLevel = entry.thinkingLevel;
  } else if (entry.type === "model_change") {
    model = { provider: entry.provider, modelId: entry.modelId };
  } else if (entry.type === "message" && entry.message.role === "assistant") {
    // 从 assistant message 中提取模型信息
    model = { provider: entry.message.provider, modelId: entry.message.model };
  } else if (entry.type === "compaction") {
    compaction = entry;
  }
}
```

**关键点**：沿着路径遍历，取各状态类型的**最新值**。

#### Step 5: 构建消息列表

```typescript
// 源码位置: session-manager.ts:370-418

const appendMessage = (entry: SessionEntry) => {
  if (entry.type === "message") {
    messages.push(entry.message);
  } else if (entry.type === "custom_message") {
    messages.push(createCustomMessage(...));
  } else if (entry.type === "branch_summary" && entry.summary) {
    messages.push(createBranchSummaryMessage(...));
  }
};

if (compaction) {
  // 有压缩的特殊处理
  // 1. 先发摘要消息
  messages.push(createCompactionSummaryMessage(compaction.summary, ...));
  
  // 2. 找压缩位置
  const compactionIdx = path.findIndex(e => e.type === "compaction" && e.id === compaction.id);
  
  // 3. 从 firstKeptEntryId 开始保留消息
  let foundFirstKept = false;
  for (let i = 0; i < compactionIdx; i++) {
    if (path[i].id === compaction.firstKeptEntryId) {
      foundFirstKept = true;
    }
    if (foundFirstKept) {
      appendMessage(path[i]);
    }
  }
  
  // 4. 压缩后的消息全部保留
  for (let i = compactionIdx + 1; i < path.length; i++) {
    appendMessage(path[i]);
  }
} else {
  // 无压缩：全部消息
  for (const entry of path) {
    appendMessage(entry);
  }
}
```

### 3.4 Compaction 处理示意图

```
无 Compaction 时:
  path: [A, B, C, D, E]
  messages: [msg(A), msg(B), msg(C), msg(D), msg(E)]

有 Compaction 时:
  path: [A, B, compaction, D, E]
  firstKeptEntryId = "B"
  
  输出:
  1. CompactionSummaryMessage (摘要)
  2. msg(B) (从 firstKeptEntryId 开始)
  3. msg(D), msg(E) (压缩后的全部)
  
  最终 messages: [摘要, msg(B), msg(D), msg(E)]
  
  注意：msg(A) 被压缩，不发送给 LLM
```

### 3.5 核心作用总结

`buildSessionContext` 的核心作用是 **构建发送给 LLM 的会话上下文**（消息列表）。

**核心逻辑流程图**：

```
┌─────────────────────────────────────────────────────────────┐
│  1. 确定叶子节点 (leafId)                                    │
│     - leafId === null → 返回空上下文（导航到第一条消息之前）    │
│     - leafId 有值 → 使用该 ID 对应的 entry                   │
│     - leafId 未提供 → 使用最后一个 entry                      │
├─────────────────────────────────────────────────────────────┤
│  2. 从叶子向根遍历 (parentId chain)                          │
│     通过 parentId 链向上遍历，收集路径上的所有条目            │
├─────────────────────────────────────────────────────────────┤
│  3. 提取设置 (settings extraction)                          │
│     - thinkingLevel (最后设置的值)                           │
│     - model (provider + modelId)                            │
│     - compaction (压缩摘要)                                 │
├─────────────────────────────────────────────────────────────┤
│  4. 构建消息列表 (message assembly)                          │
│     处理 compaction：摘要 + 保留的消息 + compaction 后的消息  │
│     处理 custom_message / branch_summary                     │
└─────────────────────────────────────────────────────────────┘
```

**返回值说明**：

```typescript
interface SessionContext {
  messages: AgentMessage[];      // 发送给 LLM 的消息列表
  thinkingLevel: string;          // 当前思考级别
  model: { provider, modelId };   // 当前模型配置
}
```

### 3.6 关于 sessionEntryTree 的澄清

**代码中没有 `sessionEntryTree` 这个概念**，但存在以下相关结构：

| 概念 | 位置 | 说明 |
|------|------|------|
| `getTree()` | 第1112-1150行 | 返回树结构 `SessionTreeNode[]`，用于可视化 |
| `byId` Map | 第714行 | ID → Entry 的快速查找映射 |
| `parentId` 链 | Entry 结构 | 通过 parentId 形成隐式树结构 |

**重要区别**：`buildSessionContext` **不使用** `getTree()` 方法，而是：

- 直接使用 `entries` 数组
- 使用 `byId` Map 来快速查找条目
- 通过 `parentId` 链实现"从叶子到根"的遍历

### 3.7 SessionManager 实例方法

```typescript
// 源码位置: session-manager.ts:1086-1088
buildSessionContext(): SessionContext {
    return buildSessionContext(this.getEntries(), this.leafId, this.byId);
}
```

这确实是通过 **当前 leaf 的位置** 来获取上下文配置 —— `this.leafId` 是关键，它指向当前所在的会话节点。

### 3.8 使用场景

| 文件 | 行号 | 使用场景 |
|------|------|---------|
| `agent-session-runtime.ts` | 239 | 恢复会话时设置消息 |
| `agent-session.ts` | 1693, 1973, 2822 | 各种会话操作中获取消息列表 |
| `compaction.ts` | 670 | 估算 token 数量 |
| `interactive-mode.ts` | 3195, 3221 | 交互模式中获取上下文 |

---

## 四、JSONL 文件格式

### 4.1 文件路径格式

```typescript
// 源码位置: session-manager.ts:427-434
export function getDefaultSessionDir(cwd: string, agentDir: string): string {
  // cwd 编码为安全目录名
  const safePath = `--${cwd.replace(/^[/\\]/, "").replace(/[/\\:]/g, "-")}--`;
  const sessionDir = join(agentDir, "sessions", safePath);
  // ...
}
```

**文件路径示例**：

```
~/.pi/agent/sessions/--home-user-project--/2026-06-19T10-30-00_abc123.jsonl
                       ↑ cwd 编码            ↑ 时间戳_UUIDv7
```

### 4.2 JSONL 文件内容格式

每行一个 JSON 对象，格式如下：

```jsonl
{"type":"session","version":3,"id":"abc123","timestamp":"2026-06-19T10-30:00Z","cwd":"/project"}
{"type":"message","id":"a1b2c3d4","parentId":null,"timestamp":"...","message":{"role":"user","content":"Hello"}}
{"type":"message","id":"b2c3d4e5","parentId":"a1b2c3d4","timestamp":"...","message":{"role":"assistant","content":"Hi"}}
{"type":"thinking_level_change","id":"c3d4e5f6","parentId":"b2c3d4e5","timestamp":"...","thinkingLevel":"high"}
{"type":"model_change","id":"d4e5f6g7","parentId":"c3d4e5f6","timestamp":"...","provider":"anthropic","modelId":"claude-sonnet-4"}
{"type":"compaction","id":"e5f6g7h8","parentId":"d4e5f6g7","timestamp":"...","summary":"...","firstKeptEntryId":"b2c3d4e5","tokensBefore":50000}
```

### 4.3 追加写入机制

```typescript
// 源码位置: session-manager.ts:838-862
_persist(entry: SessionEntry): void {
  if (!this.persist || !this.sessionFile) return;
  
  // 检查是否有 assistant 消息
  const hasAssistant = this.fileEntries.some(
    e => e.type === "message" && e.message.role === "assistant"
  );
  
  if (!hasAssistant) {
    // 没有 assistant → 不写入，等待
    this.flushed = false;
    return;
  }
  
  if (!this.flushed) {
    // 首次写入：批量写入所有已有 Entry
    for (const e of this.fileEntries) {
      appendFileSync(this.sessionFile, `${JSON.stringify(e)}\n`);
    }
    this.flushed = true;
  } else {
    // 后续写入：追加单个 Entry
    appendFileSync(this.sessionFile, `${JSON.stringify(entry)}\n`);
  }
}
```

**设计意图**：

| 情况 | 行为 |
|------|------|
| 无 assistant 消息 | 不写入文件（延迟到有 assistant） |
| 首次有 assistant | 批量写入所有已有 Entry |
| 之后 | 每次追加单个 Entry |

**好处**：
- 避免只有 user 消息的"半成品"会话文件
- 用户输入但不发送的场景不会产生无效文件

### 4.4 文件加载与解析

```typescript
// 源码位置: session-manager.ts:283-298
export function parseSessionEntries(content: string): FileEntry[] {
  const entries: FileEntry[] = [];
  const lines = content.trim().split("\n");
  
  for (const line of lines) {
    if (!line.trim()) continue;
    try {
      const entry = JSON.parse(line) as FileEntry;
      entries.push(entry);
    } catch {
      // 跳过格式错误的行
    }
  }
  
  return entries;
}
```

---

## 五、SessionManager 类详解

### 5.1 类结构概览

```typescript
// 源码位置: session-manager.ts:706-717
export class SessionManager {
  // ===== 核心状态 =====
  private sessionId: string = "";
  private sessionFile: string | undefined;
  private sessionDir: string;
  private cwd: string;
  private persist: boolean;
  
  // ===== 文件数据 =====
  private flushed: boolean = false;
  private fileEntries: FileEntry[] = [];
  
  // ===== 索引缓存 =====
  private byId: Map<string, SessionEntry> = new Map();
  private labelsById: Map<string, string> = new Map();
  private labelTimestampsById: Map<string, string> = new Map();
  
  // ===== Leaf 指针 =====
  private leafId: string | null = null;
}
```

### 5.2 索引构建：_buildIndex()

```typescript
// 源码位置: session-manager.ts:791-810
private _buildIndex(): void {
  this.byId.clear();
  this.labelsById.clear();
  this.labelTimestampsById.clear();
  this.leafId = null;
  
  for (const entry of this.fileEntries) {
    if (entry.type === "session") continue;  // 跳过 header
    
    this.byId.set(entry.id, entry);
    this.leafId = entry.id;  // 最后一个 Entry 成为 leaf
    
    if (entry.type === "label") {
      if (entry.label) {
        this.labelsById.set(entry.targetId, entry.label);
        this.labelTimestampsById.set(entry.targetId, entry.timestamp);
      } else {
        // undefined 表示删除标签
        this.labelsById.delete(entry.targetId);
        this.labelTimestampsById.delete(entry.targetId);
      }
    }
  }
}
```

**关键点**：
- `leafId` 默认为最后一个 Entry 的 id
- 标签缓存同步更新

### 5.3 Append 方法详解

所有 `appendXXX` 方法遵循统一模式：

```typescript
// 统一模式
appendXXX(...args): string {
  const entry: XXXEntry = {
    type: "xxx",
    id: generateId(this.byId),     // 生成唯一 ID
    parentId: this.leafId,         // 当前 leaf 作为父
    timestamp: new Date().toISOString(),
    // ... 特定字段
  };
  this._appendEntry(entry);
  return entry.id;
}

private _appendEntry(entry: SessionEntry): void {
  this.fileEntries.push(entry);
  this.byId.set(entry.id, entry);
  this.leafId = entry.id;          // 新 Entry 成为 leaf
  this._persist(entry);            // 持久化
}
```

**Append 方法列表**：

| 方法 | Entry 类型 | 用途 |
|------|-----------|------|
| `appendMessage()` | SessionMessageEntry | 用户/助手消息 |
| `appendThinkingLevelChange()` | ThinkingLevelChangeEntry | 思维级别变更 |
| `appendModelChange()` | ModelChangeEntry | 模型切换 |
| `appendCompaction()` | CompactionEntry | 压缩摘要 |
| `appendCustomEntry()` | CustomEntry | 扩展数据存储 |
| `appendCustomMessageEntry()` | CustomMessageEntry | 扩展消息注入 |
| `appendSessionInfo()` | SessionInfoEntry | 会话名称 |
| `appendLabelChange()` | LabelEntry | 标签标记 |

### 5.4 Branch 操作详解

Branch 操作是 SessionManager 实现"时光机"功能的核心，允许用户在会话历史中回溯并创建新分支。

#### 5.4.1 branch() - 移动 Leaf 指针

```typescript
// 源码位置: session-manager.ts:1162-1167
branch(branchFromId: string): void {
  if (!this.byId.has(branchFromId)) {
    throw new Error(`Entry ${branchFromId} not found`);
  }
  this.leafId = branchFromId;  // 仅移动指针，不修改数据
}
```

**应用场景**：

| 场景 | 说明 |
|------|------|
| **树形导航** | 用户通过 `/tree` 命令选择回到某个历史节点 |
| **重新编辑** | 用户想修改之前的某条消息，从这个节点重新开始 |
| **探索不同方案** | 从某个决策点尝试不同的实现路径 |

**工作原理**：

```
执行前的树结构:
  A → B → C → D → E
            ↑ leaf

执行 branch("C") 后:
  A → B → C → D → E (原有分支，不删除)
         ↑ leaf (移动到这里)

追加新 Entry F:
  A → B → C → D → E (原有分支，被"跳过")
         ↓
         F (新分支)
         ↑ leaf

关键点:
- branch() 不删除任何数据
- 只是移动 leafId 指针
- 原有分支 D → E 仍然存在，可通过 getTree() 看到
```

**实际调用位置**（源码分析）：

```typescript
// agent-session.ts:2813
// 当用户导航到某个节点且不需要生成摘要时
this.sessionManager.branch(newLeafId);
```

---

#### 5.4.2 resetLeaf() - 回到起点

```typescript
// 源码位置: session-manager.ts:1174-1176
resetLeaf(): void {
  this.leafId = null;  // 下一个 Entry 将成为 root
}
```

**应用场景**：

| 场景 | 说明 |
|------|------|
| **重新编辑第一条消息** | 用户想完全重写第一个问题 |
| **导航到"第一条消息之前"** | 在树形导航中选中"开始新对话"选项 |
| **清空会话起点** | 配合后续 append 创建新的 root |

**工作原理**：

```
执行前:
  A → B → C
       ↑ leaf

执行 resetLeaf() 后:
  A → B → C (原有数据保留)
  ↑ leaf = null (指向"虚空")

追加新 Entry D (parentId = null):
  A → B → C (原有分支)
  
  D (新的 root，与 A 平级)
  ↑ leaf

结果: getTree() 返回两个 root: [A, D]
```

**实际调用位置**：

```typescript
// agent-session.ts:2810
// 当用户导航到 root（newLeafId === null）且不需要摘要时
this.sessionManager.resetLeaf();
```

---

#### 5.4.3 branchWithSummary() - 带摘要分支

```typescript
// 源码位置: session-manager.ts:1183-1200
branchWithSummary(branchFromId: string | null, summary: string, details?: unknown, fromHook?: boolean): string {
  this.leafId = branchFromId;
  
  const entry: BranchSummaryEntry = {
    type: "branch_summary",
    id: generateId(this.byId),
    parentId: branchFromId,       // 直接作为 branchFromId 的子节点
    timestamp: new Date().toISOString(),
    fromId: branchFromId ?? "root",
    summary,
    details,
    fromHook,
  };
  
  this._appendEntry(entry);
  return entry.id;
}
```

**应用场景**：

| 场景 | 说明 |
|------|------|
| **保留被跳过路径的上下文** | 用户跳过了 D → E 分支，但想保留其关键信息 |
| **LLM 生成的导航摘要** | 通过 `/tree` 导航时，可选让 LLM 生成摘要 |
| **扩展注入摘要** | 扩展可以通过 hook 自定义摘要内容 |

**工作原理**：

```
执行前:
  A → B → C → D → E
            ↑ leaf

用户选择从 C 开始新分支，并生成摘要描述 D → E 的内容

执行 branchWithSummary("C", "探索了方案X，发现不可行...") 后:
  A → B → C → D → E (原有分支，仍存在)
         ↓
         [branch_summary: "探索了方案X..."]
         ↑ leaf

追加新 Entry F:
  A → B → C → D → E (原有分支)
         ↓
         [branch_summary] → F
                            ↑ leaf

关键效果:
- BranchSummaryEntry 被注入到 LLM 上下文（buildSessionContext 会处理）
- LLM 知道 D → E 分支发生了什么，不会丢失上下文
```

**摘要注入到 LLM 上下文的流程**：

```typescript
// buildSessionContext 内部处理
const appendMessage = (entry: SessionEntry) => {
  if (entry.type === "branch_summary" && entry.summary) {
    messages.push(createBranchSummaryMessage(entry.summary, entry.fromId, entry.timestamp));
  }
};

// 生成的消息格式
{
  role: "branchSummary",
  summary: "探索了方案X，发现不可行...",
  fromId: "C",
  timestamp: ...
}
```

**实际调用位置**：

```typescript
// agent-session.ts:2796-2802
// 当用户选择生成导航摘要时
const summaryId = this.sessionManager.branchWithSummary(
  newLeafId,
  summaryText,
  summaryDetails,
  fromExtension,
);
```

---

#### 5.4.4 Branch 操作对比总结

| 操作 | leafId 变化 | 是否创建 Entry | 摘要处理 | 适用场景 |
|------|------------|----------------|----------|---------|
| `branch(id)` | → `id` | ❌ 否 | ❌ 无 | 简单回溯，不需保留上下文 |
| `resetLeaf()` | → `null` | ❌ 否 | ❌ 无 | 回到起点，重新开始 |
| `branchWithSummary(id, summary)` | → `id` | ✅ 创建 BranchSummaryEntry | ✅ 注入 LLM 上下文 | 需保留被跳过路径的关键信息 |

---

### 5.5 createBranchedSession() - 创建分支会话文件

#### 5.5.1 方法签名与返回值

```typescript
// 源码位置: session-manager.ts:1207-1299
createBranchedSession(leafId: string): string | undefined
```

**返回值说明**：
- 持久化模式：返回新创建的 session 文件路径
- 内存模式：返回 `undefined`（无文件）

---

#### 5.5.2 应用场景

| 场景 | 说明 | 调用位置 |
|------|------|---------|
| **Fork 操作** | 从某个节点创建独立的会话文件 | `agent-session-runtime.ts:296, 317` |
| **提取单一路径** | 从多分支树中提取一条路径为独立会话 | 用户主动操作 |
| **跨项目 Fork** | 将某条路径复制到新项目目录 | 配合 `forkFrom()` |

**Fork 操作的两种模式**：

```typescript
// agent-session-runtime.ts 中的两种 Fork 情况

// 情况1: Fork 到新项目目录
const sessionManager = SessionManager.open(currentSessionFile, sessionDir);
const forkedSessionPath = sessionManager.createBranchedSession(targetLeafId);
// 创建新文件，保持原文件不变

// 情况2: Fork 在当前项目（替换当前 session）
const sessionManager = this.session.sessionManager;
sessionManager.createBranchedSession(targetLeafId);
// 直接替换当前 sessionManager 的内容
```

---

#### 5.5.3 完整工作原理

```
执行前的多分支树结构:
  A → B → C → D → E (分支1)
         ↓
         F → G (分支2，当前 leaf = G)
         
用户选择从 C 创建分支会话（leafId = C）

Step 1: 获取路径 getBranch("C")
  path = [A, B, C]

Step 2: 过滤 LabelEntry
  pathWithoutLabels = [A, B, C] (假设无 label)

Step 3: 创建新 SessionHeader
  {
    type: "session",
    version: 3,
    id: newSessionId,           // 新的 UUIDv7
    timestamp: newTimestamp,
    cwd: this.cwd,
    parentSession: previousSessionFile  // 指向原文件（追溯来源）
  }

Step 4: 收集路径上的标签
  查找 labelsById 中 targetId 在 {A, B, C} 集合内的标签
  重建 LabelEntry，挂在路径最后

Step 5: 更新内部状态
  this.fileEntries = [header, A, B, C, ...labelEntries]
  this.sessionId = newSessionId
  this.sessionFile = newSessionFile
  this._buildIndex()  // 重建索引

Step 6: 文件写入（延迟或立即）
  - 如果路径中有 assistant message → 立即写入
  - 否则 → 延迟到 _persist()（第一条 assistant 到达时）

最终结果:
  原 session 文件: 包含 A → B → C → D → E 和 A → B → C → F → G
  新 session 文件: 只包含 A → B → C（单一路径）
```

---

#### 5.5.4 核心代码详解

```typescript
// 源码位置: session-manager.ts:1207-1299
createBranchedSession(leafId: string): string | undefined {
  const previousSessionFile = this.sessionFile;
  const path = this.getBranch(leafId);
  if (path.length === 0) {
    throw new Error(`Entry ${leafId} not found`);
  }

  // 1. 过滤 LabelEntry（标签不参与路径，但需要重建）
  const pathWithoutLabels = path.filter((e) => e.type !== "label");

  // 2. 创建新 SessionHeader
  const newSessionId = createSessionId();
  const timestamp = new Date().toISOString();
  const fileTimestamp = timestamp.replace(/[:.]/g, "-");
  const newSessionFile = join(this.getSessionDir(), `${fileTimestamp}_${newSessionId}.jsonl`);

  const header: SessionHeader = {
    type: "session",
    version: CURRENT_SESSION_VERSION,
    id: newSessionId,
    timestamp,
    cwd: this.cwd,
    parentSession: this.persist ? previousSessionFile : undefined,
  };

  // 3. 收集路径上的标签
  const pathEntryIds = new Set(pathWithoutLabels.map((e) => e.id));
  const labelsToWrite: Array<{ targetId: string; label: string; timestamp: string }> = [];
  for (const [targetId, label] of this.labelsById) {
    if (pathEntryIds.has(targetId)) {
      labelsToWrite.push({ targetId, label, timestamp: this.labelTimestampsById.get(targetId)! });
    }
  }

  // 4. 持久化模式处理
  if (this.persist) {
    // 构建标签 Entry，挂在路径最后
    const lastEntryId = pathWithoutLabels[pathWithoutLabels.length - 1]?.id || null;
    let parentId = lastEntryId;
    const labelEntries: LabelEntry[] = [];
    for (const { targetId, label, timestamp: labelTimestamp } of labelsToWrite) {
      const labelEntry: LabelEntry = {
        type: "label",
        id: generateId(new Set(pathEntryIds)),
        parentId,
        timestamp: labelTimestamp,
        targetId,
        label,
      };
      pathEntryIds.add(labelEntry.id);
      labelEntries.push(labelEntry);
      parentId = labelEntry.id;
    }

    // 更新内部状态
    this.fileEntries = [header, ...pathWithoutLabels, ...labelEntries];
    this.sessionId = newSessionId;
    this.sessionFile = newSessionFile;
    this._buildIndex();

    // 5. 文件写入策略
    const hasAssistant = this.fileEntries.some(
      (e) => e.type === "message" && e.message.role === "assistant"
    );
    if (hasAssistant) {
      this._rewriteFile();
      this.flushed = true;
    } else {
      // 延迟写入，等待第一条 assistant message
      this.flushed = false;
    }

    return newSessionFile;
  }

  // 6. 内存模式处理
  // ... 类似逻辑，不创建文件
  return undefined;
}
```

---

#### 5.5.5 关键设计要点

| 设计要点 | 说明 |
|----------|------|
| **parentSession 字段** | 新 header 的 `parentSession` 指向原文件，支持追溯来源 |
| **标签重建** | 标签不参与路径，但需要在新 session 中重建（挂在路径末尾） |
| **延迟写入** | 路径无 assistant时不立即写入，避免"半成品"文件 |
| **内部状态替换** | 方法执行后，当前 sessionManager 的内容被替换为提取的路径 |

---

#### 5.5.6 测试用例验证

```typescript
// tree-traversal.test.ts:419-441
it("creates new session with path to specified leaf (in-memory)", () => {
  const session = SessionManager.inMemory();

  // Build: 1 → 2 → 3 → 4
  const id1 = session.appendMessage(userMsg("1"));
  const id2 = session.appendMessage(assistantMsg("2"));
  const id3 = session.appendMessage(userMsg("3"));
  session.appendMessage(assistantMsg("4"));

  // Branch from 3: 3 → 5
  session.branch(id3);
  session.appendMessage(userMsg("5"));

  // 从 id2 创建分支会话（应只保留 1 → 2）
  session.createBranchedSession(id2);

  const entries = session.getEntries();
  expect(entries).toHaveLength(2);  // 只有 id1 和 id2
  expect(entries[0].id).toBe(id1);
  expect(entries[1].id).toBe(id2);
});
```

---

### 5.6 静态工厂方法详解

SessionManager 提供了 7 个静态工厂方法，用于创建、打开和管理会话。

#### 5.6.1 方法概览

| 方法 | 功能 | 返回值 |
|------|------|--------|
| `create(cwd, sessionDir?)` | 创建新会话文件 | SessionManager |
| `open(path, sessionDir?, cwdOverride?)` | 打开指定会话文件 | SessionManager |
| `continueRecent(cwd, sessionDir?)` | 继续最近会话或创建新 | SessionManager |
| `inMemory(cwd?)` | 创建内存会话（无持久化） | SessionManager |
| `forkFrom(sourcePath, targetCwd, sessionDir?)` | 从其他项目 fork 会话 | SessionManager |
| `list(cwd, sessionDir?, onProgress?)` | 列出指定目录的会话 | Promise<SessionInfo[]> |
| `listAll(onProgress?)` | 列出所有项目的会话 | Promise<SessionInfo[]> |

---

#### 5.6.2 create() - 创建新会话

```typescript
// 源码位置: session-manager.ts:1306-1309
static create(cwd: string, sessionDir?: string): SessionManager {
  const dir = sessionDir ?? getDefaultSessionDir(cwd);
  return new SessionManager(cwd, dir, undefined, true);
}
```

**应用场景**：
- 启动新对话
- `/new` 命令
- 明确要创建全新会话

**参数说明**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `cwd` | `string` | 工作目录，存储在 header 中 |
| `sessionDir` | `string?` | 自定义会话目录，默认 `~/.pi/agent/sessions/<encoded-cwd>/` |

---

#### 5.6.3 open() - 打开指定会话文件

```typescript
// 源码位置: session-manager.ts:1317-1325
static open(path: string, sessionDir?: string, cwdOverride?: string): SessionManager {
  // 1. 从文件加载 entries
  const entries = loadEntriesFromFile(path);
  // 2. 提取 header 中的 cwd
  const header = entries.find((e) => e.type === "session") as SessionHeader | undefined;
  const cwd = cwdOverride ?? header?.cwd ?? process.cwd();
  // 3. sessionDir 默认为文件所在目录
  const dir = sessionDir ?? resolve(path, "..");
  return new SessionManager(cwd, dir, path, true);
}
```

**应用场景**：
- `/resume` 选择特定会话恢复
- `/session <path>` 指定文件路径
- 恢复指定历史会话

**参数说明**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `path` | `string` | 会话文件绝对路径 |
| `sessionDir` | `string?` | 会话目录（用于 `/new` 或 `/branch`） |
| `cwdOverride` | `string?` | 覆盖 header 中的 cwd |

---

#### 5.6.4 continueRecent() - 继续最近会话

```typescript
// 源码位置: session-manager.ts:1332-1339
static continueRecent(cwd: string, sessionDir?: string): SessionManager {
  const dir = sessionDir ?? getDefaultSessionDir(cwd);
  // 查找最近修改的会话文件
  const mostRecent = findMostRecentSession(dir);
  if (mostRecent) {
    return new SessionManager(cwd, dir, mostRecent, true);  // 恢复最近会话
  }
  return new SessionManager(cwd, dir, undefined, true);     // 无历史则创建新会话
}
```

**应用场景**：
- 默认启动模式（无指定会话时）
- "继续上次对话"功能

**工作流程**：

```
continueRecent(cwd)
    ↓
查找 sessions 目录中最最近修改的 .jsonl 文件
    ↓
┌─────────────────┬─────────────────┐
│ 找到会话文件      │ 未找到          │
│ → open(path)    │ → create(cwd)   │
└─────────────────┴─────────────────┘
```

---

#### 5.6.5 inMemory() - 内存会话

```typescript
// 源码位置: session-manager.ts:1342-1344
static inMemory(cwd: string = process.cwd()): SessionManager {
  return new SessionManager(cwd, "", undefined, false);  // persist = false
}
```

**应用场景**：
- 单次执行不需要持久化
- 测试场景
- 临时会话

**特点**：
- `persist = false` → 不写入文件
- `sessionDir = ""` → 无目录
- 所有数据只在内存中，进程结束即丢失

---

#### 5.6.6 forkFrom() - 跨项目 Fork（重点）

```typescript
// 源码位置: session-manager.ts:1353-1394
static forkFrom(sourcePath: string, targetCwd: string, sessionDir?: string): SessionManager {
  // 1. 加载源会话
  const sourceEntries = loadEntriesFromFile(sourcePath);
  if (sourceEntries.length === 0) {
    throw new Error(`Cannot fork: source session file is empty or invalid: ${sourcePath}`);
  }
  const sourceHeader = sourceEntries.find((e) => e.type === "session") as SessionHeader | undefined;
  if (!sourceHeader) {
    throw new Error(`Cannot fork: source session has no header: ${sourcePath}`);
  }

  // 2. 创建目标目录
  const dir = sessionDir ?? getDefaultSessionDir(targetCwd);
  if (!existsSync(dir)) {
    mkdirSync(dir, { recursive: true });
  }

  // 3. 创建新会话文件（新 ID，新 cwd）
  const newSessionId = createSessionId();
  const timestamp = new Date().toISOString();
  const fileTimestamp = timestamp.replace(/[:.]/g, "-");
  const newSessionFile = join(dir, `${fileTimestamp}_${newSessionId}.jsonl`);

  // 4. 写入新 Header（指向源文件为 parent）
  const newHeader: SessionHeader = {
    type: "session",
    version: CURRENT_SESSION_VERSION,
    id: newSessionId,
    timestamp,
    cwd: targetCwd,              // 目标项目目录
    parentSession: sourcePath,   // 指向源文件
  };
  appendFileSync(newSessionFile, `${JSON.stringify(newHeader)}\n`);

  // 5. 复制源会话的所有 Entry（不含 header）
  for (const entry of sourceEntries) {
    if (entry.type !== "session") {
      appendFileSync(newSessionFile, `${JSON.stringify(entry)}\n`);
    }
  }

  return new SessionManager(targetCwd, dir, newSessionFile, true);
}
```

**应用场景**：

| 场景 | 说明 |
|------|------|
| **跨项目复用对话** | 将项目 A 的会话复制到项目 B |
| **在新目录继续** | 保持历史上下文，在新工作目录工作 |
| **模板会话** | 从预设模板会话创建新会话 |

**与 createBranchedSession() 的区别**：

| 特性 | forkFrom() | createBranchedSession() |
|------|------------|------------------------|
| **调用方式** | 静态方法 | 实例方法 |
| **源会话** | 外部文件路径 | 当前 SessionManager 内部 |
| **目标目录** | 新的 targetCwd | 当前 cwd |
| **Entry 选择** | 全部复制 | 选择路径（leafId 到 root） |
| **leafId** | 保持源会话的 leafId | 设置为 leafId |

**工作流程图**：

```
源项目 A (~/.pi/sessions/--project-a--/session1.jsonl)
    │
    │  forkFrom(session1.jsonl, "/project-b")
    │
    ↓
目标项目 B (~/.pi/sessions/--project-b--/new_session.jsonl)
    │
    │  新 Header:
    │  - id: newSessionId (新)
    │  - cwd: /project-b (目标目录)
    │  - parentSession: session1.jsonl (指向源)
    │
    │  Entry: 完整复制源会话的所有 Entry
    │  - 保持相同的 id/parentId 结构
    │  - 保持相同的 leafId
    │
    ↓
返回新 SessionManager (cwd = /project-b)
```

---

#### 5.6.7 list() 和 listAll() - 会话列表

```typescript
// 源码位置: session-manager.ts:1402-1407
static async list(cwd: string, sessionDir?: string, onProgress?: SessionListProgress): Promise<SessionInfo[]> {
  const dir = sessionDir ?? getDefaultSessionDir(cwd);
  const sessions = await listSessionsFromDir(dir, onProgress);
  sessions.sort((a, b) => b.modified.getTime() - a.modified.getTime());
  return sessions;
}

// 源码位置: session-manager.ts:1413-1457
static async listAll(onProgress?: SessionListProgress): Promise<SessionInfo[]> {
  const sessionsDir = getSessionsDir();  // ~/.pi/agent/sessions/
  // 遍历所有子目录，收集所有 .jsonl 文件
  // ...
}
```

**应用场景**：
- `/resume` 显示会话列表
- 会话管理 UI

**SessionInfo 结构**：

```typescript
interface SessionInfo {
  path: string;              // 文件路径
  id: string;                // 会话 ID
  cwd: string;               // 工作目录
  name?: string;             // 用户定义名称
  parentSessionPath?: string;// Fork 来源
  created: Date;             // 创建时间
  modified: Date;            // 最后修改时间
  messageCount: number;      // 消息数量
  firstMessage: string;      // 第一条消息（用于显示）
  allMessagesText: string;   // 所有消息文本（用于搜索）
}
```

---

#### 5.6.8 静态方法选择指南

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         静态方法选择决策树                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  需要创建/获取 SessionManager                                           │
│           ↓                                                             │
│  ┌─────────────────────────────────────────┐                           │
│  │ 是否需要持久化？                          │                           │
│  ├─────────────────┬───────────────────────┤                           │
│  │ 否              │ 是                     │                           │
│  │ → inMemory()    │ ↓                      │                           │
│  └─────────────────┴───────────────────────┘                           │
│                       ↓                                                 │
│  ┌─────────────────────────────────────────┐                           │
│  │ 是否有特定会话文件路径？                   │                           │
│  ├─────────────────┬───────────────────────┤                           │
│  │ 是              │ 否                     │                           │
│  │ → open(path)    │ ↓                      │                           │
│  └─────────────────┴───────────────────────┘                           │
│                       ↓                                                 │
│  ┌─────────────────────────────────────────┐                           │
│  │ 是否要继续最近的会话？                     │                           │
│  ├─────────────────┬───────────────────────┤                           │
│  │ 是              │ 否                     │                           │
│  │ → continueRecent()│ → create(cwd)       │                           │
│  └─────────────────┴───────────────────────┘                           │
│                                                                         │
│  ┌─────────────────────────────────────────┐                           │
│  │ 是否要跨项目 Fork？                        │                           │
│  ├─────────────────┬───────────────────────┤                           │
│  │ 是              │ 否                     │                           │
│  │ → forkFrom(sourcePath, targetCwd)        │                          │
│  └─────────────────┴───────────────────────┘                           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 六、版本迁移机制

Session 文件格式经历了三次版本演进，版本迁移机制确保**旧会话文件在新版本软件中仍能正常使用**。

### 6.1 当前版本

```typescript
// 源码位置: session-manager.ts:27
export const CURRENT_SESSION_VERSION = 3;
```

---

### 6.2 版本演进历史

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Session 文件版本演进                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  v1 (最原始版本)                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 特点:                                                            │   │
│  │ • 没有 version 字段（通过缺失来判断是 v1）                          │   │
│  │ • 没有 id / parentId 字段                                        │   │
│  │ • 线性消息序列，不支持分支                                         │   │
│  │ • compaction 用 firstKeptEntryIndex（索引位置）而非 ID            │   │
│  │                                                                   │   │
│  │ 文件格式示例:                                                      │   │
│  │ {"type":"session","id":"xxx","timestamp":"...","cwd":"/project"} │   │
│  │ {"type":"message","message":{"role":"user","content":"Hello"}}   │   │
│  │ {"type":"message","message":{"role":"assistant","content":"Hi"}} │   │
│  │                                                                   │   │
│  │ 问题: 无法支持时光机、无法创建分支                                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│                              ↓ migrateV1ToV2()                          │
│                                                                         │
│  v2 (引入树结构)                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 特点:                                                            │   │
│  │ • 有 version = 2 字段                                             │   │
│  │ • 每个 Entry 有 id（8位短 UUID）                                   │   │
│  │ • 每个 Entry 有 parentId（形成树结构）                             │   │
│  │ • compaction 用 firstKeptEntryId（Entry ID）                      │   │
│  │                                                                   │   │
│  │ 文件格式示例:                                                      │   │
│  │ {"type":"session","version":2,"id":"xxx",...}                    │   │
│  │ {"type":"message","id":"a1b2c3d4","parentId":null,...}           │   │
│  │ {"type":"message","id":"b2c3d4e5","parentId":"a1b2c3d4",...}     │   │
│  │                                                                   │   │
│  │ 新能力: 支持时光机、多分支、树形导航                                 │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│                              ↓ migrateV2ToV3()                          │
│                                                                         │
│  v3 (当前版本)                                                           │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 特点:                                                            │   │
│  │ • version = 3                                                    │   │
│  │ • hookMessage role → custom role                                 │   │
│  │                                                                   │   │
│  │ 原因: 统一扩展消息类型命名                                         │   │
│  │ "hookMessage" → "custom" 更通用、更清晰                           │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### 6.3 版本差异对比表

| 版本 | version 字段 | id/parentId | compaction 引用 | 消息角色命名 |
|------|-------------|-------------|----------------|-------------|
| **v1** | 无（隐式） | 无 | `firstKeptEntryIndex`（索引） | 无 hookMessage |
| **v2** | `version: 2` | 有 | `firstKeptEntryId`（ID） | hookMessage |
| **v3** | `version: 3` | 有 | `firstKeptEntryId`（ID） | custom |

---

### 6.4 迁移触发时机

```typescript
// 源码位置: session-manager.ts:265-275
function migrateToCurrentVersion(entries: FileEntry[]): boolean {
  const header = entries.find((e) => e.type === "session");
  const version = header?.version ?? 1;  // 无 version 字段 = v1
  
  if (version >= CURRENT_SESSION_VERSION) return false;  // 已是最新，无需迁移
  
  // 依次执行迁移
  if (version < 2) migrateV1ToV2(entries);  // v1 → v2
  if (version < 3) migrateV2ToV3(entries);  // v2 → v3
  
  return true;  // 迁移完成，需要重写文件
}
```

**触发场景**：打开会话文件时（`setSessionFile()` 或 `open()`）

---

### 6.5 v1 → v2 迁移详解

```typescript
// 源码位置: session-manager.ts:215-241
function migrateV1ToV2(entries: FileEntry[]): void {
  const ids = new Set<string>();
  let prevId: string | null = null;
  
  for (const entry of entries) {
    if (entry.type === "session") {
      entry.version = 2;  // 标记为新版本
      continue;
    }
    
    // 1. 给每个 Entry 生成 id（8位短 UUID）
    entry.id = generateId(ids);
    
    // 2. 设置 parentId（线性连接，前一个 Entry 作为父）
    entry.parentId = prevId;
    prevId = entry.id;
    
    // 3. compaction: firstKeptEntryIndex → firstKeptEntryId
    if (entry.type === "compaction") {
      const comp = entry as CompactionEntry & { firstKeptEntryIndex?: number };
      if (typeof comp.firstKeptEntryIndex === "number") {
        // 旧版本用索引位置，新版本用 Entry ID
        const targetEntry = entries[comp.firstKeptEntryIndex];
        if (targetEntry && targetEntry.type !== "session") {
          comp.firstKeptEntryId = targetEntry.id;
        }
        delete comp.firstKeptEntryIndex;  // 删除旧字段
      }
    }
  }
}
```

**迁移示例**：

```
原始 v1 文件:                      迁移后 v2 文件:
┌─────────────────────────────┐   ┌─────────────────────────────────────┐
│ {"type":"session",...}       │   │ {"type":"session","version":2,...}  │
│ {"type":"message",...}       │   │ {"type":"message","id":"a1",        │
│ {"type":"message",...}       │   │  "parentId":null,...}               │
│ {"type":"message",...}       │   │ {"type":"message","id":"b2",        │
│ {"type":"compaction",        │   │  "parentId":"a1",...}               │
│  "firstKeptEntryIndex":2}    │   │ {"type":"message","id":"c3",        │
└─────────────────────────────┘   │  "parentId":"b2",...}               │
                                  │ {"type":"compaction",               │
                                  │  "firstKeptEntryId":"b2"}           │
                                  └─────────────────────────────────────┘

关键变化:
• 线性结构 → 链式树结构
• 索引位置 → Entry ID 引用
• 每个 Entry 获得 8 位 ID
```

---

### 6.6 v2 → v3 迁移详解

```typescript
// 源码位置: session-manager.ts:244-259
function migrateV2ToV3(entries: FileEntry[]): void {
  for (const entry of entries) {
    if (entry.type === "session") {
      entry.version = 3;
      continue;
    }
    
    // 重命名消息角色
    if (entry.type === "message") {
      const msgEntry = entry as SessionMessageEntry;
      if (msgEntry.message && (msgEntry.message as { role: string }).role === "hookMessage") {
        (msgEntry.message as { role: string }).role = "custom";
      }
    }
  }
}
```

**命名变更原因**：

| 原名称 | 新名称 | 原因 |
|--------|--------|------|
| `hookMessage` | `custom` | 与 hook 系统解耦，更通用、更清晰 |

**迁移示例**：

```
原始 v2 文件:                      迁移后 v3 文件:
┌─────────────────────────────┐   ┌─────────────────────────────────────┐
│ {"type":"session",          │   │ {"type":"session","version":3,...}  │
│  "version":2,...}           │   │                                     │
│ {"type":"message",          │   │ {"type":"message",                  │
│  "message":{                │   │  "message":{                        │
│    "role":"hookMessage",... │   │    "role":"custom",...              │
│  }}                         │   │  }}                                 │
└─────────────────────────────┘   └─────────────────────────────────────┘
```

---

### 6.7 迁移后的文件处理

```typescript
// 源码位置: session-manager.ts:754-756
if (migrateToCurrentVersion(this.fileEntries)) {
  this._rewriteFile();  // 迁移完成，重写整个文件
}
```

**重写逻辑**：
- 迁移后立即写入新格式
- 保证下次打开无需再次迁移
- 原始数据内容不变，只是结构升级

---

### 6.8 版本迁移的意义

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         版本迁移的意义                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  1. 向后兼容                                                             │
│     ┌─────────────────────────────────────────────────────────────┐    │
│     │ 用户可能有旧的 session 文件，升级后仍能正常打开                  │    │
│     │ 无需手动处理，系统自动迁移                                       │    │
│     └─────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  2. 无缝升级                                                             │
│     ┌─────────────────────────────────────────────────────────────┐    │
│     │ 打开旧文件时自动迁移                                            │    │
│     │ 用户无需关心版本差异                                            │    │
│     │ 新功能（时光机、多分支）对旧会话同样生效                         │    │
│     └─────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  3. 数据安全                                                             │
│     ┌─────────────────────────────────────────────────────────────┐    │
│     │ 迁移只添加新字段/重命名                                         │    │
│     │ 不删除或修改内容                                                │    │
│     │ 原始对话内容完整保留                                            │    │
│     └─────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  4. 功能演进                                                             │
│     ┌─────────────────────────────────────────────────────────────┐    │
│     │ v1 → v2: 支持时光机、多分支                                     │    │
│     │ v2 → v3: 统一扩展消息命名                                       │    │
│     │ 未来版本可能添加更多新特性                                       │    │
│     └─────────────────────────────────────────────────────────────┘    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 七、核心设计模式总结

### 7.1 追加写入模式

**原则**：永不修改已有 Entry，只追加新 Entry。

**好处**：
- 数据安全：写入失败不影响历史
- 易恢复：文件损坏可解析到最后有效行
- 支持时光机：所有历史保留，可回溯

### 7.2 树状结构模式

**原理**：Entry 通过 `id` 和 `parentId` 形成树，`leafId` 指向当前位置。

**操作**：
- `appendXXX()` → 新 Entry 成为当前 leaf 的子节点
- `branch()` → 移动 leafId，创建新分支
- `resetLeaf()` → 回到起点，重新编辑第一条消息

### 7.3 Leaf 指针模式

**作用**：标记当前位置，支持分支和回溯。

**状态**：
- `null` → 起点
- `"entryId"` → 指定 Entry
- 默认 → 最后一个 Entry

### 7.4 状态提取模式

**原理**：从路径遍历中提取最新状态（thinkingLevel、model）。

**来源**：
- ThinkingLevelChangeEntry → thinkingLevel
- ModelChangeEntry / assistant message → model

### 7.5 Compaction 处理模式

**流程**：
1. 发送摘要消息
2. 从 `firstKeptEntryId` 开始保留原始消息
3. 压缩后的消息全部保留

**效果**：历史被摘要替代，节省 token。

### 7.6 标签缓存模式

**原理**：LabelEntry 不改变树结构，通过 `labelsById` Map 维护标签缓存。

**更新时机**：`_buildIndex()` 时同步更新缓存。

---

## 附录：完整方法列表

### 查询方法

| 方法 | 返回类型 | 说明 |
|------|---------|------|
| `getCwd()` | `string` | 工作目录 |
| `getSessionDir()` | `string` | 会话目录 |
| `getSessionId()` | `string` | 会话 ID |
| `getSessionFile()` | `string \| undefined` | 会话文件路径 |
| `getSessionName()` | `string \| undefined` | 会话名称 |
| `isPersisted()` | `boolean` | 是否持久化 |
| `getLeafId()` | `string \| null` | 当前 leaf ID |
| `getLeafEntry()` | `SessionEntry \| undefined` | 当前 leaf Entry |
| `getEntry(id)` | `SessionEntry \| undefined` | 查找 Entry |
| `getChildren(parentId)` | `SessionEntry[]` | 获取子节点 |
| `getLabel(id)` | `string \| undefined` | 获取标签 |
| `getHeader()` | `SessionHeader \| null` | 会话 header |
| `getEntries()` | `SessionEntry[]` | 所有 Entry |
| `getTree()` | `SessionTreeNode[]` | 树结构 |
| `getBranch(fromId?)` | `SessionEntry[]` | 路径 |
| `buildSessionContext()` | `SessionContext` | LLM 上下文 |

### 追加方法

| 方法 | Entry 类型 | 说明 |
|------|-----------|------|
| `appendMessage()` | SessionMessageEntry | 消息 |
| `appendThinkingLevelChange()` | ThinkingLevelChangeEntry | 思维级别 |
| `appendModelChange()` | ModelChangeEntry | 模型 |
| `appendCompaction()` | CompactionEntry | 压缩 |
| `appendCustomEntry()` | CustomEntry | 扩展数据 |
| `appendCustomMessageEntry()` | CustomMessageEntry | 扩展消息 |
| `appendSessionInfo()` | SessionInfoEntry | 名称 |
| `appendLabelChange()` | LabelEntry | 标签 |

### 分支方法

| 方法 | 说明 |
|------|------|
| `branch(branchFromId)` | 移动 leaf 指针 |
| `resetLeaf()` | 回到起点 |
| `branchWithSummary(...)` | 带摘要分支 |
| `createBranchedSession(leafId)` | 创建分支文件 |

### 工厂方法

| 方法 | 说明 |
|------|------|
| `SessionManager.create(cwd, sessionDir?)` | 创建新会话 |
| `SessionManager.open(path, sessionDir?, cwdOverride?)` | 打开指定文件 |
| `SessionManager.continueRecent(cwd, sessionDir?)` | 继续最近会话 |
| `SessionManager.inMemory(cwd?)` | 内存会话 |
| `SessionManager.forkFrom(sourcePath, targetCwd, sessionDir?)` | Fork 跨项目 |
| `SessionManager.list(cwd, sessionDir?, onProgress?)` | 列出会话 |
| `SessionManager.listAll(onProgress?)` | 列出所有会话 |

---

*文档生成时间: 2026-06-19*
*源文件位置: `.learning/agent-core-study/pi/coding-agent/src/core/session-manager.ts`*