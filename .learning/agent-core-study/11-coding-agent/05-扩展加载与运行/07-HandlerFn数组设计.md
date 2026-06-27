---
name: handlerfn-array-design
description: HandlerFn[] 数组的设计意图 - 多订阅者支持、执行顺序、取消机制、链式处理
---

# HandlerFn[] 数组的设计意图

## 一、核心问题：为什么是数组而不是单个函数？

```typescript
interface Extension {
  handlers: Map<string, HandlerFn[]>;  // 为什么是数组？
}

type HandlerFn = (...args: unknown[]) => Promise<unknown>;
```

**答案**：同一个事件可以有多个处理器（多订阅者模式）

### 场景 1：一个扩展注册多个相同事件的处理器

```typescript
// event-bus.ts 示例
export default function (pi: ExtensionAPI) {
  // 第一次注册 session_start
  pi.on("session_start", async (_event, ctx) => {
    currentCtx = ctx;  // 保存 context
  });

  // 第二次注册 session_start（同一个事件！）
  pi.on("session_start", async () => {
    pi.events.emit("my:notification", {
      message: "Session started",
      from: "event-bus-example",
    });
  });
}

// 结果：handlers["session_start"] = [handler1, handler2]
```

**HandlerFn[] 数组支持同一扩展多次注册同一事件。**

### 场景 2：多个扩展注册同一个事件

```typescript
// 扩展 A
export default function (pi: ExtensionAPI) {
  pi.on("session_start", async (event, ctx) => {
    console.log("Extension A: session started");
  });
}

// 扩展 B
export default function (pi: ExtensionAPI) {
  pi.on("session_start", async (event, ctx) => {
    console.log("Extension B: session started");
  });
}

// 扩展 C
export default function (pi: ExtensionAPI) {
  pi.on("session_start", async (event, ctx) => {
    ctx.ui.notify("Welcome!", "info");
  });
}

// runner.ts 遍历所有扩展
for (const ext of this.extensions) {
  const handlers = ext.handlers.get("session_start");  // HandlerFn[]
  for (const handler of handlers) {
    await handler(event, ctx);  // 执行每个处理器
  }
}
```

**所有三个扩展的处理器都会被执行。**

## 二、HandlerFn 的类型签名

```typescript
type HandlerFn = (...args: unknown[]) => Promise<unknown>;
```

### 为什么是 (...args: unknown[]) ?

**实际调用时传入两个参数**：

```typescript
// runner.ts
const handlerResult = await handler(event, ctx);
// event: ExtensionEvent（第一个参数）
// ctx: ExtensionContext（第二个参数）
```

**为什么不用更精确的类型？**

```typescript
// ❌ 如果这样定义
type HandlerFn = (event: ExtensionEvent, ctx: ExtensionContext) => Promise<EventResult>;

// 问题：不同事件有不同的 Event 和 Result 类型
// - session_start: SessionStartEvent, void
// - session_before_switch: SessionBeforeSwitchEvent, SessionBeforeSwitchResult
// - tool_call: ToolCallEvent, ToolCallEventResult
// - context: ContextEvent, ContextEventResult
// 无法用统一的 HandlerFn 类型表达
```

**解决方案**：
```typescript
// ✅ 用宽松的类型，在 ExtensionAPI.on() 中用 overload 约束
interface ExtensionAPI {
  on(event: "session_start", handler: ExtensionHandler<SessionStartEvent>): void;
  on(event: "session_before_switch", handler: ExtensionHandler<SessionBeforeSwitchEvent, SessionBeforeSwitchResult>): void;
  on(event: "tool_call", handler: ExtensionHandler<ToolCallEvent, ToolCallEventResult>): void;
  // ...
}

// 内部存储时用宽松的 HandlerFn
handlers: Map<string, HandlerFn[]>;
```

**这是"外部强约束，内部宽松存储"的设计模式**：
- ExtensionAPI.on() 的 overload 约束每个事件的 handler 类型
- 内部用 HandlerFn[] 存储，执行时根据 event type 解析 result

## 三、执行顺序：先注册先执行

```typescript
// runner.ts 的 emit 方法
async emit(event) {
  for (const ext of this.extensions) {  // 按扩展加载顺序
    const handlers = ext.handlers.get(event.type);
    for (const handler of handlers) {  // 按注册顺序
      const result = await handler(event, ctx);
      if (result?.cancel) return result;  // 早退出
    }
  }
}
```

**执行顺序**：
1. 先加载的扩展先执行
2. 同一扩展内，先注册的 handler 先执行
3. 如果某个 handler 返回 `cancel: true`，停止执行后续 handler

### 示例：执行顺序

