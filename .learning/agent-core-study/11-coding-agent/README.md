# L11: coding-agent 实例分析

---

## 1. 心智模型构建

### 1.1 背景

#### 从核心到应用

```
pi-agent-core 提供:
├─ Agent 类: 状态管理
├─ AgentLoop: 循环机制
├─ Harness: 应用框架
└─ 基础能力

pi-coding-agent 提供:
├─ 完整编码助手
├─ 扩展能力示例
├─ 最佳实践展示
└─ 实战参考

→ 通过实例理解 agent-core 的实际应用
```

#### 实例类型

| 实例 | 核心概念 | 学习价值 |
|------|---------|---------|
| handoff.ts | Agent As Tool | 多 Agent 协作 |
| permission-gate.ts | HITL 模式 | 安全权限检查 |
| plan-mode/ | PlanAct 模式 | 结构化任务执行 |
| custom-provider/ | 自定义 Provider | 扩展性 |
| git-checkpoint.ts | 状态保存 | 版本控制集成 |

---

### 1.2 目标

#### 核心痛点

| 痛点 | 基础 Agent | 实例扩展 |
|------|-----------|---------|
| 多 Agent 协作 | 无 | handoff 实现 |
| 权限控制 | 无钩子示例 | permission-gate |
| 结构化任务 | 无 | plan-mode |
| Provider 扩展 | 标准 | custom-provider |
| 状态回滚 | 无 | git-checkpoint |

---

### 1.3 专家视角 - 概念网络

```
实例概念网络:

handoff.ts - Agent Handoff:
├─ Master Agent → Worker Agent
├─ 上下文传递: serializeContext → deserialize
├─ Agent As Tool 模式
├─ 结果汇总: Worker 结果 → Master 继续
│
├─ 实现要点:
│   ├─ createContextSnapshot()
│   ├─ AgentTool 封装 Worker Agent
│   ├─ execute 中创建新 Agent
│   └─ 返回 AgentToolResult

permission-gate.ts - HITL 权限:
├─ beforeToolCall 钩子实现
├─ Stop and Resume 模式
├─ 需要用户确认才执行
│
├─ 实现要点:
│   ├─ beforeToolCall 返回 { block: true }
│   ├─ 等待用户决策
│   ├─ 用户同意: 返回 { block: false }
│   ├─ 用户拒绝: 返回 { block: true, reason }
│   └─ 高风险工具: bash, fs 操作

plan-mode/ - PlanAct 模式:
├─ create_plan 工具生成计划
├─ execute_step 工具逐步执行
├─ verify_step 工具验证结果
│
├─ 流程:
│   ├─ User Query → create_plan
│   ├─ Plan → execute_step (loop)
│   ├─ each step → verify_step
│   ├─ all steps done → final answer
│   └─ 失败时调整计划
│
├─ 优势:
│   ├─ 结构化任务
│   ├─ 可追踪进度
│   ├─ 失败可恢复
│   └─ 质量保证

custom-provider-anthropic/:
├─ 自定义 Anthropic 配置
├─ 自定义 headers, baseUrl
├─ 自定义 model list
│
├─ 实现要点:
│   ├─ registerModel() 注册自定义模型
│   ├─ 自定义 streamFn
│   ├─ 覆盖默认 Provider
│   └─ 支持企业内部 API

git-checkpoint.ts:
├─ 在关键节点创建 git commit
├─ 用于状态回滚
├─ 用于调试追踪
│
├─ 实现要点:
│   ├─ afterToolCall 钩子
│   ├─ 检查文件变化
│   ├─ git add + commit
│   └─ 记录 commit SHA
```

---

## 2. 结构化学习 (SQ3R)

### 2.1 Survey - 实例架构

```
handoff.ts 架构:

┌─────────────────────────────────────────────────────────┐
│                    MASTER AGENT                           │
│                                                           │
│  prompt("Complex task")                                  │
│      │                                                    │
│      │ decide: delegate to Worker                        │
│      │                                                    │
│      ▼                                                    │
│  handoff_tool.execute()                                  │
│      │                                                    │
│      │ serializeContext()                                │
│      │                                                    │
└─────────────────────────────────────────────────────────┘
                         │
                         │ context snapshot
                         ▼
┌─────────────────────────────────────────────────────────┐
│                    WORKER AGENT                           │
│                                                           │
│  deserialize(context)                                    │
│      │                                                    │
│      │ execute subtask                                   │
│      │                                                    │
│      ▼                                                    │
│  return AgentToolResult                                  │
│      ├─ content: result                                  │
│      ├─ details: metadata                                │
│      └─ terminate: false                                 │
└─────────────────────────────────────────────────────────┘
                         │
                         │ result
                         ▼
┌─────────────────────────────────────────────────────────┐
│                    MASTER AGENT                           │
│                                                           │
│  continue with Worker result                             │
│      │                                                    │
│      │ next action                                       │
│      │                                                    │
│      ▼                                                    │
│  final answer                                            │
└─────────────────────────────────────────────────────────┘
```

