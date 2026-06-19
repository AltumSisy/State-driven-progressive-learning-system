# Branch Summarization 与 Compaction 对比详解

> 本文档详细讲解 Branch Summarization（分支摘要）机制，并与 Compaction（上下文压缩）进行对比，帮助理解两种摘要技术的区别与联系。

## 一、核心区别：场景不同

### 1.1 触发时机对比

| 维度 | Compaction | Branch Summarization |
|------|------------|---------------------|
| **触发时机** | 上下文超限 或 `/compact` | `/tree` 导航切换分支 |
| **目的** | 释放上下文空间 | 跨分支传递上下文 |
| **摘要对象** | 当前分支的旧消息 | **被遗弃分支**的所有消息 |
| **摘要位置** | 当前分支尾部 | 被遗弃分支尾部 |
| **传递方向** | 自己压缩自己 | 从旧分支 → 新分支 |

### 1.2 场景类比

```
Compaction = 时间维度压缩
  问题：对话太长，记不住前面的内容
  解决：把旧内容压缩成摘要，保留最新内容

      时间轴
  ───────────────────────→
  旧内容    摘要    新内容
  (压缩)   (代表)  (保留)

Branch Summarization = 空间维度传递
  问题：切换分支后，另一条分支的探索成果丢失
  解决：把另一条分支压缩成摘要，「注入」到新分支

      Session Tree
         │
    ┌────┴────┐
    │         │
  分支A     分支B
  (摘要)   (注入)
    ↓         ↓
  参考信息   当前工作
```

---

## 二、Branch Summarization 场景图解

### 2.1 Session Tree 结构

```
Session Tree（时光机树）：

         ┌─ B ─ C ─ D (当前位置 oldLeaf)
    A ───┤
         └─ E ─ F (目标位置 target)

A = 共同祖先 (common ancestor)
B-C-D = 当前分支（要被遗弃）
E-F = 目标分支（要切换过去）
```

### 2.2 导航前的状态

```
当前位置：D (oldLeaf)
目标位置：F (target)

用户输入：/tree F
系统询问：是否要为分支 B-C-D 生成摘要？

用户选择：Yes
↓
执行 Branch Summarization
```

### 2.3 Branch Summarization 流程

```
Step 1: 找共同祖先
  oldPath = [A, B, C, D]
  targetPath = [A, E, F]
  commonAncestorId = A

Step 2: 收集被遗弃分支的 entries
  从 oldLeaf (D) 往回走到 commonAncestor (A)
  entries = [B, C, D]（不包括 A）

Step 3: 生成摘要
  调用 LLM 摘要 entries = [B, C, D]

Step 4: 创建 BranchSummaryEntry
  在 D 后面追加 BranchSummaryEntry
  
Step 5: 切换到新分支
  导航到 F
  把 BranchSummaryEntry 的摘要「注入」到新分支的上下文
```

### 2.4 导航后的状态

```
         ┌─ B ─ C ─ D ─ [BranchSummaryEntry: 摘要 B,C,D]
    A ───┤
         └─ E ─ F (新当前位置)

新分支看到的上下文：
  系统提示 + BranchSummary + E + F
  ↑
  从旧分支「注入」的上下文！
```

---

## 三、关键函数解析

### 3.1 collectEntriesForBranchSummary

```typescript
// branch-summarization.ts:69-98
async function collectEntriesForBranchSummary(
  session: Session,
  oldLeafId: string | null,  // 当前位置
  targetId: string,          // 目标位置
): Promise<CollectEntriesResult>
```

**执行步骤**：

```
1. 获取 oldPath = getBranch(oldLeafId) = [A, B, C, D]
2. 获取 targetPath = getBranch(targetId) = [A, E, F]
3. 找 commonAncestorId：
   - 遍历 targetPath，找第一个同时在 oldPath 中的 entry
   - commonAncestorId = A
4. 收集被遗弃分支的 entries：
   - 从 oldLeaf (D) 往回走到 commonAncestor (A)
   - entries = [B, C, D]（不包括 A）
   - 反转顺序：[B, C, D]（按时间顺序）
5. 返回 { entries, commonAncestorId }
```

