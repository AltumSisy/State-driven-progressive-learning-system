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
├── 04-agent-class/       # Agent 类 (包装层) ⭐ 新增
├── 05-tool-system/       # 工具执行完整流程
├── 06-event-flow/        # 事件系统
├── 07-harness-base/      # Harness 基础
├── 08-session/           # Session 管理
├── 09-compaction/        # 上下文压缩
├── 10-proxy/             # Proxy 与浏览器支持
├── 11-coding-agent/      # coding-agent 实例分析
├── skills/               # 学习方法 skill 文件 ⭐ 新增
│   ├── method1-mental-model.skill.md
│   ├── method2-sq3r.skill.md
│   └── method3-adversarial-testing.skill.md
├── progress/             # 学习进度追踪
│   ├── learning-syllabus.md
│   ├── learning-state.json
│   ├── tracking.md
│   └── interview-deep-dive.md
├── pi/                   # 源代码目录
│   ├── agent/
│   ├── ai/
│   └── coding-agent/
└── README.md             # 本文件
```

## 课程设计原则

基于 **Progressive Learning Coach** 准则，每课包含：

1. **方法1**: 心智模型建构 - 建立正确的心智模型
2. **方法2**: 结构化学习 (SQ3R) - Survey/Question/Read/Recite/Review
3. **方法3**: 对抗测试 - 边界问题、反事实推理、漏洞注入
4. **渐进式披露**: 一次只显示一个TODO，完成后解锁下一个
5. **费曼检验**: 必须用自己的话复述核心概念

## 学习方法技能

- **[方法1: 心智模型建构](skills/method1-mental-model.skill.md)** - 建立专家级思维框架
- **[方法2: 结构化学习 SQ3R](skills/method2-sq3r.skill.md)** - 系统化掌握知识
- **[方法3: 对抗测试](skills/method3-adversarial-testing.skill.md)** - 暴露理解盲区

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