# Extension事件系统的整体架构 设计分析

本文档详细分析 `RunnerEmitEvent` 和 `ExtensionEvent` 的设计差异，以及事件系统的整体架构。

---

## 一、核心问题解答

### 1. 为什么 `ToolCallEvent` 等事件要单独列出？

**不是冗余，而是有意的设计**。

关键注释（runner.ts:117-119）：
```typescript
/**
 * Events handled by the generic emit() method.
 * Events with dedicated emitXxx() methods are excluded for stronger type safety.
 */
```

- `RunnerEmitEvent` 用于**通用的 `emit()` 方法**
- 被排除的事件有**专门的 emit 方法**
- 目的是**更强的类型安全**——编译器强制你使用正确的专门方法

### 2. 为什么 `MessageEndEvent` 单独列出？

`emitMessageEnd()` 需要特殊处理：

1. **链式修改** - 每个 handler 看到前一个修改后的消息
2. **校验逻辑** - 必须验证消息 `role` 不能改变
3. **返回类型不同** - 返回 `AgentMessage | undefined`，而非普通 Result 结构

---

## 二、整体架构

### 两层事件类型关系图

```
┌─────────────────────────────────────────────────────────────────┐
│                    ExtensionEvent (完整集合)                      │
│  所有事件的联合类型，用于扩展 API 的 on() 方法签名                  │
│                                                                  │
│  = SessionEvent                                                  │
│  | ContextEvent                                                  │
│  | BeforeProviderRequestEvent                                    │
│  | AfterProviderResponseEvent                                    │
│  | BeforeAgentStartEvent                                         │
│  | AgentStartEvent                                               │
│  | AgentEndEvent                                                 │
│  | TurnStartEvent                                                │
│  | TurnEndEvent                                                  │
│  | MessageStartEvent                                             │
│  | MessageUpdateEvent                                            │
│  | MessageEndEvent                                               │
│  | ToolExecutionStartEvent                                       │
│  | ToolExecutionUpdateEvent                                      │
│  | ToolExecutionEndEvent                                         │
│  | ModelSelectEvent                                              │
│  | ThinkingLevelSelectEvent                                      │
│  | UserBashEvent                                                 │
│  | InputEvent                                                    │
│  | ToolCallEvent                                                 │
│  | ToolResultEvent                                               │
│  | ProjectTrustEvent                                             │
│  | ResourcesDiscoverEvent                                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ Exclude<...>
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   RunnerEmitEvent (简化集合)                     │
│  用于通用 emit() 方法，排除需要专门处理的事件                       │
│                                                                  │
│  = ExtensionEvent 排除以下事件:                                   │
│    - ToolCallEvent           (有 emitToolCall)                   │
│    - ProjectTrustEvent       (有 emitProjectTrustEvent)          │
│    - ToolResultEvent         (有 emitToolResult)                 │
│    - UserBashEvent           (有 emitUserBash)                   │
│    - ContextEvent            (有 emitContext)                    │
│    - BeforeProviderRequestEvent (有 emitBeforeProviderRequest)   │
│    - BeforeAgentStartEvent   (有 emitBeforeAgentStart)           │
│    - MessageEndEvent         (有 emitMessageEnd)                 │
│    - ResourcesDiscoverEvent  (有 emitResourcesDiscover)          │
│    - InputEvent              (有 emitInput)                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## 三、事件处理模式分类

### 核心原因：不同的「事件处理模式」

| 模式 | 特点 | 适用事件 | 处理方法 |
|------|------|----------|----------|
| **简单广播** | 只是通知，无返回值 | `session_start`, `agent_start`, `model_select` 等 | `emit()` |
| **可取消** | handler 可以取消操作 | `session_before_*` 系列 | `emit()` |
| **链式修改** | 每个 handler 看到前一个修改后的数据 | `message_end`, `tool_result`, `context` | 专门方法 |
| **阻断/短路** | handler 可以终止流程 | `tool_call` (block), `input` (handled) | 专门方法 |
| **收集** | 收集所有 handler 的返回值 | `resources_discover` | 专门方法 |
| **复杂参数/返回** | 需要额外参数或复杂返回结构 | `before_agent_start` | 专门方法 |

---

## 四、专门方法详细分析

### 1. `emitToolCall()` — 阻断模式

**代码位置**: runner.ts:862-883

```typescript
async emitToolCall(event: ToolCallEvent): Promise<ToolCallEventResult | undefined> {
  const ctx = this.createContext();
  let result: ToolCallEventResult | undefined;

  for (const ext of this.extensions) {
    const handlers = ext.handlers.get("tool_call");
    if (!handlers || handlers.length === 0) continue;

    for (const handler of handlers) {
      const handlerResult = await handler(event, ctx);

      if (handlerResult) {
        result = handlerResult as ToolCallEventResult;
        if (result.block) {          // ⚠️ 关键：一旦 block=true，立即返回
          return result;              // 不继续执行后续 handlers
        }
      }
    }
  }

  return result;
}
```

**返回类型**:
```typescript
interface ToolCallEventResult {
  block?: boolean;    // 阻止工具执行
  reason?: string;    // 阻止原因
}
```

**特殊逻辑**:
- **短路机制**: 一旦某个 extension 返回 `block: true`，立即停止
- 不继续调用后续 handlers
- 工具执行被阻止

**为什么不能用通用 emit()**:
- 通用 emit() 无法表达「阻断」语义
- 返回类型完全不匹配

---

### 2. `emitToolResult()` — 链式修改模式

**代码位置**: runner.ts:812-860

```typescript
async emitToolResult(event: ToolResultEvent): Promise<ToolResultEventResult | undefined> {
  const ctx = this.createContext();
  const currentEvent: ToolResultEvent = { ...event };  // 🔑 可变的副本
  let modified = false;

  for (const ext of this.extensions) {
    const handlers = ext.handlers.get("tool_result");
    if (!handlers || handlers.length === 0) continue;

    for (const handler of handlers) {
      const handlerResult = (await handler(currentEvent, ctx)) as ToolResultEventResult | undefined;
      if (!handlerResult) continue;

      // ⚠️ 链式修改：每个 handler 可以修改，后续 handler 看到修改后的结果
      if (handlerResult.content !== undefined) {
        currentEvent.content = handlerResult.content;
        modified = true;
      }
      if (handlerResult.details !== undefined) {
        currentEvent.details = handlerResult.details;
        modified = true;
      }
      if (handlerResult.isError !== undefined) {
        currentEvent.isError = handlerResult.isError;
        modified = true;
      }
    }
  }

  if (!modified) return undefined;

  return {
    content: currentEvent.content,
    details: currentEvent.details,
    isError: currentEvent.isError,
  };
}
```

**返回类型**:
```typescript
interface ToolResultEventResult {
  content?: (TextContent | ImageContent)[];  // 替换内容
  details?: unknown;                         // 替换详情
  isError?: boolean;                         // 替换错误状态
}
```

**特殊逻辑**:
- **链式传递**: `currentEvent` 是可变的，每个 handler 修改后，下一个 handler 看到修改后的值
- **修改追踪**: 使用 `modified` 标记是否有实际修改

---

### 3. `emitMessageEnd()` — 链式修改 + 校验模式

**代码位置**: runner.ts:770-810

```typescript
async emitMessageEnd(event: MessageEndEvent): Promise<AgentMessage | undefined> {
  const ctx = this.createContext();
  let currentMessage = event.message;  // 🔑 需要链式传递的消息
  let modified = false;

  for (const ext of this.extensions) {
    const handlers = ext.handlers.get("message_end");
    if (!handlers || handlers.length === 0) continue;

    for (const handler of handlers) {
      try {
        // ⚠️ 每个 handler 看到的是前一个修改后的消息
        const currentEvent: MessageEndEvent = { ...event, message: currentMessage };
        const handlerResult = (await handler(currentEvent, ctx)) as MessageEndEventResult | undefined;
        if (!handlerResult?.message) continue;

        // ⚠️ 校验：role 不能改变
        if (handlerResult.message.role !== currentMessage.role) {
          this.emitError({
            extensionPath: ext.path,
            event: "message_end",
            error: "message_end handlers must return a message with the same role",
          });
          continue;  // 校验失败，跳过这个 handler 的修改
        }

        currentMessage = handlerResult.message;  // 链式传递
        modified = true;
      } catch (err) {
        // 错误处理...
      }
    }
  }

  return modified ? currentMessage : undefined;  // 只有修改过才返回
}
```

**返回类型**:
```typescript
interface MessageEndEventResult {
  message?: AgentMessage;  // 替换消息（必须保持相同 role）
}
```

**特殊逻辑**:
- **链式修改**: 每个 handler 可以修改消息
- **校验**: 必须验证 `role` 不能改变
- **返回类型独特**: 直接返回 `AgentMessage | undefined`

---

### 4. `emitContext()` — 链式修改 + 深拷贝

**代码位置**: runner.ts:914-944

```typescript
async emitContext(messages: AgentMessage[]): Promise<AgentMessage[]> {
  const ctx = this.createContext();
  let currentMessages = structuredClone(messages);  // 🔑 深拷贝，避免修改原数组

  for (const ext of this.extensions) {
    const handlers = ext.handlers.get("context");
    if (!handlers || handlers.length === 0) continue;

    for (const handler of handlers) {
      try {
        const event: ContextEvent = { type: "context", messages: currentMessages };
        const handlerResult = await handler(event, ctx);

        if (handlerResult && (handlerResult as ContextEventResult).messages) {
          currentMessages = (handlerResult as ContextEventResult).messages!;  // 链式替换
        }
      } catch (err) {
        // 错误处理...
      }
    }
  }

  return currentMessages;  // 返回最终修改后的消息数组
}
```

**特殊逻辑**:
- **深拷贝**: 使用 `structuredClone()` 避免修改原始消息数组
- **链式替换**: 每个 handler 可以完全替换消息数组
- **返回类型**: `AgentMessage[]`

---

### 5. `emitInput()` — 多模式（transform + handled）

**代码位置**: runner.ts:1094-1134

```typescript
async emitInput(
  text: string,
  images: ImageContent[] | undefined,
  source: InputSource,
  streamingBehavior?: "steer" | "followUp",
): Promise<InputEventResult> {
  const ctx = this.createContext();
  let currentText = text;
  let currentImages = images;

  for (const ext of this.extensions) {
    for (const handler of ext.handlers.get("input") ?? []) {
      try {
        const event: InputEvent = {
          type: "input",
          text: currentText,
          images: currentImages,
          source,
          streamingBehavior,
        };
        const result = (await handler(event, ctx)) as InputEventResult | undefined;
        
        // ⚠️ 短路：handled 立即终止
        if (result?.action === "handled") return result;
        
        // ⚠️ 链式修改：transform 可以修改 text/images
        if (result?.action === "transform") {
          currentText = result.text;
          currentImages = result.images ?? currentImages;
        }
      } catch (err) {
        // 错误处理...
      }
    }
  }
  
  return currentText !== text || currentImages !== images
    ? { action: "transform", text: currentText, images: currentImages }
    : { action: "continue" };
}
```

**返回类型**:
```typescript
type InputEventResult =
  | { action: "continue" }                      // 继续处理
  | { action: "transform"; text: string; images?: ImageContent[] }  // 修改输入
  | { action: "handled" };                      // 完全处理，短路
