# 会话管理

## 学习目标

理解会话的持久化机制、分支管理和会话切换功能。

## 核心源文件

- **主要文件**: `session-manager.ts` - 会话管理器
- **辅助文件**: `session-cwd.ts` - 工作目录管理

## 关键概念

### 1. SessionEntry 类型体系

SessionEntry 是会话记录的核心类型，包含多种条目：

```typescript
type SessionEntry =
  | SessionHeader               // 会话头信息
  | SessionMessageEntry         // 消息条目
  | CompactionEntry             // 压缩条目
  | BranchSummaryEntry          // 分支摘要条目
  | CustomMessageEntry          // 自定义消息
  | ModelChangeEntry            // 模型变更
  | ThinkingLevelChangeEntry    // 思维级别变更
  | SessionInfoChangeEntry      // 会话信息变更
  | LabelChangeEntry            // 标签变更
```

### 2. 会话持久化机制

**持久化时机**:
- 每次消息结束（message_end）
- 模型变更
- 思维级别变更
- 压缩完成
- 分支摘要生成

**持久化格式**:
- JSON 文件存储
- 文件路径：`.claude/session.json`
- 版本管理：CURRENT_SESSION_VERSION

### 3. 分支管理

**分支概念**:
- 主分支：默认分支
- 子分支：通过 fork 创建
- 分支摘要：压缩跨分支历史

**分支操作**:
- `getBranch()` - 获取当前分支路径
- `switchBranch()` - 切换分支
- `fork()` - 创建新分支

### 4. 会话切换机制

会话切换涉及：
1. 保存当前会话状态
2. 加载目标会话
3. 重建 Agent 状态
4. 重置扩展系统
5. 重建工具注册

### 5. 压缩边界管理

压缩后的会话维护压缩边界：
- 记录压缩条目位置
- 标记保留的起始条目
- 防止重复压缩同一段历史

### 6. 会话上下文构建

`buildSessionContext()` 方法：
1. 从分支路径读取条目
2. 处理压缩条目（替换为摘要）
3. 处理分支摘要条目
4. 构建最终消息列表
5. 返回可用的上下文

## SessionManager 核心方法

### 状态查询
```typescript
getSessionId(): string
getSessionFile(): string | undefined
getSessionName(): string | undefined
getEntries(): SessionEntry[]
getBranch(): BranchSummaryEntry[] | SessionEntry[]
```

### 状态变更
```typescript
appendMessage(message: Message): void
appendCompaction(summary, firstKeptEntryId, tokensBefore, details): void
appendModelChange(provider, modelId): void
appendThinkingLevelChange(level): void
appendCustomMessageEntry(customType, content, display, details): void
```

### 分支操作
```typescript
getLatestCompactionEntry(branch): CompactionEntry | null
collectEntriesForBranchSummary(): void
```

### 会话重建
```typescript
buildSessionContext(): SessionContext
```

## 学习建议

### 重点阅读章节

1. **类型定义**（session-manager.ts 开头）
   - 理解 SessionEntry 各种类型
   - 理解 SessionHeader 结构

2. **appendMessage 方法**
   - 理解消息如何持久化
   - 理解 timestamp 处理

3. **buildSessionContext 方法**
   - 理解如何从条目构建上下文
   - 理解压缩和分支摘要处理

4. **分支相关方法**
   - 理解分支路径概念
   - 理解 BranchSummaryEntry

### session-cwd.ts

理解工作目录管理：
- cwd 的设置和切换
- 相对路径解析
- 工作目录验证

## 关键设计模式

### 条目序列模式
会话历史不是直接存储消息，而是存储条目序列：
- 不同类型条目记录不同事件
- 通过 buildSessionContext 重构消息列表
- 压缩条目替换历史消息为摘要

### 分支路径模式
分支通过 BranchSummaryEntry 连接：
- 每个分支有自己的条目序列
- BranchSummaryEntry 指向父分支
- 形成树状分支结构

### 版本管理模式
会话文件有版本号：
- CURRENT_SESSION_VERSION
- 支持版本迁移
- 保证向后兼容

## 与 AgentSession 的关系

SessionManager 是 AgentSession 的依赖：
- AgentSession 负责运行时逻辑
- SessionManager 负责持久化
- 两者通过事件同步状态

## 实际应用场景

1. **会话恢复** - 重启后恢复对话历史
2. **分支切换** - 在不同对话分支间切换
3. **历史压缩** - 压缩过长历史节省 token
4. **会话导出** - 导出会话为 HTML