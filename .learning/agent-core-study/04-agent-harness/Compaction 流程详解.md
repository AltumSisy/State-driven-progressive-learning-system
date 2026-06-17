# Compaction 流程详解

> 本文档详细讲解 Agent Harness 中的 Compaction（上下文压缩）机制，包括触发条件、切割点逻辑、Split Turn 处理和迭代压缩。

## 一、核心概念

### 1.1 Compaction 的本质

**类比理解**：Compaction 就像是「写读书笔记」

```
读一本很厚的书：
  第1页 → 第2页 → ... → 第100页 → 记不住了！
  
解决方案：
  读前100页 → 写一份摘要 → 记住摘要 + 继续读第101页
  
Compaction：
  对话历史过长 → 写结构化摘要 → 用「摘要 + 最新内容」代替「全部历史」
```

### 1.2 Session Entry 类型体系

```
SessionTreeEntry（所有 entry 的联合类型）
├── message           ← 用户/助手消息（对话内容）
├── custom_message    ← 自定义消息
├── compaction        ← 🔥 CompactionEntry（压缩摘要）
├── branch_summary    ← 🔥 BranchSummaryEntry（分支摘要）
├── leaf              ← 🔥 LeafEntry（时光机定位点）
├── thinking_level_change
├── model_change
├── active_tools_change
├── custom
├── label
└── session_info
```

### 1.3 三种特殊 Entry 的关系

| Entry 类型 | 作用 | 产生时机 |
|------------|------|----------|
| **LeafEntry** | 时光机定位点，记录「当前在哪里」 | 用户创建/切换分支 |
| **CompactionEntry** | 压缩摘要，记录「过去发生了什么」 | 上下文超限或 `/compact` |
| **BranchSummaryEntry** | 分支摘要，记录「被遗弃分支的成果」 | `/tree` 切换分支 |

---

## 二、触发条件

### 2.1 触发公式

```typescript
// compaction.ts:196-199
function shouldCompact(contextTokens, contextWindow, settings) {
  if (!settings.enabled) return false;
  return contextTokens > contextWindow - settings.reserveTokens;
}
```

图示理解：

```
┌────────────────────────────────────────────┐  ← contextWindow（总容量）
│                                            │
│         已使用: contextTokens              │
│                                            │
│  reserveTokens（必须留出，给 AI 回复用）    │
└────────────────────────────────────────────┘

触发条件：
  已使用 + reserveTokens > 总容量
```

### 2.2 默认配置

```typescript
// compaction.ts:112-116
DEFAULT_COMPACTION_SETTINGS = {
  enabled: true,
  reserveTokens: 16384,    // 留 16k 给 AI 回复
  keepRecentTokens: 20000, // 保留最近 20k 不压缩
}
```

### 2.3 触发方式

```
1. 自动触发：上下文超过阈值时自动压缩
   → shouldCompact() 返回 true → 执行 prepareCompaction()

2. 手动触发：用户输入 /compact [可选指令]
   → 强制执行压缩，可选指令用于聚焦摘要重点
```

---

## 三、核心流程五步

### 3.1 流程概览

```
Step 1: 找切割点
  从最新消息倒推，累积到 keepRecentTokens
  
Step 2: 提取消息
  收集切割点之前的消息 → messagesToSummarize
  
Step 3: 生成摘要
  调用 LLM 生成结构化摘要
  
Step 4: 保存 Entry
  创建 CompactionEntry，记录 firstKeptEntryId
  
Step 5: 重载会话
  会话重新加载，发送「摘要 + 保留消息」给 LLM
```

### 3.2 详细图示

假设当前 entries：

```
entry:  0     1     2     3      4     5     6      7      8     9
      ┌─────┬─────┬─────┬─────┬──────┬─────┬─────┬──────┬──────┬─────┐
      │ hdr │ usr │ ass │ tool │ usr  │ ass │ tool│ tool │ ass  │tool │
      └─────┴─────┴─────┴──────┴─────┴─────┴─────┴──────┴──────┴─────┘
              └────────┬───────┘ └──────────────┬──────────────┘
             messagesToSummarize            kept messages
                                             ↑
                                    firstKeptEntryId = entry 4
```

压缩后（新增 entry 10）：

