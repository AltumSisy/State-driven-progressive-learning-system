```typescript
/**
 * Public agent state.
 *
 * `tools` and `messages` use accessor properties so implementations can copy
 * assigned arrays before storing them.
 */
export interface AgentState {
	/** System prompt sent with each model request. */
	systemPrompt: string;
	/** Active model used for future turns. */
	model: Model<any>;
	/** Requested reasoning level for future turns. */
	thinkingLevel: ThinkingLevel;
	/** Available tools. Assigning a new array copies the top-level array. */
	set tools(tools: AgentTool<any>[]);
	get tools(): AgentTool<any>[];
	/** Conversation transcript. Assigning a new array copies the top-level array. */
	set messages(messages: AgentMessage[]);
	get messages(): AgentMessage[];
	/**
	 * True while the agent is processing a prompt or continuation.
	 *
	 * This remains true until awaited `agent_end` listeners settle.
	 */
	readonly isStreaming: boolean;
	/** Partial assistant message for the current streamed response, if any. */
	readonly streamingMessage?: AgentMessage;
	/** Tool call ids currently executing. */
	readonly pendingToolCalls: ReadonlySet<string>;
	/** Error message from the most recent failed or aborted assistant turn, if any. */
	readonly errorMessage?: string;
}
```

这是一下的解释：
这段代码定义了一个 TypeScript 接口 `AgentState`，用于描述一个**公共代理（Agent）的状态**。它主要服务于类似 AI 对话系统（例如基于大语言模型的智能体），记录了代理运行所需的核心配置、对话历史以及实时状态。

具体各个字段和特性的作用如下：

- **`systemPrompt`**  
  系统提示词，每次模型请求都会携带，用于设定代理的角色、行为规则等。

- **`model`**  
  当前激活的模型（泛型 `Model<any>`），用于后续的对话轮次。

- **`thinkingLevel`**  
  请求的推理级别（`ThinkingLevel`），控制模型在回答时的“思考深度”或精细程度。

- **`tools`（访问器属性）**  
  代理可用的工具列表（`AgentTool<any>[]`）。  
  通过 `set` 赋值时会**复制数组的顶层**（浅拷贝），避免外部直接修改原数组；`get` 返回当前内部数组。这样设计可以让实现者在存储之前对数组做防御性拷贝。

- **`messages`（访问器属性）**  
  对话转录（`AgentMessage[]`），即完整的对话历史。同样通过 `set` 赋值时复制顶层数组，`get` 返回内部数组，保证状态的安全更新。

- **`isStreaming`（只读）**  
  代理是否正在处理提示或继续生成内容（流式响应）。为 `true` 期间会等待所有 `agent_end` 监听器执行完毕后才变为 `false`。

- **`streamingMessage`（只读，可选）**  
  当前流式响应中部分构建中的助手消息，用于实时展示生成的内容。

- **`pendingToolCalls`（只读）**  
  当前正在执行中的工具调用 ID 集合（`ReadonlySet<string>`），用于追踪哪些工具调用尚未完成。

- **`errorMessage`（只读，可选）**  
  最近一次失败或中止的助手轮次所产生的错误信息，便于上层进行错误处理或展示。

整体上，这个接口描述了代理的**配置快照 + 运行时状态**，并且通过访问器属性对数组类型数据进行只读或拷贝控制，增强了状态管理的可控性和安全性。它通常会被某个具体的代理类（如 `Agent` 实现）所实现，供外部调用者获取或监听代理状态的变化。

下面是一个具体的 `AgentState` 示例，展示 **浅拷贝** 的实际行为，以及为什么这种设计在 Agent 场景中足够且高效。

## 示例：创建 Agent 并修改 tools / messages

假设我们有一个实现了 `AgentState` 接口的类 `Agent`（或使用 `createMutableAgentState` 工厂函数）。

```typescript
import { createMutableAgentState } from './agent';

// 1. 创建一些工具对象（这些是对象，有属性）
const weatherTool = { name: 'get_weather', exec: () => {} };
const calculatorTool = { name: 'calc', exec: () => {} };

// 2. 外部传入的初始数组
const initialTools = [weatherTool, calculatorTool];

// 3. 创建可变状态
const state = createMutableAgentState({
  systemPrompt: 'You are a helpful assistant',
  model: 'gpt-4',
  thinkingLevel: 'high',
  tools: initialTools,
  messages: []
});

// 此时 state 内部 tools 数组是 initialTools 的浅拷贝：
//  state._tools ≠ initialTools （不同数组）
//  但 state._tools[0] === initialTools[0] （同一个 weatherTool 对象）
```

## 浅拷贝的效果：修改对象属性会影响双方

```typescript
// 外部修改工具对象的属性
weatherTool.name = 'get_current_weather';

// 内部 state 中的同一个工具对象也被修改了
console.log(state.tools[0].name); // 'get_current_weather' ✅ 同步
```

**这正是浅拷贝期望的行为**：Agent 需要知道工具的最新配置，外部修改工具对象时，Agent 自动感知。

## 浅拷贝的效果：替换数组不影响外部

```typescript
// 外部想在原数组上加一个新工具
const newTool = { name: 'search', exec: () => {} };
initialTools.push(newTool);   // 修改外部数组

// 但 state 内部的 tools 数组并没有变（因为它是独立的数组）
console.log(state.tools.length); // 2 (还是原来的两个工具，没有 search)

// 正确做法：通过 setter 整体替换
state.tools = [...state.tools, newTool]; // 内部会再浅拷贝一次
console.log(state.tools.length); // 3 ✅
```

## 如果换成深拷贝会怎样？

