# L07: Harness 基础

---

## 1. 心智模型构建

### 1.1 背景

#### Harness 的定位

```
Agent 类的问题:
├─ 无持久化: messages 不保存到磁盘
├─ 无会话管理: 无法恢复、分支、切换
├─ 无技能系统: 不能注册可复用能力
├─ 无压缩机制: Token 超限无法处理
└─ 无执行环境: fs/shell 抽象缺失

→ AgentHarness 提供完整应用框架
```

#### Harness 与 Agent 的关系

```
AgentHarness = Agent + Session + Skills + Compaction + ExecutionEnv

职责:
├─ Session 持久化: 保存/恢复/分支/合并
├─ Skills 管理: 注册/匹配/执行技能
├─ Compaction: Token 超限时自动压缩
├─ ExecutionEnv: fs + shell 操作抽象
└─ 事件扩展: AgentHarnessEvent (继承 AgentEvent)
```

---

### 1.2 目标

#### 核心痛点

| 痛点 | Agent 类 | AgentHarness |
|------|---------|--------------|
| 持久化 | 无 | Session 文件系统 |
| 恢复 | 手动重建 | loadSession() |
| 分支 | 无 | fork/merge |
| 技能 | 无 | Skills 注册系统 |
| 压缩 | 手动实现 | 自动 Compaction |
| 执行环境 | 直接 fs/shell | ExecutionEnv 抽象 |

---

### 1.3 专家视角 - 概念网络

```
Harness 概念网络:

核心类:
├─ AgentHarness
│   ├─ agent: Agent ← 内嵌 Agent 实例
│   ├─ session: Session ← 会话管理
│   ├─ skills: SkillRegistry ← 技能注册表
│   ├─ executionEnv: ExecutionEnv ← 执行环境
│   └─ compactionSettings ← 压缩配置
│
├─ AgentHarnessOptions
│   ├─ sessionDir: string ← 会话目录
│   ├─ skills: Skill[] ← 初始技能
│   ├─ executionEnv: ExecutionEnv ← 自定义环境
│   ├─ compactionSettings ← 压缩配置
│   └─ 其他 AgentOptions 继承
│
├─ AgentHarnessEvent
│   ├─ 继承 AgentEvent
│   ├─ skill_invoked: { skillName, args }
│   ├─ compaction_start/end
│   └─ session_saved/loaded

Session 管理:
├─ Session
│   ├─ tree: SessionTree ← 树形结构
│   ├─ activeLeafId: string ← 当前叶子
│   ├─ entries: SessionTreeEntry[] ← 所有条目
│   └─ save() / load() / fork() / merge()
│
├─ SessionTree
│   ├─ rootId: string
│   ├─ nodes: Map<string, SessionTreeNode>
│   └─ 每节点: { id, parentId, childrenIds, entryId }
│
├─ SessionTreeEntry
│   ├─ id: string
│   ├─ timestamp: number
│   ├─ message: AgentMessage
│   └─ summary?: string (压缩后)

Skills 系统:
├─ Skill
│   ├─ name: string
│   ├─ description: string
│   ├─ promptTemplate: PromptTemplate
│   ├─ tools: AgentTool[]
│   ├─ matchers: SkillMatcher[]
│   └─ execute: (env, args) => Promise<Result>
│
├─ SkillRegistry
│   ├─ skills: Map<string, Skill>
│   ├─ register(skill): void
│   ├─ match(query): SkillMatch[]
│   └─ execute(skillName, args): Promise<Result>
│
├─ SkillMatcher
│   ├─ type: "regex" | "keyword" | "llm"
│   ├─ pattern?: string
│   └─ keywords?: string[]

Compaction 系统:
├─ CompactionSettings
│   ├─ threshold: number ← Token 阈值
│   ├─ reserveTokens: number ← 保留 Token
│   ├─ summaryModel?: Model ← 摘要模型
│   └─ customInstructions?: string
│
├─ prepareCompaction()
│   ├─ 检查是否需要压缩
│   └─ 返回 CompactionPreparation
│
├─ compact()
│   ├─ 切割消息
│   ├─ generateSummary()
│   └─ 替换原始消息
```

---

## 2. 结构化学习 (SQ3R)

