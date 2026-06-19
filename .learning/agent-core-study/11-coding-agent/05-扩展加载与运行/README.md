# 扩展加载与运行

## 学习目标

理解 Coding Agent 的扩展系统架构，掌握扩展的生命周期、事件处理和工具注册机制。

## 核心源文件

- `extensions/index.ts` - 扩展系统入口
- `extensions/types.ts` - 类型定义（核心）
- `extensions/loader.ts` - 扩展加载器
- `extensions/runner.ts` - 扩展运行器（核心）
- `extensions/wrapper.ts` - 工具包装器

## 关键概念

### 1. Extension 类型体系

**Extension 接口**（extensions/types.ts）:
```typescript
interface Extension {
  path: string;              // 扩展路径
  factory: ExtensionFactory; // 扩展工厂函数
  sourceInfo: SourceInfo;    // 来源信息
  flags?: ExtensionFlag[];   // 扩展标记
}
```

**ExtensionFactory**:
```typescript
type ExtensionFactory = (
  context: ExtensionContext
) => ExtensionHandler | Promise<ExtensionHandler>;
```

**ExtensionHandler**:
```typescript
interface ExtensionHandler {
  // 事件处理
  'agent_start'?: (event) => Promise<void>;
  'agent_end'?: (event) => Promise<void>;
  'message_start'?: (event) => Promise<void>;
  'message_end'?: (event) => Promise<Message | void>;
  'tool_call'?: (event) => Promise<ToolCallEventResult | void>;
  'tool_result'?: (event) => Promise<ToolResultEventResult | void>;
  
  // 会话事件
  'session_start'?: (event) => Promise<void>;
  'session_shutdown'?: (event) => Promise<void>;
  'session_compact'?: (event) => Promise<void>;
  
  // 其他事件
  'input'?: (event) => Promise<InputEventResult>;
  'model_select'?: (event) => Promise<void>;
  'thinking_level_select'?: (event) => Promise<void>;
}
```

### 2. ExtensionContext

扩展上下文提供 API：
```typescript
interface ExtensionContext {
  cwd: string;                // 工作目录
  session: SessionManager;    // 会话管理器
  modelRegistry: ModelRegistry;  // 模型注册表
  
  // 核心方法
  registerTool(definition): void;
  registerCommand(invocationName, handler): void;
  registerHook(event, handler): void;
  
  // 工具控制
  getTools(): string[];
  setTools(toolNames): void;
  
  // 消息发送
  sendMessage(message, options): void;
  sendUserMessage(content, options): void;
}
```

### 3. ExtensionRunner 核心类

**核心职责**:
- 加载和初始化扩展
- 运行扩展事件处理
- 管理工具注册
- 管理命令系统

**核心方法**（extensions/runner.ts）:
```typescript
class ExtensionRunner {
  // 事件发射
  emit(event: ExtensionEvent): Promise<any>;
  
  // 特殊事件
  emitInput(text, images, source): Promise<InputEventResult>;
  emitBeforeAgentStart(...): Promise<BeforeAgentStartEventResult>;
  emitMessageEnd(event): Promise<Message | void>;
  emitToolCall(event): Promise<ToolCallEventResult>;
  emitToolResult(event): Promise<ToolResultEventResult>;
  
  // 工具管理
  getAllRegisteredTools(): RegisteredTool[];
  wrapRegisteredTools(tools, runner): AgentTool[];
  
  // 命令管理
  getRegisteredCommands(): RegisteredCommand[];
  getCommand(name): RegisteredCommand;
  createCommandContext(): ExtensionCommandContext;
  
  // 钩子管理
  hasHandlers(eventType): boolean;
  
  // 错误处理
  onError(listener): () => void;
  emitError(error): void;
  
  // 状态控制
  invalidate(message): void;
}
```

### 4. Extension 事件类型

**Agent 生命周期事件**:
- `agent_start` - Agent 开始
- `agent_end` - Agent 结束
- `turn_start` - Turn 开始
- `turn_end` - Turn 结束

**消息事件**:
- `message_start` - 消息开始
- `message_update` - 消息更新
- `message_end` - 消息结束

**工具事件**:
- `tool_call` - 工具调用（可拦截）
- `tool_result` - 工具结果（可修改）

**会话事件**:
- `session_start` - 会话启动
- `session_shutdown` - 会话关闭
- `session_compact` - 压缩完成
- `session_before_compact` - 压缩前（可取消）
- `session_before_fork` - Fork 前
- `session_before_switch` - 切换前
- `session_before_tree` - 树操作前

**输入事件**:
- `input` - 用户输入（可拦截/转换）

**模型事件**:
- `model_select` - 模型选择
- `thinking_level_select` - 思维级别选择

### 5. 工具注册机制

**注册流程**:
1. 扩展调用 `registerTool(definition)`
2. ExtensionRunner 记录工具定义
3. wrapRegisteredTools 包装工具
4. AgentSession 刷新工具注册

