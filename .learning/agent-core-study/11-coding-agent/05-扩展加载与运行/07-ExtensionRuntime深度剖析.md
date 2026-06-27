---
name: extension-runtime-deep-dive
description: ExtensionRuntime 接口的深度剖析 - State/Actions 分离、throwing stubs、分阶段填充的设计意图
---

# ExtensionRuntime 深度剖析

ExtensionRuntime 是整个扩展系统的**中央枢纽**。理解它，就理解了这个系统的核心设计思想。

## 一、整体结构：Intersection Type 的精妙用法

```typescript
/**
 * Full runtime = state + actions.
 * Created by loader with throwing action stubs, completed by runner.initialize().
 */
export interface ExtensionRuntime extends ExtensionRuntimeState, ExtensionActions {}
```

这不是简单的"组合两个接口"，而是表达了：
- **语义分离**：Runtime 由两个不同性质的组件构成
- **时间分离**：两个组件在不同阶段填充
- **安全分离**：State 可以早用，Actions 必须晚用

### 用对比来说明

```typescript
// ❌ 如果合并成一个接口
interface ExtensionRuntime {
  // State - 加载阶段就有
  flagValues: Map<string, boolean | string>;
  
  // Actions - 运行阶段才有
  sendMessage: SendMessageHandler;
  setModel: SetModelHandler;
}

// 问题：
// 1. 类型层面看不出哪些是早可用的，哪些是晚可用的
// 2. 加载阶段 runtime.sendMessage 可能是 undefined（不安全）
// 3. 没有"分阶段填充"的类型支持
```

```typescript
// ✅ 实际设计 - Intersection Type
interface ExtensionRuntime extends ExtensionRuntimeState, ExtensionActions {}

// 好处：
// 1. 语义清晰：Runtime = State + Actions
// 2. 类型完整：加载阶段就有所有属性的类型
// 3. 行为受限：通过 throwing stubs 实现"类型完整但行为受限"
```

## 二、ExtensionRuntimeState：加载阶段可用的状态

```typescript
export interface ExtensionRuntimeState {
  flagValues: Map<string, boolean | string>;
  pendingProviderRegistrations: Array<{ name: string; config: ProviderConfig; extensionPath: string }>;
  assertActive: () => void;
  invalidate: (message?: string) => void;
  registerProvider: (name: string, config: ProviderConfig, extensionPath?: string) => void;
  unregisterProvider: (name: string, extensionPath?: string) => void;
}
```

### 为什么这些在加载阶段就可用？

#### 1. flagValues：CLI flag 的默认值池

```typescript
// 扩展注册 flag
pi.registerFlag("verbose", { type: "boolean", default: true });

// loader.ts 实现
registerFlag(name, options): void {
  extension.flags.set(name, { name, extensionPath: extension.path, ...options });
  
  // 只设置默认值，不覆盖 CLI 已设置的值
  if (options.default !== undefined && !runtime.flagValues.has(name)) {
    runtime.flagValues.set(name, options.default);
  }
}
```

**设计意图**：
- 加载阶段需要收集所有扩展的 flag 定义
- CLI 参数解析后，会覆盖 flagValues 中的默认值
- 所有扩展共享一个 flagValues Map，保证全局一致性

```typescript
// 使用流程
// Phase 1: 扩展加载，设置默认值
runtime.flagValues.set("verbose", true);

// Phase 2: CLI 参数解析，覆盖默认值
runtime.flagValues.set("verbose", false);  // 用户用 --no-verbose

// Phase 3: 扩展读取值
pi.getFlag("verbose");  // false
```

#### 2. pendingProviderRegistrations：延迟绑定的 provider 队列

```typescript
// 扩展注册 provider（加载阶段）
pi.registerProvider("my-proxy", { baseUrl: "...", models: [...] });

// loader.ts 实现
registerProvider: (name, config, extensionPath = "<unknown>") => {
  runtime.pendingProviderRegistrations.push({ name, config, extensionPath });
}
```

**为什么是队列而不是直接注册？**

