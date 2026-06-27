---
name: invalidate-sync-mechanism
description: 深度剖析 invalidate 的同步失效机制 - session 切换的完整流程、teardownCurrent 的时序、assertActive 的检查
---

# invalidate 同步失效机制深度剖析

"共享 runtime 确保 invalidate 同步失效"这句话背后，是一个精心设计的 session 切换流程。

## 一、问题场景：Session 切换后，旧 Context 不能再用

### 典型错误场景

```typescript
// handoff.ts 的正确用法
pi.registerCommand("handoff", {
  handler: async (args, ctx) => {
    const currentSessionFile = ctx.sessionManager.getSessionFile();
    
    // 创建新 session
    const result = await ctx.newSession({
      parentSession: currentSessionFile,
      withSession: async (replacementCtx) => {
        // ✅ 用 replacementCtx（新 session）
        replacementCtx.ui.setEditorText(editedPrompt);
      },
    });
    
    // ❌ 不能再用 ctx（旧 session）
    // ctx.sessionManager 指向旧 session 文件
    // ctx.model 是旧 session 的 model
  },
});

// 错误用法示例
export default function(pi) {
  let cachedCtx;  // 保存了旧 context
  
  pi.on("session_start", (event, ctx) => {
    cachedCtx = ctx;  // ❌ 想复用 context
  });
  
  pi.registerCommand("bad", {
    handler: async (args, ctx) => {
      await ctx.newSession();  // 切换 session
      
      // ❌ 用了缓存的旧 context
      cachedCtx.sessionManager.getSessionFile();  // 指向旧 session
      cachedCtx.model;  // 旧 model
    }
  });
}
```

**为什么不能用旧 context？**
- `ctx.sessionManager` 指向旧 session 文件
- `ctx.model` 是旧 session 当前使用的 model
- `ctx.abort()` 会 abort 旧 session 的 agent loop

## 二、Session 切换的完整流程

让我们看一个真实的 `newSession` 流程：

```typescript
// 用户调用 /new 或 ctx.newSession()
await ctx.newSession({
  withSession: async (replacementCtx) => {
    // 用新的 replacementCtx 做后续工作
  }
});

// 实际执行流程（agent-session-runtime.ts）
async newSession(options): Promise<{ cancelled: boolean }> {
  // 1. 发出 session_before_switch 事件（可取消）
  const beforeResult = await this.emitBeforeSwitch("new");
  if (beforeResult.cancelled) return beforeResult;
  
  // 2. 记录旧 session 文件路径
  const previousSessionFile = this.session.sessionFile;
  
  // 3. 创建新 session manager
  const sessionManager = SessionManager.create(this.cwd, sessionDir);
  
  // 4. Teardown 旧 session（关键步骤！）
  await this.teardownCurrent("new", sessionManager.getSessionFile());
  
  // 5. 创建新 runtime
  this.apply(await this.createRuntime({
    cwd: this.cwd,
    agentDir: this.services.agentDir,
    sessionManager,
    sessionStartEvent: { type: "session_start", reason: "new", previousSessionFile },
  }));
  
  // 6. 调用 withSession 回调（用新 context）
  await this.finishSessionReplacement(options?.withSession);
  
  return { cancelled: false };
}
```

## 三、teardownCurrent：invalidate 的触发点

```typescript
// agent-session-runtime.ts:160-168
private async teardownCurrent(
  reason: SessionShutdownEvent["reason"],
  targetSessionFile?: string
): Promise<void> {
  // 1. 发出 session_shutdown 事件
  await emitSessionShutdownEvent(this.session.extensionRunner, {
    type: "session_shutdown",
    reason,  // "new" | "resume" | "fork" | "quit" | "reload"
    targetSessionFile,
  });
  
  // 2. 调用 beforeSessionInvalidate 回调（UI teardown）
  this.beforeSessionInvalidate?.();
  
  // 3. dispose 旧 session（触发 invalidate）
  this.session.dispose();
}
```

### session.dispose() 的实现

