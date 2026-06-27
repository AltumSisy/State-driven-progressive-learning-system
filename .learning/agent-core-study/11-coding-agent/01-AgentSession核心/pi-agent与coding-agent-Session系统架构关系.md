---
name: session-systems-relationship
description: pi/agent (AgentHarness) 与 pi/coding-agent (SessionManager) 两个 Session 系统的架构关系与操作对比
metadata:
  type: project
---

# pi/agent 与 pi/coding-agent Session 系统架构关系

> **核心发现**：两个系统是**同一个设计理念的不同层次实现**
> - `pi/agent` 是**抽象框架层**，定义接口和通用实现
> - `pi/coding-agent` 是**具体应用层**，提供更直接的操作方法

---

## 一、架构层次对比

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        pi/agent (抽象框架层)                             │
├─────────────────────────────────────────────────────────────────────────┤
│  interfaces/                                                            │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐     │
│  │ SessionStorage  │    │ SessionRepo     │    │ Session         │     │
│  │ (存储接口)       │    │ (仓库接口)       │    │ (高层封装类)    │     │
│  └─────────────────┘    └─────────────────┘    └─────────────────┘     │
│           ↓                        ↓                        ↓           │
│  implementations/                                                       │
│  ┌─────────────────┐    ┌─────────────────┐                            │
│  │ JsonlSession    │    │ InMemorySession  │                            │
│  │ Storage         │    │ Storage          │                            │
│  │ (JSONL实现)      │    │ (内存实现)       │                            │
│  └─────────────────┘    └─────────────────┘                            │
│           ↓                        ↓                                    │
│  ┌─────────────────┐    ┌─────────────────┐                            │
│  │ JsonlSession    │    │ InMemorySession  │                            │
│  │ Repo            │    │ Repo             │                            │
│  │ (JSONL仓库)      │    │ (内存仓库)       │                            │
│  └─────────────────┘    └─────────────────┘                            │
│                                                                         │
│  harness/                                                               │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ AgentHarness                                                     │   │
│  │ - compact() → 压缩历史                                            │   │
│  │ - navigateTree() → 树形导航                                        │   │
│  │ - emitHook() → 扩展事件系统                                        │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓ 使用
┌─────────────────────────────────────────────────────────────────────────┐
│                    pi/coding-agent (具体应用层)                          │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ SessionManager                                                   │   │
│  │ - 集成存储 + 仓库 + 高层封装                                        │   │
│  │ - 更直接的 API设计                                                 │   │
│  │ - 同步 API (vs pi/agent 的异步 API)                               │   │
│  │                                                                   │   │
│  │ 操作方法:                                                         │   │
│  │ - branch() → 移动 leaf                                            │   │
│  │ - branchWithSummary() → 带摘要移动 leaf                           │   │
│  │ - resetLeaf() → 回到起点                                          │   │
│  │ - createBranchedSession() → 创建分支会话                          │   │
│  │ - buildSessionContext() → 构建 LLM 上下文                         │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ AgentSessionRuntime                                              │   │
│  │ - 使用 SessionManager                                            │   │
│  │ - 实现具体的应用逻辑                                               │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 二、操作对应关系

### 2.1 核心操作对比表

| pi/agent (框架层) | pi/coding-agent (应用层) | 功能说明 |
|-------------------|-------------------------|---------|
| `Session.moveTo(entryId, summary)` | `SessionManager.branch()` 或 `branchWithSummary()` | 移动 leaf 指针到指定位置 |
| `SessionRepo.fork(source, options)` | `SessionManager.createBranchedSession()` | 从某个节点创建新会话文件 |
| `AgentHarness.compact()` | coding-agent 的 compaction 流程 | 压缩会话历史 |
| `AgentHarness.navigateTree()` | coding-agent 的树形导航流程 | 树形导航 + 可选摘要 |
| `Session.buildContext()` | `SessionManager.buildSessionContext()` | 构建 LLM 上下文 |
| `SessionStorage.setLeafId()` | `SessionManager.branch()` 内部修改 `leafId` | 设置当前 leaf |

---

### 2.2 moveTo vs branch/branchWithSummary

