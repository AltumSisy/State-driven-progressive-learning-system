# 08 - 实践示例

## 示例 1: 基础 Agent

```typescript
import { Agent } from "@earendil-works/pi-agent-core";
import { getModel } from "@earendil-works/pi-ai";

const agent = new Agent({
  initialState: {
    systemPrompt: "You are a helpful assistant.",
    model: getModel("anthropic", "claude-sonnet-4-20250514"),
  },
});

agent.subscribe((event) => {
  if (event.type === "message_update" && 
      event.assistantMessageEvent.type === "text_delta") {
    process.stdout.write(event.assistantMessageEvent.delta);
  }
});

await agent.prompt("Hello!");
await agent.waitForIdle();
```

## 示例 2: 带工具的 Agent

```typescript
import { Agent, AgentTool } from "@earendil-works/pi-agent-core";
import { Type } from "typebox";

const calculatorTool: AgentTool = {
  name: "calculator",
  label: "Calculator",
  description: "Perform calculations",
  parameters: Type.Object({
    expression: Type.String(),
  }),
  execute: async (toolCallId, params) => {
    const result = eval(params.expression); // 安全警告：实际使用需验证
    return {
      content: [{ type: "text", text: String(result) }],
      details: { expression: params.expression, result },
    };
  },
};

const agent = new Agent({
  initialState: {
    systemPrompt: "You are a calculator assistant.",
    model: getModel("anthropic", "claude-sonnet-4-20250514"),
    tools: [calculatorTool],
  },
});

await agent.prompt("Calculate 123 * 456");
```

## 示例 3: 会话持久化

```typescript
import { Agent, Session, JsonlRepository } from "@earendil-works/pi-agent-core";

const repo = new JsonlRepository({ dir: "./sessions" });
const agent = new Agent({ /* ... */ });
const session = new Session({ repo, agent });

// 加载
await session.load("my-session");

// 使用
await agent.prompt("Remember this: the answer is 42");
await session.save();

// 稍后
await session.load("my-session");
await agent.prompt("What did I ask you to remember?");
```

## 示例 4: 流式文件读取工具

```typescript
import { createReadStream } from "fs";
import { AgentTool } from "@earendil-works/pi-agent-core";
import { Type } from "typebox";

const readFileTool: AgentTool = {
  name: "read_file",
  label: "Read File",
  description: "Read a file",
  parameters: Type.Object({
    path: Type.String(),
  }),
  execute: async (toolCallId, params, signal, onUpdate) => {
    const chunks: string[] = [];
    const stream = createReadStream(params.path, { encoding: "utf-8" });
    
    for await (const chunk of stream) {
      if (signal?.aborted) throw new Error("Aborted");
      
      chunks.push(chunk);
      onUpdate?.({
        content: [{ type: "text", text: chunk }],
        details: { bytesRead: chunks.join("").length },
      });
    }
    
    const content = chunks.join("");
    return {
      content: [{ type: "text", text: content }],
      details: { path: params.path, size: content.length },
    };
  },
};
```

## 示例 5: 自定义消息类型

```typescript
// types.d.ts
declare module "@earendil-works/pi-agent-core" {
  interface CustomAgentMessages {
    notification: {
      role: "notification";
      text: string;
      timestamp: number;
      level: "info" | "warning" | "error";
    };
  }
}

// usage.ts
const agent = new Agent({
  initialState: { /* ... */ },
  convertToLlm: (messages) => {
    return messages.flatMap(m => {
      if (m.role === "notification") {
        // 转换为 user 消息
        return [{
          role: "user",
          content: `[${m.level.toUpperCase()}] ${m.text}`,
          timestamp: m.timestamp,
        }];
      }
      // 标准消息
      if (m.role === "user" || m.role === "assistant" || m.role === "toolResult") {
        return [m];
      }
      return [];
    });
  },
});

// 添加通知
agent.state.messages.push({
  role: "notification",
  text: "Low memory warning",
  timestamp: Date.now(),
  level: "warning",
});
```

## 示例 6: Steering 控制

```typescript
const agent = new Agent({ /* ... */ });

// 启动长时间任务
agent.prompt("Analyze this large codebase and find all TODO comments");

// 稍后打断
setTimeout(() => {
  agent.steer({
    role: "user",
    content: "Stop! Just give me a quick summary instead.",
    timestamp: Date.now(),
  });
}, 5000);
```

