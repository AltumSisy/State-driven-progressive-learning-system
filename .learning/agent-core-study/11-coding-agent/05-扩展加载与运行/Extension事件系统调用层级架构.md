# Extension 事件系统调用层级架构

本文档描述 Extension 事件系统的完整调用链，从顶层到事件发射层的层级关系。

---

## 一、整体层级架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          用户交互层 (Modes)                                   │
│  interactive-mode.ts, rpc-mode, print-mode                                   │
│  • 处理用户输入                                                               │
│  • 调用 AgentSessionRuntime 的会话管理方法                                    │
│  • 调用 AgentSession 的 prompt/abort 方法                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    会话管理层 (AgentSessionRuntime)                           │
│  agent-session-runtime.ts                                                    │
│  • 管理 AgentSession 的生命周期                                               │
│  • 处理会话切换、创建、fork                                                    │
│  • 发出 session_before_* 和 session_shutdown 事件                             │
│                                                                              │
│  调用方法:                                                                    │
│  • newSession() → emitBeforeSwitch("new") → emit(session_shutdown)          │
│  • switchSession() → emitBeforeSwitch("resume") → emit(session_shutdown)    │
│  • fork() → emitBeforeFork() → emit(session_shutdown)                       │
│  • dispose() → emit(session_shutdown)                                       │
└─────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Agent 运行层 (AgentSession)                               │
│  agent-session.ts                                                            │
│  • 核心 Agent 抽象，管理 agent 循环                                           │
│  • 处理 prompt、model 管理、compaction                                        │
│  • 监听 AgentEvent 并转换为 ExtensionEvent                                   │
│                                                                              │
│  事件发射点:                                                                  │
│  • prompt() → emitInput() → emitBeforeAgentStart()                          │
│  • _handleAgentEvent() → emit(各种 agent/message/tool 事件)                 │
│  • _installAgentToolHooks() → agent.beforeToolCall → emitToolCall()         │
│  • _installAgentToolHooks() → agent.afterToolCall → emitToolResult()        │
│  • setModel() → emit(model_select)                                          │
│  • setThinkingLevel() → emit(thinking_level_select)                         │
│  • compact() → emit(session_before_compact) → emit(session_compact)         │
│  • bindExtensions() → emit(session_start) → emitResourcesDiscover()         │
│  • reload() → emit(session_shutdown) → emit(session_start)                  │
└─────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     事件发射层 (ExtensionRunner)                              │
│  runner.ts                                                                   │
│  • 执行 extension handlers                                                   │
│  • 处理事件返回结果                                                           │
│                                                                              │
│  事件方法:                                                                    │
│  • emit() - 通用方法，处理 RunnerEmitEvent                                   │
│  • emitToolCall() - 专门方法，阻断模式                                        │
│  • emitToolResult() - 专门方法，链式修改                                      │
│  • emitMessageEnd() - 专门方法，链式修改+校验                                 │
│  • emitContext() - 专门方法，链式修改                                         │
│  • emitInput() - 专门方法，多模式                                             │
│  • emitBeforeAgentStart() - 专门方法，复杂参数                                │
│  • emitResourcesDiscover() - 专门方法，收集模式                               │
│  • emitUserBash() - 专门方法                                                  │
│  • emitBeforeProviderRequest() - 专门方法                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Extension 层 (Extensions)                                │
│  用户编写的扩展代码                                                            │
│  • 注册 pi.on("event_type", handler)                                        │
│  • handler 接收 (event, ctx) 参数                                            │
│  • 返回结果（某些事件）                                                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 二、各层详细分析

### 1. 用户交互层 (Modes)

**文件**: `modes/interactive/interactive-mode.ts` 等

**职责**:
- 处理用户输入
- 协调 AgentSessionRuntime 和 AgentSession
- UI 渲染

**调用示例**:
```typescript
// 用户发送消息
await session.prompt(text, { images });

// 用户切换会话
await runtime.switchSession(sessionPath);

// 用户创建新会话
await runtime.newSession();
```

---

### 2. 会话管理层 (AgentSessionRuntime)

**文件**: `agent-session-runtime.ts`