```typescript
// 假设 setter 做了深拷贝
set tools(next) { this._tools = deepClone(next); }

// 外部修改对象属性
weatherTool.name = 'new_name';
// 内部工具对象是深拷贝出来的新对象，name 还是旧值 'get_weather'
console.log(state.tools[0].name); // 'get_weather' ❌ 不同步！Bug 隐藏了
```

这就是为什么深拷贝在这里有害：**Agent 应该与外部共享工具/消息的对象实例**，除非你明确要求完全隔离（但 Agent 场景通常不需要）。

---

## 总结示例关键点

| 操作 | 浅拷贝结果 | 深拷贝结果 |
|------|-----------|-----------|
| 外部修改工具对象属性 | Agent 同步看到修改 ✅ | Agent 看不到 ❌（状态分裂） |
| 外部向原数组 push 新工具 | Agent 不受影响（安全隔离数组） | 不受影响（但浪费性能） |
| 外部替换整个数组 | 通过 setter 复制后隔离 ✅ | 隔离但每个对象都复制（昂贵） |

因此 `AgentState` 的设计选择浅拷贝是**精准防御**：只防御数组被替换（避免外部代码意外清空或换掉整个列表），同时允许共享对象变更，保持数据同步。


```typescript
/** Tool definition used by the agent runtime. */
export interface AgentTool<TParameters extends TSchema = TSchema, TDetails = any> extends Tool<TParameters> {
	/** Human-readable label for UI display. */
	label: string;
	/**
	 * Optional compatibility shim for raw tool-call arguments before schema validation.
	 * Must return an object that matches `TParameters`.
	 */
	prepareArguments?: (args: unknown) => Static<TParameters>;
	/** Execute the tool call. Throw on failure instead of encoding errors in `content`. */
	execute: (
		toolCallId: string,
		params: Static<TParameters>,
		signal?: AbortSignal,
		onUpdate?: AgentToolUpdateCallback<TDetails>,
	) => Promise<AgentToolResult<TDetails>>;
	/**
	 * Per-tool execution mode override.
	 * - "sequential": this tool must execute one at a time with other tool calls.
	 * - "parallel": this tool can execute concurrently with other tool calls.
	 *
	 * If omitted, the default execution mode applies.
	 */
	executionMode?: ToolExecutionMode;
}
```

解释下：
从 `AgentTool` 的定义来看，它扩展了基础的 `Tool<TParameters>`，为 Agent 运行时添加了更丰富的语义和控制能力。下面逐一拆解每个字段的作用，并结合前文 `AgentState` 中的 `tools` 数组说明其在实际 Agent 中的使用方式。

---

## 1. `AgentTool` 的核心作用

- 它是 Agent **可以调用的外部能力**（如搜索数据库、调用 API、执行计算等）的**描述 + 实现**。
- 与普通 `Tool` 相比，增加了 UI 展示、参数预处理、执行模式控制等 Agent 特有的需求。

---

## 2. 字段详解

### `label: string`
- **人可读的显示标签**，用于 UI（如工具选择面板、执行日志）。
- 例如：`label: "Get Weather"` 比 `name: "get_weather"` 更友好。

### `prepareArguments?: (args: unknown) => Static<TParameters>`
- **可选**的参数预处理函数，在 JSON schema 校验**之前**执行。
- 用途：处理模型传参不标准的情况（例如模型把 JSON 包在字符串里、缺少顶层字段等），将其转换为符合 `TParameters` 结构的对象。
- 输入 `args` 是原始调用参数（通常是 `unknown`），输出必须是 schema 校验能通过的对象。  
  *如果不需要预处理，可以省略该字段，直接走 schema 校验。*

### `execute: (toolCallId, params, signal?, onUpdate?) => Promise<AgentToolResult<TDetails>>`
- **工具的核心执行逻辑**。
- `toolCallId`：本次工具调用的唯一标识（用于关联结果、取消、更新回调）。
- `params`：经过 `prepareArguments` 和 schema 校验后的类型安全参数。
- `signal`：可选的 `AbortSignal`，用于支持执行中取消（例如用户点击停止、超时）。
- `onUpdate`：可选的进度/状态更新回调，允许工具在执行过程中**流式返回中间结果**（类型为 `AgentToolUpdateCallback<TDetails>`）。例如：搜索时逐步返回部分匹配项，或显示长任务的百分比。
- 返回值 `Promise<AgentToolResult<TDetails>>` 包含执行结果（成功的数据或失败信息），`TDetails` 是附加的元数据类型（可自定义，比如执行耗时、中间过程等）。

### `executionMode?: ToolExecutionMode`
- **执行模式覆盖**，控制该工具与其他工具调用之间的并发策略。
- 可能值：
  - `"sequential"`：即使多个工具调用同时请求，该工具也必须**一个一个依次执行**（例如写同一个文件、占用独占资源）。
  - `"parallel"`：可以与其他工具调用并发执行（大多数无副作用的只读工具适用）。
  - 如果省略，则遵循 Agent 全局的默认执行模式（例如由 `AgentConfig` 决定）。
- 这允许精细控制并发行为，避免竞态条件或资源冲突。

---

## 3. 在 `AgentState.tools` 中的应用

`AgentState` 中的 `tools: AgentTool<any>[]` 正是存储这些工具定义的地方。Agent 在每次调用模型前，会将工具 schema 传递给模型（模型可选择调用），收到工具调用请求后，Agent 会：

1. 根据 `toolCallId` 找到对应的 `AgentTool`。
2. 如果有 `prepareArguments`，先转换参数。
3. 使用 JSON schema 校验参数。
4. 创建 `AbortController`（与外部 `signal` 合并）并调用 `execute`。
5. 如果该工具的 `executionMode` 为 `"sequential"`，则排队等待，否则并行执行。
6. 通过 `onUpdate` 回调将中间状态写回 Agent 的 `streamingMessage` 或单独的进度消息。