**代码逻辑**：

```typescript
// 找共同祖先
const oldPath = new Set((await session.getBranch(oldLeafId)).map((e) => e.id));
const targetPath = await session.getBranch(targetId);

let commonAncestorId: string | null = null;
for (let i = targetPath.length - 1; i >= 0; i--) {
  if (oldPath.has(targetPath[i].id)) {
    commonAncestorId = targetPath[i].id;
    break;
  }
}

// 收集被遗弃分支的 entries
const entries: SessionTreeEntry[] = [];
let current: string | null = oldLeafId;

while (current && current !== commonAncestorId) {
  const entry = await session.getEntry(current);
  entries.push(entry as SessionTreeEntry);
  current = entry.parentId;  // 往回走
}
entries.reverse();  // 反转为时间顺序

return { entries, commonAncestorId };
```

---

### 3.2 prepareBranchEntries

```typescript
// branch-summarization.ts:125-164
function prepareBranchEntries(
  entries: SessionTreeEntry[],
  tokenBudget: number = 0
): BranchPreparation
```

**执行步骤**：

```
1. 继承已有的 branch_summary 的文件追踪（累积）
2. 从新到旧（倒序）遍历 entries
3. 提取消息和文件操作
4. 如果有 tokenBudget，控制在预算内
5. 返回 { messages, fileOps, totalTokens }
```

**关键逻辑**：

```typescript
const messages: AgentMessage[] = [];
const fileOps = createFileOps();
let totalTokens = 0;

// 继承已有的 branch_summary 的文件追踪
for (const entry of entries) {
  if (entry.type === "branch_summary" && !entry.fromHook && entry.details) {
    const details = entry.details as BranchSummaryDetails;
    // 累积之前的文件追踪
    for (const f of details.readFiles) fileOps.read.add(f);
    for (const f of details.modifiedFiles) fileOps.edited.add(f);
  }
}

// 从新到旧（倒序）遍历
for (let i = entries.length - 1; i >= 0; i--) {
  const entry = entries[i];
  const message = getMessageFromEntry(entry);
  if (!message) continue;
  
  extractFileOpsFromMessage(message, fileOps);
  const tokens = estimateTokens(message);
  
  // Token budget 控制
  if (tokenBudget > 0 && totalTokens + tokens > tokenBudget) {
    // 如果是 compaction 或 branch_summary，且还有 90% 预算空间
    if (entry.type === "compaction" || entry.type === "branch_summary") {
      if (totalTokens < tokenBudget * 0.9) {
        messages.unshift(message);  // 尽量包含摘要
        totalTokens += tokens;
      }
    }
    break;  // 超过预算就停止
  }
  
  messages.unshift(message);
  totalTokens += tokens;
}

return { messages, fileOps, totalTokens };
```

---

### 3.3 generateBranchSummary

```typescript
// branch-summarization.ts:201-263
async function generateBranchSummary(
  entries: SessionTreeEntry[],
  options: GenerateBranchSummaryOptions
): Promise<Result<BranchSummaryResult, BranchSummaryError>>
```

**执行步骤**：

```
1. 计算 tokenBudget = contextWindow - reserveTokens
2. prepareBranchEntries(entries, tokenBudget)
3. 序列化消息为文本
4. 调用 LLM 生成摘要
5. 添加 BRANCH_SUMMARY_PREAMBLE
6. 添加文件追踪标签
7. 返回 { summary, readFiles, modifiedFiles }
```

---

## 四、getMessageFromEntry 函数

### 4.1 Entry 类型转换规则

