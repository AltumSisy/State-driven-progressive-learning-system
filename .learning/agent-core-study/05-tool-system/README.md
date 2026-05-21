# 05 - 工具系统

## 概述

工具系统允许 Agent 调用外部功能。工具定义使用 TypeBox 进行参数验证。

## 工具定义

```typescript
import { Type } from "typebox";

const readFileTool: AgentTool = {
  // 必需属性
  name: "read_file",                           // 唯一标识符
  label: "Read File",                          // UI 显示标签
  description: "Read a file's contents",        // 功能描述
  parameters: Type.Object({                     // 参数模式（TypeBox）
    path: Type.String({ description: "File path" }),
  }),
  
  // 可选属性
  executionMode: "sequential",                   // 执行模式覆盖
  prepareArguments: (args: unknown) => {        // 参数预处理
    // 返回符合 parameters 模式的对象
    return args as { path: string };
  },
  
  // 执行函数
  execute: async (
    toolCallId: string,                        // 工具调用 ID
    params: Static<typeof parameters>,         // 验证后的参数
    signal?: AbortSignal,                       // 中止信号
    onUpdate?: AgentToolUpdateCallback        // 进度回调
  ): Promise<AgentToolResult<Details>> => {
    const content = await fs.readFile(params.path, "utf-8");
    
    // 可选: 流式进度
    onUpdate?.({
      content: [{ type: "text", text: "Reading..." }],
      details: {}
    });
    
    // 返回结果
    return {
      content: [{ type: "text", text: content }],  // 给 LLM 的内容
      details: { path: params.path, size: content.length },  // 详情
      terminate: false,  // 是否终止 Agent（可选）
    };
  },
};
```

## 工具执行模式

### Parallel（并行，默认）

```
Assistant Message (包含 3 个 tool calls)
│
├─ Tool A: preflight → execute ─┐
├─ Tool B: preflight → execute ─┤  // 并发执行
├─ Tool C: preflight → execute ─┘
│
│  // 工具按完成顺序触发事件
├─ tool_execution_end (Tool B) ─┐
├─ tool_execution_end (Tool A) ─┤  // 按完成顺序
├─ tool_execution_end (Tool C) ─┘
│
│  // 但结果消息按助手原始顺序
├─ message_start (Tool Result A)
├─ message_end (Tool Result A)
├─ message_start (Tool Result B)
├─ message_end (Tool Result B)
├─ message_start (Tool Result C)
├─ message_end (Tool Result C)
│
└─ turn_end
```

### Sequential（顺序）

```
Assistant Message (包含 3 个 tool calls)
│
├─ Tool A: preflight → execute → tool_execution_end → message_start/end
├─ Tool B: preflight → execute → tool_execution_end → message_start/end
├─ Tool C: preflight → execute → tool_execution_end → message_start/end
│
└─ turn_end
```

### 配置方式

```typescript
// 全局配置（Agent 构造函数）
const agent = new Agent({
  toolExecution: "parallel",  // 或 "sequential"
});

// 每个工具覆盖
const tool: AgentTool = {
  name: "my_tool",
  executionMode: "sequential",  // 此工具强制顺序执行
  // ...
};

// 注意: 如果一个 batch 中有任何工具是 sequential，
// 整个 batch 都会顺序执行
```

## 错误处理

### 正确方式: 抛出错误

```typescript
execute: async (toolCallId, params, signal, onUpdate) => {
  if (!fs.existsSync(params.path)) {
    // 抛出错误，Agent 会捕获并报告给 LLM
    throw new Error(`File not found: ${params.path}`);
  }
  
  // 成功时才返回内容
  return {
    content: [{ type: "text", text: "..." }],
    details: {}
  };
}
```

### 结果

```typescript
// Agent 会将错误转换为 tool result
{
  role: "toolResult",
  toolCallId: "...",
  content: [{ type: "text", text: "File not found: ..." }],
  isError: true
}
```

## 工具执行流程

```
┌─────────────────┐
│  Tool Call 收到  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  beforeToolCall │  // 预检，可阻止执行
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  validate args  │  // TypeBox 验证
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   execute()     │  // 执行工具
└────────┬────────┘
         │
         ├─ tool_execution_start
         ├─ tool_execution_update (可选)
         └─ tool_execution_end
         │
         ▼
┌─────────────────┐
│  afterToolCall  │  // 后处理，可修改结果
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   toolResult    │  // 消息添加到上下文
└─────────────────┘
```