```

**特殊逻辑**:
- **三种返回模式**: continue、transform、handled
- **短路**: `handled` 立即终止
- **链式修改**: `transform` 可以修改 text/images
- **额外参数**: 需要 `source`, `streamingBehavior`

---

### 6. `emitBeforeAgentStart()` — 复杂返回 + 动态 context

**代码位置**: runner.ts:980-1044

```typescript
async emitBeforeAgentStart(
  prompt: string,
  images: ImageContent[] | undefined,
  systemPrompt: string,
  systemPromptOptions: BuildSystemPromptOptions,
): Promise<BeforeAgentStartCombinedResult | undefined> {
  let currentSystemPrompt = systemPrompt;
  
  // ⚠️ 动态 context：getSystemPrompt() 返回当前修改后的值
  const ctx = Object.defineProperties(
    {},
    Object.getOwnPropertyDescriptors(this.createContext()),
  ) as ExtensionContext;
  ctx.getSystemPrompt = () => {
    this.assertActive();
    return currentSystemPrompt;  // 🔑 动态返回当前值
  };
  
  const messages: NonNullable<BeforeAgentStartEventResult["message"]>[] = [];
  let systemPromptModified = false;

  for (const ext of this.extensions) {
    // ...
    const handlerResult = await handler(event, ctx);

    if (handlerResult) {
      const result = handlerResult as BeforeAgentStartEventResult;
      if (result.message) {
        messages.push(result.message);  // 收集所有消息
      }
      if (result.systemPrompt !== undefined) {
        currentSystemPrompt = result.systemPrompt;  // 链式修改
        systemPromptModified = true;
      }
    }
  }

  // 返回复杂结构
  if (messages.length > 0 || systemPromptModified) {
    return {
      messages: messages.length > 0 ? messages : undefined,
      systemPrompt: systemPromptModified ? currentSystemPrompt : undefined,
    };
  }

  return undefined;
}
```

**特殊逻辑**:
- **动态 context**: `ctx.getSystemPrompt()` 返回当前修改后的值（不是初始值）
- **收集 + 链式**: 收集所有 `messages`，链式修改 `systemPrompt`
- **复杂返回**: `{ messages[], systemPrompt }`
- **多参数**: 需要 4 个参数

---

### 7. `emitResourcesDiscover()` — 收集所有结果

**代码位置**: runner.ts:1046-1092

```typescript
async emitResourcesDiscover(
  cwd: string,
  reason: ResourcesDiscoverEvent["reason"],
): Promise<{
  skillPaths: Array<{ path: string; extensionPath: string }>;
  promptPaths: Array<{ path: string; extensionPath: string }>;
  themePaths: Array<{ path: string; extensionPath: string }>;
}> {
  const ctx = this.createContext();
  const skillPaths: Array<{ path: string; extensionPath: string }> = [];
  const promptPaths: Array<{ path: string; extensionPath: string }> = [];
  const themePaths: Array<{ path: string; extensionPath: string }> = [];

  for (const ext of this.extensions) {
    // ...
    if (result?.skillPaths?.length) {
      skillPaths.push(...result.skillPaths.map((path) => ({ path, extensionPath: ext.path })));
    }
    if (result?.promptPaths?.length) {
      promptPaths.push(...result.promptPaths.map((path) => ({ path, extensionPath: ext.path })));
    }
    if (result?.themePaths?.length) {
      themePaths.push(...result.themePaths.map((path) => ({ path, extensionPath: ext.path })));
    }
  }

  return { skillPaths, promptPaths, themePaths };  // ⚠️ 收集所有 extension 的贡献
}
```

**特殊逻辑**:
- **收集模式**: 不是链式修改，而是**收集所有 extension 返回的路径**
- **来源标记**: 每个路径记录 `extensionPath`
- **返回类型**: 包含三个数组的复杂对象

---

### 8. 其他专门方法

| 方法 | 返回类型 | 特殊逻辑 |
|------|----------|----------|
| `emitUserBash()` | `UserBashEventResult` | 返回自定义操作或完整结果 |
| `emitBeforeProviderRequest()` | `unknown` | 链式替换 payload |
| `emitProjectTrustEvent()` (独立函数) | `ProjectTrustEventResult` | 专门上下文，独立函数 |

---

## 五、通用 emit() 处理的"通常事件"

### 实现

```typescript
// runner.ts:736-768
async emit<TEvent extends RunnerEmitEvent>(event: TEvent): Promise<RunnerEmitResult<TEvent>> {
  const ctx = this.createContext();
  let result: SessionBeforeEventResult | undefined;

  for (const ext of this.extensions) {
    const handlers = ext.handlers.get(event.type);
    if (!handlers || handlers.length === 0) continue;

    for (const handler of handlers) {
      try {
        const handlerResult = await handler(event, ctx);

        // ⚠️ 只有 session_before_* 事件会处理返回值
        if (this.isSessionBeforeEvent(event) && handlerResult) {
          result = handlerResult as SessionBeforeEventResult;
          if (result.cancel) {           // 如果取消，立即返回
            return result as RunnerEmitResult<TEvent>;
          }
        }
      } catch (err) {
        // emitError...
      }
    }
  }

  return result as RunnerEmitResult<TEvent>;
}
```

### RunnerEmitEvent 包含的事件

#### 模式 A：纯广播（无返回值）

```typescript
// 这些事件 handler 返回 void 或 undefined
type: "session_start" | "agent_start" | "agent_end" | 
      "turn_start" | "turn_end" | 
      "message_start" | "message_update" | 
      "tool_execution_start" | "tool_execution_update" | "tool_execution_end" |
      "model_select" | "thinking_level_select" | 
      "session_compact" | "session_shutdown" | "session_tree" |
      "after_provider_response"