```typescript
// branch-summarization.ts:99-122
function getMessageFromEntry(entry: SessionTreeEntry): AgentMessage | undefined {
  switch (entry.type) {
    case "message":
      if (entry.message.role === "toolResult") return undefined;  // 跳过 toolResult
      return entry.message;
    
    case "custom_message":
      return createCustomMessage(entry.customType, entry.content, ...);
    
    case "branch_summary":
      return createBranchSummaryMessage(entry.summary, entry.fromId, ...);
    
    case "compaction":
      return createCompactionSummaryMessage(entry.summary, entry.tokensBefore, ...);
    
    // 其他类型不参与摘要
    case "thinking_level_change":
    case "model_change":
    case "leaf":
    ...
      return undefined;
  }
}
```

### 4.2 为什么跳过 toolResult？

```
与 Compaction 相同的原因：
  toolResult 必须与 tool call 保持在一起
  
但 Branch Summarization 不需要切割点逻辑：
  因为它是「摘要全部」，不是「切割保留」
  
跳过 toolResult 的原因：
  减少摘要的 token 数
  tool call 已经包含了操作信息
  toolResult 的内容太大（文件内容、命令输出等）
```

---

## 五、Branch Summary 的特殊前缀

### 5.1 BRANCH_SUMMARY_PREAMBLE

```typescript
// branch-summarization.ts:166-169
const BRANCH_SUMMARY_PREAMBLE = `
The user explored a different conversation branch before returning here.
Summary of that exploration:

`;
```

### 5.2 为什么需要这个前缀？

```
告诉 LLM：
  「这个摘要不是当前对话的历史，而是用户之前探索的另一条分支」

区别：
  Compaction Summary: "这是之前发生的事，继续往下做"
  Branch Summary: "这是另一条探索路径的成果，供参考"

LLM 看到的 Branch Summary：
  The user explored a different conversation branch before returning here.
  Summary of that exploration:
  
  ## Goal
  ...
  ## Progress
  ...
```

---

## 六、Token Budget 控制

### 6.1 为什么需要 Token Budget？

```
Branch Summarization 可能摘要很长的分支：

  分支 B-C-D 可能包含：
    - 100 条消息
    - 多个 CompactionEntry
    - 多个 BranchSummaryEntry（嵌套切换）
  
  如果全部摘要，token 数可能超过 LLM 的输入限制
  
  解决方案：
    tokenBudget = contextWindow - reserveTokens
    控制发送给 LLM 的消息数量
```

### 6.2 Token Budget 控制逻辑

```typescript
// branch-summarization.ts:142-161
for (let i = entries.length - 1; i >= 0; i--) {
  const entry = entries[i];
  const message = getMessageFromEntry(entry);
  if (!message) continue;
  
  const tokens = estimateTokens(message);
  
  // 检查是否超过预算
  if (tokenBudget > 0 && totalTokens + tokens > tokenBudget) {
    // 特殊处理：如果是摘要 Entry，尽量包含
    if (entry.type === "compaction" || entry.type === "branch_summary") {
      if (totalTokens < tokenBudget * 0.9) {
        messages.unshift(message);
        totalTokens += tokens;
      }
    }
    break;  // 停止收集
  }
  
  messages.unshift(message);
  totalTokens += tokens;
}
```

### 6.3 为什么优先包含 compaction/branch_summary？

```
因为它们是「已压缩的摘要」，包含大量历史信息：

  CompactionEntry:
    摘要了 entry 0-39 的内容
    包含 Goal、Progress、Decisions 等
  
  BranchSummaryEntry:
    摘要了另一条分支的探索成果
  
  优先包含它们：
    能保留更多上下文
    用较少的 token 传递更多信息
```

---

## 七、嵌套场景：Branch 内有 Compaction

### 7.1 复杂 Session Tree 结构

```
         ┌─ B ─ C ─ CompactionEntry ─ D
    A ───┤
         └─ E ─ F

Branch Summarization 摘要 B-C-D 时：
  会包含 CompactionEntry 的摘要内容
```

### 7.2 prepareBranchEntries 处理逻辑

