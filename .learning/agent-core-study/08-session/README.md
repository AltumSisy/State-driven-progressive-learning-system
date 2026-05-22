# L08: Session 管理

---

## 1. 心智模型构建

### 1.1 背景

#### Session 管理的需求演进

```
早期对话管理:
├─ 单文件: messages.json
├─ 无分支: 只能线性增长
├─ 无恢复: 每次从头开始
└─ 无命名: 难以区分不同任务

中期需求:
├─ 分支探索 → 尝试不同方案
├─ 合同决策 → 多分支汇合
├─ 命名会话 → 语义化标识
├─ 快速恢复 → 从任意点继续
└─ 压缩历史 → Token 优化

→ Session 提供树形会话管理
```

---

### 1.2 目标

#### 核心痛点

| 痛点 | 线性存储 | Session 树形管理 |
|------|---------|----------------|
| 分支 | 无 | fork() 创建分支 |
| 合并 | 无 | merge() 汇合分支 |
| 恢复 | 手动重建 | loadSession() |
| 历史追踪 | 难 | parent/children 链 |
| 压缩 | 无 | summary 替换 |

---

### 1.3 专家视角 - 概念网络

```
Session 概念网络:

核心类:
├─ Session
│   ├─ tree: SessionTree ← 树形结构
│   ├─ activeLeafId: string ← 当前叶子
│   ├─ sessionId: string ← 会话标识
│   ├─ name?: string ← 语义化名称
│   ├─ metadata: Record<string, any> ← 自定义元数据
│   └─ save() / load() / fork() / merge()
│
├─ SessionTree
│   ├─ rootId: string ← 根节点 ID
│   ├─ nodes: Map<string, SessionTreeNode> ← 所有节点
│   ├─ getAncestry(nodeId): 获取祖先链
│   ├─ getChildren(nodeId): 获取子节点
│   └─ getPath(nodeId): 获取路径
│
├─ SessionTreeNode
│   ├─ id: string ← 节点唯一 ID
│   ├─ parentId?: string ← 父节点 ID
│   ├─ childrenIds: string[] ← 子节点 ID 列表
│   ├─ entryId: string ← 关联的 Entry ID
│   ├─ createdAt: number ← 创建时间
│   └─ metadata?: any ← 节点元数据
│
├─ SessionTreeEntry
│   ├─ id: string ← 条目唯一 ID
│   ├─ timestamp: number ← 时间戳
│   ├─ message: AgentMessage ← 关联消息
│   ├─ summary?: string ← 压缩后的摘要
│   ├─ originalMessages?: AgentMessage[] ← 被压缩的原消息
│   └─ metadata?: any ← 条目元数据

操作:
├─ fork()
│   ├─ 创建新分支
│   ├─ 新分支继承祖先历史
│   └─ 返回新 leafId
│
├─ merge(sourceId, targetId)
│   ├─ 将 source 分支合并到 target
│   ├─ 创建 merge 节点
│   └─ 返回新 leafId
│
├─ loadSession(sessionId)
│   ├─ 从文件恢复会话
│   ├─ 重建 SessionTree
│   └─ 设置 activeLeafId
│
├─ saveSession()
│   ├─ 序列化 SessionTree
│   ├─ 写入文件系统
│   └─ 返回 sessionId
```

---

## 2. 结构化学习 (SQ3R)

### 2.1 Survey - SessionTree 结构

```
SessionTree 结构示例:

┌─────────────────────────────────────────────────────────┐
│                    SessionTree                            │
│                                                           │
│  root (sessionId)                                        │
│      │                                                    │
│      ├─ node1 (user: "Start project")                    │
│      │   ├─ node2 (assistant: "OK, what task?")          │
│      │   │   ├─ node3 (user: "Task A") ← activeLeaf      │
│      │   │   │   ├─ node4 (assistant: "Done A")          │
│      │   │   │                                            │
│      │   │   ├─ node5 (user: "Task B") ← fork            │
│      │   │   │   ├─ node6 (assistant: "Done B")          │
│      │   │   │                                            │
│      │   │   ├─ node7 (merge point) ← merge(node5, node3)│
│      │                                                    │
│  特性:                                                    │
│  ├─ 每节点指向一个 Entry (消息)                           │
│  ├─ fork 创建新分支                                       │
│  ├─ merge 合并多个分支                                    │
│  └─ ancestry 链追踪历史                                   │
└─────────────────────────────────────────────────────────┘
```

### 2.2 Question - 关键问题驱动

**Q1**: SessionTree 如何保证历史完整性？
**Q2**: fork 和 merge 的区别是什么？
**Q3**: Entry 的 summary 字段何时填充？
**Q4**: 如何从任意节点恢复对话？

### 2.3 Read - 源代码映射

| 内容 | 源文件 | 行数 |
|------|--------|------|
| Session 类 | `harness/session/session.ts` | - |
| SessionTree 类 | `harness/session/session-tree.ts` | - |
| SessionTreeNode | `harness/types.ts` | - |
| SessionTreeEntry | `harness/types.ts` | - |
| fork() | `harness/session/session.ts` | - |
| merge() | `harness/session/session.ts` | - |
| saveSession() | `harness/session/session.ts` | - |
| loadSession() | `harness/session/session.ts` | - |
| getAncestry() | `harness/session/session-tree.ts` | - |