**核心原因**：加载阶段 ModelRegistry 还不存在

```typescript
// loader.ts 的执行顺序
const runtime = createExtensionRuntime();     // 1. 创建 runtime
await factory(api);                            // 2. 执行扩展（调用 registerProvider）
// 此时 ModelRegistry 还不存在，所以只能先入队

// runner.ts 的执行顺序
bindCore(actions, providerActions) {
  // 3. ModelRegistry 已创建，处理队列
  for (const { name, config } of runtime.pendingProviderRegistrations) {
    modelRegistry.registerProvider(name, config);
  }
  runtime.pendingProviderRegistrations = [];
  
  // 4. 从此刻起，registerProvider 直接生效
  runtime.registerProvider = (name, config) => {
    modelRegistry.registerProvider(name, config);  // 直接调用
  };
}
```

**设计洞察**：同一个方法在两个阶段有不同的行为：
- **加载阶段**：入队（延迟处理）
- **运行阶段**：直接调用（立即生效）

#### 3. assertActive / invalidate：stale context 的防御机制

```typescript
// loader.ts 实现
const state: { staleMessage?: string } = {};
const assertActive = () => {
  if (state.staleMessage) {
    throw new Error(state.staleMessage);
  }
};

const runtime: ExtensionRuntime = {
  assertActive,
  invalidate: (message) => {
    state.staleMessage ??=
      message ?? "This extension ctx is stale...";
  },
};
```

**为什么需要这个机制？**

**场景**：session 切换后，旧的 context 不能再用

```typescript
// 错误用法示例
export default function(pi) {
  let cachedCtx: ExtensionContext;
  
  pi.on("session_start", (event, ctx) => {
    cachedCtx = ctx;  // 保存了旧 context
  });
  
  // 用户执行 ctx.newSession() 后...
  pi.registerCommand("bad", {
    handler: async (args, ctx) => {
      cachedCtx.model;  // ❌ 用了旧 context！
    }
  });
}

// 正确用法
pi.registerCommand("bad", {
  handler: async (args, ctx) => {
    ctx.model;  // ✅ 用当前的 ctx
  }
});
```

**invalidate 的触发时机**：

```typescript
// runner.ts
invalidate(message?: string): void {
  if (!this.staleMessage) {
    this.staleMessage = message;
    this.runtime.invalidate(message);  // 让所有扩展都失效
  }
}

// 触发点
await ctx.newSession();     // 新 session
await ctx.fork(entryId);    // fork
await ctx.switchSession();  // 切换
await ctx.reload();         // reload
```

**所有使用 runtime 的地方都调用 assertActive**：

```typescript
// loader.ts - ExtensionAPI 的每个方法
sendMessage(message, options): void {
  runtime.assertActive();  // 先检查
  runtime.sendMessage(message, options);
}

getActiveTools(): string[] {
  runtime.assertActive();  // 先检查
  return runtime.getActiveTools();
}
```

## 三、ExtensionActions：运行阶段才有的行为

```typescript
export interface ExtensionActions {
  sendMessage: SendMessageHandler;
  sendUserMessage: SendUserMessageHandler;
  appendEntry: AppendEntryHandler;
  setSessionName: SetSessionNameHandler;
  getSessionName: GetSessionNameHandler;
  setLabel: SetLabelHandler;
  getActiveTools: GetActiveToolsHandler;
  getAllTools: GetAllToolsHandler;
  setActiveTools: SetActiveToolsHandler;
  refreshTools: RefreshToolsHandler;
  getCommands: GetCommandsHandler;
  setModel: SetModelHandler;
  getThinkingLevel: GetThinkingLevelHandler;
  setThinkingLevel: SetThinkingLevelHandler;
}
```

### 为什么这些必须等运行阶段？

**核心原因**：它们依赖 Session、Model、AgentLoop 等运行时对象