**职责**:
- 管理 AgentSession 的生命周期
- 处理会话切换、创建、fork、导入
- 发出 session 相关的 before 和 shutdown 事件

**类定义**:
```typescript
export class AgentSessionRuntime {
  private _session: AgentSession;
  private _services: AgentSessionServices;
  
  // 会话操作方法
  async switchSession(sessionPath, options): Promise<{ cancelled: boolean }>;
  async newSession(options): Promise<{ cancelled: boolean }>;
  async fork(entryId, options): Promise<{ cancelled: boolean }>;
  async importFromJsonl(inputPath, cwdOverride): Promise<{ cancelled: boolean }>;
  async dispose(): Promise<void>;
}
```

**事件发射点**:

#### `emitBeforeSwitch()` - 内部方法
```typescript
private async emitBeforeSwitch(
  reason: "new" | "resume",
  targetSessionFile?: string,
): Promise<{ cancelled: boolean }> {
  const runner = this.session.extensionRunner;
  if (!runner.hasHandlers("session_before_switch")) {
    return { cancelled: false };
  }

  const result = await runner.emit({
    type: "session_before_switch",
    reason,
    targetSessionFile,
  });
  return { cancelled: result?.cancel === true };
}
```

#### `emitBeforeFork()` - 内部方法
```typescript
private async emitBeforeFork(
  entryId: string,
  options: { position: "before" | "at" },
): Promise<{ cancelled: boolean }> {
  const runner = this.session.extensionRunner;
  if (!runner.hasHandlers("session_before_fork")) {
    return { cancelled: false };
  }

  const result = await runner.emit({
    type: "session_before_fork",
    entryId,
    ...options,
  });
  return { cancelled: result?.cancel === true };
}
```

#### `teardownCurrent()` - 发出 session_shutdown
```typescript
private async teardownCurrent(
  reason: SessionShutdownEvent["reason"],
  targetSessionFile?: string
): Promise<void> {
  await emitSessionShutdownEvent(this.session.extensionRunner, {
    type: "session_shutdown",
    reason,
    targetSessionFile,
  });
  this.beforeSessionInvalidate?.();
  this.session.dispose();
}
```

**调用流程**:

```
switchSession()
    │
    ├─► emitBeforeSwitch("resume", sessionPath)
    │       │
    │       └─► runner.emit({ type: "session_before_switch" })
    │               │
    │               └─► extension handlers
    │               │
    │               └─► { cancel?: boolean }
    │
    ├─► if cancelled → return { cancelled: true }
    │
    ├─► teardownCurrent("resume", sessionManager.getSessionFile())
    │       │
    │       └─► emitSessionShutdownEvent({ type: "session_shutdown", reason: "resume" })
    │
    ├─► createRuntime() → 新的 AgentSession
    │
    ├─► emit({ type: "session_start", reason: "resume" })
    │
    └─► finishSessionReplacement()
```

---

### 3. Agent 运行层 (AgentSession)

**文件**: `agent-session.ts`

**职责**:
- 核心 Agent 抐象
- 管理 agent 循环、消息处理
- 监听 AgentEvent 并转换为 ExtensionEvent
- 管理 model、thinking level、compaction

**类定义**:
```typescript
export class AgentSession {
  readonly agent: Agent;              // @earendil-works/pi-agent-core 的 Agent
  readonly sessionManager: SessionManager;
  private _extensionRunner: ExtensionRunner;
  
  // 核心方法
  async prompt(text: string, options?: PromptOptions): Promise<void>;
  async setModel(model: Model<any>): Promise<void>;
  setThinkingLevel(level: ThinkingLevel): void;
  async compact(customInstructions?: string): Promise<CompactionResult>;
  async bindExtensions(bindings: ExtensionBindings): Promise<void>;
  async reload(): Promise<void>;
}
```

**事件发射点**:

#### `_handleAgentEvent()` - AgentEvent → ExtensionEvent 转换
```typescript
private _handleAgentEvent = async (event: AgentEvent): Promise<void> => {
  // 先发射到 extensions
  await this._emitExtensionEvent(event);
  
  // 再发射到 session listeners
  this._emit(event);
  
  // 处理 session persistence
  if (event.type === "message_end") {
    this.sessionManager.appendMessage(event.message);
  }
};
```