```typescript
// pi/agent: Session.moveTo()
async moveTo(
  entryId: string | null,
  summary?: { summary: string; details?: unknown; fromHook?: boolean },
): Promise<string | undefined> {
  // 1. 验证 entryId 存在
  if (entryId !== null && !(await this.storage.getEntry(entryId))) {
    throw new SessionError("not_found", `Entry ${entryId} not found`);
  }
  // 2. 通过 storage.setLeafId() 移动指针
  await this.storage.setLeafId(entryId);
  // 3. 如果有 summary，创建 BranchSummaryEntry
  if (!summary) return undefined;
  return this.appendTypedEntry({
    type: "branch_summary",
    id: await this.storage.createEntryId(),
    parentId: entryId,
    timestamp: new Date().toISOString(),
    fromId: entryId ?? "root",
    summary: summary.summary,
    details: summary.details,
    fromHook: summary.fromHook,
  });
}

// pi/coding-agent: SessionManager.branch()
branch(branchFromId: string): void {
  if (!this.byId.has(branchFromId)) {
    throw new Error(`Entry ${branchFromId} not found`);
  }
  this.leafId = branchFromId;  // 直接修改内存中的 leafId
}

// pi/coding-agent: SessionManager.branchWithSummary()
branchWithSummary(branchFromId: string | null, summary: string, ...): string {
  this.leafId = branchFromId;  // 移动指针
  const entry: BranchSummaryEntry = { ... };
  this._appendEntry(entry);    // 创建摘要 Entry
  return entry.id;
}
```

**关键区别**：
- `moveTo` 是**统一方法**，通过可选参数控制是否创建摘要
- coding-agent 分成两个方法：`branch()` (无摘要) 和 `branchWithSummary()` (有摘要)

---

### 2.3 fork vs createBranchedSession

```typescript
// pi/agent: SessionRepo.fork()
async fork(
  sourceMetadata: JsonlSessionMetadata,
  options: { entryId?: string; position?: "before" | "at"; cwd: string; ... },
): Promise<Session<JsonlSessionMetadata>> {
  const source = await this.open(sourceMetadata);
  // 1. 获取要 fork 的 entries
  const forkedEntries = await getEntriesToFork(source.getStorage(), options);
  // 2. 创建新 storage
  const storage = await JsonlSessionStorage.create(this.fs, filePath, {
    cwd: options.cwd,
    sessionId: id,
    parentSessionPath: sourceMetadata.path,
  });
  // 3. 逐个追加 entries
  for (const entry of forkedEntries) {
    await storage.appendEntry(entry);
  }
  return toSession(storage);  // 返回新 Session
}

// pi/coding-agent: SessionManager.createBranchedSession()
createBranchedSession(leafId: string): string | undefined {
  // 1. 获取路径
  const path = this.getBranch(leafId);
  // 2. 创建新 header
  const header: SessionHeader = { ... };
  // 3. 直接替换当前 sessionManager 的内容
  this.fileEntries = [header, ...pathWithoutLabels, ...labelEntries];
  this.sessionId = newSessionId;
  this._buildIndex();
  // 4. 写入新文件（如果是持久化模式）
  return newSessionFile;  // 返回文件路径
}
```

**关键区别**：
- `fork` 返回**新的 Session 对象**，原 session 不变
- `createBranchedSession` **直接替换当前 SessionManager 的内容**

---

### 2.4 compact 对比

```typescript
// pi/agent: AgentHarness.compact()
async compact(customInstructions?: string): Promise<CompactResult> {
  // 1. 获取当前分支 entries
  const branchEntries = await this.session.getBranch();
  // 2. 准备压缩
  const preparationResult = prepareCompaction(branchEntries, DEFAULT_COMPACTION_SETTINGS);
  // 3. 发射 hook 事件，允许扩展自定义压缩
  const hookResult = await this.emitHook({
    type: "session_before_compact",
    preparation,
    branchEntries,
    customInstructions,
    signal: ...,
  });
  // 4. 执行压缩（如果 hook 未提供自定义结果）
  const compactResult = hookResult?.compaction
    ? { ok: true, value: hookResult.compaction }
    : await compact(preparation, model, apiKey, ...);
  // 5. 持久化 CompactionEntry
  const entryId = await this.session.appendCompaction(
    result.summary, result.firstKeptEntryId, result.tokensBefore, ...
  );
  // 6. 发射完成事件
  await this.emitOwn({ type: "session_compact", compactionEntry: entry, ... });
  return result;
}

// pi/coding-agent: 类似流程，但更直接
// 在 agent-session.ts 中实现，无 hook 事件系统
```

**关键区别**：
- pi/agent 有**完整的 hook 事件系统**，允许扩展自定义压缩逻辑
- coding-agent 直接调用 `appendCompaction()`，更简单直接