## 示例 7: 上下文压缩

```typescript
import { agentLoop, shouldCompact, compact } from "@earendil-works/pi-agent-core";

const config = {
  model,
  convertToLlm,
  transformContext: async (messages) => {
    // 检查是否需要压缩
    if (shouldCompact(messages, { threshold: 4000 })) {
      console.log("Compacting context...");
      return await compact(messages, { model });
    }
    return messages;
  },
};

for await (const event of agentLoop([userMessage], context, config)) {
  // ...
}
```

## 示例 8: 安全检查

```typescript
const agent = new Agent({
  initialState: { /* ... */ },
  
  beforeToolCall: async ({ toolCall, args }) => {
    // 阻止危险操作
    if (toolCall.name === "bash") {
      const cmd = (args as any).command;
      
      const dangerous = ["rm -rf /", "rm -rf ~", "dd if=/dev/zero"];
      if (dangerous.some(d => cmd.includes(d))) {
        return {
          block: true,
          reason: `Dangerous command blocked: ${cmd}`,
        };
      }
    }
    
    // 阻止敏感文件访问
    if (toolCall.name === "read_file") {
      const path = (args as any).path;
      if (path.includes(".env") || path.includes(".ssh")) {
        return {
          block: true,
          reason: "Access to sensitive files blocked",
        };
      }
    }
  },
  
  afterToolCall: async ({ toolCall, result, isError }) => {
    // 记录审计日志
    console.log(`[AUDIT] ${toolCall.name}: ${isError ? "FAILED" : "SUCCESS"}`);
    
    // 添加审计标记
    return {
      details: {
        ...result.details,
        audited: true,
        timestamp: Date.now(),
      },
    };
  },
});
```

## 示例 9: 多模态输入

```typescript
import { readFileSync } from "fs";

const imageData = readFileSync("./image.jpg", { encoding: "base64" });

await agent.prompt("What's in this image?", [
  {
    type: "image",
    data: imageData,
    mimeType: "image/jpeg",
  },
]);
```

## 示例 10: 完整的 CLI 应用

```typescript
import { Agent, Session, JsonlRepository, uuidv7 } from "@earendil-works/pi-agent-core";
import { getModel } from "@earendil-works/pi-ai";
import * as readline from "readline";

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout,
});

async function promptUser(): Promise<string> {
  return new Promise((resolve) => {
    rl.question("> ", resolve);
  });
}

async function main() {
  const sessionId = process.argv[2] || uuidv7();
  
  const repo = new JsonlRepository({ dir: "./sessions" });
  const agent = new Agent({
    initialState: {
      systemPrompt: "You are a helpful coding assistant.",
      model: getModel("anthropic", "claude-sonnet-4-20250514"),
    },
  });
  
  const session = new Session({ repo, agent });
  await session.load(sessionId);
  
  console.log(`Session: ${sessionId}\n`);
  
  // 流式输出
  agent.subscribe((event) => {
    if (event.type === "message_update") {
      const { assistantMessageEvent } = event;
      if (assistantMessageEvent.type === "text_delta") {
        process.stdout.write(assistantMessageEvent.delta);
      }
    }
    if (event.type === "agent_end") {
      console.log("\n");
    }
  });
  
  // 主循环
  while (true) {
    const input = await promptUser();
    
    if (input === "/quit") break;
    if (input === "/reset") {
      agent.reset();
      console.log("Session reset.\n");
      continue;
    }
    if (input === "/save") {
      await session.save();
      console.log("Session saved.\n");
      continue;
    }
    if (input.startsWith("/compact")) {
      await session.compact();
      console.log("Session compacted.\n");
      continue;
    }
    
    await agent.prompt(input);
    await session.save();
  }
  
  rl.close();
  session.dispose();
}

main().catch(console.error);
```

---

**学习完成！**

现在你已经理解了 `@earendil-works/pi-agent-core` 的核心概念：
- ✅ Agent 架构和生命周期
- ✅ 事件流和消息处理
- ✅ 工具系统
- ✅ Harness 高级功能

下一步：阅读源代码，构建实际应用！