```typescript
// agent-session.ts:709-716
dispose(): void {
  // 4. invalidate extension runner
  this._extensionRunner.invalidate(
    "This extension ctx is stale after session replacement or reload. " +
    "Do not use a captured pi or command ctx after ctx.newSession(), " +
    "ctx.fork(), ctx.switchSession(), or ctx.reload()..."
  );
  
  // 5. 断开 agent 连接
  this._disconnectFromAgent();
  
  // 6. 清理资源
  cleanupSessionResources(this.sessionId);
}
```

## 四、extensionRunner.invalidate() 的传播

```typescript
// runner.ts:466-473
invalidate(message?: string): void {
  if (!this.staleMessage) {
    this.staleMessage = message;
    
    // 传播到共享 runtime
    this.runtime.invalidate(message);
  }
}
```

### runtime.invalidate() 的实现

```typescript
// loader.ts:149-195（在 createExtensionRuntime 中）
const state: { staleMessage?: string } = {};

const runtime: ExtensionRuntime = {
  assertActive: () => {
    if (state.staleMessage) {
      throw new Error(state.staleMessage);
    }
  },
  
  invalidate: (message) => {
    // 只设置一次（??=）
    state.staleMessage ??=
      message ?? "This extension ctx is stale...";
  },
};
```

**关键点**：`state` 对象是闭包中的共享对象，所有扩展的 runtime 都引用同一个 `state`！

## 五、assertActive 的检查机制

### 每个使用 runtime 的地方都调用 assertActive

```typescript
// loader.ts - ExtensionAPI 的每个方法
sendMessage(message, options): void {
  runtime.assertActive();  // 检查
  runtime.sendMessage(message, options);
}

getActiveTools(): string[] {
  runtime.assertActive();  // 检查
  return runtime.getActiveTools();
}

// runner.ts - createContext()
createContext(): ExtensionContext {
  const runner = this;
  return {
    get model() {
      runner.assertActive();  // 检查
      return runner.getModel();
    },
    get sessionManager() {
      runner.assertActive();  // 检查
      return runner.sessionManager;
    },
    abort: () => {
      runner.assertActive();  // 检查
      runner.abortFn();
    },
  };
}
```

**访问任何属性或方法前，先调用 assertActive() 检查是否 stale。**

## 六、共享 Runtime 的同步失效效果

### 为什么共享 runtime 能同步失效？

```typescript
// loader.ts - 创建 runtime
export function createExtensionRuntime(): ExtensionRuntime {
  const state: { staleMessage?: string } = {};  // 一个 state 对象
  
  const runtime: ExtensionRuntime = {
    assertActive: () => {
      if (state.staleMessage) throw new Error(state.staleMessage);
    },
    invalidate: (message) => {
      state.staleMessage ??= message;  // 写入同一个 state
    },
  };
  
  return runtime;
}

// loader.ts - 加载扩展
export async function loadExtensions(paths) {
  const runtime = createExtensionRuntime();  // 一个 runtime
  
  for (const extPath of paths) {
    const api = createExtensionAPI(extension, runtime);  // 都用同一个
  }
}

// 所有扩展的 runtime.assertActive 和 runtime.invalidate
// 都访问同一个 state 对象
```

### 同步失效的时序图

```
用户调用 ctx.newSession()
  ↓
emitBeforeSwitch("new")
  ↓
teardownCurrent("new")
  ├─ emitSessionShutdownEvent({ reason: "new" })
  │  └─ 触发扩展的 session_shutdown handlers
  ├─ beforeSessionInvalidate()
  │  └─ UI teardown（不能 yield）
  └─ session.dispose()
     └─ extensionRunner.invalidate(message)
        └─ runtime.invalidate(message)
           └─ state.staleMessage = message  ⭐ 所有扩展共享
  ↓
createRuntime() 创建新 session
  ↓
finishSessionReplacement(withSession)
  └─ withSession(replacementCtx)  ✅ 用新 context
```