---

## 三、关键设计差异

### 3.1 Leaf 指针持久化

| 系统 | 设计方式 | 说明 |
|------|---------|------|
| **pi/agent** | `LeafEntry` 持久化 | 每次移动 leaf 时创建 `LeafEntry` 记录变化历史 |
| **pi/coding-agent** | 内存变量 `leafId` | leaf 位置只在内存中维护，不持久化 |

```typescript
// pi/agent: LeafEntry 类型定义
interface LeafEntry extends SessionTreeEntryBase {
  type: "leaf";
  targetId: string | null;  // 指向当前 leaf
}

// JsonlSessionStorage.setLeafId() 实现
async setLeafId(leafId: string | null): Promise<void> {
  const entry: LeafEntry = {
    type: "leaf",
    id: generateEntryId(this.byId),
    parentId: this.currentLeafId,
    timestamp: new Date().toISOString(),
    targetId: leafId,
  };
  await this.fs.appendFile(this.filePath, `${JSON.stringify(entry)}\n`);
  this.currentLeafId = leafId;
}

// pi/coding-agent: 直接内存变量
private leafId: string | null = null;

branch(branchFromId: string): void {
  this.leafId = branchFromId;  // 只修改内存
}
```

**设计意图**：
- pi/agent 的 `LeafEntry` 持久化保留了 leaf 位置变化的完整历史
- coding-agent 的内存变量更轻量，适合 CLI 场景（每次启动都是最新状态）

---

### 3.2 异步 vs 同步 API

| 系统 | API 风格 | 原因 |
|------|---------|------|
| **pi/agent** | 全异步 (`async/await`) | 支持多种存储后端（文件系统抽象） |
| **pi/coding-agent** | 大部分同步 | 直接操作文件系统，简化实现 |

```typescript
// pi/agent: 异步接口
interface SessionStorage {
  getLeafId(): Promise<string | null>;
  setLeafId(leafId: string | null): Promise<void>;
  getEntry(id: string): Promise<SessionTreeEntry | undefined>;
  appendEntry(entry: SessionTreeEntry): Promise<void>;
}

// pi/coding-agent: 同步方法
getLeafId(): string | null {
  return this.leafId;
}
branch(branchFromId: string): void {
  this.leafId = branchFromId;
}
getEntry(id: string): SessionEntry | undefined {
  return this.byId.get(id);
}
```

---

### 3.3 文件系统抽象

| 系统 | 文件系统访问 | 说明 |
|------|-------------|------|
| **pi/agent** | `FileSystem` 接口 | 抽象接口，支持不同实现（本地、远程、mock） |
| **pi/coding-agent** | Node.js `fs` 模块 | 直接使用 Node.js 文件系统 API |

```typescript
// pi/agent: 文件系统接口
interface FileSystem {
  cwd: string;
  readTextFile(path: string, abortSignal?: AbortSignal): Promise<Result<string, FileError>>;
  writeFile(path: string, content: string | Uint8Array, ...): Promise<Result<void, FileError>>;
  appendFile(path: string, content: string | Uint8Array, ...): Promise<Result<void, FileError>>;
  // ... 更多方法
}

// pi/coding-agent: 直接 fs
import { appendFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "fs";
```

---

## 四、总结：为什么有两个系统？

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           设计意图                                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  pi/agent (框架层):                                                     │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ • 抽象接口设计，支持多种实现                                        │   │
│  │ • 异步 API，适配不同存储后端                                        │   │
│  │ • Hook 事件系统，支持扩展定制                                       │   │
│  │ • LeafEntry 持久化，保留完整历史                                    │   │
│  │ • 目标：作为通用 Agent 框架的 Session 子系统                        │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  pi/coding-agent (应用层):                                              │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ • 具体实现，针对 CLI Coding Agent 场景                              │   │
│  │ • 同步 API，简化实现和调用                                          │   │
│  │ • 直接 fs 操作，无需抽象                                            │   │
│  │ • 内存 leafId，轻量高效                                             │   │
│  │ • 目标：为 Claude Code CLI 提供直接的 Session 管理                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  关系: pi/agent 定义抽象 → pi/coding-agent 实现具体应用                  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 五、相关文档

- [[session-manager-tree-structure]] - SessionManager 树状结构详解
- [[buildSessionContext-details]] - buildSessionContext 详细解析
- [[session-format-spec]] - Session 文件格式规范