### 2.2 Question - 关键问题驱动

**Q1**: handoff 如何传递 Agent 上下文？
**Q2**: permission-gate 的 block 机制如何工作？
**Q3**: plan-mode 的 create_plan 返回什么结构？
**Q4**: git-checkpoint 在哪些节点触发？

### 2.3 Read - 源代码映射

| 内容 | 源文件 | 行数 |
|------|--------|------|
| handoff.ts | `pi/coding-agent/examples/extensions/handoff.ts` | - |
| permission-gate.ts | `pi/coding-agent/examples/extensions/permission-gate.ts` | - |
| plan-mode/ | `pi/coding-agent/examples/extensions/plan-mode/` | - |
| custom-provider-anthropic/ | `pi/coding-agent/examples/extensions/custom-provider-anthropic/` | - |
| git-checkpoint.ts | `pi/coding-agent/examples/extensions/git-checkpoint.ts` | - |

### 2.4 Recite - 使用模板

#### Handoff 模板

```typescript
const handoffTool: AgentTool = {
  name: "delegate_to_worker",
  description: "Delegate subtask to specialized worker",
  parameters: Type.Object({
    task: Type.String(),
    context: Type.String(),
  }),
  
  label: "Delegate",
  
  execute: async (id, params, signal, onUpdate) => {
    // 创建 Worker Agent
    const worker = new Agent({
      initialState: {
        systemPrompt: `You are a specialist for: ${params.task}`,
        model: getModel("anthropic", "claude-sonnet-4"),
      },
    });
    
    // 传递上下文
    const snapshot = deserializeContext(params.context);
    worker.state.messages = snapshot.messages;
    
    // 执行子任务
    await worker.prompt(params.task);
    await worker.waitForIdle();
    
    // 返回结果
    const lastMessage = worker.state.messages[worker.state.messages.length - 1];
    return {
      content: [{ type: "text", text: lastMessage.content }],
      details: { delegated: true },
      terminate: false,
    };
  },
};
```

#### Permission Gate 模板

```typescript
const agent = new Agent({
  beforeToolCall: async ({ toolCall, args }) => {
    if (toolCall.name === "bash" && args.command.includes("rm")) {
      // 等待用户确认
      const approved = await askUser(`Allow: ${args.command}?`);
      
      if (!approved) {
        return { block: true, reason: "User denied" };
      }
    }
    return undefined;  // 不阻止
  },
});
```

#### Plan Mode 模板

```typescript
const createPlanTool: AgentTool = {
  name: "create_plan",
  description: "Create structured plan for task",
  parameters: Type.Object({
    task: Type.String(),
  }),
  
  execute: async (id, params, signal, onUpdate) => {
    const plan = await generatePlan(params.task);
    return {
      content: [{ type: "text", text: JSON.stringify(plan) }],
      details: { plan },
      terminate: false,
    };
  },
};

const executeStepTool: AgentTool = {
  name: "execute_step",
  description: "Execute one step of plan",
  parameters: Type.Object({
    stepId: Type.Number(),
    action: Type.String(),
  }),
  
  execute: async (id, params, signal, onUpdate) => {
    const result = await executeAction(params.action);
    return {
      content: [{ type: "text", text: result }],
      details: { stepId: params.stepId, success: true },
      terminate: false,
    };
  },
};
```

### 2.5 Review - TODO清单 (渐进式披露)

> 📋 **渐进式学习**: 一次只显示一个TODO，完成后才解锁下一个。

#### 🔴 TODO-1: 分析 handoff (当前激活)

**完成检查**:
- [ ] 阅读 handoff.ts 理解上下文传递
- [ ] 解释 Agent As Tool 模式

<details>
<summary>💡 提示</summary>

Agent As Tool: Master Agent → handoff_tool → Worker Agent → Result

上下文传递: serializeContext → Worker → deserialize
</details>

---

#### 🟡 TODO-2: 分析 permission-gate (待解锁)

**前置要求**: 完成 TODO-1

**完成检查**:
- [ ] 阅读 permission-gate.ts 理解 HITL 模式
- [ ] 解释 beforeToolCall block 机制

---

#### 🟡 TODO-3: 分析 plan-mode (待解锁)

**前置要求**: 完成 TODO-2

**完成检查**:
- [ ] 阅读 plan-mode/ 理解 PlanAct 模式
- [ ] 解释 create_plan → execute_step → verify_step 流程

---

#### 🟡 TODO-4: 分析其他实例 (待解锁)

**前置要求**: 完成 TODO-3

**完成检查**:
- [ ] 阅读 custom-provider 理解扩展性
- [ ] 阅读 git-checkpoint 理解状态保存

---

## 📝 费曼检验 (必须完成)

在结束本课程之前，请用自己的话解释：

### 问题 1: Handoff 模式
> "Agent As Tool 模式解决了什么问题？Master 和 Worker 如何协作？"

你的解释：_______________________________________________

