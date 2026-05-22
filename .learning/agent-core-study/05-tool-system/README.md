# L05: 工具执行完整流程

---

## 1. 心智模型构建

### 1.1 背景

#### 工具执行的历史演进

```
早期工具执行:
├─ 单工具: 简单调用
├─ 顺序执行: 一个完成后下一个
├─ 错误处理: 简单 try-catch
└─ 无并发概念

中期需求:
├─ 多工具并发执行 → 提高效率
├─ 参数验证 → TypeBox schema
├─ 执行前后钩子 → 权限检查、审计
├─ 流式进度 → 长时间任务反馈
└─ 终止提示 → 控制流程

→ agent-core 提供完整工具执行框架
```

---

### 1.2 目标

#### 核心痛点

| 痛点 | 手动实现 | agent-core 解决 |
|------|---------|----------------|
| 参数验证 | 手动检查 | TypeBox + validateToolArguments |
| 并发执行 | 手动 Promise.all + 顺序管理 | parallel 模式自动处理 |
| 执行钩子 | 手动插入 | beforeToolCall / afterToolCall |
| 进度反馈 | 无标准机制 | onUpdate 回调 + tool_execution_update |
| 终止控制 | 手动判断 | terminate 批级别机制 |

---

### 1.3 专家视角 - 概念网络

```
工具执行概念网络:

定义层:
├─ Tool (pi-ai)
│   ├─ name: string
│   ├─ description: string
│   └─ parameters: TSchema
│
├─ AgentTool (扩展)
│   ├─ label: string ← UI 标签
│   ├─ prepareArguments?: shim
│   ├─ execute: (id, params, signal, onUpdate)
│   └─ executionMode?: override

执行层:
├─ prepareToolCall
│   ├─ find tool
│   ├─ prepareArguments
│   ├─ validateToolArguments
│   ├─ beforeToolCall
│   └─ return: PreparedToolCall | Immediate
│
├─ executePreparedToolCall
│   ├─ tool.execute()
│   ├─ onUpdate → emit tool_execution_update
│   └─ return: ExecutedToolCallOutcome
│
├─ finalizeExecutedToolCall
│   ├─ afterToolCall
│   ├─ merge result
│   └─ return: FinalizedToolCallOutcome

结果层:
├─ AgentToolResult
│   ├─ content: TextContent | ImageContent[]
│   ├─ details: T
│   └─ terminate?: boolean
│
├─ ToolResultMessage
│   ├─ role: "toolResult"
│   ├─ toolCallId
│   ├─ toolName
│   ├─ content
│   └─ isError
```

---

## 2. 结构化学习 (SQ3R)

### 2.1 Survey - 执行流程概览

```
工具执行完整流程:

┌─────────────────────────────────────────────────────────┐
│                  TOOL EXECUTION FLOW                      │
└─────────────────────────────────────────────────────────┘

assistantMessage (包含 toolCalls[])
       │
       │ executeToolCalls()
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│                  MODE SELECTION                           │
│  hasSequentialToolCall?                                   │
│      ├─ Yes → executeToolCallsSequential                 │
│      └─ No  → executeToolCallsParallel                   │
└─────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│                  FOR EACH TOOL CALL                       │
│                                                           │
│  1. emit tool_execution_start                            │
│  2. prepareToolCall                                       │
│     ├─ find tool definition                              │
│     ├─ prepareArguments                                  │
│     ├─ validateToolArguments                             │
│     ├─ beforeToolCall                                    │
│     └─ block? → Immediate                                │
│  3. executePreparedToolCall                              │
│     ├─ tool.execute()                                    │
│     └─ onUpdate → emit update                            │
│  4. finalizeExecutedToolCall                             │
│     ├─ afterToolCall                                     │
│     └─ merge result                                      │
│  5. emit tool_execution_end                              │
│  6. emit message_start/end (toolResult)                  │
└─────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│                  TERMINATE CHECK                          │
│  shouldTerminateToolBatch()                              │
│  → 所有工具都 terminate?                                 │
└─────────────────────────────────────────────────────────┘
```

### 2.2 Question - 关键问题驱动

**Q1**: prepareArguments 和 validateToolArguments 的区别是什么？
**Q2**: beforeToolCall 和 afterToolCall 的触发时机和效果？
**Q3**: parallel 执行的三阶段是什么？
**Q4**: terminate 的触发条件和效果？

### 2.3 Read - 源代码映射

| 内容 | 源文件 | 行数 |
|------|--------|------|
| AgentTool 定义 | `types.ts` | L361-384 |
| AgentToolResult | `types.ts` | L344-355 |
| BeforeToolCallContext | `types.ts` | L84-93 |
| AfterToolCallContext | `types.ts` | L96-109 |
| BeforeToolCallResult | `types.ts` | L55-58 |
| AfterToolCallResult | `types.ts` | L72-81 |
| executeToolCalls | `agent-loop.ts` | L373-388 |
| executeToolCallsSequential | `agent-loop.ts` | L395-449 |
| executeToolCallsParallel | `agent-loop.ts` | L451-516 |
| prepareToolCall | `agent-loop.ts` | L562-626 |
| prepareToolCallArguments | `agent-loop.ts` | L548-560 |
| executePreparedToolCall | `agent-loop.ts` | L628-663 |
| finalizeExecutedToolCall | `agent-loop.ts` | L665-708 |
| shouldTerminateToolBatch | `agent-loop.ts` | L544-546 |
| createToolResultMessage | `agent-loop.ts` | L727-736 |

### 2.4 Recite - 使用模板

#### 工具定义模板