```
entries = [B, C, CompactionEntry, D]

遍历时：
  entry B → 提取消息
  entry C → 提取消息
  entry CompactionEntry → 转成 CompactionSummaryMessage
  entry D → 提取消息

messages = [
  B 的消息,
  C 的消息,
  CompactionSummaryMessage(summary, tokensBefore),
  D 的消息
]

LLM 看到的：
  [User]: B 的内容
  [Assistant]: C 的内容
  [Compaction Summary]: CompactionEntry 的摘要内容
  [User]: D 的内容
```

### 7.3 嵌套 Branch Summary

```
更复杂的场景：

         ┌─ B ─ BranchSummaryEntry(摘要另一分支X) ─ C
    A ───┤
         └─ E ─ F

Branch Summarization 摘要 B-C 时：
  会包含之前的 BranchSummaryEntry

messages = [
  B 的消息,
  BranchSummaryMessage(摘要另一分支X),
  C 的消息
]

结果：
  新的 BranchSummary 摘要了：
    B 的内容 + 另一分支X的摘要 + C 的内容
```

---

## 八、BranchSummaryEntry 结构

### 8.1 数据结构

```typescript
interface BranchSummaryEntry<T = unknown> {
  type: "branch_summary";
  id: string;
  parentId: string;
  timestamp: number;
  
  // 核心字段
  summary: string;           // 结构化摘要文本（带 PREAMBLE）
  
  // Branch 特有字段
  fromId: string;            // 来源 entry ID（从哪个 entry 导航过来）
  
  // 扩展相关
  fromHook?: boolean;        // 是否由扩展提供
  details?: T;               // 默认是 BranchSummaryDetails
}

interface BranchSummaryDetails {
  readFiles: string[];
  modifiedFiles: string[];
}
```

### 8.2 与 CompactionEntry 对比

| 字段 | CompactionEntry | BranchSummaryEntry |
|------|-----------------|-------------------|
| `type` | `"compaction"` | `"branch_summary"` |
| `summary` | 结构化摘要 | 结构化摘要 + PREAMBLE |
| **特有字段** | `firstKeptEntryId` | `fromId` |
| `tokensBefore` | ✓ 压缩前 token 数 | ✗ 无此字段 |
| `details` | `{readFiles, modifiedFiles}` | `{readFiles, modifiedFiles}` |

---

## 九、文件追踪累积

### 9.1 Branch Summarization 的文件追踪

```typescript
// branch-summarization.ts:129-141
// 继承已有的 branch_summary 的文件追踪
for (const entry of entries) {
  if (entry.type === "branch_summary" && !entry.fromHook && entry.details) {
    const details = entry.details as BranchSummaryDetails;
    // 累积之前的文件追踪
    for (const f of details.readFiles) fileOps.read.add(f);
    for (const f of details.modifiedFiles) fileOps.edited.add(f);
  }
}

// 从当前消息提取新的文件操作
for (let i = entries.length - 1; i >= 0; i--) {
  const message = getMessageFromEntry(entries[i]);
  if (message) extractFileOpsFromMessage(message, fileOps);
}
```

### 9.2 嵌套场景的文件追踪累积

```
场景：

         ┌─ B ─ BranchSummaryEntry ─ C ─ D
    A ───┤
         └─ E ─ F

BranchSummaryEntry 的 details：
  readFiles: [file1.ts, file2.ts]
  modifiedFiles: [file3.ts]

C 和 D 的文件操作：
  C: read file4.ts
  D: edit file5.ts

新的 Branch Summary 的文件追踪：
  readFiles: [file1.ts, file2.ts, file4.ts]  ← 继承 + 新增
  modifiedFiles: [file3.ts, file5.ts]        ← 继承 + 新增
```

---

## 十、详细对比表

### 10.1 流程对比

