# AgentSession 公共 API 详解

> 本文档深入挖掘 AgentSession 类的所有公共 API，包括属性、方法和事件类型。
> 
> **源文件**: `agent-session.ts` (3086行)

---

## 目录

- [一、公共属性（Getter）](#一公共属性getter)
- [二、公共方法](#二公共方法)
- [三、事件类型](#三事件类型)
- [四、配置接口](#四配置接口)
- [五、返回类型](#五返回类型)
- [六、使用示例](#六使用示例)

---

## 一、公共属性（Getter）

### 1. 核心实例属性

#### `readonly agent: Agent`
**类型**: `Agent` (来自 pi-agent-core)  
**访问**: 只读  
**用途**: 获取底层 Agent 实例，用于直接访问 Agent 状态和方法  
**示例**:
```typescript
const agentState = session.agent.state;
const isStreaming = session.agent.state.isStreaming;
```

#### `readonly sessionManager: SessionManager`
**类型**: `SessionManager`  
**访问**: 只读  
**用途**: 获取会话管理器，用于会话持久化和分支管理  
**示例**:
```typescript
const sessionId = session.sessionManager.getSessionId();
const entries = session.sessionManager.getEntries();
```

#### `readonly settingsManager: SettingsManager`
**类型**: `SettingsManager`  
**访问**: 只读  
**用途**: 获取设置管理器，用于读取和保存用户配置  
**示例**:
```typescript
const compactionSettings = session.settingsManager.getCompactionSettings();
const retrySettings = session.settingsManager.getRetrySettings();
```

#### `readonly modelRegistry: ModelRegistry`
**类型**: `ModelRegistry`  
**访问**: 只读  
**用途**: 获取模型注册表，用于模型发现和认证管理  
**示例**:
```typescript
const availableModels = await session.modelRegistry.getAvailable();
const hasAuth = session.modelRegistry.hasConfiguredAuth(model);
```

#### `readonly resourceLoader: ResourceLoader`
**类型**: `ResourceLoader`  
**访问**: 只读  
**用途**: 获取资源加载器，用于访问技能、模板等资源  
**示例**:
```typescript
const skills = session.resourceLoader.getSkills();
const prompts = session.resourceLoader.getPrompts();
```

#### `readonly extensionRunner: ExtensionRunner`
**类型**: `ExtensionRunner`  
**访问**: 只读  
**用途**: 获取扩展运行器，用于访问扩展系统  
**示例**:
```typescript
const commands = session.extensionRunner.getRegisteredCommands();
const hasHandlers = session.extensionRunner.hasHandlers('tool_call');
```

---

### 2. 状态属性

#### `get state(): AgentState`
**类型**: `AgentState`  
**用途**: 获取完整的 Agent 状态对象  
**包含**:
- `messages` - 消息列表
- `model` - 当前模型
- `thinkingLevel` - 思维级别
- `isStreaming` - 是否正在流式输出
- `systemPrompt` - 系统提示词
- `tools` - 当前激活的工具列表

**示例**:
```typescript
const messages = session.state.messages;
const model = session.state.model;
const isStreaming = session.state.isStreaming;
```

#### `get model(): Model<any> | undefined`
**类型**: `Model<any> | undefined`  
**用途**: 获取当前使用的模型（可能未选择）  
**示例**:
```typescript
if (session.model) {
  console.log(`Using ${session.model.provider}/${session.model.id}`);
}
```

#### `get thinkingLevel(): ThinkingLevel`
**类型**: `ThinkingLevel` ("off" | "minimal" | "low" | "medium" | "high")  
**用途**: 获取当前思维级别  
**示例**:
```typescript
console.log(`Thinking level: ${session.thinkingLevel}`);
```

#### `get isStreaming(): boolean`
**类型**: `boolean`  
**用途**: 判断 Agent 是否正在流式输出响应  
**示例**:
```typescript
if (session.isStreaming) {
  console.log("Agent is currently processing");
}
```

#### `get systemPrompt(): string`
**类型**: `string`  
**用途**: 获取当前有效的系统提示词（包含扩展修改）  
**示例**:
```typescript
const prompt = session.systemPrompt;
console.log(`System prompt length: ${prompt.length}`);
```

#### `get messages(): AgentMessage[]`
**类型**: `AgentMessage[]`  
**用途**: 获取所有消息（包括自定义类型）  
**示例**:
```typescript
const userMessages = session.messages.filter(m => m.role === 'user');
const assistantMessages = session.messages.filter(m => m.role === 'assistant');
```

---

### 3. 会话属性

#### `get sessionFile(): string | undefined`
**类型**: `string | undefined`  
**用途**: 获取当前会话文件路径（如果会话已禁用则返回 undefined）  
**示例**:
```typescript
if (session.sessionFile) {
  console.log(`Session file: ${session.sessionFile}`);
}
```

#### `get sessionId(): string`
**类型**: `string`  
**用途**: 获取当前会话的唯一标识符  
**示例**:
```typescript
console.log(`Session ID: ${session.sessionId}`);
```

#### `get sessionName(): string | undefined`
**类型**: `string | undefined`  
**用途**: 获取会话显示名称（如果已设置）  
**示例**:
```typescript
const displayName = session.sessionName || 'Unnamed session';
```

#### `get scopedModels(): ReadonlyArray<{ model: Model<any>; thinkingLevel?: ThinkingLevel }>`
**类型**: `ReadonlyArray<{ model: Model<any>; thinkingLevel?: ThinkingLevel }>`  
**用途**: 获取通过 --models 标志指定的模型列表  
**示例**:
```typescript
if (session.scopedModels.length > 0) {
  console.log(`Scoped models: ${session.scopedModels.length}`);
}
```

---

### 4. 工具属性

#### `getActiveToolNames(): string[]`
**返回类型**: `string[]`  
**用途**: 获取当前激活的工具名称列表  
**示例**:
```typescript
const activeTools = session.getActiveToolNames();
console.log(`Active tools: ${activeTools.join(', ')}`);
```

#### `getAllTools(): ToolInfo[]`
**返回类型**: `ToolInfo[]`  
**用途**: 获取所有已配置的工具及其元数据  
**ToolInfo 结构**:
```typescript
interface ToolInfo {
  name: string;
  description: string;
  parameters: JSONSchema;
  sourceInfo: SourceInfo;
}
```

**示例**:
```typescript
const allTools = session.getAllTools();
for (const tool of allTools) {
  console.log(`${tool.name}: ${tool.description}`);
}
```

#### `getToolDefinition(name: string): ToolDefinition | undefined`
**参数**:
- `name: string` - 工具名称

**返回类型**: `ToolDefinition | undefined`  
**用途**: 查找特定工具的定义  
**示例**:
```typescript
const bashDef = session.getToolDefinition('bash');
if (bashDef) {
  console.log(`Bash tool: ${bashDef.description}`);
}
```

---

### 5. 队列属性

#### `get steeringMode(): "all" | "one-at-a-time"`
**类型**: `"all" | "one-at-a-time"`  
**用途**: 获取当前 steering 消息的处理模式  
**含义**:
- `"all"` - 一次性处理所有 steering 消息
- `"one-at-a-time"` - 一次处理一条 steering 消息

**示例**:
```typescript
console.log(`Steering mode: ${session.steeringMode}`);
```

#### `get followUpMode(): "all" | "one-at-a-time"`
**类型**: `"all" | "one-at-a-time"`  
**用途**: 获取当前 follow-up 消息的处理模式  
**示例**:
```typescript
console.log(`Follow-up mode: ${session.followUpMode}`);
```

#### `get pendingMessageCount(): number`
**类型**: `number`  
**用途**: 获取待处理消息总数（steering + follow-up）  
**示例**:
```typescript
console.log(`Pending messages: ${session.pendingMessageCount}`);
```

#### `getSteeringMessages(): readonly string[]`
**返回类型**: `readonly string[]`  
**用途**: 获取待处理的 steering 消息列表（只读）  
**示例**:
```typescript
const steering = session.getSteeringMessages();
console.log(`Steering queue: ${steering.length} messages`);
```

#### `getFollowUpMessages(): readonly string[]`
**返回类型**: `readonly string[]`  
**用途**: 获取待处理的 follow-up 消息列表（只读）  
**示例**:
```typescript
const followUp = session.getFollowUpMessages();
console.log(`Follow-up queue: ${followUp.length} messages`);
```

---

### 6. 压缩属性

#### `get isCompacting(): boolean`
**类型**: `boolean`  
**用途**: 判断是否正在进行压缩或分支摘要操作  
**示例**:
```typescript
if (session.isCompacting) {
  console.log("Compaction in progress...");
}
```

#### `get autoCompactionEnabled(): boolean`
**类型**: `boolean`  
**用途**: 判断自动压缩是否启用  
**示例**:
```typescript
console.log(`Auto-compaction: ${session.autoCompactionEnabled}`);
```

---

### 7. 重试属性

#### `get retryAttempt(): number`
**类型**: `number`  
**用途**: 获取当前重试尝试次数（0 表示未重试）  
**示例**:
```typescript
console.log(`Retry attempt: ${session.retryAttempt}`);
```

#### `get isRetrying(): boolean`
**类型**: `boolean`  
**用途**: 判断是否正在进行自动重试  
**示例**:
```typescript
if (session.isRetrying) {
  console.log("Auto-retry in progress...");
}
```

#### `get autoRetryEnabled(): boolean`
**类型**: `boolean`  
**用途**: 判断自动重试是否启用  
**示例**:
```typescript
console.log(`Auto-retry: ${session.autoRetryEnabled}`);
```

---

### 8. Bash 执行属性

#### `get isBashRunning(): boolean`
**类型**: `boolean`  
**用途**: 判断是否有 Bash 命令正在运行  
**示例**:
```typescript
if (session.isBashRunning) {
  console.log("Bash command executing...");
}
```

#### `get hasPendingBashMessages(): boolean`
**类型**: `boolean`  
**用途**: 判断是否有待处理的 Bash 消息  
**示例**:
```typescript
if (session.hasPendingBashMessages) {
  console.log("Pending bash messages waiting to be flushed");
}
```

---

### 9. 其他属性

#### `get promptTemplates(): ReadonlyArray<PromptTemplate>`
**类型**: `ReadonlyArray<PromptTemplate>`  
**用途**: 获取文件基础的提示词模板列表  
**示例**:
```typescript
const templates = session.promptTemplates;
for (const template of templates) {
  console.log(`/${template.name}: ${template.description}`);
}
```

#### `get supportsThinking(): boolean`
**返回类型**: `boolean`  
**用途**: 判断当前模型是否支持思考/推理功能  
**示例**:
```typescript
if (session.supportsThinking()) {
  console.log("Model supports extended thinking");
}
```

---

## 二、公共方法

### 1. 事件订阅方法

#### `subscribe(listener: AgentSessionEventListener): () => void`
**参数**:
- `listener: AgentSessionEventListener` - 事件监听函数

**返回类型**: `() => void` - unsubscribe 函数  
**用途**: 订阅会话事件，返回取消订阅函数  
**示例**:
```typescript
const unsubscribe = session.subscribe((event) => {
  if (event.type === 'message_end') {
    console.log('Message finished');
  }
});

// 取消订阅
unsubscribe();
```

#### `dispose(): void`
**用途**: 完全销毁会话，移除所有监听器并清理资源  
**示例**:
```typescript
session.dispose();
// 会话已销毁，不能再使用
```

---

### 2. 提示方法

#### `prompt(text: string, options?: PromptOptions): Promise<void>`
**参数**:
- `text: string` - 用户输入文本
- `options?: PromptOptions` - 提示选项

**PromptOptions**:
```typescript
interface PromptOptions {
  expandPromptTemplates?: boolean;  // 是否展开模板（默认 true）
  images?: ImageContent[];          // 图片附件
  streamingBehavior?: "steer" | "followUp";  // 流式时的队列方式
  source?: InputSource;             // 输入来源（默认 "interactive"）
}
```

**用途**: 发送用户提示给 Agent  
**行为**:
- 处理扩展命令（以 `/` 开头）
- 展开技能和模板
- 流式时按 streamingBehavior 队列
- 验证模型和认证
- 触发压缩检查

**示例**:
```typescript
// 发送简单提示
await session.prompt("Hello, how are you?");

// 发送带图片的提示
await session.prompt("Look at this image", {
  images: [{ type: 'image', source: { type: 'base64', media_type: 'image/png', data: base64Data } }]
});

// 流式时队列消息
await session.prompt("Next message", {
  streamingBehavior: 'followUp'
});
```

#### `steer(text: string, images?: ImageContent[]): Promise<void>`
**参数**:
- `text: string` - 中断消息文本
- `images?: ImageContent[]` - 图片附件

**用途**: 发送中断式消息，立即插入到当前执行  
**特点**:
- 在当前 turn 执行完工具调用后立即处理
- 不能是扩展命令
- 自动展开技能和模板

**示例**:
```typescript
await session.steer("Stop! I want to change direction.");
```

#### `followUp(text: string, images?: ImageContent[]): Promise<void>`
**参数**:
- `text: string` - 后续消息文本
- `images?: ImageContent[]` - 图片附件

**用途**: 发送后续式消息，等待当前执行完成  
**特点**:
- 在 Agent 完全空闲后才处理
- 不能是扩展命令
- 自动展开技能和模板

**示例**:
```typescript
await session.followUp("After you finish, please do this...");
```

#### `sendCustomMessage<T>(message, options?): Promise<void>`
**参数**:
- `message` - 自定义消息内容
- `options?` - 发送选项

**消息结构**:
```typescript
{
  customType: string;   // 自定义类型标识
  content: T;           // 自定义内容
  display?: string;     // 显示文本
  details?: unknown;    // 详细信息
}
```

**选项结构**:
```typescript
{
  triggerTurn?: boolean;        // 是否触发新 turn
  deliverAs?: "steer" | "followUp" | "nextTurn";  // 传递方式
}
```

**用途**: 发送自定义消息到会话  
**行为**:
- `nextTurn`: 作为下轮上下文注入
- 流式时: steer 或 followUp 队列
- 非流式 + triggerTurn: 触发新 turn
- 非流式 + 无 trigger: 仅添加到状态

**示例**:
```typescript
await session.sendCustomMessage({
  customType: 'notification',
  content: { message: 'Build completed' },
  display: 'Build completed successfully'
}, {
  deliverAs: 'nextTurn'
});
```

#### `sendUserMessage(content, options?): Promise<void>`
**参数**:
- `content: string | (TextContent | ImageContent)[]` - 用户消息内容
- `options?: { deliverAs?: "steer" | "followUp" }` - 发送选项

**用途**: 发送用户消息（总是触发 turn）  
**示例**:
```typescript
await session.sendUserMessage("Please analyze this code");
await session.sendUserMessage([
  { type: 'text', text: 'Look at this' },
  { type: 'image', source: { ... } }
]);
```

---

### 3. 队列管理方法

#### `clearQueue(): { steering: string[]; followUp: string[] }`
**返回类型**: `{ steering: string[]; followUp: string[] }`  
**用途**: 清空所有队列消息并返回它们  
**示例**:
```typescript
const { steering, followUp } = session.clearQueue();
console.log(`Cleared ${steering.length} steering, ${followUp.length} follow-up`);
```

---

### 4. 中断方法

#### `abort(): Promise<void>`
**用途**: 中断当前操作并等待 Agent 变为空闲  
**示例**:
```typescript
await session.abort();
console.log("Agent is now idle");
```

---

### 5. 工具管理方法

#### `setActiveToolsByName(toolNames: string[]): void`
**参数**:
- `toolNames: string[]` - 工具名称数组

**用途**: 设置激活的工具，重建系统提示词  
**示例**:
```typescript
session.setActiveToolsByName(['read', 'bash', 'edit', 'write', 'grep']);
console.log(`Active tools: ${session.getActiveToolNames()}`);
```

---

### 6. 模型管理方法

#### `setModel(model: Model<any>): Promise<void>`
**参数**:
- `model: Model<any>` - 要设置的模型

**用途**: 直接设置模型，验证认证并保存  
**行为**:
- 验证认证配置
- 更新 Agent 状态
- 保存到会话和设置
- 重新 clamp 思维级别

**示例**:
```typescript
const model = await modelRegistry.find('anthropic', 'claude-sonnet-4');
await session.setModel(model);
```

#### `cycleModel(direction?: "forward" | "backward"): Promise<ModelCycleResult | undefined>`
**参数**:
- `direction?: "forward" | "backward"` - 切换方向（默认 "forward"）

**返回类型**: `ModelCycleResult | undefined`  
**ModelCycleResult**:
```typescript
interface ModelCycleResult {
  model: Model<any>;
  thinkingLevel: ThinkingLevel;
  isScoped: boolean;  // 是否来自 scoped models
}
```

**用途**: 循环切换模型  
**行为**:
- 有 scoped models 时切换 scoped models
- 否则切换所有可用模型

**示例**:
```typescript
const result = await session.cycleModel('forward');
if (result) {
  console.log(`Switched to ${result.model.id}`);
}
```

---

### 7. 思维级别管理方法

#### `setThinkingLevel(level: ThinkingLevel): void`
**参数**:
- `level: ThinkingLevel` - 思维级别

**用途**: 设置思维级别，clamp 到模型能力  
**行为**:
- Clamp 到模型支持的级别
- 仅在级别改变时持久化
- 发送事件通知

**示例**:
```typescript
session.setThinkingLevel('high');
console.log(`Thinking level: ${session.thinkingLevel}`);
```

#### `cycleThinkingLevel(): ThinkingLevel | undefined`
**返回类型**: `ThinkingLevel | undefined`  
**用途**: 循环切换思维级别  
**示例**:
```typescript
const nextLevel = session.cycleThinkingLevel();
if (nextLevel) {
  console.log(`Thinking level: ${nextLevel}`);
}
```

#### `getAvailableThinkingLevels(): ThinkingLevel[]`
**返回类型**: `ThinkingLevel[]`  
**用途**: 获取当前模型支持的思维级别列表  
**示例**:
```typescript
const levels = session.getAvailableThinkingLevels();
console.log(`Available levels: ${levels.join(', ')}`);
```

#### `supportsThinking(): boolean`
**返回类型**: `boolean`  
**用途**: 判断当前模型是否支持思考功能  
**示例**:
```typescript
if (session.supportsThinking()) {
  console.log("Extended thinking available");
}
```

---

### 8. 队列模式管理方法

#### `setSteeringMode(mode: "all" | "one-at-a-time"): void`
**参数**:
- `mode: "all" | "one-at-a-time"` - 处理模式

**用途**: 设置 steering 消息处理模式  
**示例**:
```typescript
session.setSteeringMode('one-at-a-time');
```

#### `setFollowUpMode(mode: "all" | "one-at-a-time"): void`
**参数**:
- `mode: "all" | "one-at-a-time"` - 处理模式

**用途**: 设置 follow-up 消息处理模式  
**示例**:
```typescript
session.setFollowUpMode('all');
```

---

### 9. 压缩方法

#### `compact(customInstructions?: string): Promise<CompactionResult>`
**参数**:
- `customInstructions?: string` - 自定义压缩指令

**返回类型**: `CompactionResult`  
**CompactionResult**:
```typescript
interface CompactionResult {
  summary: string;            // 压缩摘要
  firstKeptEntryId: string;   // 保留的起始条目 ID
  tokensBefore: number;       // 压缩前 token 数
  details?: unknown;          // 详细信息
}
```

**用途**: 手动压缩会话上下文  
**行为**:
- 中止当前 Agent 操作
- 准备压缩数据
- 扩展可拦截或提供压缩内容
- LLM 生成摘要
- 更新会话状态

**示例**:
```typescript
const result = await session.compact("Focus on main tasks only");
console.log(`Compacted: ${result.tokensBefore} tokens -> summary`);
```

#### `abortCompaction(): void`
**用途**: 中止进行中的压缩（手动或自动）  
**示例**:
```typescript
session.abortCompaction();
```

#### `abortBranchSummary(): void`
**用途**: 中止进行中的分支摘要生成  
**示例**:
```typescript
session.abortBranchSummary();
```

#### `setAutoCompactionEnabled(enabled: boolean): void`
**参数**:
- `enabled: boolean` - 是否启用

**用途**: 设置自动压缩开关  
**示例**:
```typescript
session.setAutoCompactionEnabled(true);
```

---

### 10. 扩展方法

#### `bindExtensions(bindings: ExtensionBindings): Promise<void>`
**参数**:
- `bindings: ExtensionBindings` - 扩展绑定

**ExtensionBindings**:
```typescript
interface ExtensionBindings {
  uiContext?: ExtensionUIContext;
  commandContextActions?: ExtensionCommandContextActions;
  abortHandler?: () => void;
  shutdownHandler?: ShutdownHandler;
  onError?: ExtensionErrorListener;
}
```

**用途**: 绑定扩展 UI 上下文和回调  
**示例**:
```typescript
await session.bindExtensions({
  uiContext: myUIContext,
  onError: (error) => console.error(error)
});
```

#### `reload(): Promise<void>`
**用途**: 重载会话（重新加载设置、资源和扩展）  
**行为**:
- 发送 shutdown 事件
- 重载设置
- 重载资源
- 重构运行时
- 发送 start 事件

**示例**:
```typescript
await session.reload();
console.log("Session reloaded");
```

---

### 11. 重试方法

#### `abortRetry(): void`
**用途**: 中止进行中的自动重试  
**示例**:
```typescript
session.abortRetry();
```

#### `setAutoRetryEnabled(enabled: boolean): void`
**参数**:
- `enabled: boolean` - 是否启用

**用途**: 设置自动重试开关  
**示例**:
```typescript
session.setAutoRetryEnabled(true);
```

---

### 12. Bash 执行方法

#### `executeBash(command, onChunk?, options?): Promise<BashResult>`
**参数**:
- `command: string` - Bash 命令
- `onChunk?: (chunk: string) => void` - 流式输出回调
- `options?: { excludeFromContext?: boolean; operations?: BashOperations }` - 执行选项

**返回类型**: `BashResult`  
**BashResult**:
```typescript
interface BashResult {
  output: string;      // 输出内容
  exitCode: number;    // 退出码
  cancelled: boolean;  // 是否被取消
  truncated: boolean;  // 是否被截断
  fullOutputPath?: string;  // 完整输出路径
}
```

**用途**: 执行 Bash 命令  
**行为**:
- 应用命令前缀（如 alias 支持）
- 流式输出回调
- 支持中止
- 记录到会话

**示例**:
```typescript
const result = await session.executeBash('npm run build', (chunk) => {
  console.log(chunk);
});
console.log(`Exit code: ${result.exitCode}`);
```

#### `recordBashResult(command, result, options?): void`
**参数**:
- `command: string` - Bash 命令
- `result: BashResult` - 执行结果
- `options?: { excludeFromContext?: boolean }` - 选项

**用途**: 记录 Bash 执行结果到会话历史  
**应用**: 扩展自己处理 Bash 执行后记录结果

**示例**:
```typescript
session.recordBashResult('npm test', result, {
  excludeFromContext: false
});
```

#### `abortBash(): void`
**用途**: 中止正在运行的 Bash 命令  
**示例**:
```typescript
session.abortBash();
```

---

### 13. 会话管理方法

#### `setSessionName(name: string): void`
**参数**:
- `name: string` - 会话显示名称

**用途**: 设置会话显示名称  
**示例**:
```typescript
session.setSessionName("Code Review Session");
console.log(`Session name: ${session.sessionName}`);
```

#### `setScopedModels(scopedModels): void`
**参数**:
- `scopedModels: Array<{ model: Model<any>; thinkingLevel?: ThinkingLevel }>` - scoped 模型列表

**用途**: 更新 scoped 模型列表  
**示例**:
```typescript
session.setScopedModels([
  { model: claudeSonnet4, thinkingLevel: 'high' },
  { model: claudeOpus4, thinkingLevel: 'medium' }
]);
```

---

### 14. 树形导航方法

#### `navigateTree(targetId, options?): Promise<{ editorText?, cancelled, aborted?, summaryEntry? }>`
**参数**:
- `targetId: string` - 目标条目 ID
- `options?: { summarize?, customInstructions?, replaceInstructions?, label? }` - 导航选项

**返回类型**:
```typescript
{
  editorText?: string;    // 用户消息文本（如需恢复到编辑器）
  cancelled: boolean;     // 是否被取消
  aborted?: boolean;      // 是否被中止
  summaryEntry?: BranchSummaryEntry;  // 摘要条目（如果生成了）
}
```

**用途**: 在会话树中导航到不同节点  
**行为**:
- 查找目标条目
- 扩展可拦截
- 可选择生成分支摘要
- 更新 Agent 状态

**示例**:
```typescript
const result = await session.navigateTree(targetEntryId, {
  summarize: true,
  customInstructions: "Focus on completed tasks",
  label: "Review checkpoint"
});

if (result.editorText) {
  // 恢复到编辑器
  editor.setContent(result.editorText);
}
```

#### `getUserMessagesForForking(): Array<{ entryId: string; text: string }>`
**返回类型**: `Array<{ entryId: string; text: string }>`  
**用途**: 获取所有用户消息用于 fork 选择器  
**示例**:
```typescript
const messages = session.getUserMessagesForForking();
for (const msg of messages) {
  console.log(`${msg.entryId}: ${msg.text}`);
}
```

---

### 15. 统计和导出方法

#### `getSessionStats(): SessionStats`
**返回类型**: `SessionStats`  
**SessionStats**:
```typescript
interface SessionStats {
  sessionFile: string | undefined;
  sessionId: string;
  userMessages: number;
  assistantMessages: number;
  toolCalls: number;
  toolResults: number;
  totalMessages: number;
  tokens: {
    input: number;
    output: number;
    cacheRead: number;
    cacheWrite: number;
    total: number;
  };
  cost: number;
  contextUsage?: ContextUsage;
}
```

**用途**: 获取会话统计信息  
**示例**:
```typescript
const stats = session.getSessionStats();
console.log(`Total messages: ${stats.totalMessages}`);
console.log(`Total tokens: ${stats.tokens.total}`);
console.log(`Cost: $${stats.cost}`);
```

#### `getContextUsage(): ContextUsage | undefined`
**返回类型**: `ContextUsage | undefined`  
**ContextUsage**:
```typescript
interface ContextUsage {
  tokens: number | null;      // 当前上下文 token 数
  contextWindow: number;      // 上下文窗口大小
  percent: number | null;     // 使用百分比
}
```

**用途**: 获取上下文使用情况  
**示例**:
```typescript
const usage = session.getContextUsage();
if (usage) {
  console.log(`Context usage: ${usage.percent?.toFixed(1)}%`);
}
```

#### `exportToHtml(outputPath?: string): Promise<string>`
**参数**:
- `outputPath?: string` - 输出路径（默认会话目录）

**返回类型**: `string` - 导出文件路径  
**用途**: 导出会话为 HTML  
**示例**:
```typescript
const htmlPath = await session.exportToHtml();
console.log(`Exported to: ${htmlPath}`);
```

#### `exportToJsonl(outputPath?: string): string`
**参数**:
- `outputPath?: string` - 输出路径（默认当前目录带时间戳）

**返回类型**: `string` - 导出文件路径  
**用途**: 导出当前会话分支为 JSONL 文件  
**示例**:
```typescript
const jsonlPath = session.exportToJsonl('session-backup.jsonl');
console.log(`Exported to: ${jsonlPath}`);
```

---

### 16. 工具方法

#### `getLastAssistantText(): string | undefined`
**返回类型**: `string | undefined`  
**用途**: 获取最后一条助手消息的文本内容  
**应用**: `/copy` 命令使用

**示例**:
```typescript
const lastText = session.getLastAssistantText();
if (lastText) {
  clipboard.write(lastText);
}
```

#### `createReplacedSessionContext(): ReplacedSessionContext`
**返回类型**: `ReplacedSessionContext`  
**用途**: 创建替换会话上下文（用于会话替换后的操作）  
**示例**:
```typescript
const ctx = session.createReplacedSessionContext();
ctx.sendMessage({ customType: 'info', content: 'Session replaced' });
```

#### `hasExtensionHandlers(eventType: string): boolean`
**参数**:
- `eventType: string` - 事件类型

**返回类型**: `boolean`  
**用途**: 检查扩展是否处理特定事件  
**示例**:
```typescript
if (session.hasExtensionHandlers('tool_call')) {
  console.log("Extensions will intercept tool calls");
}
```

---

## 三、事件类型

### AgentSessionEvent 完整列表

#### 1. Agent 事件（继承自 AgentEvent）

**agent_start**
```typescript
{ type: 'agent_start' }
```
**触发时机**: Agent 开始处理新 turn

**agent_end**
```typescript
{
  type: 'agent_end';
  messages: AgentMessage[];
  willRetry: boolean;  // 是否会自动重试
}
```
**触发时机**: Agent 结束处理

**turn_start**
```typescript
{ type: 'turn_start' }
```
**触发时机**: Turn 开始

**turn_end**
```typescript
{
  type: 'turn_end';
  message: AgentMessage;
  toolResults?: ToolResultMessage[];
}
```
**触发时机**: Turn 结束

**message_start**
```typescript
{
  type: 'message_start';
  message: AgentMessage;
}
```
**触发时机**: 消息开始

**message_update**
```typescript
{
  type: 'message_update';
  message: AgentMessage;
  assistantMessageEvent?: any;
}
```
**触发时机**: 消息更新（流式）

**message_end**
```typescript
{
  type: 'message_end';
  message: AgentMessage;
}
```
**触发时机**: 消息结束

**tool_execution_start**
```typescript
{
  type: 'tool_execution_start';
  toolCallId: string;
  toolName: string;
  args: any;
}
```
**触发时机**: 工具开始执行

**tool_execution_update**
```typescript
{
  type: 'tool_execution_update';
  toolCallId: string;
  toolName: string;
  args: any;
  partialResult: any;
}
```
**触发时机**: 工具执行更新（流式）

**tool_execution_end**
```typescript
{
  type: 'tool_execution_end';
  toolCallId: string;
  toolName: string;
  result: any;
  isError: boolean;
}
```
**触发时机**: 工具执行结束

---

#### 2. Session 扩展事件

**queue_update**
```typescript
{
  type: 'queue_update';
  steering: readonly string[];
  followUp: readonly string[];
}
```
**触发时机**: 消息队列更新

**compaction_start**
```typescript
{
  type: 'compaction_start';
  reason: 'manual' | 'threshold' | 'overflow';
}
```
**触发时机**: 压缩开始  
**reason 说明**:
- `manual`: 用户手动触发
- `threshold`: 上下文超过阈值
- `overflow`: LLM 返回溢出错误

**compaction_end**
```typescript
{
  type: 'compaction_end';
  reason: 'manual' | 'threshold' | 'overflow';
  result: CompactionResult | undefined;
  aborted: boolean;
  willRetry: boolean;
  errorMessage?: string;
}
```
**触发时机**: 压缩结束

**session_info_changed**
```typescript
{
  type: 'session_info_changed';
  name: string | undefined;
}
```
**触发时机**: 会话名称变更

**thinking_level_changed**
```typescript
{
  type: 'thinking_level_changed';
  level: ThinkingLevel;
}
```
**触发时机**: 思维级别变更

**auto_retry_start**
```typescript
{
  type: 'auto_retry_start';
  attempt: number;
  maxAttempts: number;
  delayMs: number;
  errorMessage: string;
}
```
**触发时机**: 自动重试开始

**auto_retry_end**
```typescript
{
  type: 'auto_retry_end';
  success: boolean;
  attempt: number;
  finalError?: string;
}
```
**触发时机**: 自动重试结束

---

## 四、配置接口

### AgentSessionConfig

```typescript
interface AgentSessionConfig {
  agent: Agent;              // 核心 Agent 实例
  sessionManager: SessionManager;   // 会话管理器
  settingsManager: SettingsManager; // 设置管理器
  cwd: string;               // 工作目录
  
  // 模型配置
  scopedModels?: Array<{ model: Model<any>; thinkingLevel?: ThinkingLevel }>;
  
  // 资源加载
  resourceLoader: ResourceLoader;
  
  // 工具配置
  customTools?: ToolDefinition[];
  initialActiveToolNames?: string[];
  allowedToolNames?: string[];
  baseToolsOverride?: Record<string, AgentTool>;
  
  // 模型注册
  modelRegistry: ModelRegistry;
  
  // 扩展系统
  extensionRunnerRef?: { current?: ExtensionRunner };
  sessionStartEvent?: SessionStartEvent;
}
```

### PromptOptions

```typescript
interface PromptOptions {
  expandPromptTemplates?: boolean;  // 是否展开模板（默认 true）
  images?: ImageContent[];          // 图片附件
  streamingBehavior?: "steer" | "followUp";  // 流式时队列方式
  source?: InputSource;             // 输入来源（默认 "interactive"）
  preflightResult?: (success: boolean) => void;  // 内部钩子
}
```

### ExtensionBindings

```typescript
interface ExtensionBindings {
  uiContext?: ExtensionUIContext;
  commandContextActions?: ExtensionCommandContextActions;
  abortHandler?: () => void;
  shutdownHandler?: ShutdownHandler;
  onError?: ExtensionErrorListener;
}
```

---

## 五、返回类型

### ModelCycleResult

```typescript
interface ModelCycleResult {
  model: Model<any>;
  thinkingLevel: ThinkingLevel;
  isScoped: boolean;  // 是否来自 scoped models
}
```

### SessionStats

```typescript
interface SessionStats {
  sessionFile: string | undefined;
  sessionId: string;
  userMessages: number;
  assistantMessages: number;
  toolCalls: number;
  toolResults: number;
  totalMessages: number;
  tokens: {
    input: number;
    output: number;
    cacheRead: number;
    cacheWrite: number;
    total: number;
  };
  cost: number;
  contextUsage?: ContextUsage;
}
```

### CompactionResult

```typescript
interface CompactionResult {
  summary: string;
  firstKeptEntryId: string;
  tokensBefore: number;
  details?: unknown;
}
```

### ContextUsage

```typescript
interface ContextUsage {
  tokens: number | null;
  contextWindow: number;
  percent: number | null;
}
```

### BashResult

```typescript
interface BashResult {
  output: string;
  exitCode: number;
  cancelled: boolean;
  truncated: boolean;
  fullOutputPath?: string;
}
```

---

## 六、使用示例

### 示例 1: 基础会话使用

```typescript
// 创建会话
const session = new AgentSession({
  agent: agent,
  sessionManager: sessionManager,
  settingsManager: settingsManager,
  cwd: '/project/path',
  resourceLoader: resourceLoader,
  modelRegistry: modelRegistry
});

// 订阅事件
const unsubscribe = session.subscribe((event) => {
  console.log(`Event: ${event.type}`);
});

// 发送提示
await session.prompt("Hello!");

// 获取统计
const stats = session.getSessionStats();
console.log(`Messages: ${stats.totalMessages}`);

// 清理
unsubscribe();
session.dispose();
```

---

### 示例 2: 流式处理和消息队列

```typescript
// Agent 正在流式输出
if (session.isStreaming) {
  // 队列后续消息
  await session.followUp("After you finish, analyze this code");
  
  // 或中断当前执行
  await session.steer("Stop! Change direction");
}

// 检查队列状态
console.log(`Pending: ${session.pendingMessageCount}`);
console.log(`Steering: ${session.getSteeringMessages().length}`);
console.log(`Follow-up: ${session.getFollowUpMessages().length}`);

// 清空队列
const { steering, followUp } = session.clearQueue();
```

---

### 示例 3: 模型和思维级别管理

```typescript
// 设置模型
const model = modelRegistry.find('anthropic', 'claude-sonnet-4');
await session.setModel(model);

// 循环切换模型
const nextModel = await session.cycleModel('forward');
console.log(`Switched to: ${nextModel?.model.id}`);

// 设置思维级别
session.setThinkingLevel('high');
console.log(`Thinking: ${session.thinkingLevel}`);

// 循环切换思维级别
const nextLevel = session.cycleThinkingLevel();
console.log(`Level: ${nextLevel}`);

// 检查模型能力
if (session.supportsThinking()) {
  console.log("Extended thinking available");
}
```

---

### 示例 4: 压缩和上下文管理

```typescript
// 手动压缩
const result = await session.compact("Focus on key decisions");
console.log(`Compacted: ${result.tokensBefore} tokens`);

// 检查压缩状态
if (session.isCompacting) {
  console.log("Compaction in progress");
}

// 中止压缩
session.abortCompaction();

// 获取上下文使用情况
const usage = session.getContextUsage();
if (usage?.percent) {
  console.log(`Context: ${usage.percent.toFixed(1)}% used`);
  
  if (usage.percent > 80) {
    console.log("Context approaching limit, consider compacting");
  }
}

// 设置自动压缩
session.setAutoCompactionEnabled(true);
```

---

### 示例 5: Bash 执行

```typescript
// 执行命令并流式显示输出
const result = await session.executeBash(
  'npm run build',
  (chunk) => console.log(chunk)
);

console.log(`Exit code: ${result.exitCode}`);

if (result.exitCode === 0) {
  console.log("Build succeeded");
} else {
  console.log("Build failed");
}

// 中止命令
session.abortBash();

// 检查状态
if (session.isBashRunning) {
  console.log("Bash executing...");
}
```

---

### 示例 6: 会话树导航

```typescript
// 获取可 fork 的用户消息
const messages = session.getUserMessagesForForking();

// 导航到历史节点
const targetId = messages[0].entryId;
const result = await session.navigateTree(targetId, {
  summarize: true,
  customInstructions: "Summarize completed work",
  label: "Checkpoint 1"
});

if (result.editorText) {
  // 恢复到编辑器
  editor.setContent(result.editorText);
}

if (result.summaryEntry) {
  console.log(`Summary created: ${result.summaryEntry.id}`);
}
```

---

### 示例 7: 导出和统计

```typescript
// 导出为 HTML
const htmlPath = await session.exportToHtml('/exports/session.html');
console.log(`HTML exported: ${htmlPath}`);

// 导出为 JSONL
const jsonlPath = session.exportToJsonl('/exports/session.jsonl');
console.log(`JSONL exported: ${jsonlPath}`);

// 获取统计
const stats = session.getSessionStats();
console.log(`
Session Statistics:
- Messages: ${stats.totalMessages}
- User: ${stats.userMessages}
- Assistant: ${stats.assistantMessages}
- Tool calls: ${stats.toolCalls}
- Tokens: ${stats.tokens.total}
- Cost: $${stats.cost.toFixed(2)}
`);
```

---

### 示例 8: 扩展集成

```typescript
// 绑定扩展
await session.bindExtensions({
  uiContext: {
    displayMessage: (msg) => console.log(msg),
    showWorkingIndicator: (options) => showSpinner(options)
  },
  onError: (error) => {
    console.error(`Extension error: ${error.error}`);
  }
});

// 检查扩展处理
if (session.hasExtensionHandlers('tool_call')) {
  console.log("Tools will be intercepted by extensions");
}

// 重载会话
await session.reload();
console.log("Session reloaded");
```

---

### 示例 9: 自定义消息和工具管理

```typescript
// 发送自定义消息
await session.sendCustomMessage({
  customType: 'notification',
  content: { type: 'success', message: 'Task completed' },
  display: '✓ Task completed'
}, {
  deliverAs: 'nextTurn'
});

// 工具管理
const activeTools = session.getActiveToolNames();
console.log(`Active: ${activeTools}`);

// 添加工具
session.setActiveToolsByName(['read', 'bash', 'edit', 'write', 'grep']);

// 获取所有工具信息
const allTools = session.getAllTools();
for (const tool of allTools) {
  console.log(`${tool.name}: ${tool.description}`);
}
```

---

### 示例 10: 完整事件监听

```typescript
const unsubscribe = session.subscribe((event) => {
  switch (event.type) {
    case 'message_start':
      console.log('Message started');
      break;
      
    case 'message_end':
      if (event.message.role === 'assistant') {
        console.log('Assistant finished');
      }
      break;
      
    case 'tool_execution_start':
      console.log(`Tool ${event.toolName} started`);
      break;
      
    case 'tool_execution_end':
      console.log(`Tool ${event.toolName} ended`);
      if (event.isError) {
        console.log('Tool failed');
      }
      break;
      
    case 'compaction_start':
      console.log(`Compaction started (${event.reason})`);
      break;
      
    case 'compaction_end':
      if (event.result) {
        console.log(`Compacted: ${event.result.tokensBefore} tokens`);
      }
      break;
      
    case 'queue_update':
      console.log(`Queue: ${event.steering.length} steering, ${event.followUp.length} follow-up`);
      break;
      
    case 'auto_retry_start':
      console.log(`Retry attempt ${event.attempt}/${event.maxAttempts}`);
      break;
      
    case 'auto_retry_end':
      console.log(`Retry ${event.success ? 'succeeded' : 'failed'}`);
      break;
      
    case 'thinking_level_changed':
      console.log(`Thinking level: ${event.level}`);
      break;
      
    case 'session_info_changed':
      console.log(`Session name: ${event.name}`);
      break;
  }
});
```

---

## 总结

AgentSession 提供了 **50+ 公共 API**，分为以下类别：

1. **核心属性** (9个) - Agent、SessionManager、SettingsManager 等
2. **状态属性** (6个) - state、model、thinkingLevel 等
3. **会话属性** (4个) - sessionId、sessionFile 等
4. **工具属性** (3个方法) - getActiveToolNames、getAllTools 等
5. **队列属性** (5个) - steeringMode、pendingMessageCount 等
6. **压缩属性** (2个) - isCompacting、autoCompactionEnabled
7. **重试属性** (3个) - retryAttempt、isRetrying 等
8. **Bash 属性** (2个) - isBashRunning、hasPendingBashMessages
9. **提示方法** (5个) - prompt、steer、followUp 等
10. **模型管理方法** (5个) - setModel、cycleModel 等
11. **思维级别方法** (4个) - setThinkingLevel、cycleThinkingLevel 等
12. **压缩方法** (4个) - compact、abortCompaction 等
13. **Bash 执行方法** (3个) - executeBash、abortBash 等
14. **会话管理方法** (2个) - setSessionName、setScopedModels
15. **树形导航方法** (2个) - navigateTree、getUserMessagesForForking
16. **统计导出方法** (4个) - getSessionStats、exportToHtml 等
17. **事件订阅** (2个) - subscribe、dispose
18. **其他方法** (7个) - abort、reload、bindExtensions 等

**事件类型** 共 17 种，涵盖：
- Agent 生命周期事件 (9种)
- Session 扩展事件 (8种)

AgentSession 是 Coding Agent 的核心抽象，通过这些丰富的 API，实现了完整的会话生命周期管理。