**invalidate 一次，所有扩展的 assertActive 都会抛错**：

```typescript
// 扩展 A 的代码
pi.sendMessage(...);  // runtime.assertActive() → throw!

// 扩展 B 的代码
pi.getActiveTools();  // runtime.assertActive() → throw!

// 扩展 C 的代码
ctx.model;  // runner.assertActive() → throw!

// 因为它们都检查同一个 state.staleMessage
```

## 七、如果每个扩展独立 Runtime 会怎样？

### 独立 runtime 的混乱场景

```typescript
// ❌ 独立 runtime 的假设实现
export async function loadExtensions(paths) {
  const extensions = [];
  
  for (const extPath of paths) {
    const runtime = createExtensionRuntime();  // 每个扩展独立
    const api = createExtensionAPI(extension, runtime);
    extensions.push({ extension, runtime });
  }
}

// teardown 时需要逐个 invalidate
async teardownCurrent() {
  for (const { extension, runtime } of extensions) {
    runtime.invalidate();  // 需要手动遍历
  }
}

// 问题：
// 1. 需要维护所有 runtime 的列表
// 2. invalidate 的顺序不确定
// 3. 如果某个 runtime 的 invalidate 失败怎么办？
// 4. 状态分散，难以确保同步
```

### 共享 runtime 的简洁性

```typescript
// ✅ 共享 runtime
export async function loadExtensions(paths) {
  const runtime = createExtensionRuntime();  // 一个
  
  for (const extPath of paths) {
    const api = createExtensionAPI(extension, runtime);  // 都用同一个
  }
}

// teardown 时一次 invalidate
async teardownCurrent() {
  this.session.dispose();  // 触发 extensionRunner.invalidate()
  // 自动让所有扩展失效
}
```

## 八、withSession 的 replacement context

### 为什么需要 withSession 回调？

```typescript
// session 切换后的代码需要用新 context
await ctx.newSession({
  withSession: async (replacementCtx) => {
    // replacementCtx 是新 session 的 context
    // assertActive 不抛错（staleMessage 清空）
    replacementCtx.ui.setEditorText(...);  // ✅ OK
  }
});

// ❌ 错误：await ctx.newSession() 后直接用 ctx
await ctx.newSession();
ctx.ui.setEditorText(...);  // 抛错！
```

### replacement context 的创建

```typescript
// agent-session-runtime.ts:177-184
private async finishSessionReplacement(
  withSession?: (ctx: ReplacedSessionContext) => Promise<void>
): Promise<void> {
  // 重新绑定 UI（新 session）
  if (this.rebindSession) {
    await this.rebindSession(this.session);
  }
  
  // 调用 withSession，传入新 context
  if (withSession) {
    await withSession(this.session.createReplacedSessionContext());
  }
}

// agent-session.ts - createReplacedSessionContext()
createReplacedSessionContext(): ReplacedSessionContext {
  // 新的 runner（staleMessage = undefined）
  const runner = this.extensionRunner;
  runner.staleMessage = undefined;  // 清空 stale 状态
  
  return runner.createCommandContext();  // 创建新 context
}
```

**withSession 回调收到的新 context**：
- `staleMessage` 已清空
- `assertActive()` 不抛错
- `sessionManager` 指向新 session
- `model` 是新 session 的 model

## 九、完整的状态生命周期

