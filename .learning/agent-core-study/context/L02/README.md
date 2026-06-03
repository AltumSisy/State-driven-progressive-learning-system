# L02 Context: 类型系统 (AgentState + AgentTool + 配置)

## 核心概念速查

### AgentState 属性分类

| 分类 | 属性 | 特性 |
|------|------|------|
| **可变** | `systemPrompt`, `model`, `thinkingLevel` | 直接赋值修改 |
| **可变+复制** | `tools`, `messages` | setter 时 `slice()` 复制 |
| **只读** | `isStreaming`, `streamingMessage`, `pendingToolCalls`, `errorMessage` | 运行状态观察 |

### 防御性拷贝机制

```typescript
// 闭包私有变量
let tools = initialState?.tools?.slice() ?? [];

// getter/setter
get tools() { return tools; }           // 暴露内部引用
set tools(next) { tools = next.slice(); } // 赋值时复制
```

**两种修改方式对比**：
- 原地 `push()`: 不触发 setter，直接修改内部数组
- 赋值新数组: 触发 setter，内外隔离

### AgentTool 结构

**继承自 pi-ai Tool**:
- `name`: 工具名称
- `description`: 工具描述
- `parameters`: TypeBox schema

**agent-core 新增**:
- `label`: UI 显示标签
- `prepareArguments`: 兼容性 shim（非验证器）
- `execute`: 执行函数签名
- `executionMode`: `"sequential" | "parallel"`

### execute 参数签名

```typescript
execute: (
  toolCallId: string,       // 事件关联 ID
  params: Static<TSchema>,  // TypeBox 验证后的参数
  signal?: AbortSignal,     // 取消信号
  onUpdate?: Callback,      // 进度回调
) => Promise<AgentToolResult>
```

### AgentLoopConfig 钩子

| 钩子 | 触发时机 | 返回值语义 |
|------|---------|-----------|
| `beforeToolCall` | 工具执行前 | `{ block: true }` → 发出 error tool result |
| `afterToolCall` | 工具执行后 | 字段级替换，无深度合并 |
| `shouldStopAfterTurn` | turn 结束后 | `true` → 优雅停止 |
| `prepareNextTurn` | 下一轮前 | 返回替换 context/model/thinkingLevel |
| `transformContext` | convertToLlm 前 | 上下文裁剪/注入 |

### 枚举类型

| 枚举 | 值 | 关键细节 |
|------|-----|---------|
| `ToolExecutionMode` | `sequential \| parallel` | parallel: 预检顺序 → 执行并发 → 结果按原序 |
| `QueueMode` | `all \| one-at-a-time` | 用户消息队列注入策略 |
| `ThinkingLevel` | `off → xhigh` (6级) | xhigh 仅部分模型支持，需检查 metadata |

## 设计哲学

### Discriminated Union
```typescript
type AgentEvent =
  | { type: "agent_start" }
  | { type: "agent_end"; messages: AgentMessage[] }
  // TypeScript 根据 type 字段推断其他字段
```

### Getter/Setter 保护
- 目的：拒绝外部数组替换，允许原地修改
- 实现：闭包私有变量 + setter 复制

### 泛型参数化
```typescript
interface AgentTool<TParameters extends TSchema, TDetails = any> {
  execute: (id, params: Static<TParameters>, ...) => Promise<AgentToolResult<TDetails>>;
}
```

## 常见错误

| 错误 | 后果 | 正确做法 |
|------|------|---------|
| 遗漏 `parameters` | TypeBox 验证失败 | `Type.Object({})` 空 schema |
| 混淆 `prepareArguments` | 当成验证器用 | 它是兼容性 shim，验证在之后 |
| `afterToolCallResult` 深度合并期望 | 丢失原值 | 手动 `{ ...result.details, new }` |
| `xhigh` 不检查模型 | 部分模型忽略/报错 | 检查 `getModelThinkingLevel(model)` |

## 源码映射

| 内容 | 文件 | 行数 |
|------|------|------|
| AgentState | `types.ts` | L317-342 |
| AgentTool | `types.ts` | L361-384 |
| AgentLoopConfig | `types.ts` | L135-277 |
| AgentEvent | `types.ts` | L403-418 |
| ThinkingLevel | `types.ts` | L284 |