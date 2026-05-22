# L02: 类型系统 (合并)

---

## 1. 心智模型构建

### 1.1 背景

#### 为什么需要完整的类型系统？

```
问题演进:
├─ 早期: JavaScript 动态类型，运行时错误多
├─ 中期: TypeScript 部分类型，但仍不完整
├─ 现在: 完整类型系统
│   ├─ 类型安全: 编译时捕获错误
│   ├─ 文档化: 类型即文档
│   ├─ IDE支持: 自动补全、重构
│   └─ 扩展性: 声明合并、泛型
```

#### agent 类型系统的两个源头

| 文件 | 行数 | 职责 |
|------|------|------|
| `types.ts` | ~420行 | Agent 核心类型 |
| `harness/types.ts` | ~300行 | Harness 专有类型 |

**设计意图**: 核心类型与 Harness 类型分离，保持 agent 核心的纯粹性。

---

### 1.2 目标

#### 核心痛点

| 痛点 | 无类型系统时 | 有类型系统后 |
|------|-------------|-------------|
| 工具参数验证 | 运行时手动检查 | TypeBox 编译时验证 |
| 状态修改 | 不确定哪些可修改 | AgentState 明确区分可变/只读 |
| 事件处理 | 可能遗漏事件类型 | AgentEvent 联合类型覆盖全部 |
| 自定义扩展 | 类型丢失 | 声明合并保持类型安全 |

---

### 1.3 专家视角 - 概念网络

```
类型系统概念网络:

基础类型 (来自 pi-ai):
├─ Message (user/assistant/toolResult)
├─ Model (id, provider, contextWindow, cost)
├─ Tool (name, description, parameters)
├─ AssistantMessageEvent (流式事件类型)
└─ TextContent / ImageContent

核心类型 (types.ts):
├─ AgentMessage ← Message + CustomAgentMessages
├─ AgentState ← 可变属性 + 只读属性
├─ AgentTool ← Tool + label + execute + executionMode
├─ AgentEvent ← 10种生命周期事件
├─ AgentContext ← 快照 (prompt + messages + tools)
├─ AgentLoopConfig ← 完整配置
├─ BeforeToolCallContext / AfterToolCallContext ← 钩子上下文
└─ AgentToolResult ← content + details + terminate

Harness类型 (harness/types.ts):
├─ Skill ← name + description + promptTemplate + tools
├─ PromptTemplate ← template + args
├─ Session ← 会话管理接口
├─ ExecutionEnv ← fs + shell 抽象
├─ AgentHarnessEvent ← 继承 AgentEvent + Harness专有事件
└─ AgentHarnessError ← 错误类型体系
```

#### 核心概念定义

| 概念 | 定义 | 关键特性 |
|------|------|---------|
| AgentState | Agent 的状态接口 | getter/setter 复制机制 |
| AgentTool | 工具定义接口 | 继承 Tool + execute 签名 |
| AgentEvent | 事件联合类型 | Discriminated Union |
| ThinkingLevel | 推理级别枚举 | off → xhigh (6级) |

---

## 2. 结构化学习 (SQ3R)

### 2.1 Survey - 类型层级概览

```
AgentState 层级:
┌─────────────────────────────────────────────────────────┐
│                    AgentState                            │
│                                                          │
│  可变属性 (可赋值修改):                                  │
│  ├─ systemPrompt: string                                │
│  ├─ model: Model<any>                                   │
│  ├─ thinkingLevel: ThinkingLevel                        │
│  ├─ tools: AgentTool[] ← setter 复制                    │
│  ├─ messages: AgentMessage[] ← setter 复制              │
│                                                          │
│  只读属性 (不可赋值):                                    │
│  ├─ isStreaming: boolean                                │
│  ├─ streamingMessage?: AgentMessage                     │
│  ├─ pendingToolCalls: ReadonlySet<string>               │
│  └─ errorMessage?: string                               │
└─────────────────────────────────────────────────────────┘

AgentTool 层级:
┌─────────────────────────────────────────────────────────┐
│ AgentTool<TParameters, TDetails>                         │
│                                                          │
│  继承自 pi-ai Tool:                                      │
│  ├─ name: string                                        │
│  ├─ description: string                                 │
│  ├─ parameters: TSchema (TypeBox)                       │
│                                                          │
│  agent-core 新增:                                        │
│  ├─ label: string ← UI 显示标签                         │
│  ├─ prepareArguments?: (args) => validated              │
│  ├─ execute: (id, params, signal, onUpdate) => Result   │
│  └─ executionMode?: ToolExecutionMode                   │
└─────────────────────────────────────────────────────────┘
```