---

## 4. 与前文“浅拷贝”的关联

因为 `tools` 数组存储的是 **对象引用**（浅拷贝），所以：
- 外部代码可以**动态修改某个 `AgentTool` 的属性**（例如修改 `label`、替换 `execute` 实现），Agent 会立即感知，无需替换整个数组。
- 但如果外部执行 `agent.state.tools = [newTool]`，setter 会复制新数组，保护 Agent 内部状态不被意外替换。

这种设计在工具管理中很有用：例如运行时启用/禁用某个工具（修改 `enabled` 字段，虽然接口中没显式给出，但可以自定义属性），或动态调整工具的 `executionMode`。

---

## 总结

`AgentTool` 是一个 **面向 Agent 的增强工具接口**，提供了：
- UI 友好的展示（`label`）
- 参数容错（`prepareArguments`）
- 可中断、可流式更新的执行（`execute` 的 `signal` 和 `onUpdate`）
- 细粒度并发控制（`executionMode`）

它与 `AgentState` 中的 `tools` 数组紧密结合，并且浅拷贝策略让工具对象自身可以安全地在外部被修改，同时数组结构本身受 setter 保护。


完全理解。TypeScript 的泛型（`<...>`）对新手来说确实有点吓人。我们拆开来看，用大白话解释。

---

## 1. 基础：什么是泛型？

泛型就是 **“类型参数”** —— 让你在使用接口/函数时再指定具体类型，而不是提前写死。

类比函数的参数：
- 函数参数：`function add(a, b) { return a + b; }` — `a` 和 `b` 是具体的值，调用时传入 `1, 2`
- 泛型参数：`interface Box<T> { value: T }` — `T` 是一个**类型的占位符**，使用时可以写 `Box<string>`，表示 `value` 是 `string` 类型

这样接口可以适配多种类型，不用为每个类型单独写一个接口。

---

## 2. `AgentTool<TParameters extends TSchema = TSchema, TDetails = any>`

这里有三个部分：

### ① `<TParameters extends TSchema>`
- 声明了一个类型参数叫 `TParameters`
- `extends TSchema` 表示 `TParameters` **必须符合** `TSchema` 的形状（即必须是某种 JSON Schema 类型约束）
- 为什么约束？因为这个工具的参数要能被 JSON Schema 校验，所以参数类型必须能描述为 Schema。

### ② `= TSchema`
- 给 `TParameters` 一个**默认类型**：如果你不指定，它默认就是 `TSchema`
- 大多数情况下你不需要关心具体参数形状，所以默认就行。

### ③ `TDetails = any`
- 第二个类型参数 `TDetails`，默认是 `any`
- 这个 `TDetails` 用于工具执行过程中返回的额外元数据（比如进度信息、执行日志等）。你如果不关心，就用 `any`。

---

## 3. 图解：泛型如何在实际中填入具体类型

假设我们要定义一个获取天气的工具：

```typescript
// 1. 定义工具参数的 TypeScript 类型（符合 TSchema 约束）
interface GetWeatherParams {
  city: string;
  unit: 'celsius' | 'fahrenheit';
}

// 2. 实现 AgentTool，此时填入具体的 TParameters
const weatherTool: AgentTool<GetWeatherParams, { requestId: string }> = {
  name: 'get_weather',   // 继承自 Tool
  label: 'Get Weather',
  execute: async (toolCallId, params, signal, onUpdate) => {
    // params 的类型自动推断为 GetWeatherParams，有 city 和 unit
    console.log(params.city);
    return { content: 'Sunny', details: { requestId: '123' } };
  }
};
```

如果不指定 `TDetails`，可以省略：
```typescript
const weatherTool: AgentTool<GetWeatherParams> = { ... }
// TDetails 默认 any
```

如果参数很简单，甚至可以默认：
```typescript
const simpleTool: AgentTool = { ... }  // TParameters 默认 TSchema，TDetails 默认 any
```

---

## 4. 为什么需要这样写？

- **类型安全**：`execute` 函数里的 `params` 会自动获得正确的类型（如上面的 `city` 和 `unit`），不用手动断言。
- **灵活性**：同一个 `AgentTool` 接口可以用于参数形状完全不同的工具（天气、搜索、发送邮件等）。
- **与 schema 集成**：`TParameters extends TSchema` 确保参数类型可以被 JSON Schema 验证（框架内部会用 schema 校验参数）。

---

## 5. 新手常见困惑：`extends` 在这里不是“继承类”

- 在泛型约束中，`T extends U` 表示 **T 必须是 U 的子类型**，也就是 T 可以赋值给 U。
- 对于对象类型：`{ city: string } extends { city: string; unit?: string }` 是成立的（前者有必要的属性）。
- 你不需要完全理解深层原理，只需知道：`TParameters extends TSchema` 表示 TParameters 必须是一个可以被 schema 描述的类型。

---

## 总结

| 写法 | 通俗含义 |
|------|---------|
| `<TParameters extends TSchema>` | 定义一个类型参数，它必须是符合某种规范的类型 |
| `= TSchema` | 如果不指定，默认就是那个规范类型 |
| `<TDetails = any>` | 另一个类型参数，默认是 any，用于额外信息 |

所以读 `AgentTool<TParameters extends TSchema = TSchema, TDetails = any>` 就是：  
**“一个工具，它接受两类类型参数：第一类是它的参数形状（默认是通用 schema），第二类是额外详情类型（默认 any）”**。


这里总结一下：
我用最直白的方式帮你总结，保证好记。

---

## AgentState（代理的状态）— “三块记忆法”

把状态分成三块：**配置**、**对话**、**运行中**。