#### `_emitExtensionEvent()` - 详细的事件转换
```typescript
private async _emitExtensionEvent(event: AgentEvent): Promise<void> {
  if (event.type === "agent_start") {
    await this._extensionRunner.emit({ type: "agent_start" });
    
  } else if (event.type === "agent_end") {
    await this._extensionRunner.emit({ type: "agent_end", messages: event.messages });
    
  } else if (event.type === "turn_start") {
    await this._extensionRunner.emit({
      type: "turn_start",
      turnIndex: this._turnIndex,
      timestamp: Date.now(),
    });
    
  } else if (event.type === "turn_end") {
    await this._extensionRunner.emit({
      type: "turn_end",
      turnIndex: this._turnIndex,
      message: event.message,
      toolResults: event.toolResults,
    });
    this._turnIndex++;
    
  } else if (event.type === "message_start") {
    await this._extensionRunner.emit({
      type: "message_start",
      message: event.message,
    });
    
  } else if (event.type === "message_update") {
    await this._extensionRunner.emit({
      type: "message_update",
      message: event.message,
      assistantMessageEvent: event.assistantMessageEvent,
    });
    
  } else if (event.type === "message_end") {
    const replacement = await this._extensionRunner.emitMessageEnd({
      type: "message_end",
      message: event.message,
    });
    if (replacement) {
      this._replaceMessageInPlace(event.message, replacement);
    }
    
  } else if (event.type === "tool_execution_start") {
    await this._extensionRunner.emit({
      type: "tool_execution_start",
      toolCallId: event.toolCallId,
      toolName: event.toolName,
      args: event.args,
    });
    
  } else if (event.type === "tool_execution_update") {
    await this._extensionRunner.emit({
      type: "tool_execution_update",
      toolCallId: event.toolCallId,
      toolName: event.toolName,
      args: event.args,
      partialResult: event.partialResult,
    });
    
  } else if (event.type === "tool_execution_end") {
    await this._extensionRunner.emit({
      type: "tool_execution_end",
      toolCallId: event.toolCallId,
      toolName: event.toolName,
      result: event.result,
      isError: event.isError,
    });
  }
}
```

#### `_installAgentToolHooks()` - 工具调用拦截
```typescript
private _installAgentToolHooks(): void {
  // 工具调用前拦截
  this.agent.beforeToolCall = async ({ toolCall, args }) => {
    const runner = this._extensionRunner;
    if (!runner.hasHandlers("tool_call")) {
      return undefined;
    }

    return await runner.emitToolCall({
      type: "tool_call",
      toolName: toolCall.name,
      toolCallId: toolCall.id,
      input: args as Record<string, unknown>,
    });
  };

  // 工具调用后拦截
  this.agent.afterToolCall = async ({ toolCall, args, result, isError }) => {
    const runner = this._extensionRunner;
    if (!runner.hasHandlers("tool_result")) {
      return undefined;
    }

    return await runner.emitToolResult({
      type: "tool_result",
      toolName: toolCall.name,
      toolCallId: toolCall.id,
      input: args as Record<string, unknown>,
      content: result.content,
      details: result.details,
      isError,
    });
  };
}
```

#### `prompt()` - 发射 input 和 before_agent_start
```typescript
async prompt(text: string, options?: PromptOptions): Promise<void> {
  // 发射 input 事件（如果有 handler）
  if (this._extensionRunner.hasHandlers("input")) {
    const inputResult = await this._extensionRunner.emitInput(
      currentText,
      currentImages,
      options?.source ?? "interactive",
      this.isStreaming ? options?.streamingBehavior : undefined,
    );
    if (inputResult.action === "handled") return;
    if (inputResult.action === "transform") {
      currentText = inputResult.text;
      currentImages = inputResult.images ?? currentImages;
    }
  }
  
  // 发射 before_agent_start 事件
  const result = await this._extensionRunner.emitBeforeAgentStart(
    expandedText,
    currentImages,
    this._baseSystemPrompt,
    this._baseSystemPromptOptions,
  );
  
  // 应用 extension 返回的修改
  if (result?.messages) {
    messages.push(...result.messages);
  }
  if (result?.systemPrompt) {
    this.agent.state.systemPrompt = result.systemPrompt;
  }
  
  // 执行 agent prompt
  await this._runAgentPrompt(messages);
}
```

