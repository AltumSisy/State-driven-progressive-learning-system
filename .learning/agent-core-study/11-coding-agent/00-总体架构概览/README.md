# 总体架构概览

## Coding Agent Core 架构总览

### 核心设计理念

Coding Agent 的 Core 模块是所有运行模式（interactive、print、rpc）共享的核心抽象层，采用了**会话驱动**的设计模式。

### 架构分层

```
┌─────────────────────────────────────────┐
│         应用层（Modes）                   │
│  interactive / print / rpc               │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│         AgentSession（核心抽象）          │
│  - 会话生命周期管理                        │
│  - 事件订阅机制                           │
│  - 扩展系统集成                           │
│  - 自动压缩与重试                         │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│      基础设施层（Infrastructure）         │
│  - Tools（工具系统）                      │
│  - Extensions（扩展系统）                 │
│  - SessionManager（会话持久化）           │
│  - ModelRegistry（模型注册）              │
│  - Compaction（上下文压缩）               │
└─────────────────────────────────────────┘
```

### 核心模块关系图

```
AgentSession
    ├── Agent（来自 pi-agent-core）
    ├── SessionManager
    ├── SettingsManager
    ├── ModelRegistry
    ├── ResourceLoader
    ├── ExtensionRunner
    ├── ToolRegistry
    └── Compaction
```

### 关键设计模式

1. **事件驱动架构** - 通过事件总线连接各组件
2. **扩展点设计** - 工具、命令、钩子都可扩展
3. **会话持久化** - 所有状态变更记录到 session 文件
4. **上下文压缩** - 自动管理对话上下文长度
5. **工具注册机制** - Definition-first 的工具管理

### 学习路径

按照编号顺序学习，从 01 开始逐步深入：

1. **01-AgentSession核心** - 理解核心抽象（最重要）
2. **02-会话管理** - 理解会话持久化机制
3. **03-工具系统** - 理解工具定义和执行
4. **05-扩展系统** - 理解扩展架构
5. **06-压缩系统** - 理解上下文管理
6. 其他模块按需学习

### 关键源文件位置

所有源文件位于：
```
.learning/agent-core-study/pi/coding-agent/src/core/
```

### 核心类型体系

- `AgentSession` - 会话核心类
- `SessionManager` - 会话持久化管理器
- `ExtensionRunner` - 扩展运行器
- `ToolDefinition` - 工具定义接口
- `CompactionEntry` - 压缩条目类型
- `ModelRegistry` - 模型注册表

### 建议阅读顺序

1. 先读 `core/index.ts` 了解导出的公共 API
2. 读 `agent-session.ts` 理解核心会话逻辑
3. 读 `tools/index.ts` 理解工具系统架构
4. 读 `extensions/index.ts` 理解扩展系统
5. 逐步深入各子系统细节