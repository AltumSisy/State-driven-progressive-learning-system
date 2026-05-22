# @earendil-works/pi-agent-core 学习项目

## 项目概览

**包名**: `@earendil-works/pi-agent-core`  
**源码路径**: `.learning/agent-core-study/pi/agent/`  
**学习方法**: FastLearn (快速理解 → 实践验证)

## 三包架构

```
pi/
├── ai/              # @earendil-works/pi-ai (基础层)
│   └── Model, Message, streamSimple, validateToolArguments...
│
├── agent/           # @earendil-works/pi-agent-core (本次学习目标)
│   ├── types.ts     # AgentMessage, AgentTool, AgentEvent...
│   ├── agent.ts     # Agent 类
│   ├── agent-loop.ts # agentLoop 底层
│   └── harness/     # Harness 系统
│
└── coding-agent/    # 完整应用 (应用层)
    └── examples/    # 扩展示例
```

## 学习目录结构 (重构版 11 课)

```
agent-core-study/
├── 01-overview/          # 架构概览 + pi/ai 依赖
├── 02-core-types/        # 类型系统 (types.ts + harness/types.ts)
├── 03-agent-loop/        # Agent Loop 底层机制
├── 04-agent-class/       # Agent 类 (包装层)
├── 05-tool-system/       # 工具执行完整流程
├── 06-event-flow/        # 事件系统
├── 07-harness/           # Harness 基础
├── 08-session/           # Session 管理 (原 08-examples)
├── 09-compaction/        # 上下文压缩 (新增)
├── 10-proxy/             # Proxy 与浏览器支持 (新增)
├── 11-coding-agent/      # coding-agent 实例分析 (新增)
├── progress/             # 学习进度追踪
│   ├── learning-syllabus.md
│   ├── learning-state.json
│   ├── memory-store.json
│   ├── tracking.md
│   └── interview-deep-dive.md
├── pi/                   # 源代码目录
│   ├── agent/
│   ├── ai/
│   └── coding-agent/
└── README.md             # 本文件
```

## 学习顺序调整

原顺序问题：Agent 类在 Agent Loop 之前，但 Agent 内部调用 agentLoop

**新顺序**：
```
L01 → L02 → L03 → L04 → L05 → L06 → L07 → L08 → L09 → L10 → L11
架构 → 类型 → Loop → Agent → 工具 → 事件 → Harness → Session → 压缩 → Proxy → 实例
```

先底层 (agentLoop) 后包装层 (Agent 类)，理解更自然。

## 核心概念速览

### AgentMessage vs Message

```
AgentMessage[] (应用层) → transformContext → convertToLlm → Message[] (LLM)
```

### 事件流序列

```
agent_start → turn_start → message_* → turn_end → agent_end
                    ↓
            tool_execution_* (if tools)
```

### 工具执行模式

- **parallel** (默认): 预检顺序，执行并发
- **sequential**: 全部顺序执行

## 学习目标

1. 理解 Agent 架构和生命周期
2. 掌握事件流和消息处理
3. 学会定义和使用工具
4. 理解 Harness 系统
5. 能够基于该包构建应用

---

**开始时间**: 2026-05-22  
**学习方法**: FastLearn