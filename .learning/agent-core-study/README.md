# @earendil-works/pi-agent-core 学习项目

## 项目概览

**包名**: `@earendil-works/pi-agent-core`  
**版本**: 0.75.4  
**作者**: Mario Zechner  
**路径**: `.learning/pi/packages/agent`

## 核心定位

这是一个通用 AI Agent 核心库，提供：
- 传输抽象（Transport abstraction）
- 状态管理（State management）
- 附件支持（Attachment support）
- 工具执行（Tool execution）
- 事件流（Event streaming）

构建于 `@earendil-works/pi-ai` 之上。

## 学习目录结构

```
agent-core-study/
├── 01-overview/          # 架构概览和快速开始
├── 02-core-types/        # 核心类型系统
├── 03-agent-class/       # Agent 类深入分析
├── 04-agent-loop/        # Agent 循环机制
├── 05-tool-system/       # 工具系统
├── 06-event-flow/        # 事件流和消息流
├── 07-harness/           # Harness 系统（会话、压缩等）
├── 08-examples/          # 代码示例和实践
├── progress/             # 学习进度追踪
└── README.md             # 本文件
```

## 核心概念速览

### AgentMessage vs LLM Message

```
AgentMessage[] → transformContext() → AgentMessage[] → convertToLlm() → Message[] → LLM
```

### 事件流序列 (prompt())

```
prompt("Hello")
├─ agent_start
├─ turn_start
├─ message_start   { message: userMessage }
├─ message_end
├─ message_start   { message: assistantMessage }
├─ message_update  { message: partial... }
├─ message_end
├─ turn_end        { message, toolResults: [] }
└─ agent_end       { messages: [...] }
```

### 工具执行模式

- **parallel** (默认): 预检顺序执行，允许的工具并发执行
- **sequential**: 顺序执行，历史兼容模式

## 关键文件映射

| 学习主题 | 源文件路径 |
|---------|-----------|
| 类型定义 | `src/types.ts` |
| Agent 类 | `src/agent.ts` |
| Agent 循环 | `src/agent-loop.ts` |
| 代理功能 | `src/proxy.ts` |
| Harness | `src/harness/` |
| 会话管理 | `src/harness/session/` |
| 上下文压缩 | `src/harness/compaction/` |

## 学习目标

1. 理解 Agent 架构和生命周期
2. 掌握事件流和消息处理
3. 学会定义和使用工具
4. 理解 Harness 系统（会话、压缩、状态）
5. 能够基于该包构建应用

## 学习进度

- [ ] 01: 架构概览
- [ ] 02: 核心类型
- [ ] 03: Agent 类
- [ ] 04: Agent 循环
- [ ] 05: 工具系统
- [ ] 06: 事件流
- [ ] 07: Harness 系统
- [ ] 08: 实践示例

---

**开始时间**: 2026-05-22  
**学习方法**: Method 4 - FastLearn (快速理解 → 实践验证)