```

**特点**:
- handler 返回值被忽略
- 所有 handler 都会被调用（不会短路）
- 只用于通知/日志/统计等用途

**示例**:
```typescript
pi.on("agent_start", (event, ctx) => {
  console.log("Agent started!");
});

pi.on("model_select", (event, ctx) => {
  ctx.ui.notify(`Switched to ${event.model.name}`);
});
```

#### 模式 B：可取消的 "before" 事件

```typescript
type: "session_before_switch" | "session_before_fork" | 
      "session_before_compact" | "session_before_tree"
```

**特点**:
- handler 返回 `{ cancel?: boolean }`
- `cancel=true` 立即停止，操作被取消

**返回类型推断**:
```typescript
type RunnerEmitResult<TEvent extends RunnerEmitEvent> = 
  TEvent extends { type: "session_before_switch" }
    ? SessionBeforeSwitchResult | undefined
  : TEvent extends { type: "session_before_fork" }
    ? SessionBeforeForkResult | undefined
  : TEvent extends { type: "session_before_compact" }
    ? SessionBeforeCompactResult | undefined
  : TEvent extends { type: "session_before_tree" }
    ? SessionBeforeTreeResult | undefined
  : undefined;  // 其他事件返回 undefined
```

**示例**:
```typescript
pi.on("session_before_switch", async (event, ctx) => {
  const confirmed = await ctx.ui.confirm(
    "Switch Session?",
    `About to switch to ${event.targetSessionFile}. Continue?`
  );
  
  if (!confirmed) {
    return { cancel: true };  // ⚠️ 取消操作
  }
});
```

---

## 六、通用 emit() 调用流程图

```
┌─────────────────────────────────────────────────────────────┐
│                    runner.emit(event)                        │
└─────────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│              createContext() 创建上下文                       │
└─────────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│          遍历所有 extensions                                  │
│   for (const ext of this.extensions)                         │
└─────────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│      获取该事件类型的 handlers                                 │
│   ext.handlers.get(event.type)                               │
└─────────────────────────────────────────────────────────────┘
                        │
            ┌───────────┴───────────┐
            │                       │
     无 handlers              有 handlers
            │                       │
            ▼                       ▼
      跳过该 extension    ┌─────────────────────────────────┐
                          │  遍历所有 handlers               │
                          │  for (const handler of handlers) │
                          └─────────────────────────────────┘
                                      │
                                      ▼
                          ┌─────────────────────────────────┐
                          │   await handler(event, ctx)     │
                          └─────────────────────────────────┘
                                      │
                          ┌───────────┴───────────┐
                          │                       │
                    抛出错误                  正常返回
                          │                       │
                          ▼                       ▼
                  emitError() 记录     ┌─────────────────────────┐
                                      │ 是否是 session_before_* │
                                      └─────────────────────────┘
                                      │
                          ┌───────────┴───────────┐
                          │                       │
                        是                      否
                          │                       │
                          ▼                       ▼
               ┌─────────────────────┐     handlerResult 被忽略
               │ 检查 result.cancel  │     继续下一个 handler
               └─────────────────────┘
                          │
               ┌──────────┴──────────┐
               │                     │
          cancel=true           cancel=false
               │                     │
               ▼                     ▼
      立即返回 result        继续下一个 handler
      (短路终止)
                          │
                          ▼ (遍历完成后)
               ┌─────────────────────────────────┐
               │  返回 result 或 undefined        │
               └─────────────────────────────────┘