### 问题 2: HITL 模式
> "permission-gate 如何实现人工介入？beforeToolCall 返回 block 会怎样？"

你的解释：_______________________________________________

### 问题 3: PlanAct 模式
> "create_plan → execute_step → verify_step 的流程是什么？为什么结构化执行更好？"

你的解释：_______________________________________________

### 问题 4: 扩展性
> "如何通过 custom-provider 扩展？git-checkpoint 在什么时候触发？"

你的解释：_______________________________________________

<details>
<summary>✅ 检查你的理解</summary>

**问题 1 参考答案**:
- 解决复杂任务分工问题
- Master 决策，Worker 执行
- 上下文传递保持状态连续

**问题 2 参考答案**:
- beforeToolCall 检查风险操作
- block: true 阻止执行，返回错误
- 等待用户确认后再放行

**问题 3 参考答案**:
- create_plan: 生成任务计划
- execute_step: 执行单个步骤
- verify_step: 验证执行结果
- 结构化：可追踪、可恢复、可验证

**问题 4 参考答案**:
- custom-provider: 注册自定义模型
- git-checkpoint: 在工具调用后触发
- 用于状态回滚和调试追踪
</details>

---

## 3. 对抗性测试

### 3.1 边界问题

#### Handoff 上下文大小

```typescript
// 大量 messages 传递给 Worker
serializeContext(messages)  // 可能很大
// 结果：Worker 启动慢，上下文解析耗时
// 教训：筛选必要上下文传递
```

#### Permission Gate 阻塞时间

```typescript
// 用户长时间不响应
await askUser();  // 等待 10 分钟
// 结果：Agent 卡住，无法继续
// 教训：设置超时，或异步处理
```

### 3.2 反事实推理

**情境 1**: 如果 Worker Agent 失败？
```typescript
await worker.prompt(task);
// Worker 抛异常
// 结果：AgentToolResult isError: true
// 教训：Master 应处理 Worker 错误
```

**情境 2**: 如果 Plan 无法执行？
```typescript
plan = { steps: [impossible_action] }
// 结果：execute_step 失败
// 教训：Plan 应可调整，失败时重规划
```

**情境 3**: 如果 git-checkpoint 失败？
```typescript
// git 操作失败 (dirty state)
// 结果：afterToolCall 返回错误
// 教训：git 操作应安全，处理失败
```

### 3.3 漏洞注入 - 常见错误

| 错误类型 | 示例 | 后果 |
|---------|------|------|
| Handoff 全量传递 | messages 全传 | Worker 慢 |
| Permission 无超时 | 用户不响应 | Agent 卡住 |
| Plan 过度复杂 | steps 过多 | 执行慢 |
| Provider 配置错误 | baseUrl 错误 | API 调用失败 |
| git dirty state | 未提交变更 | checkpoint 失败 |

---

## 4. 思想与迁移

### 4.1 设计哲学

#### Agent As Tool

```
Master Agent → handoff_tool → Worker Agent → Result → Master
```

**思想**: Agent 可以作为 Tool 使用，支持分层协作。

#### HITL 模式

```
Tool → beforeToolCall → User Decision → Execute or Block
```

**思想**: 关键操作需要人工确认，安全可控。

#### PlanAct 模式

```
Query → Plan → Execute Steps → Verify → Answer
```

**思想**: 结构化执行，失败可恢复，质量可验证。

### 4.2 可迁移思维

| 思想 | 实例应用 | 可迁移领域 |
|------|---------|-----------|
| **Agent As Tool** | handoff | 多 Agent 协作、任务分层 |
| **HITL 模式** | permission-gate | 安全操作、审批流程 |
| **PlanAct 模式** | plan-mode | 项目管理、任务调度 |
| **扩展性** | custom-provider | 框架定制、企业集成 |
| **版本集成** | git-checkpoint | 状态管理、审计追踪 |

---

## 学习完成！

你已经完成 11 课的学习：

| 课程 | 内容 |
|------|------|
| L01 | 架构概览 + pi/ai 依赖 |
| L02 | 类型系统 |
| L03 | Agent Loop 底层机制 |
| L04 | Agent 类 |
| L05 | 工具执行流程 |
| L06 | 事件系统 |
| L07 | Harness 基础 |
| L08 | Session 管理 |
| L09 | 上下文压缩 |
| L10 | Proxy 支持 |
| L11 | coding-agent 实例 |

**下一步**：
- 阅读完整源代码
- 构建 MVP 项目
- 实现自定义扩展

---

## 源文件映射

| 内容 | 源文件 |
|------|--------|
| handoff.ts | `pi/coding-agent/examples/extensions/handoff.ts` |
| permission-gate.ts | `pi/coding-agent/examples/extensions/permission-gate.ts` |
| plan-mode/ | `pi/coding-agent/examples/extensions/plan-mode/` |
| custom-provider/ | `pi/coding-agent/examples/extensions/custom-provider-anthropic/` |
| git-checkpoint.ts | `pi/coding-agent/examples/extensions/git-checkpoint.ts` |