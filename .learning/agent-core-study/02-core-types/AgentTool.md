
`AgentTool` 是一个 **面向 Agent 的增强工具接口**，提供了：

- UI 友好的展示（`label`）
    
- 参数容错（`prepareArguments`）
    
- 可中断、可流式更新的执行（`execute` 的 `signal` 和 `onUpdate`）
    
- 细粒度并发控制（`executionMode`）
    

它与 `AgentState` 中的 `tools` 数组紧密结合，并且浅拷贝策略让工具对象自身可以安全地在外部被修改，同时数组结构本身受 setter 保护。

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