```

---

## 七、完整事件分类对比表

| 分类 | 事件 | 处理方法 | 返回值 | 特点 |
|------|------|----------|--------|------|
| **纯广播** | `agent_start`, `agent_end`, `turn_start`, `turn_end`, `message_start`, `message_update`, `tool_execution_start/update/end`, `model_select`, `thinking_level_select`, `session_compact`, `session_shutdown`, `session_tree`, `session_start`, `after_provider_response` | `emit()` | `undefined` | 只是通知，无返回值 |
| **可取消** | `session_before_switch`, `session_before_fork`, `session_before_compact`, `session_before_tree` | `emit()` | `{ cancel?: boolean }` | 可以取消操作 |
| **链式修改** | `message_end`, `tool_result`, `context` | 专门方法 | 修改后的数据 | 每个 handler 看到前一个的修改 |
| **阻断** | `tool_call`, `input` | 专门方法 | `{ block/handled }` | 可以短路终止 |
| **复杂** | `before_agent_start`, `resources_discover` | 专门方法 | 复杂结构 | 收集多个值/特殊参数 |

---

## 八、类型安全机制

### TypeScript `Exclude` 类型

```typescript
type RunnerEmitEvent = Exclude<ExtensionEvent, ToolCallEvent | ...>;
```

**效果**: 如果尝试用 `emit()` 调用 `ToolCallEvent`，编译器会报错：

```typescript
// ❌ 编译错误！ToolCallEvent 不在 RunnerEmitEvent 中
runner.emit({ type: "tool_call", toolName: "bash", toolCallId: "123", input: {...} });