```
entry:  0     1     2     3      4     5     6      7      8     9    10
      ┌─────┬─────┬─────┬─────┬──────┬─────┬─────┬──────┬──────┬─────┬─────┐
      │ hdr │ usr │ ass │ tool │ usr  │ ass │ tool│ tool │ ass  │tool │ cmp │
      └─────┴─────┴─────┴──────┴─────┴─────┴─────┴──────┴──────┴─────┴─────┘
             └──────────┬──────┘ └──────────────────────┬───────────────────┘
               不发送给 LLM                         发送给 LLM
                                                      ↑
                                           从 firstKeptEntryId 开始
```

LLM 看到的内容：

```
┌────────┬─────────┬─────┬─────┬──────┬──────┬─────┬──────┐
│ system │ summary │ usr │ ass │ tool │ tool │ ass │ tool │
└────────┴─────────┴─────┴─────┴──────┴──────┴─────┴──────┘
     ↑         ↑      └─────────────────┬────────────────┘
   prompt   来自 entry 10      messages from firstKeptEntryId
```

---

## 四、切割点逻辑（核心）

### 4.1 切割点选择算法

```typescript
// compaction.ts:329-377
function findCutPoint(
  entries: SessionTreeEntry[],
  startIndex: number,
  endIndex: number,
  keepRecentTokens: number
): CutPointResult {
  firstKeptEntryIndex: number;  // 切割点索引
  turnStartIndex: number;       // turn 起点索引
  isSplitTurn: boolean;         // 是否切到 turn 中间
}
```

### 4.2 有效切割点规则

```typescript
// compaction.ts:261-299
// 可以切割的位置：
case "message":
  switch (role) {
    case "user":           ✅ 可以切割
    case "assistant":      ✅ 可以切割
    case "bashExecution":  ✅ 可以切割
    case "custom":         ✅ 可以切割
    case "branchSummary":  ✅ 可以切割
    case "compactionSummary": ✅ 可以切割
    case "toolResult":     ❌ 不能切割！
  }

case "branch_summary":     ✅ 可以切割
case "custom_message":     ✅ 可以切割

// 其他 entry 类型都不能作为切割点
```

### 4.3 为什么 toolResult 不能切割？

```
正确的对话结构：
  assistant → tool call (read file A)
  toolResult → (file A 的内容)

如果切割在 toolResult：
  → tool call 在被压缩部分
  → toolResult 在保留部分
  → AI 看到 toolResult 但不知道是谁调用的！

必须保持：
  tool call + toolResult 作为一个整体
```

### 4.4 倒推累积算法

```typescript
// compaction.ts:340-357
let accumulatedTokens = 0;

// 从最新往回走
for (let i = endIndex - 1; i >= startIndex; i--) {
  const entry = entries[i];
  if (entry.type !== "message") continue;
  
  const messageTokens = estimateTokens(entry.message);
  accumulatedTokens += messageTokens;
  
  // 累积达到目标
  if (accumulatedTokens >= keepRecentTokens) {
    // 找到第一个 >= 当前位置的切割点
    for (let c = 0; c < cutPoints.length; c++) {
      if (cutPoints[c] >= i) {
        cutIndex = cutPoints[c];
        break;
      }
    }
    break;
  }
}
```

---

## 五、Turn 的定义与识别

### 5.1 Turn 结构

```
Turn = 一次完整的「用户请求 → AI 响应」循环

结构：
  user message (起点)
    ↓
  assistant response (可能多次)
    ↓
  tool calls + toolResults (可能多次)
    ↓
  下一个 user message (新 Turn 起点)

例子：
  Turn 1: user → assistant → tool → toolResult
  Turn 2: user → assistant → tool → toolResult
  Turn 3: user → assistant
```

### 5.2 Turn 起点识别

```typescript
// compaction.ts:302-316
function findTurnStartIndex(entries, entryIndex, startIndex): number {
  // 从切割点往回找，找到 user 或 bashExecution 消息
  for (let i = entryIndex; i >= startIndex; i--) {
    const entry = entries[i];
    
    if (entry.type === "message") {
      const role = entry.message.role;
      if (role === "user" || role === "bashExecution") {
        return i;  // ← 找到了 Turn 起点！
      }
    }
  }
  return -1;
}
```