```typescript
// 加载顺序：A → B → C
extensions = [extA, extB, extC];

// extA 注册了 2 个 session_start handler
extA.handlers["session_start"] = [handlerA1, handlerA2];

// extB 注册了 1 个 session_start handler
extB.handlers["session_start"] = [handlerB1];

// 执行顺序
await emit({ type: "session_start" });
// 1. handlerA1(event, ctx)
// 2. handlerA2(event, ctx)
// 3. handlerB1(event, ctx)
```

## 四、取消机制：before_xxx 事件的早退出

```typescript
// confirm-destructive.ts 示例
pi.on("session_before_switch", async (event, ctx) => {
  if (!ctx.hasUI) return;
  
  if (event.reason === "new") {
    const confirmed = await ctx.ui.confirm(
      "Clear session?",
      "This will delete all messages in the current session."
    );
    
    if (!confirmed) {
      ctx.ui.notify("Clear cancelled", "info");
      return { cancel: true };  // ⭐ 取消！
    }
  }
});

// runner.ts 的 emit 方法
async emit(event) {
  for (const ext of this.extensions) {
    const handlers = ext.handlers.get(event.type);
    for (const handler of handlers) {
      const result = await handler(event, ctx);
      
      if (result?.cancel) {
        return result;  // ⭐ 早退出，不执行后续 handler
      }
    }
  }
}
```

**取消的效果**：
- 第一个返回 `{ cancel: true }` 的 handler 会阻止后续所有 handler 执行
- session 切换被取消，不继续 teardown

### 为什么需要多个 before_xxx handler？

**场景**：多个扩展都想检查是否允许 session 切换

```typescript
// 扩展 A：检查是否有未保存的工作
pi.on("session_before_switch", async (event, ctx) => {
  if (hasUnsavedWork) {
    const confirmed = await ctx.ui.confirm("Unsaved work. Continue?");
    if (!confirmed) return { cancel: true };
  }
});

// 扩展 B：检查是否有正在运行的任务
pi.on("session_before_switch", async (event, ctx) => {
  if (!ctx.isIdle()) {
    const confirmed = await ctx.ui.confirm("Agent is busy. Continue?");
    if (!confirmed) return { cancel: true };
  }
});

// 执行流程
await emit({ type: "session_before_switch" });
// 1. 扩展 A 的 handler 检查 → 用户确认 → 继续
// 2. 扩展 B 的 handler 检查 → 用户确认 → 继续
// 如果任一 handler 返回 cancel: true，后续不执行，session 不切换
```

## 五、链式处理：某些事件可以修改数据

### message_end 的链式修改

```typescript
// runner.ts
async emitMessageEnd(event: MessageEndEvent) {
  let currentMessage = event.message;
  
  for (const ext of this.extensions) {
    for (const handler of ext.handlers.get("message_end")) {
      const result = await handler({ ...event, message: currentMessage }, ctx);
      
      if (result?.message) {
        currentMessage = result.message;  // ⭐ 修改
      }
    }
  }
  
  return currentMessage;  // 返回最终修改后的消息
}
```

**链式效果**：

```typescript
// 扩展 A：添加水印
pi.on("message_end", async (event) => {
  const message = event.message;
  if (message.role === "assistant") {
    return {
      message: {
        ...message,
        content: [...message.content, { type: "text", text: "\n\n---\nGenerated by pi" }]
      }
    };
  }
});

// 扩展 B：过滤敏感内容
pi.on("message_end", async (event) => {
  const message = event.message;
  if (message.role === "assistant") {
    return {
      message: {
        ...message,
        content: message.content.map(c => 
          c.type === "text" ? { ...c, text: sanitize(c.text) } : c
        )
      }
    };
  }
});

// 执行流程
await emitMessageEnd({ message: originalMessage });
// 1. 扩展 A 处理 → 添加水印 → currentMessage = watermarkedMessage
// 2. 扩展 B 处理 → 过滤内容 → currentMessage = sanitizedMessage
// 返回 sanitizedMessage（A 和 B 的处理都生效）
```

### tool_result 的链式修改

```typescript
// runner.ts
async emitToolResult(event: ToolResultEvent) {
  const currentEvent = { ...event };
  
  for (const ext of this.extensions) {
    for (const handler of ext.handlers.get("tool_result")) {
      const result = await handler(currentEvent, ctx);
      
      if (result?.content !== undefined) {
        currentEvent.content = result.content;  // ⭐ 修改 content
      }
      if (result?.isError !== undefined) {
        currentEvent.isError = result.isError;  // ⭐ 修改 isError
      }
    }
  }
  
  return {
    content: currentEvent.content,
    isError: currentEvent.isError,
  };
}
```