**工具拦截**:
- `tool_call` 事件：调用前拦截
- `tool_result` 事件：结果后修改

### 6. 命令系统

**命令注册**:
```typescript
registerCommand(invocationName, description, handler)
```

**命令执行**:
- ExtensionRunner 维护命令表
- `createCommandContext()` 创建执行上下文
- AgentSession 通过 `_tryExecuteExtensionCommand()` 执行

### 7. 扩展加载流程（extensions/loader.ts）

**加载步骤**:
1. 发现扩展文件（`discoverExtensions()`）
2. 解析扩展配置
3. 加载扩展模块
4. 调用工厂函数
5. 返回 Extension 数组

**扩展发现**:
```typescript
discoverAndLoadExtensions(cwd, runtime): LoadExtensionsResult
```

## 重点阅读

### extensions/types.ts（最重要）

理解所有扩展相关类型：
1. Extension 接口结构
2. ExtensionHandler 事件定义
3. ExtensionContext API
4. 各种 Event 类型
5. Result 类型

### extensions/runner.ts

理解扩展运行机制：
1. **构造函数** - 初始化扩展
2. **emit 方法** - 事件分发
3. **emitInput** - 输入拦截
4. **emitToolCall/emitToolResult** - 工具拦截
5. **wrapRegisteredTools** - 工具包装
6. **createCommandContext** - 命令上下文

### extensions/loader.ts

理解扩展加载：
1. **discoverExtensions** - 发现扩展
2. **loadExtension** - 加载单个扩展
3. **parseExtensionConfig** - 解析配置

### extensions/wrapper.ts

理解工具包装：
1. 如何包装扩展注册的工具
2. 如何注入扩展上下文
3. 如何处理工具钩子

### extensions/index.ts

理解导出的公共 API：
1. 导出的类型
2. 导出的函数
3. 公共接口

## 关键设计模式

### 工厂模式
ExtensionFactory 创建 ExtensionHandler：
- 扩展通过工厂函数创建
- 支持异步初始化
- 支持依赖注入

### 观察者模式
ExtensionRunner 作为事件中心：
- 扩展订阅事件
- ExtensionRunner 分发事件
- 支持异步处理

### 拦截器模式
事件拦截机制：
- `tool_call` 拦截工具调用
- `tool_result` 拦截工具结果
- `input` 拦截用户输入
- `session_before_compact` 拦截压缩

### 包装器模式
wrapRegisteredTools 包装工具：
- 注入扩展上下文
- 添加钩子处理
- 保持工具功能

## 学习建议

### 阅读顺序

1. **extensions/types.ts** - 先理解所有类型定义
2. **extensions/index.ts** - 理解导出的公共 API
3. **extensions/runner.ts** - 理解扩展运行核心
4. **extensions/loader.ts** - 理解扩展加载
5. **extensions/wrapper.ts** - 理解工具包装

### 重点理解

1. **事件系统** - ExtensionRunner 的 emit 机制
2. **工具拦截** - tool_call/tool_result 钩子
3. **命令系统** - 命令注册和执行
4. **工具包装** - 如何适配扩展工具到 Agent
5. **扩展生命周期** - 从加载到运行到关闭

## 实际应用场景

### 1. 注册自定义工具
```typescript
export default (ctx: ExtensionContext) => ({
  'session_start': async () => {
    ctx.registerTool({
      name: 'my_tool',
      description: 'My custom tool',
      parameters: { ... },
      execute: async (input) => { ... }
    });
  }
});
```

### 2. 拦截工具调用
```typescript
export default (ctx: ExtensionContext) => ({
  'tool_call': async (event) => {
    if (event.toolName === 'bash') {
      // 验证或修改 bash 命令
      return { approved: true };
    }
  }
});
```

### 3. 注册命令
```typescript
export default (ctx: ExtensionContext) => ({
  'session_start': async () => {
    ctx.registerCommand('/mycommand', 'My custom command', async (args, ctx) => {
      // 命令逻辑
    });
  }
});
```

### 4. 拦截用户输入
```typescript
export default (ctx: ExtensionContext) => ({
  'input': async (text, images, source) => {
    // 转换输入
    return { action: 'transform', text: modifiedText };
  }
});
```

## 与 AgentSession 的关系

ExtensionRunner 在 AgentSession 中：
1. **创建**：`_buildRuntime()` 创建 ExtensionRunner
2. **绑定**：`bindExtensions()` 绑定 UI 上下文
3. **事件转发**：`_emitExtensionEvent()` 转发 Agent 事件
4. **工具刷新**：`_refreshToolRegistry()` 使用扩展工具
5. **命令执行**：`_tryExecuteExtensionCommand()` 执行扩展命令

## 扩展思考

### 性能考虑
- 扩展事件处理性能影响
- 工具包装的性能开销
- 事件异步处理顺序

### 安全考虑
- 扩展权限控制
- 工具调用拦截安全
- 命令执行安全

### 架构扩展
- 如何添加新事件类型
- 如何支持扩展依赖
- 如何实现扩展热加载