| 维度 | Compaction | Branch Summarization |
|------|------------|---------------------|
| **触发** | 上下文超限 或 `/compact` | `/tree` 切换分支 |
| **目的** | 释放上下文空间 | 跨分支传递上下文 |
| **摘要对象** | 当前分支的旧消息 | 被遗弃分支的完整内容 |
| **搜索方向** | 从新到旧（倒推） | 从新到旧（倒序） |
| **切割点** | 有切割点 | 无切割点（摘要全部） |
| **保留范围** | 保留最新部分 | 不保留（切换到新分支） |
| **Entry 类型** | `CompactionEntry` | `BranchSummaryEntry` |
| **迭代性** | 可多次压缩 | 单次摘要 |

### 10.2 数据结构对比

| 维度 | CompactionEntry | BranchSummaryEntry |
|------|-----------------|-------------------|
| `type` | `"compaction"` | `"branch_summary"` |
| `summary` | 标准格式 | 标准格式 + PREAMBLE |
| **特有字段** | `firstKeptEntryId` | `fromId` |
| `tokensBefore` | ✓ 记录压缩前 token | ✗ 无 |
| `details` | `{readFiles, modifiedFiles}` | `{readFiles, modifiedFiles}` |

### 10.3 Token 控制对比

| 维度 | Compaction | Branch Summarization |
|------|------------|---------------------|
| **控制参数** | `keepRecentTokens` | `tokenBudget` |
| **计算方式** | 倒推累积到目标值 | 预算限制总输入 |
| **优先包含** | 无特殊处理 | compaction/branch_summary |
| **截断方式** | 切割点切割 | 预算超限时停止 |

---

## 十一、摘要格式对比

### 11.1 Compaction Summary 格式

```markdown
## Goal
[What the user is trying to accomplish]

## Constraints & Preferences
- [Requirements mentioned by user]

## Progress
### Done
- [x] [Completed tasks]

### In Progress
- [ ] [Current work]

### Blocked
- [Issues, if any]

## Key Decisions
- **[Decision]**: [Rationale]

## Next Steps
1. [What should happen next]

## Critical Context
- [Data needed to continue]

<read-files>
path/to/file1.ts
</read-files>

<modified-files>
path/to/changed.ts
</modified-files>
```

### 11.2 Branch Summary 格式

```markdown
The user explored a different conversation branch before returning here.
Summary of that exploration:

## Goal
[What was the user trying to accomplish in this branch?]

## Constraints & Preferences
- [Any constraints, preferences, or requirements mentioned]
- [Or "(none)" if none were mentioned]

## Progress
### Done
- [x] [Completed tasks/changes]

### In Progress
- [ ] [Work that was started but not finished]

### Blocked
- [Issues preventing progress, if any]

## Key Decisions
- **[Decision]**: [Brief rationale]

## Next Steps
1. [What should happen next to continue this work]

<read-files>
path/to/file1.ts
</read-files>

<modified-files>
path/to/changed.ts
</modified-files>
```

**关键区别**：
- Branch Summary 有 `BRANCH_SUMMARY_PREAMBLE` 前缀
- 前缀告诉 LLM 这是「另一条分支的探索成果」

---

## 十二、核心理解总结

### 12.1 Compaction

```
场景：对话太长
方向：时间维度（纵向）
动作：压缩自己
目的：腾出空间继续对话
Entry：CompactionEntry
关键字段：firstKeptEntryId（切割点）
Token 控制：keepRecentTokens
迭代性：可多次压缩
```

### 12.2 Branch Summarization

```
场景：切换分支
方向：空间维度（横向）
动作：摘要另一条分支
目的：把探索成果带到新分支
Entry：BranchSummaryEntry
关键字段：fromId（来源 entry）
Token 控制：tokenBudget
迭代性：单次摘要（但可嵌套）
```

### 12.3 共同点

```
1. 都用相同的摘要格式（Goal、Progress、Decisions 等）
2. 都追踪文件操作（readFiles, modifiedFiles）
3. 都序列化消息为文本（serializeConversation）
4. 都从新到旧遍历
5. 都继承之前的摘要：
   - Compaction 继承 previousSummary
   - Branch 继承已有的 branch_summary
6. 都使用 SUMMARIZATION_SYSTEM_PROMPT
```

