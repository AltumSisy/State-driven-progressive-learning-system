# 压缩系统

## 学习目标

深入理解 Coding Agent 的上下文压缩机制，这是管理长对话上下文的核心技术。

## 核心源文件

- `compaction/index.ts` - 压缩系统入口
- `compaction/compaction.ts` - 压缩核心逻辑（重要）
- `compaction/branch-summarization.ts` - 分支摘要生成
- `compaction/utils.ts` - 压缩工具函数

## 关键概念

### 1. 压缩触发条件

两种触发方式：

#### overflow（溢出）
LLM 返回上下文溢出错误：
- `context_length_exceeded`
- `max_context_window_reached`

处理流程：
1. 检测溢出错误
2. 移除错误消息
3. 执行压缩
4. 自动重试（仅一次）

#### threshold（阈值）
上下文超过配置阈值：
- 默认阈值：80% context window
- 用户可配置阈值

处理流程：
1. 检查 token 使用率
2. 超过阈值触发压缩
3. 不自动重试（用户继续）

### 2. 压缩准备（prepareCompaction）

**CompactionPreparation 结构**:
```typescript
interface CompactionPreparation {
  messages: Message[];        // 要压缩的消息
  firstKeptEntryId: string;   // 保留的起始条目 ID
  tokensBefore: number;       // 压缩前 token 数
  model: Model;               // 用于摘要的模型
}
```

**准备流程**:
1. 从 SessionManager 获取分支路径
2. buildSessionContext 构建消息列表
3. 识别压缩边界（保留最近消息）
4. 计算压缩前 token 数
5. 返回 Preparation 或 null（无法压缩）

### 3. 压缩执行（compact 函数）

**核心流程**:
```typescript
async function compact(
  preparation: CompactionPreparation,
  model: Model,
  apiKey: string,
  headers: Record<string, string>,
  customInstructions?: string,
  signal?: AbortSignal,
  thinkingLevel?: ThinkingLevel,
  streamFn?: StreamFunction
): Promise<CompactionResult>
```

**压缩步骤**:
1. 构建压缩提示词
2. 调用 LLM 生成摘要
3. 流式接收摘要内容
4. 处理中止信号
5. 返回压缩结果

**CompactionResult**:
```typescript
interface CompactionResult {
  summary: string;            // 压缩摘要
  firstKeptEntryId: string;   // 保留的起始条目
  tokensBefore: number;       // 压缩前 token 数
  details?: unknown;          // 详细信息
}
```

### 4. 压缩摘要生成

**摘要提示词结构**:
```
请将以下对话历史压缩为简洁的摘要，保留：
1. 用户的主要请求和目标
2. Agent 的关键决策和行动
3. 重要的技术细节和发现
4. 未完成的任务和待解决的问题

对话历史：
[消息列表]

自定义指令：[可选]
```

**摘要要求**:
- 保留关键信息
- 移除冗余细节
- 保持上下文连贯
- 支持后续对话

### 5. 分支摘要（branch-summarization.ts）

**BranchSummaryEntry**:
```typescript
interface BranchSummaryEntry {
  type: 'branch_summary';
  timestamp: string;
  summary: string;            // 分支摘要
  parentBranchId: string;     // 父分支 ID
  entriesCount: number;       // 条目数量
  tokensBefore: number;       // 摘要前 token 数
}
```

**生成流程**:
1. 收集分支条目（`collectEntriesForBranchSummary`）
2. 构建摘要提示词
3. LLM 生成摘要
4. 创建 BranchSummaryEntry
5. 替换分支历史为摘要

**应用场景**:
- 会话切换时压缩历史分支
- Fork 时压缩父分支
- 跨分支上下文管理

### 6. 压缩边界管理

**压缩条目记录**:
```typescript
interface CompactionEntry {
  type: 'compaction';
  timestamp: string;
  summary: string;
  firstKeptEntryId: string;   // 压缩边界
  tokensBefore: number;
  details?: unknown;
  fromExtension?: boolean;    // 是否来自扩展
}
```

**边界维护**:
- 记录 `firstKeptEntryId`
- 防止重复压缩
- 支持压缩历史追踪
- 重建上下文时识别边界

### 7. Token 计算（utils.ts）

**calculateContextTokens**:
```typescript
calculateContextTokens(usage: UsageInfo): number
```
计算上下文 token 数：
- input tokens
- cache read tokens
- 估算历史消息 tokens