### 1. 配置（怎么干活）
- `systemPrompt` — 系统提示词（角色设定）
- `model` — 用哪个模型（GPT-4、Claude...）
- `thinkingLevel` — 思考深度（off / low / high）

### 2. 对话内容（记着什么）
- `tools` — 可用工具列表（数组，有防护）
- `messages` — 聊天记录（数组，有防护）

### 3. 运行中状态（正在干嘛）
- `isStreaming` — 是否正在输出（只读）
- `streamingMessage` — 当前输出到一半的消息（只读）
- `pendingToolCalls` — 正在执行的工具调用ID集合（只读）
- `errorMessage` — 最近一次错误信息（只读）

> 记忆口诀：**配置、对话、运行中，三块记住不头痛。**

---

## AgentTool（代理的工具）— “五要素法”

一个工具包含这五样东西：

1. **`label`** — 显示名字（给人看的，如“查天气”）
2. **`prepareArguments`**（可选）— 参数预处理（模型给的参数不标准时，你帮他修一下）
3. **`execute`** — 真正干活的方法（核心！）
4. **`executionMode`**（可选）— 执行模式（串行还是并行）
5. 还从基础 `Tool` 继承 `name` 和 `schema`（工具标识和参数格式）

### `execute` 的参数（四个参数）
- `toolCallId` — 这次调用的唯一ID
- `params` — 校验后的参数（类型安全）
- `signal` — 取消信号（可以中途停止）
- `onUpdate` — 进度回调（干到一半时回报）

> 记忆口诀：**名标预执模，干活传四宝（ID、参数、信号、回调）。**

---

## 一句话对比

- **AgentState**：代理的“状态卡”，记着配置、聊天记录和正在干嘛。
- **AgentTool**：代理的“技能卡”，写着技能叫什么、怎么准备参数、怎么执行、能否并行。

这样是不是好记多了？



```typescript
export interface AgentLoopConfig extends SimpleStreamOptions {
	model: Model<any>;

	/**
	 * Converts AgentMessage[] to LLM-compatible Message[] before each LLM call.
	 *
	 * Each AgentMessage must be converted to a UserMessage, AssistantMessage, or ToolResultMessage
	 * that the LLM can understand. AgentMessages that cannot be converted (e.g., UI-only notifications,
	 * status messages) should be filtered out.
	 *
	 * Contract: must not throw or reject. Return a safe fallback value instead.
	 * Throwing interrupts the low-level agent loop without producing a normal event sequence.
	 *
	 * @example
	 * ```typescript
	 * convertToLlm: (messages) => messages.flatMap(m => {
	 *   if (m.role === "custom") {
	 *     // Convert custom message to user message
	 *     return [{ role: "user", content: m.content, timestamp: m.timestamp }];
	 *   }
	 *   if (m.role === "notification") {
	 *     // Filter out UI-only messages
	 *     return [];
	 *   }
	 *   // Pass through standard LLM messages
	 *   return [m];
	 * })
	 * ```
	 */
	convertToLlm: (messages: AgentMessage[]) => Message[] | Promise<Message[]>;

	/**
	 * Optional transform applied to the context before `convertToLlm`.
	 *
	 * Use this for operations that work at the AgentMessage level:
	 * - Context window management (pruning old messages)
	 * - Injecting context from external sources
	 *
	 * Contract: must not throw or reject. Return the original messages or another
	 * safe fallback value instead.
	 *
	 * @example
	 * ```typescript
	 * transformContext: async (messages) => {
	 *   if (estimateTokens(messages) > MAX_TOKENS) {
	 *     return pruneOldMessages(messages);
	 *   }
	 *   return messages;
	 * }
	 * ```
	 */
	transformContext?: (messages: AgentMessage[], signal?: AbortSignal) => Promise<AgentMessage[]>;

	/**
	 * Resolves an API key dynamically for each LLM call.
	 *
	 * Useful for short-lived OAuth tokens (e.g., GitHub Copilot) that may expire
	 * during long-running tool execution phases.
	 *
	 * Contract: must not throw or reject. Return undefined when no key is available.
	 */
	getApiKey?: (provider: string) => Promise<string | undefined> | string | undefined;

	/**
	 * Called after each turn fully completes and `turn_end` has been emitted.
	 *
	 * If it returns true, the loop emits `agent_end` and exits before polling steering or follow-up queues,
	 * without starting another LLM call. The current assistant response and any tool executions finish normally.
	 *
	 * Use this to request a graceful stop after the current turn, e.g. before context gets too full.
	 *
	 * Contract: must not throw or reject. Throwing interrupts the low-level agent loop without producing a normal event sequence.
	 */
	shouldStopAfterTurn?: (context: ShouldStopAfterTurnContext) => boolean | Promise<boolean>;

	/**
	 * Called after `turn_end` and before the loop decides whether another provider request should start.
	 * Return replacement context/model/thinking state to affect the next turn in this run.
	 * Return undefined to keep using the current context/config.
	 */
	prepareNextTurn?: (
		context: PrepareNextTurnContext,
	) => AgentLoopTurnUpdate | undefined | Promise<AgentLoopTurnUpdate | undefined>;

	/**
	 * Returns steering messages to inject into the conversation mid-run.
	 *
	 * Called after the current assistant turn finishes executing its tool calls, unless `shouldStopAfterTurn` exits first.
	 * If messages are returned, they are added to the context before the next LLM call.
	 * Tool calls from the current assistant message are not skipped.
	 *
	 * Use this for "steering" the agent while it's working.
	 *
	 * Contract: must not throw or reject. Return [] when no steering messages are available.
	 */
	getSteeringMessages?: () => Promise<AgentMessage[]>;

	/**
	 * Returns follow-up messages to process after the agent would otherwise stop.
	 *
	 * Called when the agent has no more tool calls and no steering messages.
	 * If messages are returned, they're added to the context and the agent
	 * continues with another turn.
	 *
	 * Use this for follow-up messages that should wait until the agent finishes.
	 *
	 * Contract: must not throw or reject. Return [] when no follow-up messages are available.
	 */
	getFollowUpMessages?: () => Promise<AgentMessage[]>;

	/**
	 * Tool execution mode.
	 * - "sequential": execute tool calls one by one
	 * - "parallel": preflight tool calls sequentially, then execute allowed tools concurrently;
	 *   emit `tool_execution_end` in tool completion order after each tool is finalized,
	 *   then emit tool-result message artifacts later in assistant source order
	 *
	 * Default: "parallel"
	 */
	toolExecution?: ToolExecutionMode;

	/**
	 * Called before a tool is executed, after arguments have been validated.
	 *
	 * Return `{ block: true }` to prevent execution. The loop emits an error tool result instead.
	 * The hook receives the agent abort signal and is responsible for honoring it.
	 */
	beforeToolCall?: (context: BeforeToolCallContext, signal?: AbortSignal) => Promise<BeforeToolCallResult | undefined>;

	/**
	 * Called after a tool finishes executing, before `tool_execution_end` and tool-result message events are emitted.
	 *
	 * Return an `AfterToolCallResult` to override parts of the executed tool result:
	 * - `content` replaces the full content array
	 * - `details` replaces the full details payload
	 * - `isError` replaces the error flag
	 * - `terminate` replaces the early-termination hint
	 *
	 * Any omitted fields keep their original values. No deep merge is performed.
	 * The hook receives the agent abort signal and is responsible for honoring it.
	 */
	afterToolCall?: (context: AfterToolCallContext, signal?: AbortSignal) => Promise<AfterToolCallResult | undefined>;
}
```