### 2.1 Survey - Harness 架构概览

```
AgentHarness 架构:

┌─────────────────────────────────────────────────────────┐
│                    AgentHarness                           │
│                                                           │
│  核心组件:                                                │
│  ├─ agent: Agent (内嵌)                                  │
│  ├─ session: Session (持久化)                            │
│  ├─ skills: SkillRegistry (技能)                         │
│  ├─ executionEnv: ExecutionEnv (执行环境)                │
│  └─ compaction: CompactionSettings (压缩)                │
│                                                           │
│  公开方法:                                                │
│  ├─ prompt(text | messages)                              │
│  ├─ continue()                                           │
│  ├─ loadSession(sessionId)                               │
│  ├─ saveSession()                                        │
│  ├─ forkSession() / mergeSession()                       │
│  ├─ registerSkill(skill)                                 │
│  ├─ matchSkills(query)                                   │
│  ├─ executeSkill(skillName, args)                        │
│  └─ subscribe(listener)                                  │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                    SessionTree                            │
│                                                           │
│  rootId                                                  │
│      │                                                    │
│      ├─ node1 (user: "Hello")                            │
│      │   ├─ node2 (assistant: "Hi!")                     │
│      │   │   ├─ node3 (user: "Task A") ← activeLeaf     │
│      │   │   └─ node4 (user: "Task B") ← fork            │
│      │                                                    │
│  支持分支、合并、恢复                                     │
└─────────────────────────────────────────────────────────┘
```

### 2.2 Question - 关键问题驱动

**Q1**: SessionTree 如何支持分支和合并？
**Q2**: SkillMatcher 的三种匹配类型如何工作？
**Q3**: Compaction 的切割点如何选择？
**Q4**: ExecutionEnv 为什么需要抽象 fs/shell？

### 2.3 Read - 源代码映射

| 内容 | 源文件 | 行数 |
|------|--------|------|
| AgentHarness 类 | `harness/agent-harness.ts` | L1-1000 |
| AgentHarnessOptions | `harness/types.ts` | L50-80 |
| Session 类 | `harness/session/session.ts` | - |
| SessionTree | `harness/session/session-tree.ts` | - |
| SessionTreeEntry | `harness/types.ts` | - |
| Skill 类型 | `harness/types.ts` | L100-150 |
| SkillRegistry | `harness/skills/skill-registry.ts` | - |
| SkillMatcher | `harness/types.ts` | - |
| CompactionSettings | `harness/types.ts` | - |
| ExecutionEnv | `harness/types.ts` | L200-250 |

### 2.4 Recite - 使用模板

#### Harness 基础使用模板

```typescript
import { AgentHarness } from "@earendil-works/pi-agent-core";
import { getModel } from "@earendil-works/pi-ai";

const harness = new AgentHarness({
  initialState: {
    systemPrompt: "You are helpful.",
    model: getModel("anthropic", "claude-sonnet-4"),
  },
  sessionDir: "./sessions",
  executionEnv: {
    fs: nodeFs,
    shell: nodeShell,
  },
});

harness.subscribe((event) => {
  if (event.type === "skill_invoked") {
    console.log(`Skill ${event.skillName} invoked`);
  }
});

await harness.prompt("Hello!");
await harness.saveSession();
```

#### Session 分支模板

```typescript
// 当前会话在 leaf3
await harness.prompt("Task A");

// 分支到新 leaf4
const forkedId = await harness.forkSession();

// 在原分支继续
await harness.prompt("Task A continuation");

// 切换到 fork 分支
await harness.loadSession(forkedId);
await harness.prompt("Task B");
```

#### Skills 注册模板

```typescript
const mySkill: Skill = {
  name: "analyze_code",
  description: "Analyze code quality",
  promptTemplate: {
    template: "Analyze {{file}} for quality issues",
    args: ["file"],
  },
  tools: [readFileTool],
  matchers: [
    { type: "keyword", keywords: ["analyze", "code"] },
  ],
  execute: async (env, args) => {
    const content = await env.fs.readFile(args.file);
    return { result: analyze(content) };
  },
};

harness.registerSkill(mySkill);
```

### 2.5 Review - TODO清单