### 2.4 Recite - 使用模板

#### Session 分支模板

```typescript
// 创建初始对话
await harness.prompt("Start project analysis");
await harness.saveSession();

// fork 分支探索方案 A
const branchA = await harness.forkSession();
await harness.prompt("Try approach A");
await harness.saveSession();

// 切换回原分支
await harness.loadSession(harness.session.activeLeafId);

// fork 分支探索方案 B
const branchB = await harness.forkSession();
await harness.prompt("Try approach B");
await harness.saveSession();

// 合并两个分支
const merged = await harness.mergeSession(branchA, branchB);
```

#### Session 恢复模板

```typescript
// 保存会话
const sessionId = await harness.saveSession();
console.log(`Session saved: ${sessionId}`);

// 加载会话
await harness.loadSession(sessionId);
console.log(`Active leaf: ${harness.session.activeLeafId}`);

// 从特定节点恢复
const ancestry = harness.session.tree.getAncestry(nodeId);
const messages = ancestry.map(node => 
  harness.session.entries.find(e => e.id === node.entryId)?.message
);
```

### 2.5 Review - TODO清单

#### TODO-1: 掌握 SessionTree 结构 (🔴)
**完成检查**:
- [ ] 列举 SessionTreeNode 的 5 个字段
- [ ] 解释 ancestry 链的作用

#### TODO-2: 掌握 fork/merge (🔴)
**完成检查**:
- [ ] 解释 fork 创建分支的过程
- [ ] 解释 merge 合并分支的过程

#### TODO-3: 掌握持久化 (🟠)
**完成检查**:
- [ ] 解释 saveSession 的序列化过程
- [ ] 解释 loadSession 的重建过程

#### TODO-4: 掌握 Entry 压缩 (🟠)
**完成检查**:
- [ ] 解释 summary 字段的填充时机
- [ ] 解释 originalMessages 的保留目的

---

## 3. 对抗性测试

### 3.1 边界问题

#### 无限 fork 的限制

```typescript
// 可以无限 fork，但每个创建新节点
for (let i = 0; i < 1000; i++) {
  harness.forkSession();
}
// 结果：SessionTree 节点爆炸，性能下降
// 教训：合理控制分支数量
```

#### merge 的前提条件

```typescript
// ❌ 错误：合并同一分支
merge(nodeId, nodeId);  // 无意义

// ✅ 正确：合并不同分支
const branchA = fork();
const branchB = fork();
merge(branchA, branchB);
```

### 3.2 反事实推理

**情境 1**: 如果 fork 后不切换？
```typescript
const branchId = harness.forkSession();
// 不调用 loadSession(branchId)
// 结果：继续在原分支工作，新分支空闲
// 教训：fork 后需要主动切换
```

**情境 2**: 如果 Entry 消息损坏？
```typescript
entry.message = null;  // 消息丢失
// 结果：loadSession 时重建失败
// 教训：序列化需保证完整性
```

**情境 3**: 如果 merge 两个不相关分支？
```typescript
// branchA 和 branchB 无共同祖先
merge(branchA, branchB);
// 结果：创建新 merge 节点，但历史断裂
// 教训：merge 应在同一 SessionTree 内
```

### 3.3 漏洞注入 - 常见错误

| 错误类型 | 示例 | 后果 |
|---------|------|------|
| 无限 fork | 循环创建分支 | 性能下降 |
| fork 后不切换 | 继续原分支 | 分支浪费 |
| 合并同分支 | merge(a, a) | 无效果 |
| 遗漏 saveSession | 不持久化 | 数据丢失 |
| 损坏 Entry | 消息丢失 | 恢复失败 |

---

## 4. 思想与迁移

### 4.1 设计哲学

#### 树形状态管理

```
root → node → node → activeLeaf
              → fork
              → merge
```

**思想**: 支持探索、回退、合并，保留完整历史。

#### 祖先链追踪

```typescript
getAncestry(nodeId): SessionTreeNode[]
// 从当前节点回溯到 root
```

**思想**: 保证历史可追溯，支持任意点恢复。

#### Entry 压缩保留

```typescript
entry.summary = "摘要内容";
entry.originalMessages = [...original];  // 保留原文
```

**思想**: 压缩不丢失，可追溯原始内容。

### 4.2 可迁移思维

| 思想 | Session 应用 | 可迁移领域 |
|------|-------------|-----------|
| **树形状态** | SessionTree 分支 | 版本控制 (Git)、游戏状态 |
| **祖先链** | getAncestry | 调试栈、调用链 |
| **压缩保留** | summary + original | 缓存系统、日志压缩 |
| **ID 唯一性** | UUID node/entry ID | 分布式系统 |
| **元数据扩展** | metadata 字段 | 标签系统、分类 |

---

## 源文件映射

| 内容 | 源文件 | 行数 |
|------|--------|------|
| Session 类 | `harness/session/session.ts` | - |
| SessionTree 类 | `harness/session/session-tree.ts` | - |
| Session 类型 | `harness/types.ts` | - |

---

## 下一步

→ [L09: 上下文压缩](../09-compaction)