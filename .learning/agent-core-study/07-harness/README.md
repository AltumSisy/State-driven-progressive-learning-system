# 07 - Harness 系统

## 概述

Harness 是高级功能模块，提供会话管理、上下文压缩、技能管理等能力。

## 目录结构

```
src/harness/
├── agent-harness.ts           # Agent 包装器
├── messages.ts                # 消息处理
├── prompt-templates.ts        # 提示模板
├── skills.ts                  # 技能管理
├── system-prompt.ts           # 系统提示
├── types.ts                   # Harness 类型
├── compaction/                # 上下文压缩
│   ├── compaction.ts
│   ├── branch-summarization.ts
│   └── utils.ts
├── env/                       # 环境
│   └── nodejs.ts
├── session/                   # 会话管理
│   ├── session.ts
│   ├── jsonl-repo.ts
│   ├── jsonl-storage.ts
│   ├── memory-repo.ts
│   ├── memory-storage.ts
│   ├── repo-utils.ts
│   └── uuid.ts
└── utils/                     # 工具
    ├── shell-output.ts
    └── truncate.ts
```

## 会话管理

### Session 类

```typescript
import { Session } from "@earendil-works/pi-agent-core";

const session = new Session({
  repo,           // SessionRepository
  agent,          // Agent 实例
  config?: {       // 可选配置
    compact?: boolean;      // 是否自动压缩
    compactThreshold?: number;  // 压缩阈值
  }
});

// 方法
await session.load(id);        // 加载会话
await session.save();          // 保存会话
await session.compact();       // 手动压缩
session.dispose();             // 清理资源
```

### 存储仓库

#### MemoryRepository（内存）

```typescript
import { MemoryRepository } from "@earendil-works/pi-agent-core";

const repo = new MemoryRepository();
```

#### JsonlRepository（文件）

```typescript
import { JsonlRepository } from "@earendil-works/pi-agent-core";

const repo = new JsonlRepository({
  dir: "./sessions",  // 存储目录
});
```

### 完整示例

```typescript
import { Agent, Session, JsonlRepository } from "@earendil-works/pi-agent-core";

// 创建仓库
const repo = new JsonlRepository({ dir: "./sessions" });

// 创建 Agent
const agent = new Agent({
  initialState: {
    systemPrompt: "You are a helpful assistant.",
    model: getModel("anthropic", "claude-sonnet-4-20250514"),
  }
});

// 创建会话
const session = new Session({ repo, agent });

// 加载或创建
await session.load("my-session-id");

// 使用
await agent.prompt("Hello!");
await session.save();
```

## 上下文压缩

### Compaction 功能

当上下文过长时自动或手动压缩：

```typescript
import {
  compact,
  shouldCompact,
  estimateTokens,
  findCutPoint,
  generateSummary,
} from "@earendil-works/pi-agent-core";

// 估算 Token
const tokenCount = estimateTokens(messages);

// 是否应该压缩
if (shouldCompact(messages, { threshold: 4000 })) {
  // 找到切割点
  const cutPoint = findCutPoint(messages);
  
  // 生成摘要
  const summary = await generateSummary(messages, model);
  
  // 执行压缩
  const compacted = await compact(messages, {
    summary,
    cutPoint,
  });
}
```

### 自动压缩配置

```typescript
const session = new Session({
  repo,
  agent,
  config: {
    compact: true,
    compactThreshold: 4000,  // Token 阈值
  }
});
```

### Branch Summarization（分支摘要）

用于保存分支会话的历史摘要：

```typescript
import {
  collectEntriesForBranchSummary,
  generateBranchSummary,
  prepareBranchEntries,
} from "@earendil-works/pi-agent-core";

// 收集条目
const entries = collectEntriesForBranchSummary(session);

// 准备条目
const prepared = prepareBranchEntries(entries);

// 生成分支摘要
const summary = await generateBranchSummary(prepared, model);
```

## 技能管理

### Skills 系统

```typescript
import { Skills } from "@earendil-works/pi-agent-core";

const skills = new Skills({
  // 配置
});

// 注册技能
skills.register({
  name: "read_file",
  label: "Read File",
  description: "Read file contents",
  // ...
});

// 获取工具
const tools = skills.toTools();
agent.state.tools = tools;
```

## 系统提示模板

### 模板系统

```typescript
import { systemPrompt } from "@earendil-works/pi-agent-core";

// 使用模板
const prompt = systemPrompt({
  base: "You are a helpful assistant.",
  tools: availableTools,
  context: additionalContext,
});

agent.state.systemPrompt = prompt;
```

## AgentHarness

### 包装器

`AgentHarness` 是 `Agent` 的扩展包装，提供额外功能：

```typescript
import { AgentHarness } from "@earendil-works/pi-agent-core";

const harness = new AgentHarness({
  agent,
  session,
  config: {
    autoCompact: true,
    // ...
  }
});

// 使用
await harness.prompt("Hello!");
```

## 工具函数

### Shell Output 处理

```typescript
import { formatShellOutput, truncateShellOutput } from "@earendil-works/pi-agent-core";

// 格式化 shell 输出
const formatted = formatShellOutput(stdout, stderr);

// 截断输出
const truncated = truncateShellOutput(output, { maxLines: 100 });
```

### 文本截断

```typescript
import { truncate } from "@earendil-works/pi-agent-core";

const truncated = truncate(text, { maxLength: 2000 });
```

## UUID 生成

```typescript
import { uuidv7 } from "@earendil-works/pi-agent-core";

const id = uuidv7();  // 基于时间的 UUID v7
```

## 完整应用示例

```typescript
import {
  Agent,
  Session,
  JsonlRepository,
  Skills,
  systemPrompt,
  uuidv7,
} from "@earendil-works/pi-agent-core";

async function main() {
  // 1. 初始化仓库
  const repo = new JsonlRepository({ dir: "./data/sessions" });
  
  // 2. 初始化技能
  const skills = new Skills();
  await skills.loadFromDir("./skills");
  
  // 3. 创建 Agent
  const agent = new Agent({
    initialState: {
      systemPrompt: systemPrompt({
        base: "You are a coding assistant.",
        tools: skills.getDescriptions(),
      }),
      model: getModel("anthropic", "claude-sonnet-4-20250514"),
      tools: skills.toTools(),
    },
    beforeToolCall: async ({ toolCall, args }) => {
      // 安全检查
      console.log(`Executing: ${toolCall.name}`);
    },
  });
  
  // 4. 创建会话
  const session = new Session({
    repo,
    agent,
    config: {
      compact: true,
      compactThreshold: 8000,
    }
  });
  
  // 5. 加载或创建会话
  const sessionId = process.argv[2] || uuidv7();
  await session.load(sessionId);
  console.log(`Session: ${sessionId}`);
  
  // 6. 运行交互
  agent.subscribe((event) => {
    if (event.type === "message_update") {
      const { assistantMessageEvent } = event;
      if (assistantMessageEvent.type === "text_delta") {
        process.stdout.write(assistantMessageEvent.delta);
      }
    }
    if (event.type === "agent_end") {
      console.log("\n---");
    }
  });
  
  // 7. 主循环
  while (true) {
    const input = await promptUser();
    if (input === "exit") break;
    
    await agent.prompt(input);
    await session.save();
  }
  
  // 8. 清理
  session.dispose();
}

main().catch(console.error);
```

## 下一步

→ [08 - 实践示例](./08-examples)