#### `setModel()` - 发射 model_select
```typescript
async setModel(model: Model<any>): Promise<void> {
  // 设置 model...
  
  await this._emitModelSelect(model, previousModel, "set");
}

private async _emitModelSelect(
  nextModel: Model<any>,
  previousModel: Model<any> | undefined,
  source: "set" | "cycle" | "restore",
): Promise<void> {
  await this._extensionRunner.emit({
    type: "model_select",
    model: nextModel,
    previousModel,
    source,
  });
}
```

#### `setThinkingLevel()` - 发射 thinking_level_select
```typescript
setThinkingLevel(level: ThinkingLevel): void {
  // 设置 thinking level...
  
  void this._extensionRunner.emit({
    type: "thinking_level_select",
    level: effectiveLevel,
    previousLevel,
  });
}
```

#### `compact()` - 发射 session_before_compact 和 session_compact
```typescript
async compact(customInstructions?: string): Promise<CompactionResult> {
  // 发射 session_before_compact（如果可以取消或自定义）
  if (this._extensionRunner.hasHandlers("session_before_compact")) {
    const result = await this._extensionRunner.emit({
      type: "session_before_compact",
      preparation,
      branchEntries: pathEntries,
      customInstructions,
      signal: this._compactionAbortController.signal,
    });
    
    if (result?.cancel) throw new Error("Compaction cancelled");
    if (result?.compaction) {
      // 使用 extension 提供的 compaction 结果
    }
  }
  
  // 执行 compaction...
  
  // 发射 session_compact
  await this._extensionRunner.emit({
    type: "session_compact",
    compactionEntry: savedCompactionEntry,
    fromExtension,
  });
}
```

#### `bindExtensions()` - 发射 session_start 和 resources_discover
```typescript
async bindExtensions(bindings: ExtensionBindings): Promise<void> {
  // 应用 bindings...
  
  // 发射 session_start
  await this._extensionRunner.emit(this._sessionStartEvent);
  
  // 发射 resources_discover（如果需要）
  await this.extendResourcesFromExtensions(
    this._sessionStartEvent.reason === "reload" ? "reload" : "startup"
  );
}

private async extendResourcesFromExtensions(reason: "startup" | "reload"): Promise<void> {
  if (!this._extensionRunner.hasHandlers("resources_discover")) return;

  const { skillPaths, promptPaths, themePaths } = 
    await this._extensionRunner.emitResourcesDiscover(this._cwd, reason);

  // 添加到 resource loader...
}
```

#### `reload()` - 发射 session_shutdown 和 session_start
```typescript
async reload(): Promise<void> {
  await emitSessionShutdownEvent(this._extensionRunner, {
    type: "session_shutdown",
    reason: "reload"
  });
  
  await this.settingsManager.reload();
  await this._resourceLoader.reload();
  this._buildRuntime({ ... });
  
  await this._extensionRunner.emit({ type: "session_start", reason: "reload" });
  await this.extendResourcesFromExtensions("reload");
}
```

---

### 4. 事件发射层 (ExtensionRunner)

**文件**: `runner.ts`

**职责**:
- 执行 extension handlers
- 处理事件返回结果
- 管理不同的事件处理模式

**方法分类**:

| 方法 | 事件类型 | 处理模式 |
|------|----------|----------|
| `emit()` | RunnerEmitEvent | 简单广播 / 可取消 |
| `emitToolCall()` | ToolCallEvent | 阻断模式 |
| `emitToolResult()` | ToolResultEvent | 链式修改 |
| `emitMessageEnd()` | MessageEndEvent | 链式修改+校验 |
| `emitContext()` | ContextEvent | 链式修改+深拷贝 |
| `emitInput()` | InputEvent | 多模式（transform/handled） |
| `emitBeforeAgentStart()` | BeforeAgentStartEvent | 复杂参数+动态 context |
| `emitResourcesDiscover()` | ResourcesDiscoverEvent | 收集模式 |
| `emitUserBash()` | UserBashEvent | 简单返回 |
| `emitBeforeProviderRequest()` | BeforeProviderRequestEvent | 链式替换 |