好的，我们再来拆解 `AgentLoopConfig`。这个接口比 `AgentState` 复杂很多，但我们可以用 **“配置主循环的八大钩子”** 来记。

---

## AgentLoopConfig — 代理主循环的配置中心

主循环是什么？就是 **“模型推理 → 执行工具 → 继续推理”** 这个无限循环，直到没有工具调用且没有后续消息为止。  
`AgentLoopConfig` 就是用来**定制这个循环每一个关键步骤**的配置对象。

### 先看它扩展了什么：`SimpleStreamOptions`
- 通常包含 `stream: true`、`onChunk` 等基础流式选项（具体这里没展示，但知道它是基础就行）。

### 八大钩子（按执行顺序记忆）

1. **`model`** — 用哪个模型（必填，跟 `AgentState` 里的 `model` 不同：这里的是循环配置专用的）

2. **`convertToLlm`** — 把内部 `AgentMessage[]` 转成 LLM 能理解的 `Message[]`。  
   - 作用：过滤掉 UI 通知、状态消息等无用消息；将自定义角色转为标准角色。  
   - 记忆点：**“翻译官”**，把内部语言翻译给模型听。

3. **`transformContext`**（可选）— 在翻译之前对完整对话做预处理。  
   - 常见用法：裁剪超长对话、注入外部知识。  
   - 记忆点：**“整理官”**，先整理好对话内容再交给翻译官。

4. **`getApiKey`**（可选）— 每次调用模型前动态获取 API Key。  
   - 用于短时令牌（如 OAuth），避免工具执行很久后 Key 过期。  
   - 记忆点：**“钥匙官”**，关键时刻提供钥匙。

5. **`shouldStopAfterTurn`**（可选）— 每轮结束（模型输出 + 工具执行都完成）后，询问“是否就此停止？”  
   - 返回 `true` 就优雅退出循环，不再发起下一轮 LLM 调用。  
   - 记忆点：**“刹车官”**，看时机叫停。

6. **`prepareNextTurn`**（可选）— 决定下一轮的上下文、模型、思考深度是否要改变。  
   - 可以替换整个状态，返回 `undefined` 就保持原样。  
   - 记忆点：**“调参官”**，调整下一回合的配置。

7. **`getSteeringMessages`**（可选）— 在下一轮开始前，主动注入一些“引导消息”。  
   - 例如：“注意用户情绪”、“优先使用缓存”。  
   - 记忆点：**“方向盘”**，引导代理走向。

8. **`getFollowUpMessages`**（可选）— 当代理什么工具都不调用、也没有引导消息时，询问是否还有“后续消息”需要处理。  
   - 例如：外部队列里有人补充了一条新问题。  
   - 记忆点：**“加餐官”**，代理快停了，再喂它点东西。

### 工具执行相关的配置（也是循环的一部分）

- **`toolExecution`** — 工具执行模式：`"sequential"`（串行）还是 `"parallel"`（并行），默认并行。  
- **`beforeToolCall`**（可选）— 每个工具执行前调用，可阻止执行（`{ block: true }`）。  
- **`afterToolCall`**（可选）— 每个工具执行后调用，可修改结果内容、错误标志等。

---

## 一图流记忆（想象一个流水线）

```
[LLM 调用] 
   ↑            ↓
   ↑       [工具执行]
   ↑            ↓
   ↑       [循环结束？]
   ↑            ↓
[后处理]  ←  [注入引导/后续消息]
```

每个步骤都有对应的钩子：
- 调用 LLM 前：`transformContext` → `convertToLlm` → `getApiKey`
- 工具执行前后：`beforeToolCall` / `afterToolCall`
- 整轮结束后：`shouldStopAfterTurn` → `prepareNextTurn`
- 下一轮开始前：`getSteeringMessages`
- 无工具且无引导时：`getFollowUpMessages`

---

## 与 AgentState、AgentTool 的关系

