# Agent 包完整学习大纲

## 概述

**目标**: 系统掌握 `@earendil-works/pi-agent-core` 包  
**版本**: 0.75.4  
**难度**: 中级到高级  
**预计时间**: 15-20 小时

---

## 第一阶段：基础概念 (入门)

### 1. 核心类型系统
- **AgentMessage** - 消息类型的联合类型（LLM 消息 + 自定义消息）
  - 声明合并扩展：`CustomAgentMessages` 接口
  - 标准角色：`user`, `assistant`, `toolResult`
  - 自定义角色：通过模块扩展
- **AgentTool** - 工具定义接口
  - `name`, `label`, `description`
  - `parameters`: TypeBox 模式
  - `execute()`: 执行函数签名
  - `executionMode`: 执行模式覆盖
- **AgentToolResult** - 工具执行结果
  - `content`: 返回给 LLM 的内容
  - `details`: 结构化详情
  - `terminate`: 终止提示
- **AgentContext** - 上下文快照
  - `systemPrompt`, `messages`, `tools`

### 2. Agent 生命周期
- **Agent 类的基本使用**
  - 构造函数：`AgentOptions`
  - `prompt()`: 启动对话（文本/消息/批量）
  - `continue()`: 继续对话（从当前上下文）
- **状态管理：AgentState**
  - 可变属性：`systemPrompt`, `model`, `thinkingLevel`
  - 数组属性：`tools`, `messages`（赋值时复制）
  - 只读状态：`isStreaming`, `streamingMessage`, `pendingToolCalls`, `errorMessage`
- **Agent 类 vs Agent Loop 对比**
  | 特性 | Agent 类 | agentLoop |
  |-----|---------|-----------|
  | 事件处理 | 等待订阅者完成 | 观察性流 |
  | 队列管理 | 内置 steering/follow-up | 通过配置钩子 |
  | 状态管理 | 自动管理 | 外部手动管理 |
  | 屏障行为 | `message_end` 是工具预检屏障 | 无屏障 |
  | 适用场景 | UI 应用 | 批处理/低级控制 |

### 3. 事件系统
- **AgentEvent 类型** - 完整事件体系
  - 生命周期：`agent_start`, `agent_end`
  - 回合事件：`turn_start`, `turn_end`
  - 消息事件：`message_start`, `message_update`, `message_end`
  - 工具事件：`tool_execution_start`, `tool_execution_update`, `tool_execution_end`
- **事件序列**
  ```
  prompt()
  ├─ agent_start
  ├─ turn_start
  ├─ message_start { user }
  ├─ message_end
  ├─ message_start { assistant }
  ├─ message_update { streaming }
  ├─ message_end
  ├─ tool_execution_* { if tools }
  ├─ turn_end
  └─ agent_end
  ```
- **订阅与取消**
  - `subscribe()`: 注册监听器
  - 返回值：取消订阅函数
  - `agent_end` 是最后屏障（等待监听器完成）

---

## 第二阶段：Agent Loop 深入

### 4. Agent Loop 机制
- **核心函数**
  - `agentLoop()`: 主循环，接受初始消息
  - `agentLoopContinue()`: 继续模式，不添加新消息
  - `runAgentLoop()` / `runAgentLoopContinue()`: Promise 包装
- **AgentLoopConfig 配置**
  - 必需：`model`, `convertToLlm`
  - 可选：`transformContext`, `getApiKey`
  - 钩子：`shouldStopAfterTurn`, `prepareNextTurn`
  - 队列：`getSteeringMessages`, `getFollowUpMessages`
- **消息队列**
  - `steer()`: 运行时注入消息（打断）
  - `followUp()`: 完成后继续
  - `QueueMode`: `"all"` vs `"one-at-a-time"`

### 5. 消息转换管道
- **消息流程**
  ```
  AgentMessage[] → transformContext() → AgentMessage[] → convertToLlm() → Message[] → LLM
  ```
- **transformContext**
  - 用途：上下文窗口管理、外部信息注入
  - 示例：pruneOldMessages, estimateTokens
- **convertToLlm**
  - 用途：过滤 UI 消息、转换自定义类型
  - 契约：必须返回有效 Message[]，不能抛出
- **默认值**
  - `defaultConvertToLlm`: 过滤保留 user/assistant/toolResult

### 6. 工具执行详解
- **工具调用流程**
  ```
  beforeToolCall → validate args → execute → afterToolCall → toolResult
  ```
- **参数验证**
  - `validateToolArguments`: TypeBox 静态验证
  - `prepareArguments`: 可选的预处理钩子
