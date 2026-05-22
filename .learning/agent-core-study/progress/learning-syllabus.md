# Agent Core 学习大纲 (重构版)

## 概述

**目标包**: `@earendil-works/pi-agent-core`  
**版本**: 基于 `.learning/agent-core-study/pi/agent/` 源码  
**学习方法**: FastLearn (快速理解 → 实践验证)

## 课程结构 (11 课)

### L01: 架构概览 + pi/ai 依赖
**核心内容**:
- 三包架构: agent / ai / coding-agent
- agent 包的导出结构 (`index.ts`)
- pi/ai 提供的基础类型: Model, Message, streamSimple, Tool, validateToolArguments

**源文件**: `src/index.ts`, `pi/ai/src/` (浏览)

---

### L02: 类型系统 (合并)
**核心内容**:
- `types.ts`: AgentMessage, AgentState, AgentTool, AgentEvent, AgentContext, AgentLoopConfig
- `harness/types.ts`: Skill, PromptTemplate, Session, AgentHarnessEvent, ExecutionEnv

**源文件**: `src/types.ts` (420行), `src/harness/types.ts` (~300行)

---

### L03: Agent Loop 底层机制
**核心内容**:
- `agentLoop()` / `agentLoopContinue()` 函数签名
- `runLoop()` 主循环逻辑
- `streamAssistantResponse()` - LLM 调用边界
- `executeToolCalls()` - 并行/顺序执行

**源文件**: `src/agent-loop.ts` (740行)

---

### L04: Agent 类 (包装层)
**核心内容**:
- Agent 构造函数和 AgentOptions
- 状态管理: MutableAgentState, getter/setter 复制
- prompt() / continue() / reset() 方法
- Steering/Follow-up 队列 (PendingMessageQueue)
- subscribe() 和 processEvents()

**源文件**: `src/agent.ts` (560行)

---

### L05: 工具执行完整流程
**核心内容**:
- AgentTool 定义
- 参数验证: prepareArguments + validateToolArguments
- beforeToolCall / afterToolCall 钩子
- executeToolCallsSequential / executeToolCallsParallel
- AgentToolResult 和 terminate 机制

**源文件**: `types.ts` (AgentTool), `agent-loop.ts` (第373-742行)

---

### L06: 事件系统
**核心内容**:
- AgentEvent 类型定义
- processEvents() 状态更新逻辑
- subscribe() 监听器机制
- agent_end 屏障行为

**源文件**: `types.ts` (AgentEvent), `agent.ts` (第509-556行)

---

### L07: Harness 基础
**核心内容**:
- AgentHarness 类结构
- AgentHarnessResources (skills, promptTemplates)
- ExecutionEnv (fs, shell)
- prompt() / skill() / promptFromTemplate()
- Steering/Follow-up/NextTurn 队列管理

**源文件**: `src/harness/agent-harness.ts` (前半部分)

---

### L08: Session 管理
**核心内容**:
- Session 类
- SessionStorage 接口: jsonl-storage, memory-storage
- SessionRepo: jsonl-repo, memory-repo
- uuidv7() 时间排序 UUID

**源文件**: `src/harness/session/` 目录

---

### L09: 上下文压缩
**核心内容**:
- compact() 函数
- prepareCompaction() / shouldCompact()
- estimateTokens() / calculateContextTokens()
- findCutPoint() / findTurnStartIndex()
- Branch Summary: collectEntriesForBranchSummary, generateBranchSummary

**源文件**: `src/harness/compaction/` 目录

---

### L10: Proxy 与浏览器支持
**核心内容**:
- streamProxy() 函数
- 浏览器代理后端配置
- 认证 Token 传递
- node.ts Node.js 特定导出

**源文件**: `src/proxy.ts`, `src/node.ts`

---

### L11: coding-agent 实例分析
**核心内容**:
- `examples/extensions/handoff.ts` - Agent Handoff
- `examples/extensions/permission-gate.ts` - HITL 权限
- `examples/extensions/plan-mode/` - PlanAct 模式
- `examples/extensions/custom-provider-anthropic/` - 自定义 Provider
- `examples/extensions/git-checkpoint.ts` - 状态保存

**源文件**: `pi/coding-agent/examples/extensions/` 目录

---

## 学习顺序调整说明

原顺序问题:
- 03(Agent类) → 04(Agent Loop) 但 Agent 内部调用 agentLoop

新顺序优势:
- 先底层(agentLoop)后包装层(Agent类)，理解更自然

---

## 预计时间

- 每课: 30-60 分钟 (FastLearn 模式)
- 总计: 6-11 小时