---

## 六、正常切割 vs Split Turn

### 6.1 核心区别

```
切割点落在 User Message → Turn 边界 → 正常切割
切割点落在 Assistant Message → Turn 中间 → Split Turn
```

### 6.2 判断逻辑

```typescript
// compaction.ts:369-376
const cutEntry = entries[cutIndex];

// 判断切割点的 entry 类型
const isUserMessage = cutEntry.type === "message" && cutEntry.message.role === "user";

// 如果不是 user message，往回找 turn 起点
const turnStartIndex = isUserMessage 
  ? -1
  : findTurnStartIndex(entries, cutIndex, startIndex);

return {
  firstKeptEntryIndex: cutIndex,
  turnStartIndex,
  isSplitTurn: !isUserMessage && turnStartIndex !== -1,
};
```

---

## 七、正常切割详解

### 7.1 场景图示

```
entry:  0   1   2   3    4    5    6    7    8    9   10   11   12
      ┌───┬───┬───┬────┬────┬────┬────┬────┬────┬───┬────┬────┬────┐
      │hdr│usr│ass│tool│usr │ass │tool│usr │ass │tool│usr │ass │tool│
      └───┴───┴───┴────┴────┴────┴────┴────┴────┴───┴────┴────┴────┘
          ↑       ↑         ↑              ↑
        turn1   turn2     turn3          turn4
        
切割点落在 entry 7 (user message)：
  firstKeptEntryId = "entry-7-id"
  turnStartIndex = -1
  isSplitTurn = false
  historyEnd = firstKeptEntryIndex = 7
```

### 7.2 Entry 分配表

| Entry Index | Entry 类型 | 处理方式 | 说明 |
|-------------|-----------|----------|------|
| 0 | header | 不处理 | 会话头 |
| **1** | **user** | **→ Summary** | Turn 1 起点 |
| **2** | **assistant** | **→ Summary** | Turn 1 响应 |
| **3** | **toolResult** | **→ Summary** | Turn 1 工具结果 |
| **4-6** | **turn2** | **→ Summary** | Turn 2 完整内容 |
| **7** | **user** | **✅ 保留** | Turn 3 起点（切割点） |
| **8-12** | **turn3 + turn4** | **✅ 保留** | 最新对话 |

### 7.3 代码逻辑

```typescript
// compaction.ts:573-588
const historyEnd = cutPoint.isSplitTurn 
  ? cutPoint.turnStartIndex
  : cutPoint.firstKeptEntryIndex;  // ← 7

// 收集要压缩的消息
const messagesToSummarize: AgentMessage[] = [];
for (let i = boundaryStart; i < historyEnd; i++) {  // ← i 从 0 到 6
  const msg = getMessageFromEntryForCompaction(pathEntries[i]);
  if (msg) messagesToSummarize.push(msg);
}

// entry 7-12 保留
```

---

## 八、Split Turn 详细处理

### 8.1 场景图示

```
entry:  0   1   2   3    4    5    6    7    8    9   10   11   12
      ┌───┬───┬───┬────┬────┬────┬────┬────┬────┬───┬────┬────┬────┐
      │hdr│usr│ass│tool│usr │ass │tool│usr │ass │tool│usr │ass │tool│
      └───┴───┴───┴────┴────┴────┴────┴────┴────┴───┴────┴────┴────┘
          ↑       ↑         ↑    └─────────────────┘
        turn1   turn2     turn3      turn3 (被切割)
        
切割点落在 entry 8 (assistant message)：
  firstKeptEntryId = "entry-8-id"
  turnStartIndex = 7
  isSplitTurn = true
  historyEnd = turnStartIndex = 7
```

### 8.2 Entry 分配表

| Entry Index | Entry 类型 | 处理方式 |
|-------------|-----------|----------|
| **1-6** | **turn1 + turn2** | **→ History Summary** |
| **7** | **user** | **→ Turn Prefix Summary** |
| **8** | **assistant** | **✅ 保留（切割点）** |
| **9-12** | **turn3 后半 + turn4** | **✅ 保留** |

### 8.3 双摘要生成逻辑