---

## 十三、记忆口诀

```
Compaction：
  自己压缩自己
  时间维度纵向
  firstKeptEntryId = 切割点
  keepRecentTokens = 保留量

Branch Summarization：
  摘要另一条分支
  空间维度横向
  fromId = 来源 entry
  tokenBudget = 输入限制

共同技术：
  相同摘要格式
  文件追踪累积
  消息序列化
  从新到旧遍历
  继承之前摘要
```

---

## 十四、函数调用链对比

### 14.1 Compaction 调用链

```
shouldCompact()          → 判断是否需要压缩
    ↓
prepareCompaction()      → 准备压缩数据
    │
    ├─→ findCutPoint()           → 找切割点
    ├─→ extractFileOperations()  → 提取文件操作
    └─→ 返回 CompactionPreparation
    ↓
compact()                → 执行压缩
    │
    ├─→ generateSummary()        → 生成摘要
    │       └─→ serializeConversation()
    ├─→ generateTurnPrefixSummary() → (split turn)
    └─→ 返回 CompactionResult
    ↓
创建 CompactionEntry     → 保存到 session tree
```

### 14.2 Branch Summarization 调用链

```
collectEntriesForBranchSummary()  → 收集被遗弃分支 entries
    │
    ├─→ session.getBranch()       → 获取路径
    ├─→ 找 commonAncestorId
    └─→ 返回 { entries, commonAncestorId }
    ↓
prepareBranchEntries()            → 准备摘要数据
    │
    ├─→ 继承已有的 branch_summary 文件追踪
    ├─→ 从新到旧遍历 entries
    ├─→ extractFileOpsFromMessage()
    ├─→ Token budget 控制
    └─→ 返回 BranchPreparation
    ↓
generateBranchSummary()           → 生成摘要
    │
    ├─→ serializeConversation()
    ├─→ 调用 LLM
    ├─→ 添加 BRANCH_SUMMARY_PREAMBLE
    ├─→ formatFileOperations()
    └─→ 返回 BranchSummaryResult
    ↓
创建 BranchSummaryEntry           → 保存到 session tree
```

---

## 十五、关键理解点

### 15.1 Compaction 关键点

1. **切割点选择**：从新到旧倒推，找 firstKeptEntryId
2. **有效切割点**：user、assistant、bashExecution 等
3. **不能切割**：toolResult（必须与 tool call 在一起）
4. **Split Turn**：Turn 太大时，切割点落在 assistant message
5. **迭代压缩**：继承 previousSummary，使用 UPDATE prompt
6. **文件追踪累积**：继承之前 compaction 的文件列表

### 15.2 Branch Summarization 关键点

1. **共同祖先**：找 oldPath 和 targetPath 的交集
2. **收集范围**：从 oldLeaf 到 commonAncestor（不包括）
3. **Token Budget**：控制发送给 LLM 的消息数量
4. **优先包含**：compaction/branch_summary（包含更多历史）
5. **嵌套摘要**：可包含 CompactionEntry 和 BranchSummaryEntry
6. **文件追踪累积**：继承已有 branch_summary 的文件列表
7. **特殊前缀**：BRANCH_SUMMARY_PREAMBLE 区分来源

---

## 参考资料

- **源文件**：
  - `packages/agent/src/harness/compaction/compaction.ts` - Compaction 主流程
  - `packages/agent/src/harness/compaction/branch-summarization.ts` - Branch Summarization
  - `packages/agent/src/harness/compaction/utils.ts` - 共用工具函数
  - `packages/agent/src/harness/types.ts` - Entry 类型定义

- **相关文档**：
  - `Compaction 流程详解.md` - Compaction 详细讲解
  - `Agent Harness 与 Session 架构知识体系.md` - Session Entry 类型体系
  - `compaction.md` (pi 官方文档) - Compaction 概念概述