- **执行模式**
  - `sequential`: 顺序执行
  - `parallel`: 并发执行（默认）
  - 混合 batch：有 sequential 工具则全部顺序
- **Turn 控制钩子**
  - `shouldStopAfterTurn`: 决定是否停止循环
    - 在 `turn_end` 后调用
    - 返回 true 则跳过队列检查，直接 `agent_end`
  - `prepareNextTurn`: 准备下一回合
    - 可替换 context/model/thinkingLevel
    - 用于动态模型切换
- **终止机制**
  - 工具返回 `terminate: true`
  - 仅当 batch 中**所有**工具都返回 true 时生效
  - 可在 `execute()` 或 `afterToolCall` 中设置

---

## 第三阶段：Harness 层 (应用框架)

### 7. AgentHarness 基础
- **Harness 与 Agent 的区别**
  - Agent: 底层事件循环
  - Harness: 高级应用框架
  - 关系：Harness 包装 Agent，提供额外功能
- **AgentHarness 配置**
  - 资源系统：`AgentHarnessResources`
  - 执行环境：`ExecutionEnv`
  - 流选项：`AgentHarnessStreamOptions`
- **核心方法**
  - `prompt()`: 提示（增强版）
  - `skill()`: 执行技能
  - `promptFromTemplate()`: 从模板提示

### 8. 资源管理
- **Skill 接口**
  ```typescript
  interface Skill {
    name: string;
    description: string;
    tools: AgentTool[];
    // ...
  }
  ```
- **技能系统**
  - `Skills` 类：技能注册与管理
  - `loadFromDir()`: 从目录加载技能
  - `toTools()`: 转换为工具列表
- **PromptTemplate 模板系统**
  - 模板变量替换
  - 条件渲染
  - 嵌套模板

### 9. 会话系统 (Session)
- **Session 类**
  - 封装 Agent + 持久化
  - 自动保存/加载
  - 压缩管理
- **SessionTreeEntry 类型**
  - 会话树结构
  - 分支管理
  - 父子关系
- **上下文构建**
  - 从会话历史重建
  - 摘要注入
  - 系统提示管理

### 10. UUID 生成
- **uuidv7()**
  - 基于时间的 UUID
  - 用于会话 ID 生成
  - 字典序可排序

---

## 第四阶段：高级特性

### 11. Context Compaction (上下文压缩)
- **为什么需要 compaction**
  - 上下文窗口限制
  - Token 成本控制
  - 性能优化
- **compact() 函数**
  ```typescript
  const compacted = await compact(messages, {
    model,
    settings: compactionSettings,
  });
  ```
- **CompactionSettings 配置**
  - `threshold`: 压缩阈值
  - `reserveTokens`: 保留 Token 数
  - `summaryModel`: 摘要专用模型
- **Token 估算**
  - `estimateTokens()`: 粗略估算
  - `calculateContextTokens()`: 精确计算
- **保留策略**
  - `findCutPoint()`: 找到切割点
  - `findTurnStartIndex()`: 找到回合起点
  - 保留最近 N 回合完整历史

### 12. 分支管理 (Branch Summary)
- **分支总结函数**
  - `collectEntriesForBranchSummary()`: 收集条目
  - `prepareBranchEntries()`: 准备条目
  - `generateBranchSummary()`: 生成分支摘要
- **navigateTree()**
  - 会话树导航
  - 跳转到指定节点
  - 重建历史路径
- **时间旅行式管理**
  - 创建分支
  - 切换分支
  - 合并分支

### 13. Hook 系统
- **会话生命周期钩子**
  - `before_agent_start`
  - `session_before_compact`
  - `session_before_tree`
- **消息处理钩子**
  - `tool_call`: 工具调用时
  - `tool_result`: 工具结果时
  - `context`: 上下文转换
- **Agent 级钩子**
  - `beforeToolCall`
  - `afterToolCall`

---

## 第五阶段：存储与持久化

### 14. 存储实现
- **SessionStorage 接口**
  - `load()`: 加载会话
  - `save()`: 保存会话
  - `delete()`: 删除会话
  - `list()`: 列会话
- **JsonlSessionStorage**
  - JSON Lines 格式
  - 追加写入优化
  - 压缩支持
- **MemorySessionStorage**
  - 内存存储
  - 测试使用
  - 临时会话
- **SessionRepo 仓库模式**
  - 抽象存储层
  - 事务支持
  - 版本管理

### 15. 执行环境
- **ExecutionEnv 接口**
  ```typescript
  interface ExecutionEnv {
    fs: FileSystem;
    shell: Shell;
    // ...
  }
  ```
- **FileSystem 抽象**
  - `readFile()`, `writeFile()`
  - `readdir()`, `stat()`
  - `exists()`, `mkdir()`
  - Node.js 实现：`src/harness/env/nodejs.ts`