```typescript
// compaction.ts:653-681
if (isSplitTurn && turnPrefixMessages.length > 0) {
  // 并行生成两个摘要
  const [historyResult, turnPrefixResult] = await Promise.all([
    
    // 1. History summary（完整的历史 turns）
    messagesToSummarize.length > 0
      ? generateSummary(messagesToSummarize, ...)
      : ok("No prior history."),
    
    // 2. Turn prefix summary（被切割的 turn 前缀）
    generateTurnPrefixSummary(turnPrefixMessages, ...)
  ]);
  
  // 合并两个摘要
  summary = `${historyResult.value}\n\n---\n\n**Turn Context (split turn):**\n\n${turnPrefixResult.value}`;
}
```

### 8.4 Turn Prefix Summary 的特殊 Prompt

```typescript
// compaction.ts:609-622
const TURN_PREFIX_SUMMARIZATION_PROMPT = `
This is the PREFIX of a turn that was too large to keep.
The SUFFIX (recent work) is retained.

Summarize the prefix to provide context for the retained suffix:

## Original Request
[What did the user ask for in this turn?]

## Early Progress
- [Key decisions and work done in the prefix]

## Context for Suffix
- [Information needed to understand the retained recent work]

Be concise. Focus on what's needed to understand the kept suffix.
`;
```

### 8.5 为什么需要特殊 Prompt？

```
普通摘要：总结过去发生的事，供未来参考
Turn prefix 摘要：为「紧接着的 suffix」提供理解上下文

区别：
  普通摘要：「Goal: build feature X, Progress: 50%...」
  
  Turn prefix 摘要：
    「Original Request: 用户要读取 config.ts 并修改
     Early Progress: 读取了 config.ts，发现需要修改第 50 行
     Context for Suffix: 当前正在修改第 50 行，需要知道原始值是 "foo"」
```

---

## 九、复杂 Split Turn 示例

### 9.1 场景：超大 Turn

```
entry:  0   1   2   3    4    5    6    7    8    9   10   11   12   13   14
      ┌───┬───┬───┬────┬────┬────┬────┬────┬────┬───┬────┬────┬────┬────┬────┐
      │hdr│usr│ass│tool│usr │ass │tool│usr │ass │tool│ass │tool│ass │tool│tool│
      └───┴───┴───┴────┴────┴────┴────┴────┴────┴───┴────┴────┴────┴────┴────┘
          ↑       ↑         ↑    └──────────────────────────────────────────┘
        turn1   turn2     turn3                 turn3 (超大！)
        
切割点落在 entry 11 (assistant message)：
  firstKeptEntryId = "entry-11-id"
  turnStartIndex = 7
  isSplitTurn = true
```

### 9.2 Entry 分配

| Entry Index | 处理方式 |
|-------------|----------|
| **1-6** | **→ History Summary**（完整的历史 turns） |
| **7-10** | **→ Turn Prefix Summary**（Turn 前缀：user + 3个 assistant/tool） |
| **11-14** | **✅ 保留**（切割点开始） |

---

## 十、综合对比表

| 维度 | 正常切割 | Split Turn |
|------|----------|------------|
| **切割点位置** | User Message | Assistant Message |
| **切割点 entry** | entry 7 (user) | entry 8 (assistant) |
| **historyEnd** | `firstKeptEntryIndex` | `turnStartIndex` |
| **messagesToSummarize 范围** | entry 1 到 firstKeptEntryIndex-1 | entry 1 到 turnStartIndex-1 |
| **turnPrefixMessages 范围** | 无 | entry turnStartIndex 到 firstKeptEntryIndex-1 |
| **保留范围** | entry firstKeptEntryIndex 到最后 | entry firstKeptEntryIndex 到最后 |
| **生成摘要数量** | 1 个 | 2 个（合并） |
| **摘要类型** | 标准 Summary | History Summary + Turn Prefix Summary |

---

## 十一、关键范围公式

```
正常切割：
  historyEnd = firstKeptEntryIndex
  
  messagesToSummarize 范围 = [boundaryStart, historyEnd)
                           = [boundaryStart, firstKeptEntryIndex)
  
  保留范围 = [firstKeptEntryIndex, endIndex)

Split Turn：
  historyEnd = turnStartIndex
  
  messagesToSummarize 范围 = [boundaryStart, historyEnd)
                           = [boundaryStart, turnStartIndex)
                           （完整的历史 turns）
  
  turnPrefixMessages 范围 = [turnStartIndex, firstKeptEntryIndex)
                          （被切割的 turn 前缀）
  
  保留范围 = [firstKeptEntryIndex, endIndex)
```