## 终止 Agent

工具可以提示 Agent 在工具 batch 完成后停止：

```typescript
execute: async (toolCallId, params, signal, onUpdate) => {
  // ...
  return {
    content: [{ type: "text", text: "Task complete" }],
    details: {},
    terminate: true,  // 提示终止
  };
}
```

**终止条件**:
- 只有当 batch 中 **所有** 已完成的工具结果都设置 `terminate: true` 时，Agent 才会停止
- 也可以在 `afterToolCall` 中设置 `terminate: true`

## 流式更新

### onUpdate 回调

```typescript
execute: async (toolCallId, params, signal, onUpdate) => {
  const stream = createSomeStream();
  
  for await (const chunk of stream) {
    // 报告进度
    onUpdate?.({
      content: [{ type: "text", text: chunk }],
      details: { progress: chunk.length }
    });
  }
  
  return {
    content: [{ type: "text", text: finalResult }],
    details: { totalSize: finalResult.length }
  };
}
```

### 事件流

```
tool_execution_start
├─ tool_execution_update (partial 1)
├─ tool_execution_update (partial 2)
├─ tool_execution_update (partial 3)
└─ tool_execution_end
```

## 工具钩子

### beforeToolCall

```typescript
beforeToolCall: async ({ toolCall, args, context }, signal) => {
  // 示例: 阻止特定工具
  if (toolCall.name === "bash") {
    return {
      block: true,
      reason: "bash tool is disabled for security"
    };
  }
  
  // 示例: 阻止危险参数
  if (toolCall.name === "delete_file") {
    const path = args.path;
    if (path.includes("/system/")) {
      return {
        block: true,
        reason: "Cannot delete system files"
      };
    }
  }
  
  // 返回 undefined 表示允许执行
}
```

### afterToolCall

```typescript
afterToolCall: async ({ toolCall, result, isError, context }, signal) => {
  // 示例: 添加审计标记
  if (!isError) {
    return {
      details: { ...result.details, audited: true, timestamp: Date.now() }
    };
  }
  
  // 示例: 修改内容
  if (toolCall.name === "fetch") {
    return {
      content: [{ type: "text", text: sanitizeHtml(result.content[0].text) }]
    };
  }
  
  // 示例: 设置终止标志
  if (toolCall.name === "notify_done") {
    return { terminate: true };
  }
}
```

## 工具集合

```typescript
// 创建工具集
const tools: AgentTool[] = [
  readFileTool,
  writeFileTool,
  bashTool,
  searchTool,
];

// 应用到 Agent
agent.state.tools = tools;
```

## 完整示例

```typescript
import { Agent } from "@earendil-works/pi-agent-core";
import { Type } from "typebox";

// 定义计算器工具
const calculatorTool: AgentTool = {
  name: "calculator",
  label: "Calculator",
  description: "Perform mathematical calculations",
  parameters: Type.Object({
    expression: Type.String({ description: "Math expression to evaluate" }),
  }),
  execute: async (toolCallId, params, signal, onUpdate) => {
    // 模拟流式计算
    onUpdate?.({
      content: [{ type: "text", text: "Computing..." }],
      details: {}
    });
    
    const result = eval(params.expression); // 注意: 实际使用需要安全评估
    
    return {
      content: [{ type: "text", text: String(result) }],
      details: { expression: params.expression, result }
    };
  }
};

// 创建 Agent
const agent = new Agent({
  initialState: {
    systemPrompt: "You are a helpful assistant with access to a calculator.",
    model: getModel("anthropic", "claude-sonnet-4-20250514"),
    tools: [calculatorTool],
  },
  beforeToolCall: async ({ toolCall, args }) => {
    // 安全检查
    const expr = args.expression as string;
    if (expr.includes("rm") || expr.includes("exec")) {
      return { block: true, reason: "Unsafe expression" };
    }
  }
});

// 使用
await agent.prompt("Calculate 2 + 2");
```

## 最佳实践

1. **抛出错误而非返回错误内容** - Agent 会自动处理错误
2. **使用 onUpdate 报告进度** - 对于长时间运行的工具
3. **设置 executionMode** - 对于需要独占资源的工具使用 sequential
4. **在 afterToolCall 中审计** - 记录工具使用情况
5. **验证参数** - 利用 TypeBox 的静态类型

## 下一步

→ [06 - 事件流](./06-event-flow)