// ✅ 正确！必须使用专门的 emitToolCall()
runner.emitToolCall({ type: "tool_call", toolName: "bash", ... });
```

### 通用 emit() 的类型签名

```typescript
async emit<TEvent extends RunnerEmitEvent>(
  event: TEvent
): Promise<RunnerEmitResult<TEvent>>
```

- 参数 `event` 必须是 `RunnerEmitEvent` 的子类型
- 返回值根据事件类型自动推断

---

## 九、设计原则总结

1. **类型安全优先**
   - 用 `Exclude` 类型强制调用者使用正确的方法
   - 编译时检查，避免运行时错误

2. **语义清晰**
   - 不同事件有不同的处理语义（广播、链式、阻断、收集）
   - 每种语义有对应的方法签名

3. **单一职责**
   - 通用 `emit()` 只处理两种基本模式
   - 每个专门方法只处理一种复杂模式

4. **简单优先**
   - 简单事件用简单方法
   - 复杂事件才用专门方法
   - "简单的事情简单做，复杂的事情专门做"

5. **可扩展性**
   - 新增简单事件直接加入 `ExtensionEvent`
   - 新增复杂事件添加专门方法并从 `RunnerEmitEvent` 排除

---

## 十、实际使用示例

### 纯广播事件 - 统计用途

```typescript
pi.on("turn_start", (event, ctx) => {
  console.log(`Turn ${event.turnIndex} started at ${event.timestamp}`);
});