| 概念 | 作用 | 存放位置 |
|------|------|----------|
| `AgentState` | 代理的**当前瞬时状态**（当前模型、当前对话、当前工具列表） | 运行时不断变化 |
| `AgentTool` | 定义**单个技能**（叫什么、怎么执行、是否并发） | 放在 `AgentState.tools` 数组中 |
| `AgentLoopConfig` | 定义**主循环的行为规则**（如何翻译消息、何时停止、如何动态调整） | 代理创建时传入，通常不变 |

简单说：  
- **State** = 这一刻的“是什么”  
- **Tool** = 技能卡  
- **LoopConfig** = 工作流程规则书

这样是不是好记多了？

```typescript
/**
 * Stream function used by the agent loop.
 *
 * Contract:
 * - Must not throw or return a rejected promise for request/model/runtime failures.
 * - Must return an AssistantMessageEventStream.
 * - Failures must be encoded in the returned stream via protocol events and a
 *   final AssistantMessage with stopReason "error" or "aborted" and errorMessage.
 */
export type StreamFn = (
	...args: Parameters<typeof streamSimple>
) => ReturnType<typeof streamSimple> | Promise<ReturnType<typeof streamSimple>>;

/**
 * Configuration for how tool calls from a single assistant message are executed.
 *
 * - "sequential": each tool call is prepared, executed, and finalized before the next one starts.
 * - "parallel": tool calls are prepared sequentially, then allowed tools execute concurrently.
 *   `tool_execution_end` is emitted in tool completion order after each tool is finalized,
 *   while tool-result message artifacts are emitted later in assistant source order.
 */
export type ToolExecutionMode = "sequential" | "parallel";

/**
 * Controls how many queued user messages are injected when the agent loop reaches a queue drain point.
 *
 * - "all": drain and inject every queued message at that point.
 * - "one-at-a-time": drain and inject only the oldest queued message, leaving the rest queued for later drain points.
 */
export type QueueMode = "all" | "one-at-a-time";

/** A single tool call content block emitted by an assistant message. */
export type AgentToolCall = Extract<AssistantMessage["content"][number], { type: "toolCall" }>;

/**
 * Result returned from `beforeToolCall`.
 *
 * Returning `{ block: true }` prevents the tool from executing. The loop emits an error tool result instead.
 * `reason` becomes the text shown in that error result. If omitted, a default blocked message is used.
 */
export interface BeforeToolCallResult {
	block?: boolean;
	reason?: string;
}
```

好的，我们继续看这几个辅助类型。它们主要是为 `AgentLoopConfig` 里的钩子和配置提供更精细的控制。

---

## 1. `StreamFn` — 流式函数包装器

```typescript
export type StreamFn = (
  ...args: Parameters<typeof streamSimple>
) => ReturnType<typeof streamSimple> | Promise<ReturnType<typeof streamSimple>>;
```

**作用**：定义一个**不会抛出异常**的流式调用函数，所有失败都通过流内部的事件（比如 `error` 消息）来表达。

**通俗理解**：  
- `streamSimple` 是底层的一个 LLM 流式调用函数（这里没给出定义，但可以想象它接受模型、消息、选项，返回一个事件流）。  
- `StreamFn` 就是 `streamSimple` 的“签名复制版” —— 参数和返回值类型完全一样，但额外加了一个**强制契约**：绝不能 throw 或 reject，只能正常返回一个流，即使模型请求失败也要在流里输出错误事件。  
- 这样外层循环就不用 `try-catch` 每个调用，而是统一监听流事件来处理错误。

**何时用**：  
通常由框架内部提供，普通用户很少直接定义。但在定制 `AgentLoopConfig` 时，你可以替换默认的流函数（例如改用不同的后端），只要遵循这个契约。

---

## 2. `ToolExecutionMode` — 工具执行模式

```typescript
export type ToolExecutionMode = "sequential" | "parallel";
```

你已经见过，在 `AgentLoopConfig.toolExecution` 中使用。

- **`sequential`**：一次只执行一个工具调用，等前一个完成再开始下一个。  
  - 适合有冲突风险的写操作（如写同一文件、更新同一数据库行）。

- **`parallel`**：可以同时执行多个工具调用（具体哪些能并行由工具自身的 `executionMode` 以及框架调度决定）。  
  - 适合只读或独立的操作（如查多个不同 API）。

---

## 3. `QueueMode` — 队列消耗模式

```typescript
export type QueueMode = "all" | "one-at-a-time";
```

**作用**：控制当代理循环“排空点”（没有更多工具调用、没有引导消息时）如何处理挂起的用户消息队列。

- **`"all"`**：一次性注入队列中的所有待处理消息，然后继续循环。  
  - 适合批量处理场景，比如用户一次上传了多个问题。

- **`"one-at-a-time"`**：只注入最老的一条消息，其他的留在队列里，等到下一次排空点再处理。  
  - 适合需要逐条处理、中间可能触发复杂工具调用的场景，避免一次塞太多导致上下文爆炸。

这个模式可能出现在 `getFollowUpMessages` 或 `getSteeringMessages` 相关配置中（具体未展示，但常见于消息队列管理）。

---

## 4. `AgentToolCall` — 助理消息中的工具调用块

```typescript
export type AgentToolCall = Extract<AssistantMessage["content"][number], { type: "toolCall" }>;
```

**技术细节**：  
- `AssistantMessage["content"]` 是一个数组，每个元素可能包含文本、图像、toolCall 等不同类型。  
- `Extract<T, U>` 是 TypeScript 的实用类型，从联合类型 T 中筛选出符合 U 形状的那些成员。  
- 这里提取出 `content` 数组中 `type` 属性为 `"toolCall"` 的元素类型。

**通俗理解**：  
`AgentToolCall` 就是助理消息里**那个代表“我要调用工具”的块**。例如：
```json
{
  "type": "toolCall",
  "toolCallId": "call_abc",
  "toolName": "get_weather",
  "arguments": { "city": "Beijing" }
}
```
这个类型就是用来描述这种结构的。