---

## 三、事件来源完整映射表

| 事件类型 | 发射位置 | 发射时机 | 处理方法 |
|----------|----------|----------|----------|
| **Session 事件** |
| `session_start` | `AgentSession.bindExtensions()` | 扩展绑定后 | `emit()` |
| `session_before_switch` | `AgentSessionRuntime.emitBeforeSwitch()` | 会话切换前 | `emit()` |
| `session_before_fork` | `AgentSessionRuntime.emitBeforeFork()` | Fork 前 | `emit()` |
| `session_before_compact` | `AgentSession.compact()` | 压缩前 | `emit()` |
| `session_before_tree` | `AgentSession.navigateTree()` | 树导航前 | `emit()` |
| `session_compact` | `AgentSession.compact()` | 压缩完成 | `emit()` |
| `session_shutdown` | `AgentSessionRuntime.teardownCurrent()` | 会话关闭 | `emitSessionShutdownEvent()` |
| `session_tree` | `AgentSession.navigateTree()` | 树导航完成 | `emit()` |
| **Agent 事件** |
| `agent_start` | `AgentSession._emitExtensionEvent()` | Agent 循环开始 | `emit()` |
| `agent_end` | `AgentSession._emitExtensionEvent()` | Agent 循环结束 | `emit()` |
| `turn_start` | `AgentSession._emitExtensionEvent()` | Turn 开始 | `emit()` |
| `turn_end` | `AgentSession._emitExtensionEvent()` | Turn 结束 | `emit()` |
| `before_agent_start` | `AgentSession.prompt()` | Prompt 发送前 | `emitBeforeAgentStart()` |
| **Message 事件** |
| `message_start` | `AgentSession._emitExtensionEvent()` | 消息开始 | `emit()` |
| `message_update` | `AgentSession._emitExtensionEvent()` | 消息更新（流式） | `emit()` |
| `message_end` | `AgentSession._emitExtensionEvent()` | 消息结束 | `emitMessageEnd()` |
| **Tool 事件** |
| `tool_call` | `AgentSession._installAgentToolHooks()` | 工具调用前 | `emitToolCall()` |
| `tool_result` | `AgentSession._installAgentToolHooks()` | 工具调用后 | `emitToolResult()` |
| `tool_execution_start` | `AgentSession._emitExtensionEvent()` | 工具执行开始 | `emit()` |
| `tool_execution_update` | `AgentSession._emitExtensionEvent()` | 工具执行更新 | `emit()` |
| `tool_execution_end` | `AgentSession._emitExtensionEvent()` | 工具执行结束 | `emit()` |
| **Model 事件** |
| `model_select` | `AgentSession._emitModelSelect()` | 模型选择 | `emit()` |
| `thinking_level_select` | `AgentSession.setThinkingLevel()` | 思考级别选择 | `emit()` |
| **Input 事件** |
| `input` | `AgentSession.prompt()` | 输入处理前 | `emitInput()` |
| **Provider 事件** |
| `before_provider_request` | Agent 核心 | Provider 请求前 | `emitBeforeProviderRequest()` |
| `after_provider_response` | Agent 核心 | Provider 响应后 | `emit()` |
| **Context 事件** |
| `context` | Agent 核心 | 上下文构建 | `emitContext()` |
| **Resource 事件** |
| `resources_discover` | `AgentSession.extendResourcesFromExtensions()` | 资源发现 | `emitResourcesDiscover()` |
| **User Bash 事件** |
| `user_bash` | Interactive mode | 用户 bash 命令 | `emitUserBash()` |
| **Project Trust 事件** |
| `project_trust` | SDK 启动 | 项目信任检查 | `emitProjectTrustEvent()` |

---

## 四、Agent 事件到 Extension 事件的转换流程

