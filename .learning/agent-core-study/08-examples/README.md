# L08: Session 管理

## 学习目标

- 🔴 掌握 Session 类核心方法
- 🔴 理解 SessionStorage 接口
- 🟠 理解 SessionRepo 仓库模式
- 🟡 理解 uuidv7() 时间排序 UUID

---

## 源文件

`src/harness/session/` 目录

---

## 1. Session 类

```typescript
// session/session.ts

class Session {
  // 核心方法
  async appendMessage(message: AgentMessage): Promise<string>;
  async appendCompaction(summary: string, firstKeptEntryId: string, ...): Promise<string>;
  async appendModelChange(provider: string, modelId: string): Promise<string>;
  async appendThinkingLevelChange(level: ThinkingLevel): Promise<string>;
  async appendCustomEntry(type: string, data: any): Promise<string>;
  
  async buildContext(): Promise<AgentContext>;
  async getBranch(): Promise<SessionTreeEntry[]>;
  async getEntry(id: string): Promise<SessionTreeEntry | undefined>;
  async getLeafId(): Promise<string>;
  async getMetadata(): Promise<SessionMetadata>;
  
  async moveTo(targetId: string, summary?: BranchSummary): Promise<string | undefined>;
  getStorage(): SessionStorage;
}
```

---

## 2. SessionStorage 接口

```typescript
// session/types.ts

interface SessionStorage {
  load(id: string): Promise<SessionTreeEntry[]>;
  save(entries: SessionTreeEntry[]): Promise<void>;
  delete(id: string): Promise<void>;
  list(): Promise<string[]>;
  setLeafId(id: string): Promise<void>;
  getLeafId(): Promise<string | undefined>;
}
```

### JsonlSessionStorage

源文件：`session/jsonl-storage.ts`

- JSON Lines 格式存储
- 追加写入优化
- 支持压缩

### MemorySessionStorage

源文件：`session/memory-storage.ts`

- 内存存储
- 测试用
- 临时会话

---

## 3. SessionRepo 仓库模式

```typescript
// session/jsonl-repo.ts

class JsonlSessionRepo implements SessionRepository {
  constructor(options: { dir: string });
  async load(id: string): Promise<SessionTreeEntry[]>;
  async save(entries: SessionTreeEntry[]): Promise<void>;
  // ...
}

// session/memory-repo.ts
class MemorySessionRepo implements SessionRepository { ... }
```

---

## 4. SessionTreeEntry 类型

```typescript
interface SessionTreeEntry {
  type: "message" | "compaction" | "model_change" | "thinking_level_change" | "branch_summary" | "custom";
  id: string;
  parentId: string | null;
  timestamp: number;
  // 根据类型有不同字段
}
```

---

## 5. uuidv7()

```typescript
// session/uuid.ts

export function uuidv7(): string;
```

**特点**：
- 基于时间的 UUID
- 字典序可排序
- 用于会话 ID 生成

---

## TODO 清单

### TODO-1: 掌握 Session 方法 (🔴)
**完成检查**:
- [ ] 列举 appendMessage, appendCompaction, buildContext 三者的用途

### TODO-2: 掌握 SessionStorage (🟠)
**完成检查**:
- [ ] 列举 SessionStorage 的 6 个方法

---

## 下一步

→ [L09: 上下文压缩](./09-compaction)