```
┌─────────────────────────────────────────────────────┐
│  Phase 1: 创建 Runtime                              │
│  state.staleMessage = undefined                     │
│  assertActive() → 不抛错                             │
├─────────────────────────────────────────────────────┤
│  Phase 2: 正常运行                                   │
│  所有扩展正常使用 runtime                            │
│  pi.sendMessage(...) → OK                           │
│  ctx.model → OK                                     │
├─────────────────────────────────────────────────────┤
│  Phase 3: Session 切换                               │
│  teardownCurrent()                                  │
│  ├─ emitSessionShutdown                             │
│  ├─ beforeSessionInvalidate                         │
│  └─ session.dispose()                               │
│     └─ extensionRunner.invalidate()                 │
│        └─ runtime.invalidate()                      │
│           └─ state.staleMessage = message ⭐        │
├─────────────────────────────────────────────────────┤
│  Phase 4: Stale 状态                                │
│  所有扩展的 assertActive() 抛错                      │
│  pi.sendMessage(...) → throw!                       │
│  ctx.model → throw!                                 │
│  因为都检查同一个 state.staleMessage                 │
├─────────────────────────────────────────────────────┤
│  Phase 5: Replacement Context                       │
│  createRuntime() 创建新 session                     │
│  finishSessionReplacement(withSession)             │
│  ├─ runner.staleMessage = undefined（清空）         │
│  └─ withSession(replacementCtx)                     │
│     └─ replacementCtx.assertActive() → 不抛错       │
└─────────────────────────────────────────────────────┘
```

## 十、beforeSessionInvalidate 的特殊作用

```typescript
// agent-session-runtime.ts:122-124
setBeforeSessionInvalidate(beforeSessionInvalidate?: () => void): void {
  this.beforeSessionInvalidate = beforeSessionInvalidate;
}

// teardownCurrent 中调用
await emitSessionShutdownEvent(...);
this.beforeSessionInvalidate?.();  // 不能 yield！
this.session.dispose();
```

**为什么不能 yield？**

```typescript
// interactive-mode.ts:362-364
this.runtimeHost.setBeforeSessionInvalidate(() => {
  this.resetExtensionUI();  // UI teardown
});
```

**场景**：扩展可能设置了自定义 footer/header/widget

```typescript
// 扩展设置了自定义 footer
pi.on("session_start", (e, ctx) => {
  ctx.ui.setFooter(factory);  // 注册自定义 footer
});

// session 切换时，需要在 invalidate 之前清理 UI
// 否则 footer factory 还会被调用（旧 context）
// 但此时 state.staleMessage 已设置，assertActive 抛错
// 导致 footer 无法正常 render
```

**beforeSessionInvalidate 确保**：
1. 先清理 UI 组件（同步，不 yield）
2. 再设置 stale 状态
3. 防止 UI 组件在 stale 状态下被调用

## 十一、设计精髓总结

### 1. 共享 state 对象的同步效果

```typescript
const state: { staleMessage?: string } = {};
// 所有扩展的 runtime.assertActive 都检查同一个 state
// invalidate 时写入一次，所有扩展立即失效
```

### 2. assertActive 的全面防御

```typescript
// 每个属性访问、每个方法调用前都检查
ctx.model → runner.assertActive()
pi.sendMessage → runtime.assertActive()
// 在 stale 状态下，任何访问都抛错
```

### 3. teardownCurrent 的时序保证

```typescript
// 严格的时序
emitSessionShutdown → 扩展清理
beforeSessionInvalidate → UI teardown（不 yield）
session.dispose → invalidate runtime
createRuntime → 创建新 session
withSession → 用新 context
```

### 4. withSession 的正确用法

```typescript
await ctx.newSession({
  withSession: async (replacementCtx) => {
    // 用 replacementCtx（新 context）
    replacementCtx.ui.setEditorText(...);
  }
});

// ❌ await ctx.newSession() 后不能用 ctx
await ctx.newSession();
ctx.ui.setEditorText(...);  // 抛错！
```

### 5. beforeSessionInvalidate 的同步清理

```typescript
setBeforeSessionInvalidate(() => {
  this.resetExtensionUI();  // UI teardown，不 yield
});

// 确保 UI 组件在 stale 状态之前被清理
// 防止 stale context 被 UI 组件引用
```

---

**核心设计洞察**：

invalidate 的"同步效果"不是魔法，而是**闭包共享 state 对象**的设计：
- 所有扩展的 runtime.assertActive 检查同一个 state
- invalidate 时写入一次，所有检查立即抛错
- 不需要遍历、不需要通知、不需要订阅

这是"以数据结构代替控制流"的高级设计 taste。