```
┌─────────────────────────────────────────────────────────────┐
│                   Agent Core (@pi-agent-core)                │
│                                                              │
│  发出 AgentEvent:                                            │
│  • agent_start                                               │
│  • agent_end                                                 │
│  • turn_start                                                │
│  • turn_end                                                  │
│  • message_start                                             │
│  • message_update                                            │
│  • message_end                                               │
│  • tool_execution_start                                      │
│  • tool_execution_update                                     │
│  • tool_execution_end                                        │
│                                                              │
│  提供 Hooks:                                                 │
│  • beforeToolCall                                            │
│  • afterToolCall                                             │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ agent.subscribe(handler)
                              │ agent.beforeToolCall = hook
                              │ agent.afterToolCall = hook
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    AgentSession                              │
│                                                              │
│  _handleAgentEvent(event: AgentEvent):                       │
│    → _emitExtensionEvent(event)                              │
│    → _emit(event) to session listeners                       │
│    → sessionManager.appendMessage()                          │
│                                                              │
│  _installAgentToolHooks():                                   │
│    → agent.beforeToolCall → emitToolCall()                   │
│    → agent.afterToolCall → emitToolResult()                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   ExtensionRunner                            │
│                                                              │
│  根据事件类型选择发射方法:                                     │
│  • 简单事件 → emit()                                         │
│  • message_end → emitMessageEnd()                            │
│  • tool_call → emitToolCall()                                │
│  • tool_result → emitToolResult()                            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Extension Handlers                         │
│                                                              │
│  pi.on("event_type", (event, ctx) => {                       │
│    // 处理事件                                                │
│    return result; // 可选                                    │
│  });                                                         │
└─────────────────────────────────────────────────────────────┘
```

---

## 五、关键设计点

### 1. 事件转换层 (AgentSession)

**AgentSession 是事件转换的核心**：
- 监听 Agent Core 的 AgentEvent
- 转换为 ExtensionEvent
- 选择正确的发射方法

### 2. 两类事件的分层

| 层级 | 通用事件 (emit) | 专门事件 (emitXxx) |
|------|-----------------|-------------------|
| AgentSessionRuntime | `session_before_*`, `session_shutdown` | 无 |
| AgentSession | `agent_start/end`, `turn_*`, `message_start/update`, `tool_execution_*`, `model_select`, `thinking_level_select` | `message_end`, `tool_call`, `tool_result`, `input`, `before_agent_start`, `context`, `resources_discover` |

### 3. Hook vs Event

| 类型 | 说明 | 示例 |
|------|------|------|
| **Agent Hook** | Agent Core 提供的拦截点 | `beforeToolCall`, `afterToolCall` |
| **Extension Event** | ExtensionRunner 发出的通知 | `tool_call`, `tool_result` |

Hook 是 Agent Core 的机制，Event 是 Extension 系统的机制。AgentSession 通过 Hook 捕获并转换为 Event。

### 4. 事件来源分类

| 来源 | 事件 |
|------|------|
| **AgentSessionRuntime** | session_before_switch, session_before_fork, session_shutdown |
| **AgentSession.prompt()** | input, before_agent_start |
| **AgentSession._handleAgentEvent()** | agent_start, agent_end, turn_start, turn_end, message_start, message_update, message_end, tool_execution_* |
| **AgentSession._installAgentToolHooks()** | tool_call, tool_result |
| **AgentSession 模型管理** | model_select, thinking_level_select |
| **AgentSession 压缩** | session_before_compact, session_compact |
| **AgentSession 绑定** | session_start, resources_discover |
| **AgentSession.reload()** | session_shutdown (reason: reload), session_start (reason: reload) |

---

## 六、总结

整个事件系统的调用层级：

```
Modes (用户交互)
    │
    ▼
AgentSessionRuntime (会话管理)
    │ → emit session_before_*, session_shutdown
    │
    ▼
AgentSession (Agent 运行)
    │ → 监听 AgentEvent
    │ → 转换为 ExtensionEvent
    │ → 选择 emit 或 emitXxx
    │ → emit input, before_agent_start, model_select, etc.
    │
    ▼
ExtensionRunner (事件发射)
    │ → 执行 handlers
    │ → 处理返回结果
    │
    ▼
Extensions (用户代码)
```

**关键点**：
- AgentSessionRuntime 处理会话生命周期事件
- AgentSession 处理 agent 运行时事件
- ExtensionRunner 执行具体的事件分发
- 不同事件类型有不同的处理模式和方法