**链式修改的效果**：
- 第一个 handler 的修改传递给下一个 handler
- 最后返回所有修改的最终结果

## 六、错误隔离：单个 handler 失败不影响其他

```typescript
// runner.ts
async emit(event) {
  for (const ext of this.extensions) {
    for (const handler of handlers) {
      try {
        const result = await handler(event, ctx);
        if (result?.cancel) return result;
      } catch (err) {
        // ⭐ 只记录错误，继续执行其他 handler
        this.emitError({
          extensionPath: ext.path,
          event: event.type,
          error: err.message,
          stack: err.stack,
        });
        // 不阻止后续 handler 执行
      }
    }
  }
}
```

**设计意图**：单个扩展的 handler 失败，不应该影响整个系统和其他扩展。

```typescript
// 扩展 A 的 handler 出错
pi.on("session_start", async () => {
  throw new Error("Oops");  // 失败
});

// 扩展 B 的 handler 正常
pi.on("session_start", async (event, ctx) => {
  ctx.ui.notify("Welcome!", "info");  // ✅ 仍然执行
});

// 执行结果
// 1. 扩展 A 失败 → emitError 记录
// 2. 扩展 B 正常 → 显示通知
```

## 七、对比：如果 handlers 是 Map<string, HandlerFn> 会怎样？

```typescript
// ❌ 单个函数的设计
interface Extension {
  handlers: Map<string, HandlerFn>;
}

// 问题 1：不能多次注册同一事件
pi.on("session_start", handler1);
pi.on("session_start", handler2);  // 覆盖 handler1！

// 问题 2：不能有多个扩展监听同一事件
// 最后注册的 wins
extA.handlers.set("session_start", handlerA);  // 设置
extB.handlers.set("session_start", handlerB);  // 覆盖！

// runner.ts 执行
const handler = ext.handlers.get("session_start");  // 只有 handlerB
await handler(event, ctx);  // handlerA 被丢失
```

**HandlerFn[] 数组解决的问题**：
1. 同一扩展可以多次注册同一事件
2. 多个扩展可以监听同一事件
3. 按注册顺序执行
4. 支持 cancel 早退出
5. 支持链式修改
6. 错误隔离

## 八、总结：HandlerFn[] 的设计模式

### 1. 多订阅者模式

```typescript
handlers: Map<string, HandlerFn[]>
```

**类比**：Node.js 的 EventEmitter

```typescript
// Node.js
emitter.on("event", handler1);
emitter.on("event", handler2);
emitter.emit("event");  // 执行 handler1 和 handler2

// pi 扩展系统
pi.on("session_start", handler1);
pi.on("session_start", handler2);
runner.emit({ type: "session_start" });  // 执行 handler1 和 handler2
```

### 2. 执行顺序 + 取消机制

```typescript
for (const handler of handlers) {
  const result = await handler(event, ctx);
  if (result?.cancel) return result;  // 早退出
}
```

**类比**：Express.js 的 middleware chain

```typescript
// Express
app.use((req, res, next) => {
  if (!authorized) return res.status(403).send();  // 早退出
  next();  // 继续
});

// pi 扩展系统
pi.on("session_before_switch", async (event, ctx) => {
  if (!confirmed) return { cancel: true };  // 早退出
  // 隐式继续（不返回 cancel）
});
```

### 3. 式修改

```typescript
let currentMessage = event.message;
for (const handler of handlers) {
  const result = await handler({ ...event, message: currentMessage }, ctx);
  if (result?.message) {
    currentMessage = result.message;  // 修改传递给下一个
  }
}
```

**类比**：Redux 的 middleware chain

```typescript
// Redux
const middleware = store => next => action => {
  const modifiedAction = { ...action, timestamp: Date.now() };
  return next(modifiedAction);  // 传递修改后的 action
};
```

### 4. 错误隔离

```typescript
try {
  await handler(event, ctx);
} catch (err) {
  emitError(err);  // 记录，不阻止其他
}
```

**类比**：Promise.allSettled

```typescript
// Promise.allSettled 不会因单个失败而终止
const results = await Promise.allSettled(promises);
// 所有 promise 都执行，失败的记录状态

// pi 扩展系统
for (const handler of handlers) {
  try { await handler(...); }
  catch { emitError(...); }  // 不终止循环
}
```

---

**核心设计洞察**：

HandlerFn[] 数组不是简单的"存储多个函数"，而是表达了一个**事件处理管道**：
- 输入：事件 + context
- 输出：result（可能是 cancel、修改后的数据、void）
- 执行：顺序执行，支持早退出和链式修改
- 错误：隔离处理，不阻塞管道

这是"管道模式"的高级应用。