### 2.2 Question - 关键问题驱动

**Q1**: AgentState 的 tools 和 messages 为什么使用 getter/setter？
**Q2**: AgentEvent 如何保证事件类型的完整性？
**Q3**: BeforeToolCallResult 和 AfterToolCallResult 的合并语义是什么？
**Q4**: ThinkingLevel 的 6 个级别如何影响 LLM 行为？

### 2.3 Read - 源代码映射

| 内容 | 源文件 | 行数 |
|------|--------|------|
| AgentMessage 定义 | `types.ts` | L300-309 |
| AgentState 定义 | `types.ts` | L317-342 |
| AgentTool 定义 | `types.ts` | L361-384 |
| AgentToolResult 定义 | `types.ts` | L344-355 |
| AgentEvent 定义 | `types.ts` | L403-418 |
| AgentContext 定义 | `types.ts` | L387-394 |
| AgentLoopConfig | `types.ts` | L135-277 |
| BeforeToolCallContext | `types.ts` | L84-93 |
| AfterToolCallContext | `types.ts` | L96-109 |
| BeforeToolCallResult | `types.ts` | L55-58 |
| AfterToolCallResult | `types.ts` | L72-81 |
| ToolExecutionMode | `types.ts` | L36 |
| QueueMode | `types.ts` | L44 |
| ThinkingLevel | `types.ts` | L284 |

### 2.4 Recite - 使用模板

#### AgentTool 定义模板

```typescript
import { Type } from "typebox";

const myTool: AgentTool = {
  // 继承自 Tool
  name: "read_file",
  description: "Read a file's contents",
  parameters: Type.Object({
    path: Type.String({ description: "File path" }),
  }),
  
  // agent-core 新增
  label: "Read File",  // UI 显示
  
  prepareArguments: (args) => {
    // 兼容性 shim
    return args as { path: string };
  },
  
  execute: async (toolCallId, params, signal, onUpdate) => {
    onUpdate?.({ content: [{ type: "text", text: "Reading..." }], details: {} });
    
    const content = await fs.readFile(params.path);
    return {
      content: [{ type: "text", text: content }],
      details: { path: params.path },
      terminate: false,
    };
  },
  
  executionMode: "sequential",  // 或 "parallel"
};
```

#### AgentState 使用模板

```typescript
// 可变属性赋值 (复制顶层数组)
agent.state.tools = [tool1, tool2];     // 内部复制
agent.state.messages = [...newMessages]; // 内部复制

// 只读属性 (不能赋值)
agent.state.isStreaming = true;  // ❌ 编译错误

// 直接修改数组 (不触发复制)
agent.state.tools.push(tool3);         // 直接修改
agent.state.messages.push(newMessage); // 直接修改
```

### 2.5 Review - TODO清单

#### TODO-1: 掌握核心类型结构 (🔴)
**完成检查**:
- [ ] 列举 AgentState 的 5 个可变属性和 4 个只读属性
- [ ] 解释 getter/setter 复制机制

#### TODO-2: 掌握 AgentTool (🔴)
**完成检查**:
- [ ] 列举继承自 Tool 的 3 个字段
- [ ] 列举 agent-core 新增的 4 个字段
- [ ] 解释 execute 的 4 个参数含义

#### TODO-3: 掌握 AgentLoopConfig (🟠)
**完成检查**:
- [ ] 列举必需配置项 (model, convertToLlm)
- [ ] 列举可选配置项中的 5 个钩子

#### TODO-4: 掌握枚举类型 (🟠)
**完成检查**:
- [ ] 列举 ToolExecutionMode 两种模式
- [ ] 列举 QueueMode 两种模式
- [ ] 列举 ThinkingLevel 6 个级别