**estimateContextTokens**:
```typescript
estimateContextTokens(messages: Message[]): EstimateResult
```
估算消息列表的 token 数：
- 查找最近的 usage 数据
- 基于历史 usage 估算
- 返回估算值和数据来源

**shouldCompact**:
```typescript
shouldCompact(tokens: number, contextWindow: number, settings): boolean
```
判断是否需要压缩：
- 计算 token 使用率
- 比较阈值配置
- 返回是否需要压缩

## 重点阅读

### compaction.ts（最重要）

理解压缩核心逻辑：
1. **prepareCompaction** - 压缩准备
2. **compact 函数** - 执行压缩
3. **摘要生成** - LLM 调用
4. **结果处理** - CompactionResult

### branch-summarization.ts

理解分支摘要：
1. **collectEntriesForBranchSummary** - 收集条目
2. **generateBranchSummary** - 生成摘要
3. **跨分支处理** - 父分支连接

### utils.ts

理解工具函数：
1. **token 计算** - calculateContextTokens
2. **token 估算** - estimateContextTokens
3. **阈值判断** - shouldCompact

### index.ts

理解导出的公共 API：
1. **prepareCompaction**
2. **compact**
3. **generateBranchSummary**
4. **collectEntriesForBranchSummary**
5. **工具函数导出**

## 关键设计模式

### 策略模式
两种压缩策略：
- overflow 策略（自动重试）
- threshold 策略（用户继续）

### 流式处理模式
压缩摘要流式生成：
- 使用 streamFn 流式接收
- 实时显示进度
- 支持中止

### 边界管理模式
压缩边界维护：
- firstKeptEntryId 标记边界
- buildSessionContext 识别边界
- 防止重复压缩

### 分层压缩模式
两级压缩：
- Compaction 压缩当前分支
- BranchSummary 压缩跨分支历史

## 学习建议

### 阅读顺序

1. **compaction/index.ts** - 理解导出的 API
2. **compaction/utils.ts** - 理解工具函数
3. **compaction/compaction.ts** - 理解压缩核心
4. **compaction/branch-summarization.ts** - 理解分支摘要

### 重点理解

1. **压缩触发** - overflow 和 threshold 两种条件
2. **压缩准备** - 如何选择保留消息
3. **摘要生成** - LLM 如何生成摘要
4. **边界维护** - firstKeptEntryId 机制
5. **分支摘要** - 跨分支历史管理
6. **Token 计算** - 如何估算上下文大小

## 在 AgentSession 中的应用

### 手动压缩
```typescript
async compact(customInstructions?: string): Promise<CompactionResult>
```

### 自动压缩检查
```typescript
private async _checkCompaction(assistantMessage): Promise<boolean>
```

### 自动压缩执行
```typescript
private async _runAutoCompaction(reason, willRetry): Promise<boolean>
```

### 压缩流程

1. **检查触发**：
   - `_checkCompaction()` 判断是否需要压缩

2. **准备压缩**：
   - `prepareCompaction()` 准备数据

3. **扩展拦截**：
   - `session_before_compact` 事件
   - 扩展可取消或提供自定义压缩

4. **执行压缩**：
   - `compact()` 生成摘要

5. **更新会话**：
   - `sessionManager.appendCompaction()`
   - `agent.state.messages` 更新

6. **发送事件**：
   - `session_compact` 事件

7. **重试**（overflow）：
   - 移除错误消息
   - `agent.continue()` 重试

## 实际应用场景

### 1. 长对话管理
用户长时间对话，上下文不断增长：
- 自动触发压缩
- 保留关键信息
- 继续对话

### 2. 错误恢复
LLM 返回溢出错误：
- 自动压缩
- 移除错误消息
- 自动重试请求

### 3. 分支切换
用户切换会话分支：
- 生成分支摘要
- 压缩历史分支
- 减少上下文占用

### 4. 会话持久化
压缩结果持久化：
- CompactionEntry 记录
- 会话恢复时重建
- 保持上下文连贯

## 扩展思考

### 性能考虑
- 压缩 LLM 调用成本
- 压缩时机优化
- 摘要质量评估

### 信息保留
- 如何平衡信息保留和压缩率
- 不同对话类型的压缩策略
- 用户自定义压缩指令

### 跨会话压缩
- 多会话共享摘要
- 会话间的信息迁移
- 长期记忆机制

### 扩展集成
- 扩展提供自定义压缩逻辑
- 扩展可取消压缩
- 扩展可提供压缩内容