```typescript
// sendMessage 的实现
sendMessage: (message, options) => {
  sessionManager.appendEntry(message);  // 需要 SessionManager
  if (options.triggerTurn) {
    agentLoop.triggerTurn();             // 需要 AgentLoop
  }
}

// setModel 的实现
setModel: async (model) => {
  const apiKey = modelRegistry.getApiKey(model);  // 需要 ModelRegistry
  if (!apiKey) return false;
  currentModel = model;
  return true;
}

// getActiveTools 的实现
getActiveTools: () => {
  return toolManager.getActiveTools();  // 需要 ToolManager
}
```

**这些对象在加载阶段不存在**：
- `SessionManager`：需要 session 文件路径
- `AgentLoop`：需要 session 启动
- `ToolManager`：需要 agent 初始化

## 四、Throwing Stubs：类型完整但行为受限

### loader.ts 的精妙实现

```typescript
export function createExtensionRuntime(): ExtensionRuntime {
  const notInitialized = () => {
    throw new Error(
      "Extension runtime not initialized. " +
      "Action methods cannot be called during extension loading."
    );
  };
  
  const runtime: ExtensionRuntime = {
    // State 部分 - 真实实现
    flagValues: new Map(),
    pendingProviderRegistrations: [],
    assertActive,
    invalidate,
    registerProvider: queueRegistration,
    unregisterProvider: removeFromQueue,
    
    // Actions 部分 - throwing stubs
    sendMessage: notInitialized,
    sendUserMessage: notInitialized,
    setModel: () => Promise.reject(notInitialized()),
    getActiveTools: notInitialized,
    // ...
  };
  
  return runtime;
}
```

**关键洞察**：runtime 对象在加载阶段就**类型完整**，但**行为受限**

```typescript
// 类型层面
runtime.sendMessage;  // 类型是 SendMessageHandler，编译器认可

// 行为层面
runtime.sendMessage(...);  // 抛错："Extension runtime not initialized"
```

### 为什么不用 undefined？

```typescript
// ❌ 如果用 undefined
interface ExtensionRuntime {
  sendMessage?: SendMessageHandler;  // 可选属性
}

// 问题 1：类型不完整
runtime.sendMessage(...);  // 编译错误：可能是 undefined
// 需要 runtime.sendMessage?.(...)，语义不清晰

// 问题 2：运行时行为不可控
runtime.sendMessage?.(...);  // 如果 undefined，什么都不发生
// 没有"明确的错误信息"，扩展开发者不知道发生了什么

// ✅ 用 throwing stubs
runtime.sendMessage(...);  // 抛出明确的错误信息
// 扩展开发者立即知道：这里不能调用
```

### 设计 taste：在类型系统之外，用行为来表达设计意图

TypeScript 的类型系统只能表达"属性是否存在"，不能表达"属性何时可用"。Throwing stubs 补充了这个空白：
- **类型层面**：属性存在（编译通过）
- **行为层面**：属性不可用（运行时抛错）

这比 undefined 更好，因为错误信息是**明确的、可教育的**：
```
Extension runtime not initialized. 
Action methods cannot be called during extension loading.
```

扩展开发者看到这个错误，就知道应该怎么改：
```typescript
// ❌ 错误：在加载阶段调用
export default function(pi) {
  pi.sendMessage(...);  // 抛错
}

// ✅ 正确：在事件处理器中调用
export default function(pi) {
  pi.on("session_start", (event, ctx) => {
    pi.sendMessage(...);  // OK
  });
}
```

## 五、分阶段填充的实现

### Phase 1: 创建（loader.ts）

```typescript
export function createExtensionRuntime(): ExtensionRuntime {
  const notInitialized = () => { throw new Error(...); };
  
  const runtime: ExtensionRuntime = {
    // State 真实，Actions 是 stubs
    flagValues: new Map(),
    sendMessage: notInitialized,
    // ...
  };
  
  return runtime;
}
```

**此时**：
- State 部分已可用（flagValues、registerProvider 等）
- Actions 部分是 stubs（调用会抛错）

### Phase 2: 加载扩展

