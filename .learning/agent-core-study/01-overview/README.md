# L01: 架构概览 + pi/ai 依赖

---

## 1. 心智模型构建

### 1.1 背景

#### 历史演进

```
早期 AI 应用:
├─ 直接调用 LLM API (curl, openai SDK)
├─ 单次请求-响应，无状态
├─ 工具调用手动处理
└─ 无法处理长对话、复杂任务

→ 状态管理需求出现

中期框架:
├─ LangChain: 链式调用，但粒度粗糙
├─ AutoGPT: 自主 Agent，但难以控制
├─ 各家自建框架，不互通
└─ 重复造轮子

→ 需要通用、可复用的 Agent 核心
```

#### pi-agent-core 的诞生

**作者**: Mario Zechner (pi 框架作者)

**定位**: 
- 不是完整应用，而是 **Agent 核心引擎**
- 提供可复用的状态管理、工具执行、事件流
- 构建于 `pi-ai` (LLM Provider 抽象) 之上

#### 三包架构

| 包 | 层次 | 职责 |
|---|------|------|
| `pi-ai` | 基础层 | LLM Provider 抽象、流式处理、模型注册 |
| `pi-agent-core` | 核心层 | Agent 状态、工具执行、事件流、Harness |
| `pi-coding-agent` | 应用层 | 完整的编码助手应用 |

---

### 1.2 目标

#### 核心痛点

| 痛点 | 具体问题 |
|------|---------|
| 状态管理 | 每次调用需手动管理 messages、tools |
| 工具执行 | 并发/顺序执行复杂，错误处理混乱 |
| 事件流 | UI 需要知道进度，但没有统一事件 |
| 上下文限制 | Token 超限，需要压缩，但逻辑复杂 |
| 会话持久化 | 对话历史保存/恢复，分支管理 |

#### 期望效果

```typescript
// 期望：简单几行代码构建 Agent

const agent = new Agent({
  initialState: {
    systemPrompt: "You are helpful.",
    model: getModel("anthropic", "claude-sonnet-4-20250514"),
  },
});

agent.subscribe((event) => {
  if (event.type === "message_update") {
    ui.update(event.delta);
  }
});

await agent.prompt("Hello!");
```

---

### 1.3 专家视角 - 概念网络

```
核心概念关系图：

     pi-ai (基础层)
         │
         │ 提供: Model, Message, streamSimple, Tool
         ▼
  ┌──────────────────┐
  │ AgentMessage     │ ← 可扩展消息类型 (声明合并)
  │ AgentTool        │ ← 工具定义 (TypeBox + execute)
  │ AgentEvent       │ ← 事件流 (10种事件类型)
  │ AgentState       │ ← 状态管理 (可变 + 只读)
  └──────────────────┘
         │
         │ 组合形成
         ▼
  ┌──────────────────┐
  │ AgentContext     │ ← 上下文快照 (prompt + messages + tools)
  │ AgentLoopConfig  │ ← 配置 (hooks + queues + convert)
  └──────────────────┘
         │
         │ 驱动
         ▼
  ┌──────────────────┐
  │ agentLoop        │ ← 底层循环 (生成事件流，不等待)
  │ Agent 类         │ ← 包装层 (等待订阅者完成)
  │ AgentHarness     │ ← 应用框架 (Session + Skills + Compaction)
  └──────────────────┘
```

#### 核心概念定义

| 概念 | 定义 | 来源 |
|------|------|------|
| AgentMessage | LLM标准消息 + 自定义消息的联合类型 | `types.ts:309` |
| AgentContext | 系统提示 + 消息历史 + 工具列表的快照 | `types.ts:387` |
| AgentLoopConfig | 模型 + 转换函数 + 钩子 + 队列的配置 | `types.ts:135` |
| AgentEvent | 生命周期事件的联合类型 (10种) | `types.ts:403` |

---

## 2. 结构化学习 (SQ3R)

### 2.1 Survey - 核心架构概览

```
Application Layer
┌─────────────────────────────────────────────────────────┐
│  Agent Class (高级 API)                                 │
│  ├─ 状态管理: MutableAgentState                         │
│  ├─ 队列: Steering + Follow-up                          │
│  ├─ subscribe(): 等待监听器完成                         │
│                                                          │
│  agentLoop (低级 API)                                   │
│  ├─ EventStream: 观察性流                               │
│  ├─ 无状态管理                                          │
│                                                          │
│  AgentHarness (应用框架)                                │
│  ├─ Session 持久化                                      │
│  ├─ Skills 技能管理                                     │
│  ├─ Compaction 压缩                                     │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  AgentEvent Stream                                       │
│  agent_start → turn_start → message_* → turn_end        │
│                      ↓                                   │
│         tool_execution_* (if tools called)              │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  @earendil-works/pi-ai (LLM Provider)                   │
│  Model, Message, streamSimple, validateToolArguments    │
└─────────────────────────────────────────────────────────┘
```