#### TODO-1: 掌握 Harness 结构 (🔴)
**完成检查**:
- [ ] 列举 AgentHarness 的 5 个核心组件
- [ ] 解释 Harness 与 Agent 的关系

#### TODO-2: 掌握 Session 管理 (🔴)
**完成检查**:
- [ ] 解释 SessionTree 的树形结构
- [ ] 解释 fork/merge 的操作

#### TODO-3: 掌握 Skills 系统 (🟠)
**完成检查**:
- [ ] 列举 Skill 的 5 个字段
- [ ] 解释 SkillMatcher 的三种类型

#### TODO-4: 掌握 Compaction (🟠)
**完成检查**:
- [ ] 解释 threshold 和 reserveTokens 的作用
- [ ] 解释切割点选择策略

---

## 3. 对抗性测试

### 3.1 边界问题

#### SessionTree 分支限制

```typescript
// 分支深度无限制，但实际受文件系统限制
session.fork(session.activeLeafId);
// 可以无限 fork，但每个 fork 创建新文件
```

**边界**: 文件系统性能和存储限制。

#### SkillMatcher 匹配优先级

```typescript
// 多个 Skill 匹配时，按优先级排序
matchers: [
  { type: "regex", pattern: "analyze\\s+(.+)" },  // 高优先级
  { type: "keyword", keywords: ["analyze"] },     // 低优先级
];
// regex 匹配优先于 keyword
```

### 3.2 反事实推理

**情境 1**: 如果 Session 目录不存在？
```typescript
sessionDir: "./nonexistent"
// 结果：Harness 创建目录
// 教训：自动创建，无需手动准备
```

**情境 2**: 如果 Compaction threshold 设置过低？
```typescript
threshold: 100  // 太低
// 结果：频繁压缩，性能下降
// 教训：threshold 应合理设置 (如 4000)
```

**情境 3**: 如果 Skill execute 抛异常？
```typescript
execute: async () => { throw new Error("Failed"); }
// 结果：skill_invoked 事件带 isError 标记
// 教训：错误被编码为事件，不中断流程
```

### 3.3 漏洞注入 - 常见错误

| 错误类型 | 示例 | 后果 |
|---------|------|------|
| 遗漏 executionEnv | 无 fs/shell | 工具执行失败 |
| threshold 过低 | threshold: 100 | 频繁压缩 |
| Skill 无 matchers | 无法匹配 | 技能不被触发 |
| fork 后不切换 | 继续在原分支 | 任务混乱 |
| Session 目录权限问题 | 无写入权限 | 持久化失败 |

---

## 4. 思想与迁移

### 4.1 设计哲学

#### 组合而非继承

```typescript
// AgentHarness 组合 Agent
class AgentHarness {
  private agent: Agent;  // 组合
  private session: Session;
  private skills: SkillRegistry;
}
```

**思想**: 组合更灵活，可替换各组件。

#### 树形会话结构

```
root → node1 → node2 → node3 (active)
              → node4 (fork)
```

**思想**: 支持分支、合并，保留完整历史。

#### 抽象执行环境

```typescript
interface ExecutionEnv {
  fs: FileSystem;
  shell: Shell;
}
```

**思想**: 解耦具体实现，支持浏览器/Node.js/自定义环境。

### 4.2 可迁移思维

| 思想 | Harness 应用 | 可迁移领域 |
|------|-------------|-----------|
| **组合模式** | Agent + Session + Skills | 框架设计、插件系统 |
| **树形状态** | SessionTree 分支 | 版本控制、游戏状态 |
| **匹配系统** | SkillMatcher 多类型 | 命令路由、意图识别 |
| **环境抽象** | ExecutionEnv | 跨平台应用 |
| **自动压缩** | Compaction | 缓存管理、内存优化 |

---

## 源文件映射

| 内容 | 源文件 | 行数 |
|------|--------|------|
| AgentHarness 类 | `harness/agent-harness.ts` | ~1000 |
| Harness 类型 | `harness/types.ts` | ~300 |
| Session 管理 | `harness/session/` | - |
| Skills 系统 | `harness/skills/` | - |

---

## 下一步

→ [L08: Session 管理](../08-session)