---

## 3. 对抗性测试

### 3.1 边界问题

#### AgentState setter 行为

```typescript
// 赋值时复制
agent.state.tools = [...];  // 内部: tools = [...].slice()

// 直接修改不复制
const tools = agent.state.tools;
tools.push(newTool);  // 直接修改内部数组
```

**边界**: 两种修改方式效果不同，需根据场景选择。

#### AfterToolCallResult 合并语义

```typescript
// 字段级替换，无深度合并
afterToolCall: async ({ result }) => {
  return {
    details: { ...result.details, audited: true },  // 替换整个 details
  };
}
```

**边界**: 不做深度合并，整字段替换。

### 3.2 反事实推理

**情境 1**: 如果 AgentTool 没有 parameters？
```typescript
const tool: AgentTool = {
  name: "simple_tool",
  description: "...",
  // 没有 parameters
};
// 结果：TypeBox 验证可能失败，或使用空 schema
// 教训：必须定义 parameters (即使是 Type.Object({}))
```

**情境 2**: 如果 ThinkingLevel 设置为 "xhigh" 但模型不支持？
```typescript
thinkingLevel: "xhigh"
// 结果：部分模型忽略，部分模型报错
// 教训：检查模型 metadata 中的 thinkingLevel 支持
```

**情境 3**: 如果 AgentEvent 添加新类型？
```typescript
// 当前 AgentEvent 是联合类型
type AgentEvent = ... | { type: "new_event" };
// 需要修改 types.ts，更新 switch 处理
// 教训：事件类型是封闭的，需要框架支持
```

### 3.3 漏洞注入 - 常见错误

| 错误类型 | 示例 | 后果 |
|---------|------|------|
| 遗漏 Tool.parameters | 不定义 schema | 验证失败 |
| 错误的 ThinkingLevel | 用 "ultra" | 编译错误 |
| 忽略 ReadonlySet | `pendingToolCalls.add(id)` | 编译错误 |
| 混淆 Context 顺序 | `prepareNextTurn` 返回时机错误 | 状态不一致 |
| AfterToolCallResult 深度合并期望 | 期望部分合并 | 整字段替换，丢失原值 |

---

## 4. 思想与迁移

### 4.1 设计哲学

#### Discriminated Union (可辨识联合)

```typescript
type AgentEvent =
  | { type: "agent_start" }
  | { type: "agent_end"; messages: AgentMessage[] }
  | { type: "message_start"; message: AgentMessage }
  // ...
```

**优势**: 
- TypeScript 能根据 `type` 字段推断其他字段
- switch 语句有完整性检查

#### Getter/Setter 保护机制

```typescript
get tools() { return tools; }
set tools(next) { tools = next.slice(); }  // 赋值复制
```

**目的**: 防止外部赋值污染内部状态，同时允许原地修改。

#### 泛型参数化

```typescript
interface AgentTool<TParameters extends TSchema, TDetails = any> {
  execute: (id, params: Static<TParameters>, ...) => Promise<AgentToolResult<TDetails>>;
}
```

**目的**: TypeBox schema → Static 类型推导，参数类型安全。

### 4.2 可迁移思维

| 思想 | agent-core 应用 | 可迁移领域 |
|------|----------------|-----------|
| **Discriminated Union** | AgentEvent 事件类型 | Redux action、消息协议 |
| **Getter/Setter 保护** | tools/messages 复制 | 状态管理框架 |
| **泛型参数化** | AgentTool<TParameters, TDetails> | 库设计、API接口 |
| **继承扩展** | AgentTool extends Tool | 类库设计 |
| **枚举设计** | ThinkingLevel 6级 | 配置系统、模式选择 |

---

## 源文件映射

| 内容 | 源文件 | 行数 |
|------|--------|------|
| types.ts 核心类型 | `src/types.ts` | ~420 |
| harness/types.ts | `src/harness/types.ts` | ~300 |

---

## 下一步

→ [L03: Agent Loop 底层机制](./03-agent-loop)