### 2.2 Question - 关键问题驱动

学习本课后，应能回答：

**Q1**: 为什么需要 AgentMessage 和 Message 两层抽象？
**Q2**: convertToLlm 函数为什么不能抛异常？
**Q3**: Agent 类和 agentLoop 的核心区别是什么？
**Q4**: pi-ai 包提供了哪些 agent 核心依赖的类型？

### 2.3 Read - 源代码映射

| 内容 | 源文件 | 行数范围 |
|------|--------|---------|
| AgentMessage 定义 | `types.ts` | L300-309 |
| CustomAgentMessages | `types.ts` | L300-302 |
| AgentContext 定义 | `types.ts` | L387-394 |
| AgentLoopConfig | `types.ts` | L135-277 |
| AgentEvent 定义 | `types.ts` | L403-418 |
| defaultConvertToLlm | `agent.ts` | L31-35 |
| Agent 类结构 | `agent.ts` | L166-219 |
| 导出汇总 | `index.ts` | L1-45 |

### 2.4 Recite - 使用模板

#### 基础使用模板

```typescript
import { Agent } from "@earendil-works/pi-agent-core";
import { getModel } from "@earendil-works/pi-ai";

const agent = new Agent({
  initialState: {
    systemPrompt: "You are a helpful assistant.",
    model: getModel("anthropic", "claude-sonnet-4-20250514"),
  },
});

agent.subscribe((event) => {
  if (event.type === "message_update" && 
      event.assistantMessageEvent.type === "text_delta") {
    process.stdout.write(event.assistantMessageEvent.delta);
  }
});

await agent.prompt("Hello!");
```

#### 自定义消息类型模板

```typescript
// 1. 声明合并扩展
declare module "@earendil-works/pi-agent-core" {
  interface CustomAgentMessages {
    notification: { role: "notification"; text: string; timestamp: number };
  }
}

// 2. convertToLlm 处理
const agent = new Agent({
  convertToLlm: (messages) => messages.flatMap(m => {
    if (m.role === "notification") return [];  // 过滤 UI-only
    return [m];
  }),
});

// 3. 使用自定义消息
agent.state.messages.push({
  role: "notification",
  text: "System update",
  timestamp: Date.now(),
});
```

### 2.5 Review - TODO清单 (渐进式披露)

> 📋 **渐进式学习**: 一次只显示一个TODO，完成后才解锁下一个。

#### 🔴 TODO-1: 理解概念网络 (当前激活)

**完成检查**:
- [ ] 列举 pi-ai 提供给 agent 的 5 个以上核心类型
- [ ] 画出 AgentMessage → Message 的转换流程

<details>
<summary>💡 提示</summary>

pi-ai 提供的核心类型:
- Model, Message, streamSimple
- Tool, validateToolArguments
- AssistantMessage, UserMessage, ToolResultMessage
- TextContent, ImageContent

转换流程: AgentMessage[] → convertToLlm → Message[] → LLM API
</details>

---

#### 🟡 TODO-2: 理解双层抽象 (待解锁)

**前置要求**: 完成 TODO-1

**完成检查**:
- [ ] 解释为什么需要 AgentMessage 和 Message 两层
- [ ] 写出声明合并扩展语法

---

#### 🟡 TODO-3: 理解契约 (待解锁)

**前置要求**: 完成 TODO-2

**完成检查**:
- [ ] 解释 convertToLlm 不能抛异常的原因

---

## 📝 费曼检验 (必须完成)

在继续下一课之前，请用自己的话解释：

### 问题 1: 三层架构
> "请解释 pi-ai → pi-agent-core → pi-coding-agent 三层各自职责，为什么需要分层？"

你的解释：_______________________________________________

### 问题 2: 双层抽象
> "为什么需要 AgentMessage 和 Message 两层抽象？直接用一种消息格式有什么问题？"

你的解释：_______________________________________________

<details>
<summary>✅ 检查你的理解</summary>

**问题 1 参考答案**:
- pi-ai: LLM Provider 抽象，不关心 Agent 逻辑
- pi-agent-core: Agent 核心引擎，状态、事件、工具执行
- pi-coding-agent: 完整应用，TUI、扩展、技能
- 分层：每层只解决自己的问题，可复用、可测试、可维护

**问题 2 参考答案**:
- AgentMessage: 应用层可扩展（支持自定义消息类型）
- Message: LLM 标准消息格式
- 分离原因：应用需要灵活扩展，LLM 需要标准格式
- 转换通过 convertToLlm 完成
</details>

