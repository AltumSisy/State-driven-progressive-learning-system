# AgentSession 核心

## 学习目标

深入理解 AgentSession 这个核心抽象类，它是所有运行模式共享的基础。

## 核心源文件

- **主要文件**: `agent-session.ts` (3086行) - 核心实现
- **运行时**: `agent-session-runtime.ts` - 运行时工厂
- **服务层**: `agent-session-services.ts` - 服务抽象

## 关键概念

### 1. AgentSession 的职责

AgentSession 封装了：
- Agent 状态访问
- 事件订阅与会话持久化
- 模型和思维级别管理
- 压缩（手动和自动）
- Bash 执行
- 会话切换和分支

### 2. 核心属性

```typescript
class AgentSession {
  readonly agent: Agent;              // 核心 Agent 实例
  readonly sessionManager: SessionManager;   // 会话管理器
  readonly settingsManager: SettingsManager; // 设置管理器
  readonly modelRegistry: ModelRegistry;     // 模型注册表
  
  // 状态访问
  get state(): AgentState;
  get model(): Model | undefined;
  get thinkingLevel(): ThinkingLevel;
  get isStreaming(): boolean;
  get systemPrompt(): string;
}
```

### 3. 事件系统

**AgentSessionEvent 类型**:
- `agent_start` / `agent_end` - Agent 开始/结束
- `message_start` / `message_end` - 消息开始/结束
- `turn_start` / `turn_end` - Turn 开始/结束
- `tool_execution_start` / `tool_execution_end` - 工具执行
- `compaction_start` / `compaction_end` - 压缩事件
- `auto_retry_start` / `auto_retry_end` - 自动重试
- `queue_update` - 消息队列更新

### 4. 消息队列系统

三种消息传递模式：
- **steer()** - 中断式消息，立即插入
- **followUp()** - 后续式消息，等待执行完成
- **pendingNextTurn** - 下轮消息，作为上下文注入

### 5. 自动压缩机制

压缩触发条件：
- **overflow** - LLM 返回上下文溢出错误
- **threshold** - 上下文超过阈值

压缩流程：
1. 检查是否需要压缩
2. 准备压缩数据
3. LLM 生成摘要
4. 更新会话状态
5. 自动重试（overflow 情况）

### 6. 自动重试机制

重试条件：
- 过载错误 (overloaded)
- 速率限制 (rate limit)
- 服务器错误 (500, 502, 503, 504)
- 网络错误

重试策略：
- 指数退避
- 最大重试次数限制
- 可中止

### 7. 扩展系统集成

AgentSession 提供扩展集成点：
- `bindExtensions()` - 绑定扩展
- `ExtensionRunner` - 扩展运行器
- 工具注册/注销
- 命令系统
- 事件钩子

## 重点阅读章节

### agent-session.ts 分段阅读建议

1. **第 1-240 行** - 类型定义和接口
   - AgentSessionEvent
   - AgentSessionConfig
   - PromptOptions

2. **第 241-342 行** - 构造函数和初始化
   - 如何初始化 AgentSession
   - 工具钩子安装

3. **第 343-717 行** - 事件订阅系统
   - _handleAgentEvent 内部处理
   - subscribe/dispose API

4. **第 718-811 行** - 状态访问
   - 各种 getter 属性

5. **第 912-1111 行** - prompt() 方法
   - 如何发送用户提示
   - 消息队列处理
   - 扩展拦截

6. **第 1610-2026 行** - 压缩系统
   - compact() 手动压缩
   - _checkCompaction() 自动压缩检查
   - _runAutoCompaction() 执行压缩

7. **第 2422-2521 行** - 自动重试
   - _isRetryableError()
   - _prepareRetry()

8. **第 2343-2395 行** - 运行时构建
   - _buildRuntime()
   - 工具注册刷新

## 学习建议

1. **先读构造函数**理解初始化流程
2. **重点读 prompt() 方法**理解消息处理
3. **理解事件系统**它是连接所有组件的纽带
4. **深入压缩机制**这是上下文管理的关键
5. **理解扩展集成**这是架构扩展性的核心

## 关键设计模式

### 事件转发模式
AgentSession 订阅 Agent 事件，然后：
1. 发送给扩展系统
2. 发送给用户监听器
3. 执行内部处理（如会话持久化）

### 工具注册模式
Definition-first 的工具管理：
- 工具定义优先
- 从定义生成工具实例
- 工具包装器适配扩展

### 状态同步模式
AgentState、SessionManager、SettingsManager 三层状态：
- AgentState：运行时状态
- SessionManager：持久化状态
- SettingsManager：用户配置