---

## 十二、迭代压缩

### 12.1 多次压缩场景

```
第一次压缩：
  entry 0-50 → entry 51 (CompactionEntry, firstKeptEntryId=40)
  
继续对话到 entry 80，又超了：

第二次压缩：
  从 firstKeptEntryId=40 开始搜索新的切割点
  entry 40-70 → entry 81 (CompactionEntry, firstKeptEntryId=65)
  
  关键：第二次压缩会「继承」第一次的摘要！
```

### 12.2 迭代逻辑

```typescript
// compaction.ts:550-566
// 找到上一个 compaction 的位置
let prevCompactionIndex = -1;
for (let i = pathEntries.length - 1; i >= 0; i--) {
  if (pathEntries[i].type === "compaction") {
    prevCompactionIndex = i;
    break;
  }
}

// 如果有之前的压缩
if (prevCompactionIndex >= 0) {
  const prevCompaction = pathEntries[prevCompactionIndex] as CompactionEntry;
  previousSummary = prevCompaction.summary;  // ← 继承之前的摘要！
  boundaryStart = firstKeptEntryIndex >= 0 ? firstKeptEntryIndex : prevCompactionIndex + 1;
}
```

### 12.3 摘要更新 vs 新摘要

```typescript
// compaction.ts:456-481
// 如果有 previousSummary → 使用 UPDATE_SUMMARIZATION_PROMPT
// 否则 → 使用 SUMMARIZATION_PROMPT

UPDATE_SUMMARIZATION_PROMPT = `
Update the existing structured summary with new information. RULES:
- PRESERVE all existing information from the previous summary
- ADD new progress, decisions, and context from the new messages
- UPDATE the Progress section: move items from "In Progress" to "Done"
- UPDATE "Next Steps" based on what was accomplished
`
```

---

## 十三、CompactionEntry 结构

```typescript
// compaction.ts:119-141
interface CompactionEntry<T = unknown> {
  type: "compaction";
  id: string;
  parentId: string;
  timestamp: number;
  
  // 核心字段
  summary: string;           // 结构化摘要文本
  firstKeptEntryId: string;  // 从哪个 entry 开始保留
  tokensBefore: number;      // 压缩前的 token 数
  
  // 扩展相关
  fromHook?: boolean;        // 是否由扩展提供
  details?: T;               // 默认是 CompactionDetails（readFiles/modifiedFiles）
}

interface CompactionDetails {
  readFiles: string[];
  modifiedFiles: string[];
}
```

---

## 十四、函数调用链

```
shouldCompact()          → 判断是否需要压缩
    ↓
prepareCompaction()      → 准备压缩数据
    │
    ├─→ findCutPoint()           → 找切割点
    │       └─→ findValidCutPoints() → 找所有有效切割点
    │
    ├─→ estimateContextTokens()  → 计算 token 数
    │
    ├─→ extractFileOperations()  → 提取文件操作（累积）
    │
    └─→ 返回 CompactionPreparation
    ↓
compact()                → 执行压缩
    │
    ├─→ generateSummary()        → 生成主摘要
    │       └─→ serializeConversation() → 序列化消息
    │
    ├─→ generateTurnPrefixSummary() → (如果是 split turn)
    │
    ├─→ computeFileLists()       → 计算文件列表
    │
    └─→ 返回 CompactionResult
    ↓
创建 CompactionEntry     → 保存到 session tree
    ↓
会话重载                 → 使用新摘要继续对话
```

---

## 十五、消息序列化

### 15.1 序列化格式

```typescript
// utils.ts:91-144
// 压缩前，消息会被序列化为纯文本：

[User]: What they said
[Assistant thinking]: Internal reasoning
[Assistant]: Response text
[Assistant tool calls]: read(path="foo.ts"); edit(path="bar.ts", ...)
[Tool result]: Output from tool  ← 截断到 2000 字符
```

### 15.2 为什么序列化？

**目的**：防止模型把这当作「要继续的对话」，而是当作「要总结的历史」。