---

## 3. 对抗性测试

### 3.1 边界问题

#### convertToLlm 契约

```typescript
// ❌ 错误：抛异常会中断 agentLoop
convertToLlm: (messages) => {
  if (invalid(messages)) throw new Error("Invalid");
  return messages;
}

// ✅ 正确：返回安全回退值
convertToLlm: (messages) => {
  if (invalid(messages)) return [];
  return messages;
}
```

**契约**: 必须返回有效 `Message[]`，不能抛异常或 reject。

#### transformContext 契约

```typescript
// ✅ 正确实现
transformContext: async (messages, signal) => {
  if (signal?.aborted) return messages;  // 尊重中止信号
  try {
    return await pruneMessages(messages);
  } catch {
    return messages;  // 失败时返回原消息
  }
}
```

### 3.2 反事实推理

**情境 1**: 如果 convertToLlm 返回空数组？
```typescript
convertToLlm: () => []
// 结果：LLM 收到空消息，可能报错或返回默认响应
// 教训：必须保证至少有一条有效消息
```

**情境 2**: 如果运行时修改 state.messages？
```typescript
// Agent 运行中
agent.state.messages.push(newMessage);
// 结果：不影响当前运行（上下文已创建快照）
// 教训：修改在下一个 prompt/continue 才生效
```

**情境 3**: 如果没有 subscribe 监听器？
```typescript
const agent = new Agent({...});
// 不订阅，直接 await agent.prompt("Hello");
// 结果：正常工作，事件流发出但无处理
// 教训：不订阅也能用，但无法追踪进度
```

### 3.3 漏洞注入 - 常见错误

| 错误类型 | 示例 | 后果 | 修复 |
|---------|------|------|------|
| convertToLlm 抛异常 | `throw new Error()` | 中断循环，事件序列不完整 | 返回 `[]` |
| 未过滤自定义消息 | 发送 `notification` 给 LLM | API 报错 400 | 在 convertToLlm 过滤 |
| 忽略中止信号 | 不检查 `signal?.aborted` | 无法取消操作 | 检查并提前返回 |
| 循环中修改 messages | `agent.prompt()` 时修改 | 状态不一致 | 用 steer/followUp |

---

## 4. 思想与迁移

### 4.1 设计哲学

#### 分层抽象

```
pi-ai:      LLM Provider 抽象 (不关心 Agent 逻辑)
pi-agent:   Agent 核心抽象 (不关心具体应用)
pi-coding:  应用层 (使用 agent + ai)
```

**原则**: 每层只解决自己的问题，不越界。

#### 契约优于配置

```typescript
// 契约：函数签名和返回值承诺
convertToLlm: (messages) => Message[] | Promise<Message[]>
// 契约：不能抛异常，必须返回有效值

// 不是硬编码检查，而是依赖调用者遵守契约
```

**原则**: 信任调用者，明确契约边界，不做防御性编程。

#### 事件流而非回调

```typescript
// 回调模式 (旧)
llm.call(prompt, {
  onText: (text) => ui.update(text),
  onComplete: (result) => save(result),
});

// 事件流模式 (新)
agent.subscribe((event) => {
  if (event.type === "message_update") ui.update(...);
  if (event.type === "agent_end") save(...);
});
```

**优势**: 单一订阅点、事件顺序有保证、多个监听器。

#### 声明合并扩展

```typescript
// TypeScript 特性，不修改原代码
declare module "@earendil-works/pi-agent-core" {
  interface CustomAgentMessages {
    // 应用自定义
  }
}
```

**原则**: 开放扩展，封闭修改。

### 4.2 可迁移思维

| 思想 | agent-core 应用 | 可迁移领域 |
|------|----------------|-----------|
| **分层抽象** | ai → agent → app | 任何复杂系统 |
| **契约优于配置** | convertToLlm 不抛异常 | API/接口设计 |
| **事件流模式** | Agent.subscribe | UI框架、消息系统 |
| **声明合并扩展** | CustomAgentMessages | TypeScript插件 |
| **可观察性分层** | agentLoop(观察) vs Agent(控制) | 流处理、状态机 |

---

## 源文件映射

| 学习内容 | 源文件 | 行数 |
|---------|--------|------|
| 三包架构 | 目录结构 | - |
| pi/ai 导入 | `types.ts:1-13` | 13 |
| agent 导出 | `index.ts:1-45` | 45 |
| CustomAgentMessages | `types.ts:300-302` | 3 |
| AgentMessage | `types.ts:309` | 1 |
| AgentLoopConfig.convertToLlm | `types.ts:163-164` | 2 |
| defaultConvertToLlm | `agent.ts:31-35` | 5 |

---

## 下一步

→ [L02: 类型系统](./02-core-types)