```typescript
import { Type } from "typebox";

const readFileTool: AgentTool = {
  name: "read_file",
  description: "Read a file's contents",
  parameters: Type.Object({
    path: Type.String({ description: "File path" }),
  }),
  
  label: "Read File",
  
  prepareArguments: (args) => args as { path: string },
  
  execute: async (toolCallId, params, signal, onUpdate) => {
    if (signal?.aborted) throw new Error("Aborted");
    
    onUpdate?.({ content: [{ type: "text", text: "Reading..." }], details: {} });
    
    const content = await fs.readFile(params.path);
    return {
      content: [{ type: "text", text: content }],
      details: { path, size: content.length },
      terminate: false,
    };
  },
  
  executionMode: "sequential",
};
```

#### 钩子使用模板

```typescript
const agent = new Agent({
  beforeToolCall: async ({ toolCall, args }) => {
    if (toolCall.name === "bash" && args.command.includes("rm -rf")) {
      return { block: true, reason: "Dangerous command" };
    }
  },
  
  afterToolCall: async ({ toolCall, result, isError }) => {
    if (!isError) {
      return { details: { ...result.details, audited: true } };
    }
  },
});
```

### 2.5 Review - TODO清单

#### TODO-1: 掌握 AgentTool 结构 (🔴)
**完成检查**:
- [ ] 列举继承自 Tool 的 3 个字段
- [ ] 列举新增的 4 个字段
- [ ] 解释 execute 的 4 个参数

#### TODO-2: 掌握参数验证 (🔴)
**完成检查**:
- [ ] 解释 prepareArguments 和 validateToolArguments 的区别
- [ ] 解释 validateToolArguments 失败时的处理

#### TODO-3: 掌握钩子机制 (🔴)
**完成检查**:
- [ ] 解释 beforeToolCall 的 block 效果
- [ ] 解释 afterToolCall 的合并语义

#### TODO-4: 掌握并行执行 (🟠)
**完成检查**:
- [ ] 列举三阶段
- [ ] 解释事件顺序差异

#### TODO-5: 掌握 terminate (🟠)
**完成检查**:
- [ ] 解释触发条件
- [ ] 列举两个设置位置

---

## 3. 对抗性测试

### 3.1 边界问题

#### executionMode 混合批

```typescript
// 工具 A: executionMode: "sequential"
// 工具 B: executionMode: "parallel"

// 结果: 整批顺序执行
// 规则: 一个 sequential → 全部 sequential
```

#### afterToolCallResult 合并语义

```typescript
// ❌ 期望深度合并
return { details: { audited: true } };
// 结果: details 整字段替换，原 details 丢失

// ✅ 正确做法
return { details: { ...result.details, audited: true } };
```

### 3.2 反事实推理

**情境 1**: 如果工具找不到？
```typescript
LLM 调用 tool "unknown_tool"
// prepareToolCall: 找不到 tool 定义
// 结果: ImmediateToolCallOutcome { isError: true, result: "Tool not found" }
// 教训: 错误被编码为 tool result，不中断流程
```

**情境 2**: 如果 beforeToolCall 不返回？
```typescript
beforeToolCall: async () => { await longOperation(); }
// 结果: 阻塞工具预检，整个 batch 等待
// 教训: beforeToolCall 应快速执行
```

**情境 3**: 如果 execute 抛异常？
```typescript
execute: async () => { throw new Error("Failed"); }
// 结果: executePreparedToolCall 捕获，返回 isError: true
// 教训: 抛异常被处理为错误 tool result
```

### 3.3 漏洞注入 - 常见错误

| 错误类型 | 示例 | 后果 |
|---------|------|------|
| 遗漏 parameters | 无 schema | 验证失败 |
| 深度合并期望 | 只返回部分 details | 原值丢失 |
| 不抛异常返回错误 | 返回 error 内容 | 不是 isError |
| terminate 混合批 | 只有部分工具 terminate | 不生效 |

---

## 4. 思想与迁移

### 4.1 设计哲学

#### 预检-执行-后处理三阶段

```
Preflight (预检):
├─ 参数预处理
├─ 参数验证
├─ 钩子检查
└─ 决定是否执行

Execute (执行):
├─ 实际调用工具
├─ 流式进度
└─ 返回结果

Postprocess (后处理):
├─ 钩子修改
├─ 结果编码
└─ 事件发出
```

**思想**: 分离关注点，每个阶段独立可控。

#### 批级别终止

```typescript
// 只有全部同意才终止
shouldTerminateToolBatch: finalizedCalls.every(f => f.result.terminate)
```

**思想**: 集体决策，防止单个工具意外终止。

#### 错误编码而非中断

```typescript
// 工具失败不中断流程
executePreparedToolCall: catch error → return { isError: true }
```

**思想**: 错误是结果的一部分，流程继续。

### 4.2 可迁移思维

| 思想 | 工具执行应用 | 可迁移领域 |
|------|-------------|-----------|
| **三阶段处理** | 预检-执行-后处理 | 请求处理、中间件 |
| **批级别决策** | terminate 所有同意 | 分布式决策、投票 |
| **错误编码** | isError 标记 | API设计、错误处理 |
| **流式进度** | onUpdate 回调 | 长任务、下载 |
| **Hook 系统** | before/after 钩子 | 拦截器、审计 |

---

## 源文件映射

| 内容 | 源文件 | 行数 |
|------|--------|------|
| AgentTool 类型 | `types.ts` | L361-384 |
| 工具执行逻辑 | `agent-loop.ts` | L373-742 |

---

## 下一步

→ [L06: 事件系统](../06-event-flow)