```typescript
export async function loadExtensions(paths, cwd, eventBus) {
  const runtime = createExtensionRuntime();  // 创建
  
  for (const extPath of paths) {
    const extension = createExtension(extPath);
    const api = createExtensionAPI(extension, runtime);  // 传给扩展
    await factory(api);  // 执行扩展的注册代码
    
    // 扩展可能调用：
    // - runtime.flagValues.set(...)  ✅ OK
    // - runtime.registerProvider(...) ✅ OK（入队）
    // - runtime.sendMessage(...)     ❌ 抛错
  }
  
  return { extensions, runtime };
}
```

### Phase 3: 绑定（runner.ts）

```typescript
bindCore(actions: ExtensionActions, ...) {
  // 用真实实现替换 stubs
  this.runtime.sendMessage = actions.sendMessage;
  this.runtime.sendUserMessage = actions.sendUserMessage;
  this.runtime.setSessionName = actions.setSessionName;
  // ...
  
  // 处理队列中的 provider 注册
  for (const { name, config } of this.runtime.pendingProviderRegistrations) {
    modelRegistry.registerProvider(name, config);
  }
  
  // 从此刻起，registerProvider 直接生效
  this.runtime.registerProvider = (name, config) => {
    modelRegistry.registerProvider(name, config);
  };
}
```

**此时**：
- State 和 Actions 都已可用
- Provider 注册直接生效（不再入队）

## 六、共享 Runtime 的设计意图

### 所有扩展共用一个 runtime

```typescript
export async function loadExtensions(paths, ...) {
  const runtime = createExtensionRuntime();  // 一个 runtime
  
  for (const extPath of paths) {
    const extension = createExtension(extPath);  // 每个扩展独立
    const api = createExtensionAPI(extension, runtime);  // 共享 runtime
    await factory(api);
  }
}
```

### 为什么共享而不是独立？

#### 1. Flag 值的全局一致性

```typescript
// 扩展 A
pi.registerFlag("verbose", { type: "boolean", default: true });
pi.getFlag("verbose");  // true

// 扩展 B
pi.getFlag("verbose");  // true（同一个值）

// CLI --no-verbose
runtime.flagValues.set("verbose", false);

// 扩展 A 和 B 都看到 false
```

**如果每个扩展独立 runtime**：
```typescript
// 扩展 A 的 runtime.flagValues.set("verbose", false)
// 扩展 B 的 runtime.flagValues 还是 true ❌ 不一致
```

#### 2. Action 的唯一性

```typescript
runtime.sendMessage(message);

// 如果每个扩展独立 runtime：
// 哪个 runtime.sendMessage 会被调用？混乱
```

**共享 runtime 保证**：
- `sendMessage` 只有一个实现
- 所有扩展调用的是同一个方法

#### 3. invalidate 的同步效果

```typescript
// runner.ts
invalidate(): void {
  this.runtime.invalidate(message);
}

// loader.ts
invalidate: (message) => {
  state.staleMessage = message;
}

// 所有扩展的 assertActive 都会抛错
// 因为它们共享同一个 state
```

**如果每个扩展独立 runtime**：
```typescript
// invalidate 扩展 A 的 runtime
// 扩展 B 的 runtime.assertActive 还是不抛错 ❌ 危险
```

### Extension 为什么独立？

```typescript
interface Extension {
  path: string;
  handlers: Map<string, HandlerFn[]>;     // 独立的事件处理器
  tools: Map<string, RegisteredTool>;      // 独立的工具注册
  commands: Map<string, RegisteredCommand>; // 独立的命令注册
}
```

**独立收集的好处**：
- 每个扩展有自己的注册项（可以追踪来源）
- runner 可以遍历所有扩展，合并 handlers/tools/commands
- SourceInfo 可以指明是哪个扩展注册的

```typescript
// runner.ts
getAllRegisteredTools(): RegisteredTool[] {
  const toolsByName = new Map();
  for (const ext of this.extensions) {  // 遍历所有扩展
    for (const tool of ext.tools.values()) {
      if (!toolsByName.has(tool.definition.name)) {
        toolsByName.set(tool.definition.name, {
          definition: tool.definition,
          sourceInfo: ext.sourceInfo,  // 来源信息
        });
      }
    }
  }
  return Array.from(toolsByName.values());
}
```