**用途**：在钩子函数（如 `beforeToolCall`、`afterToolCall`）中，你会拿到这个 `AgentToolCall` 对象，从而知道要调用哪个工具、参数是什么。

---

## 5. `BeforeToolCallResult` — 工具调用前的拦截结果

```typescript
export interface BeforeToolCallResult {
  block?: boolean;
  reason?: string;
}
```

**作用**：`beforeToolCall` 钩子的返回值类型。用于决定是否阻止执行该工具。

- **`block: true`**：阻止本次工具调用。框架会生成一个“工具执行被阻止”的错误结果，添加到消息历史中。
- **`reason`**：可选，错误结果中显示的文本。如果不提供，会使用默认的阻止消息（如 "Tool call was blocked"）。

**示例**：
```typescript
beforeToolCall: async ({ toolCall }) => {
  if (toolCall.toolName === 'delete_file' && !userIsAdmin) {
    return { block: true, reason: 'You are not allowed to delete files.' };
  }
  return {}; // 不阻止
}
```

---

## 整体记忆

| 类型 | 一句话作用 |
|------|-----------|
| `StreamFn` | 安全的流式调用函数，不抛异常 |
| `ToolExecutionMode` | 工具是串行还是并行 |
| `QueueMode` | 挂起消息是一次全取还是一条一条取 |
| `AgentToolCall` | 消息中的工具调用块的结构定义 |
| `BeforeToolCallResult` | 钩子返回，决定是否阻止工具执行 |

这些类型共同构成了 `AgentLoopConfig` 背后精细控制的基础。把它们当作**配置的小零件**，组装起来就能定制复杂的代理行为。


实践：
好的，下面分别给出 `AgentState`、`AgentTool`、`AgentLoopConfig` 的完整用例。  
我会尽量写得像真实代码，并加上注释，方便你理解每个部分怎么用。

---

## 1. `AgentState` 用例

**场景**：创建一个 Agent 的状态，展示如何修改 `tools` 和 `messages`，以及只读属性的含义。

```typescript
import { createMutableAgentState } from './agent';

// 假设已有这些类型
type AgentTool<T = any> = { name: string; label: string; execute: () => Promise<any> };
type AgentMessage = { role: 'user' | 'assistant'; content: string };

// 1. 创建初始状态
const initialState = {
  systemPrompt: 'You are a helpful assistant.',
  model: 'gpt-4',
  thinkingLevel: 'high',
  tools: [
    { name: 'weather', label: 'Get Weather', execute: async () => ({ temp: 25 }) },
  ],
  messages: [
    { role: 'user', content: 'What is the weather?' },
  ],
};

const state = createMutableAgentState(initialState);

// 2. 读取配置
console.log(state.systemPrompt);     // "You are a helpful assistant."
console.log(state.model);            // "gpt-4"
console.log(state.thinkingLevel);    // "high"

// 3. 修改 tools（触发 setter，内部浅拷贝）
const newTool = { name: 'calculator', label: 'Calculate', execute: async () => ({ result: 42 }) };
state.tools = [...state.tools, newTool];  // 推荐方式：赋值新数组
console.log(state.tools.length);           // 2

// ❌ 直接 push 不会触发 setter，但能修改内部数组（设计上允许，但不推荐）
state.tools.push({ name: 'hack', label: 'Hack', execute: async () => ({}) });
console.log(state.tools.length);           // 3 → 意外增加了，说明这种操作会污染内部

// 正确做法：通过 setter 替换，保持控制
state.tools = state.tools.filter(t => t.name !== 'hack');
console.log(state.tools.length);           // 2

// 4. 修改 messages（同理）
state.messages = [...state.messages, { role: 'assistant', content: 'The weather is sunny.' }];
console.log(state.messages.length);        // 2

// 5. 只读属性（由框架维护，不能手动赋值）
console.log(state.isStreaming);            // false
console.log(state.pendingToolCalls);       // Set(0)
console.log(state.errorMessage);           // undefined
// state.isStreaming = true;               // ❌ 编译错误（只读）

// 6. 模拟流式过程中读取
// 假设内部设置了 streamingMessage
console.log(state.streamingMessage);       // undefined 或部分消息
```

**要点总结**：
- `tools` 和 `messages` 的 setter 会浅拷贝，防止外部数组被替换；
- 直接修改数组内容（如 `push`）虽被允许，但容易造成状态不可控，推荐整体替换；
- 只读属性只能由框架内部更新，外部只能读取。

---

## 2. `AgentTool` 用例

**场景**：定义一个查询天气的工具，包含参数预处理、执行逻辑、进度回调、执行模式。

```typescript
import { AgentTool } from './agent';

// 1. 定义参数类型（符合 TSchema）
interface WeatherParams {
  city: string;
  unit?: 'celsius' | 'fahrenheit';
}

// 2. 实现 AgentTool
const weatherTool: AgentTool<WeatherParams, { requestId: string }> = {
  name: 'get_weather',          // 继承自基础 Tool
  label: 'Get Weather',         // UI 显示用
  // 可选：参数预处理（兼容模型可能传错的格式）
  prepareArguments: (args: unknown) => {
    // 假设模型有时会把 city 包在字符串里："city=Beijing"
    if (typeof args === 'string' && args.includes('=')) {
      const city = args.split('=')[1];
      return { city } as WeatherParams;
    }
    // 否则直接返回（后续会有 schema 校验）
    return args as WeatherParams;
  },
  // 核心执行函数
  execute: async (toolCallId, params, signal, onUpdate) => {
    const { city, unit = 'celsius' } = params;
    
    // 模拟进度更新
    onUpdate?.({ status: 'fetching', details: { progress: 30 } });
    
    // 模拟可中断的异步请求
    const response = await fetch(`https://api.weather.com/${city}?unit=${unit}`, { signal });
    const data = await response.json();
    
    onUpdate?.({ status: 'done', details: { progress: 100 } });
    
    return {
      content: [{ type: 'text', text: `Temperature in ${city}: ${data.temp}°${unit === 'celsius' ? 'C' : 'F'}` }],
      details: { requestId: data.requestId },
    };
  },
  // 执行模式：并行（默认）或串行
  executionMode: 'parallel',   // 多个天气查询可并发
};