- **Shell 抽象**
  - `execute()`: 命令执行
  - `spawn()`: 流式执行
  - 工作目录管理
  - 环境变量支持
- **Node.js 实现**
  - 基于 `fs/promises`
  - 基于 `child_process`

---

## 第六阶段：扩展与定制

### 16. 自定义消息类型
- **CustomAgentMessages 接口扩展**
  ```typescript
  declare module "@earendil-works/pi-agent-core" {
    interface CustomAgentMessages {
      notification: NotificationMessage;
      artifact: ArtifactMessage;
    }
  }
  ```
- **声明合并模式**
  - TypeScript 模块扩展
  - 类型安全保证
  - 运行时过滤
- **convertToLlm 处理**
  - 过滤自定义消息
  - 转换为 LLM 兼容格式

### 17. Proxy 支持
- **streamProxy()**
  - 浏览器代理后端
  - 认证 Token 传递
  - 自定义代理 URL
- **使用场景**
  - 前端应用
  - 认证代理
  - 跨域请求

### 18. 流选项与传输
- **AgentHarnessStreamOptions**
  - `sessionId`: 缓存标识
  - `thinkingBudgets`: 思考预算
  - `transport`: 传输方式
  - `maxRetryDelayMs`: 重试策略
- **Transport 配置**
  - `"auto"`: 自动选择
  - `"http"`: HTTP 传输
  - 自定义传输
- **缓存策略**
  - Provider 缓存
  - 会话级缓存
  - Prompt 缓存

### 19. 错误处理
- **错误类型体系**
  - `AgentHarnessError`: Harness 级错误
  - `SessionError`: 会话错误
  - `CompactionError`: 压缩错误
  - `ToolExecutionError`: 工具执行错误
- **错误代码**
  - `SESSION_NOT_FOUND`
  - `COMPACTION_FAILED`
  - `TOOL_BLOCKED`
  - `INVALID_ARGUMENTS`
- **Result<T, E> 模式**
  - 函数式错误处理
  - 显式错误传播
  - 类型安全

---

## 第七阶段：测试与调试

### 20. 测试策略
- **Vitest 配置**
  - `vitest.config.ts`: 单元测试
  - `vitest.harness.config.ts`: Harness 集成测试
- **测试工具**
  - `test/harness/session-test-utils.ts`
  - 模拟 SessionStorage
  - 测试数据生成
- **模拟和存根模式**
  - Mock 模型响应
  - 模拟工具执行
  - 事件流断言
- **测试用例类型**
  - Agent Loop 测试
  - Harness 集成测试
  - Session 持久化测试
  - Compaction 测试

### 21. 调试技巧
- **事件流调试**
  - 订阅所有事件并打印
  - 事件序列验证
- **状态检查**
  - `agent.state.isStreaming`
  - `agent.state.pendingToolCalls`
- **日志记录**
  - Hook 中插入日志
  - 自定义 onPayload 回调

---

## 第八阶段：完整应用开发

### 22. CLI 应用
- 命令行交互
- 会话持久化
- 文件操作工具

### 23. Web 应用
- 前端代理
- 流式响应
- 会话管理

### 24. VS Code 扩展
- 编辑器集成
- 工作区工具
- 状态管理

---

## 学习路径建议

### 推荐顺序

1. **入口文件** (`src/index.ts`) - 了解整体导出结构
2. **类型定义** (`src/types.ts`) - 核心概念
3. **Agent 类** (`src/agent.ts`) - 高级 API
4. **Agent Loop** (`src/agent-loop.ts`) - 底层机制
5. **测试文件** (`test/`) - 实际用法
6. **Harness** (`src/harness/`) - 应用框架
   - `agent-harness.ts`
   - `session/session.ts`
   - `compaction/compaction.ts`
   - `compaction/branch-summarization.ts`
   - `env/nodejs.ts`
7. **Proxy** (`src/proxy.ts`) - 浏览器支持

### 实践项目

1. **简单计算器** - 基础 Agent + 工具
2. **文件助手** - 使用文件系统工具
3. **会话管理器** - 使用 Session 和存储
4. **分支聊天** - 使用分支总结功能
5. **完整应用** - 集成所有功能

---

## 参考文档

- `README.md` - 官方文档
- `docs/durable-harness.md` - 持久化 Harness
- `docs/hooks.md` - Hook 系统
- `docs/observability.md` - 可观测性

---

**总知识点数**: 约 24 个主要领域  
**代码行数**: ~5000+ 行  
**学习时间**: 15-20 小时（基础）+ 10 小时（实践）