## 七、registerProvider 的双阶段行为

这是最精妙的设计之一：

```typescript
// Phase 1: 加载阶段
registerProvider: (name, config, extensionPath) => {
  runtime.pendingProviderRegistrations.push({ name, config, extensionPath });
}

// Phase 2: 运行阶段
registerProvider: (name, config) => {
  modelRegistry.registerProvider(name, config);  // 直接生效
}
```

### 为什么要这样设计？

**问题**：ModelRegistry 在加载阶段不存在，但扩展需要在加载阶段注册 provider

**方案对比**：

```typescript
// ❌ 方案 A：加载阶段不能注册
// 扩展开发者必须等 session_start 事件才能注册 provider
pi.on("session_start", () => {
  pi.registerProvider("my-proxy", {...});  // 太晚了
});

// ❌ 方案 B：加载阶段注册，但保存到 Extension
// Extension.providerRegistrations = [...]
// runner.bindCore() 时遍历所有 Extension 处理
// 问题：每个扩展都要加 providerRegistrations 属性，结构复杂

// ✅ 方案 C：runtime 统一管理
// pendingProviderRegistrations 在 runtime 中
// bindCore() 时一次处理完，然后替换方法实现
// 清晰、统一、单一职责
```

### 同一个方法名，不同阶段不同行为

```typescript
// loader.ts - Phase 1
runtime.registerProvider = (name, config, extensionPath) => {
  runtime.pendingProviderRegistrations.push({ name, config, extensionPath });
};

// runner.ts - Phase 2
runtime.registerProvider = (name, config) => {
  modelRegistry.registerProvider(name, config);
};
```

**这是高级的设计 taste**：
- 方法名不变（扩展开发者无需关心阶段）
- 内部行为改变（系统自动处理）
- 类型注释说明了这个行为变化：
  ```typescript
  /**
   * Before bindCore(): queues registrations.
   * After bindCore(): calls ModelRegistry directly.
   */
  registerProvider: (name: string, config: ProviderConfig, extensionPath?: string) => void;
  ```

## 八、总结：ExtensionRuntime 的设计精髓

### 1. Intersection Type 的语义表达

```typescript
ExtensionRuntime extends ExtensionRuntimeState, ExtensionActions
```

表达：Runtime = State（早可用）+ Actions（晚可用）

### 2. Throwing Stubs 的安全保证

```typescript
sendMessage: notInitialized  // 类型完整，行为受限
```

比 undefined 更好：明确的错误信息 + 可教育的错误

### 3. 双阶段行为的无缝切换

```typescript
// Phase 1: 入队
registerProvider = queue;

// Phase 2: 直接调用
registerProvider = directCall;
```

同一个方法名，内部行为自动适配阶段

### 4. 共享 Runtime + 独立 Extension

```
┌─────────────────────────────────────┐
│  Shared Runtime                     │
│  - flagValues（全局一致）            │
│  - Actions（唯一实现）               │
│  - invalidate（同步失效）            │
├─────────────────────────────────────┤
│  Extension A │ Extension B │ ...    │
│  handlers    │ handlers    │        │
│  tools       │ tools       │        │
│  commands    │ commands    │        │
└─────────────────────────────────────┘
```

### 5. assertActive 的 stale 防御

```typescript
runtime.assertActive();  // 每次使用前检查
runtime.invalidate();    // session 切换时失效
```

防止扩展开发者误用旧 context

---

**应用场景判断**：

如果你的系统有以下特征，可以用这个设计：

1. **多阶段初始化**：需要先收集信息，后绑定实现
2. **方法行为需要切换**：同一个方法名，不同阶段不同行为
3. **全局状态共享**：多个组件需要看到同一个状态
4. **stale 防御**：某些操作会让其他引用失效

**相关阅读**：
- [[extension-system-design-analysis]] 扩展系统整体设计
- [[throwing-stubs-pattern]] Throwing Stubs 模式的更多应用