// 使用示例：在 Agent 中注册
// agent.state.tools = [weatherTool, ...otherTools];

// 模拟工具调用（Agent 内部会调用）
const result = await weatherTool.execute(
  'call_123',
  { city: 'Beijing', unit: 'celsius' },
  new AbortController().signal,
  (update) => console.log('Progress:', update)
);
console.log(result.content[0].text); // "Temperature in Beijing: 25°C"
```

**要点总结**：
- `prepareArguments` 对模型传参做容错；
- `execute` 接收 `toolCallId`、参数、取消信号、进度回调；
- `executionMode` 控制并发策略。

---

## 3. `AgentLoopConfig` 用例

**场景**：配置一个智能客服代理，包含消息转换、上下文修剪、动态 API Key、工具拦截、动态停止等。

```typescript
import { AgentLoopConfig, BeforeToolCallContext, AfterToolCallContext } from './agent';

const loopConfig: AgentLoopConfig = {
  // 基础模型
  model: 'gpt-4',

  // 1. 消息翻译：将内部消息转为 LLM 格式，过滤 UI 通知
  convertToLlm: (messages) => {
    return messages.flatMap(msg => {
      if (msg.role === 'notification') return [];           // 过滤掉通知消息
      if (msg.role === 'custom') {
        // 将自定义角色转为 user 消息
        return [{ role: 'user', content: msg.content, timestamp: msg.timestamp }];
      }
      return [msg];  // user/assistant/tool 原样通过
    });
  },

  // 2. 上下文预处理：裁剪超过 5000 字符的对话
  transformContext: async (messages) => {
    let totalLength = messages.reduce((sum, m) => sum + (m.content?.length || 0), 0);
    if (totalLength > 5000) {
      // 保留最近的 10 条消息
      return messages.slice(-10);
    }
    return messages;
  },

  // 3. 动态获取 API Key（例如从 OAuth 服务获取短期令牌）
  getApiKey: async (provider) => {
    if (provider === 'openai') {
      const token = await fetch('https://auth.example.com/token').then(r => r.json());
      return token.apiKey;
    }
    return undefined;
  },

  // 4. 工具执行前拦截：禁止 "delete_all_files" 工具
  beforeToolCall: async (context: BeforeToolCallContext, signal) => {
    if (context.toolCall.toolName === 'delete_all_files') {
      return { block: true, reason: 'This operation is not allowed.' };
    }
    return {}; // 允许执行
  },

  // 5. 工具执行后修改结果：为所有结果添加时间戳
  afterToolCall: async (context: AfterToolCallContext, signal) => {
    if (context.result.content) {
      // 在原内容后追加一个时间戳
      const timestamp = new Date().toISOString();
      context.result.content.push({ type: 'text', text: `\n[Executed at ${timestamp}]` });
    }
    return {}; // 返回空对象表示不覆盖其他字段
  },

  // 6. 每轮结束后决定是否停止（例如已经解决了用户问题）
  shouldStopAfterTurn: async (context) => {
    const lastAssistantMessage = context.messages.findLast(m => m.role === 'assistant');
    if (lastAssistantMessage?.content.includes('Solved')) {
      return true;  // 停止循环
    }
    return false;
  },

  // 7. 准备下一轮：可以动态修改模型或思考级别
  prepareNextTurn: async (context) => {
    if (context.turnCount > 3) {
      return { model: 'gpt-3.5-turbo', thinkingLevel: 'low' }; // 降级省钱
    }
    return undefined; // 保持原状
  },

  // 8. 获取引导消息（在下一轮 LLM 调用前注入）
  getSteeringMessages: async () => {
    // 例如从外部队列获取优先级指令
    const queue = await fetchPriorityQueue();
    return queue.map(cmd => ({ role: 'user', content: cmd }));
  },

  // 9. 获取后续消息（当代理没有工具调用且无引导时）
  getFollowUpMessages: async () => {
    // 例如从用户输入缓冲区取新消息
    const pending = await getUserPendingMessages();
    return pending.map(text => ({ role: 'user', content: text }));
  },

  // 10. 工具执行模式（默认并行）
  toolExecution: 'parallel',
};

// 然后创建 Agent 时传入这个配置
// const agent = new Agent({ initialState, loopConfig });
// agent.run("What's the weather?");
```

**要点总结**：
- 每个钩子都有明确的职责和输入/输出；
- 钩子函数**不能抛出异常**（契约要求），必须安全返回 fallback 值；
- 通过组合这些钩子，可以实现非常灵活和健壮的 Agent 行为。

---

## 最后的小抄

| 概念 | 一句话用途 |
|------|-----------|
| `AgentState` | 存储代理当前的状态（配置、对话、运行标志），通过 setter 浅拷贝保护数组引用。 |
| `AgentTool` | 定义一个可被代理调用的技能，包含参数预处理、执行逻辑、并发模式。 |
| `AgentLoopConfig` | 配置代理主循环的各个钩子，用于消息翻译、上下文管理、工具拦截、动态停止等。 |

希望这些例子能帮到你！如果有具体某个钩子还不清楚，欢迎继续提问。