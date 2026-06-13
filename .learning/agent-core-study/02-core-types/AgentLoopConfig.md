# AgentLoopConfig — 场景速查

好的，我们再来拆解 `AgentLoopConfig`。这个接口比 `AgentState` 复杂很多，但我们可以用 **”配置主循环的八大钩子”** 来记。

先用一个表格快速了解每个 Hook 的典型应用场景，后续再深入细节。

---

## 按阶段分组记忆

### LLM 调用前

| Hook | 场景 |
|------|------|
| `transformContext` | 对话太长要裁剪、需要注入外部知识、敏感信息要过滤 |
| `convertToLlm` | 有些消息模型不该看、角色格式不兼容 |
| `getApiKey` | Token 会过期、每个用户有不同 Key |

### 工具执行前后

| Hook             | 场景                             |
| ---------------- | ------------------------------ |
| `beforeToolCall` | 删除文件要确认、搜索有次数限制、所有调用要留痕        |
| `afterToolCall`  | 文件内容太长、命令失败要给建议、shutdown 执行完就停 |

### Turn 结束后

| Hook                  | 场景                     |
| --------------------- | ---------------------- |
| `prepareNextTurn`     | 分析复杂换强模型、对话积累太多、出错需要深思 |
| `shouldStopAfterTurn` | Token 用完了、用户不想等了、一直出错  |

### 消息注入

| Hook | 场景 |
|------|------|
| `getSteeringMessages` | 用户突然改口、每5轮提醒规则、文件被别人改了 |
| `getFollowUpMessages` | 任务队列排队、批量处理文件、回答完又有新问题 |

## 详细拆解

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