```typescript
// 工具结果截断
const TOOL_RESULT_MAX_CHARS = 2000;

function truncateForSummary(text, maxChars) {
  if (text.length <= maxChars) return text;
  const truncatedChars = text.length - maxChars;
  return `${text.slice(0, maxChars)}\n\n[... ${truncatedChars} more characters truncated]`;
}
```

---

## 十六、文件追踪累积

### 16.1 累积逻辑

```typescript
// compaction.ts:36-59
function extractFileOperations(messages, entries, prevCompactionIndex) {
  const fileOps = createFileOps();
  
  // 从上一个 compaction 继承文件列表
  if (prevCompactionIndex >= 0) {
    const prevCompaction = entries[prevCompactionIndex] as CompactionEntry;
    if (!prevCompaction.fromHook && prevCompaction.details) {
      const details = prevCompaction.details as CompactionDetails;
      // 继承之前追踪的文件
      for (const f of details.readFiles) fileOps.read.add(f);
      for (const f of details.modifiedFiles) fileOps.edited.add(f);
    }
  }
  
  // 从当前消息提取新的文件操作
  for (const msg of messages) {
    extractFileOpsFromMessage(msg, fileOps);
  }
  
  return fileOps;
}
```

### 16.2 文件操作类型

```typescript
// utils.ts:4-12
interface FileOperations {
  read: Set<string>;    // 读取的文件
  written: Set<string>; // 写入的文件（全文件写入）
  edited: Set<string>;  // 编辑的文件（部分修改）
}
```

### 16.3 摘要中的文件标签

```markdown
<read-files>
path/to/file1.ts
path/to/file2.ts
</read-files>

<modified-files>
path/to/changed.ts
</modified-files>
```

---

## 十七、记忆口诀

```
切割点选择：
  倒推累积 token → 找有效切割点
  User Message = Turn 边界 = 正常切割
  Assistant Message = Turn 中间 = Split Turn

正常切割：
  切割点 = User Message
  → 前面所有完整 turns → Summary
  → 切割点开始 → 保留

Split Turn：
  切割点 = Assistant Message
  → 前面完整 turns → History Summary
  → 被切割的 Turn 前缀 → Turn Prefix Summary
  → 切割点开始 → 保留

迭代压缩：
  previousSummary 作为输入
  使用 UPDATE_SUMMARIZATION_PROMPT
  文件追踪累积继承
```

---

## 十八、核心数据结构

```typescript
// 准备阶段返回
CompactionPreparation {
  firstKeptEntryId: string;
  messagesToSummarize: AgentMessage[];
  turnPrefixMessages: AgentMessage[];
  isSplitTurn: boolean;
  tokensBefore: number;
  previousSummary?: string;
  fileOps: FileOperations;
  settings: CompactionSettings;
}

// 压缩结果
CompactionResult {
  summary: string;
  firstKeptEntryId: string;
  tokensBefore: number;
  details?: { readFiles, modifiedFiles }
}
```

---

## 十九、关键理解点总结

1. **切割点选择**：从最新倒推，累积到 `keepRecentTokens`
2. **有效切割点**：user、assistant、bashExecution、custom、branch_summary、compactionSummary
3. **不能切割**：toolResult（必须与 tool call 在一起）
4. **Turn 边界识别**：User Message 是 Turn 起点
5. **Split Turn**：Turn 太大时，切割点落在 assistant message
6. **双摘要合并**：History summary + Turn prefix summary
7. **迭代压缩**：`previousSummary` 作为输入，使用 `UPDATE_SUMMARIZATION_PROMPT`
8. **文件追踪累积**：继承之前 compaction 的文件列表，持续累积

---

## 参考资料

- **源文件**：
  - `packages/agent/src/harness/compaction/compaction.ts` - 主流程
  - `packages/agent/src/harness/compaction/branch-summarization.ts` - 分支摘要
  - `packages/agent/src/harness/compaction/utils.ts` - 工具函数
  - `packages/agent/src/harness/types.ts` - Entry 类型定义

- **相关文档**：
  - `Agent Harness 与 Session 架构知识体系.md` - Session Entry 类型体系
  - `compaction.md` (pi 官方文档) - Compaction 概念概述