pi.on("tool_execution_end", (event, ctx) => {
  if (event.isError) {
    ctx.ui.notify(`Tool ${event.toolName} failed`, "error");
  }
});

pi.on("model_select", (event, ctx) => {
  ctx.ui.setStatus("model", `Model: ${event.model.name}`);
});
```

### 可取消事件 - 用户确认

```typescript
pi.on("session_before_switch", async (event, ctx) => {
  const proceed = await ctx.ui.confirm(
    "Switch Session?",
    `Switching to ${event.targetSessionFile || "new session"}`
  );
  return { cancel: !proceed };
});

pi.on("session_before_compact", (event, ctx) => {
  if (event.branchEntries.length < 10) {
    return { cancel: true };  // 条件性取消
  }
});
```

### 链式修改事件

```typescript
// 修改工具结果
pi.on("tool_result", (event, ctx) => {
  if (event.toolName === "bash") {
    // 可以修改内容、详情或错误状态
    return {
      content: [{ type: "text", text: "Modified output..." }],
      isError: false,
    };
  }
});

// 修改消息（必须保持 role）
pi.on("message_end", (event, ctx) => {
  if (event.message.role === "assistant") {
    return {
      message: {
        ...event.message,
        content: [{ type: "text", text: "Modified response..." }],
      },
    };
  }
});
```

### 阻断事件

```typescript
// 阻止工具执行
pi.on("tool_call", (event, ctx) => {
  if (event.toolName === "bash" && event.input.command.includes("rm")) {
    return {
      block: true,
      reason: "Dangerous command blocked",
    };
  }
});

// 处理输入（短路）
pi.on("input", (event, ctx) => {
  if (event.text.startsWith("/custom ")) {
    // 自定义处理
    return { action: "handled" };
  }
  // 转换输入
  return { action: "transform", text: event.text.toUpperCase() };
});
```

---

## 附录：类型定义速查

### RunnerEmitEvent

```typescript
type RunnerEmitEvent = Exclude<
  ExtensionEvent,
  | ToolCallEvent
  | ProjectTrustEvent
  | ToolResultEvent
  | UserBashEvent
  | ContextEvent
  | BeforeProviderRequestEvent
  | BeforeAgentStartEvent
  | MessageEndEvent
  | ResourcesDiscoverEvent
  | InputEvent
>;
```

### SessionBeforeEvent

```typescript
type SessionBeforeEvent = Extract<
  RunnerEmitEvent,
  { type: "session_before_switch" | "session_before_fork" | 
          "session_before_compact" | "session_before_tree" }
>;
```

### RunnerEmitResult

```typescript
type RunnerEmitResult<TEvent extends RunnerEmitEvent> = 
  TEvent extends { type: "session_before_switch" }
    ? SessionBeforeSwitchResult | undefined
  : TEvent extends { type: "session_before_fork" }
    ? SessionBeforeForkResult | undefined
  : TEvent extends { type: "session_before_compact" }
    ? SessionBeforeCompactResult | undefined
  : TEvent extends { type: "session_before_tree" }
    ? SessionBeforeTreeResult | undefined
  : undefined;
```