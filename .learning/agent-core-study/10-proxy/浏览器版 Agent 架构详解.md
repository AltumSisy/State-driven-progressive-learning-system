# 浏览器版 Agent 架构详解

> 本文档详细讲解浏览器环境下 Agent Harness 的架构设计，包括前后端分工、Proxy 角色、WebSocket vs streamProxy、以及 Agent 放置位置的决策依据。

---

## 一、Proxy 解决的核心问题

### 1.1 浏览器环境的四大障碍

```
┌─────────────────────────────────────────────────────────┐
│  Node.js 环境（原生 Agent 设计）                        │
│                                                         │
│  ✓ 直接调用 Anthropic API                              │
│  ✓ fs/shell 本地操作                                   │
│  ✓ API Key 安全（环境变量）                            │
│  ✓ 完全控制                                            │
└─────────────────────────────────────────────────────────┘

                    ↓ 浏览器遇到的问题 ↓

┌─────────────────────────────────────────────────────────┐
│  浏览器环境                                             │
│                                                         │
│  ❌ CORS 限制 → 浏览器不能直接调用 Anthropic API        │
│  ❌ API Key 泄露 → 客户端存储 API Key 极危险            │
│  ❌ fs/shell 缺失 → 没有文件系统/命令行                 │
│  ❌ 安全限制 → 多种 Web 安全约束                        │
└─────────────────────────────────────────────────────────┘
```

### 1.2 streamProxy 解决方案

核心思路：**浏览器 → 代理服务器 → Anthropic API**

```
┌─────────────────────────────────────────────────────────┐
│                    BROWSER                               │
│                                                          │
│  Agent                                                    │
│      │                                                    │
│      │ streamFn: streamProxy                             │
│      │                                                    │
│      ▼                                                    │
│  streamProxy(model, context, {                            │
│      proxyUrl: "https://backend/api/stream",  ← 代理地址 │
│      authToken: "user-token",               ← 用户凭证   │
│  })                                                       │
│      │                                                    │
│      │ HTTP POST + authToken                             │
│      │                                                    │
└─────────────────────────────────────────────────────────┘
                         │
                         │ HTTPS
                         ▼
┌─────────────────────────────────────────────────────────┐
│                    BACKEND                                │
│                                                          │
│  POST /api/stream                                         │
│      │                                                    │
│      │ 1. 验证 authToken → 用户身份                      │
│      │ 2. 获取真实 API Key（后端保管）                    │
│      │ 3. 调用 Anthropic API                             │
│      │                                                    │
│      ▼                                                    │
│  SSE 流式转发回 Browser                                   │
└─────────────────────────────────────────────────────────┘
```

### 1.3 四个痛点对应解决

| 痛点 | 直接浏览器调用 | streamProxy 方案 |
|------|--------------|-----------------|
| **CORS** | API 报错 | 代理服务器转发（同源） |
| **API Key 安全** | 泄露风险 | 后端保管，浏览器只发 authToken |
| **认证传递** | 无标准 | authToken → 后端转换 API Key |
| **流式体验** | 无法保持 | SSE 端到端保持流式 |

---

## 二、Proxy 的多重角色

Proxy 是**多重角色合一的中间层**：

### 2.1 角色 1: API Gateway（统一入口）

```
Browser 所有请求都经过 Proxy:
  streamProxy() → POST /api/stream
  runShell()   → POST /api/shell
  readFile()   → POST /api/fs/read

Proxy:
  /api/stream → Anthropic API
  /api/shell  → Node.js child_process
  /api/fs/*   → Node.js fs module

好处:
  ✓ 统一认证
  ✓ 统一错误处理
  ✓ 统一日志记录
  ✓ 浏览器只需知道 proxyUrl
```

### 2.2 角色 2: 安全隔离层

```
传统方案（危险）:
  Browser 存储 API Key → localStorage
  ↓
  泄露风险：任何 JS 都能读取
  ↓
  攻击者拿到 API Key → 滥用

Proxy 方案（安全）:
  Browser 存储 authToken → localStorage
  ↓
  authToken 只是用户凭证（可刷新、可撤销）
  ↓
  Proxy 用 authToken 验证身份 → 获取真实 API Key
  ↓
  API Key 只存在 Proxy 后端内存/密钥管理服务
```

### 2.3 角色 3: 环境适配层

```
浏览器缺失的能力，由 Proxy 提供:

BrowserExecutionEnv:
  async runShellCommand(command) {
    // 浏览器无法执行 shell
    // → 调用 Proxy
    return fetch("/api/shell", { body: { command } });
  }

Proxy:
  app.post("/api/shell", (req, res) => {
    // Node.js 可以执行 shell
    exec(req.body.command, (err, stdout, stderr) => {
      res.json({ stdout, stderr });
    });
  });

本质:
  Browser 的 ExecutionEnv 是 "ProxyExecutionEnv"
  所有操作都转发到后端执行
```

### 2.4 角色 4: 流式保持层

```
一次性返回（差体验）:
  Browser → Proxy → Anthropic
                    ↓
              等待完整响应（10秒）
                    ↓
  Browser ← Proxy ← 完整 JSON

SSE 流式保持（好体验）:
  Browser → Proxy → Anthropic
                    ↓
              SSE 流式开始
                    ↓
  Browser ← Proxy ← SSE delta (实时)
                    ↓
              持续推送...
                    ↓
  Browser ← Proxy ← SSE 结束

Proxy 必须转发 SSE，不能一次性返回
```

---

## 三、AgentHarness 添加 customTool

### 3.1 添加位置

在 `AgentHarnessOptions` 的 `tools` 参数中配置：

```typescript
interface AgentHarnessOptions<
  TSkill extends Skill = Skill,
  TPromptTemplate extends PromptTemplate = PromptTemplate,
  TTool extends AgentTool = AgentTool,  // 🔥 泛型参数
> {
  env: ExecutionEnv;
  session: Session;
  tools?: TTool[];  // 🔥 这里添加 customTool
  activeToolNames?: string[];  // 🔥 控制哪些 tool 激活
  // ...其他参数
}
```

### 3.2 示例：添加自定义 tool

```typescript
import { AgentHarness } from "@earendil-works/pi-agent-core";
import { getModel } from "@earendil-works/pi-ai";
import type { AgentTool } from "@earendil-works/pi-agent-core";

// ========== 1. 定义 customTool ==========
const myCustomTool: AgentTool = {
  name: "get_weather",  // tool 名称
  label: "获取天气",    // UI 显示标签
  
  // 参数 schema（JSON Schema）
  inputSchema: {
    type: "object",
    properties: {
      city: { type: "string", description: "城市名称" },
    },
    required: ["city"],
  },
  
  // 🔥 执行函数
  execute: async (toolCallId, args, context, signal, onUpdate) => {
    const { city } = args as { city: string };
    
    // 调用天气 API（示例）
    const weather = await fetch(`https://api.weather.com/${city}`);
    const data = await weather.json();
    
    // 返回结果
    return {
      content: [{ 
        type: "text", 
        text: `${city} 当前天气：${data.temperature}°C` 
      }],
      details: { temperature: data.temperature },  // 结构化数据
    };
  },
  
  // 可选：执行模式
  executionMode: "parallel",  // 可与其他 tool 并行执行
};

// ========== 2. 配置 AgentHarness ==========
const harness = new AgentHarness({
  env: executionEnv,
  session: sessionStorage,
  
  // 🔥 添加 tools
  tools: [
    myCustomTool,  // 自定义 tool
    // ...其他 tools
  ],
  
  // 🔥 可选：控制哪些 tool 激活
  activeToolNames: ["get_weather", "read", "edit"],
  
  // 其他配置
  model: getModel("anthropic", "claude-sonnet-4"),
  systemPrompt: "你是助手，可以使用 get_weather 工具。",
});
```

### 3.3 AgentTool 接口详解

```typescript
interface AgentTool<TParameters = any, TDetails = any> {
  // ========== 必需字段 ==========
  
  name: string;  // tool 名称（唯一）
  label: string;  // UI 显示标签
  
  inputSchema: TSchema;  // JSON Schema 参数定义
  
  // 🔥 执行函数
  execute: (
    toolCallId: string,        // tool call ID
    args: Static<TParameters>, // 验证后的参数
    context: AgentContext,     // 当前 Agent context
    signal?: AbortSignal,      // 中断信号
    onUpdate?: (partialResult: AgentToolResult<TDetails>) => void  // 更新回调
  ) => Promise<AgentToolResult<TDetails>>;
  
  // ========== 可选字段 ==========
  
  prepareArguments?: (args: unknown) => Static<TParameters>;  // 参数预处理
  
  executionMode?: "parallel" | "sequential";  // 执行模式
}

// execute 返回的结果
interface AgentToolResult<TDetails> {
  content: (TextContent | ImageContent)[];  // 返回给 LLM 的内容
  details: TDetails;  // 结构化数据（用于日志/UI）
  terminate?: boolean;  // 是否提前终止
}
```

---

## 四、Web vs Backend 分工架构

### 4.1 正确的前后端分工

```
┌─────────────────────────────────────────────────────────┐
│                    WEB (Browser)                         │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Agent 实例层                                     │   │
│  │                                                  │   │
│  │  AgentHarness                                    │   │
│  │      ├─ tools: [AgentTool定义]  ← 🔥 定义在 Web │   │
│  │      ├─ skills: [...]                           │   │
│  │      ├─ systemPrompt                            │   │
│  │      ├─ Session 管理                            │   │
│  │      └─ Extension 扩展                          │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Tool Execute 实现                                │   │
│  │                                                  │   │
│  │  AgentTool.execute:                             │   │
│  │      ├─ 简单逻辑 → 直接在 Web 执行              │   │
│  │      ├─ 复杂操作 → fetch 调用 Backend           │   │
│  │      ├─ 数据库 → fetch 调用 Backend             │   │
│  │      ├─ 第三方 API → fetch 调用 Backend         │   │
│  │      └─ Shell/fs → fetch 调用 Backend           │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ LLM 调用                                         │   │
│  │                                                  │   │
│  │  streamProxy() → POST /api/stream               │   │
│  │  🔥 所有 LLM 调用都通过 streamProxy             │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
                         │
                         │ fetch / SSE
                         ▼
┌─────────────────────────────────────────────────────────┐
│                    BACKEND (Proxy)                       │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ LLM 代理                                         │   │
│  │                                                  │   │
│  │  /api/stream                                     │   │
│  │      ├─ Anthropic API                           │   │
│  │      ├─ OpenAI API  ← 🔥 可扩展其他 LLM        │   │
│  │      ├─ 其他 LLM SDK                            │   │
│  │      └─ API Key 管理                            │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Node.js 能力                                     │   │
│  │                                                  │   │
│  │  /api/shell → exec()                            │   │
│  │  /api/fs/*  → fs module                         │   │
│  │  /api/database → 数据库操作                     │   │
│  │  /api/external → 第三方 API                     │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Session 持久化（可选）                           │   │
│  │                                                  │   │
│  │  /api/session → 写入数据库                      │   │
│  │  🔥 Web 可用 IndexedDB 或 Backend API          │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### 4.2 详细分工表

| 功能 | Web 端 | Backend 端 | 说明 |
|------|--------|-----------|------|
| **AgentTool 定义** | ✅ 定义在 Web | ❌ | `tools: [myTool]` |
| **AgentTool execute** | ✅ 函数定义在 Web | ✅ 实际执行可能在 Backend | 简单逻辑在 Web，复杂操作 fetch Backend |
| **Session 管理** | ✅ IndexedDB 或 API | ✅ 持久化到数据库 | 可选方案 |
| **Extension 扩展** | ✅ 定义在 Web | ✅ 可能需要 Backend | 视扩展类型 |
| **LLM 调用** | ✅ streamProxy() | ✅ 转发到真实 API | 所有 LLM 调用走 Proxy |
| **Shell/fs 操作** | ❌ | ✅ Backend 提供 | Web 无能力 |
| **数据库操作** | ❌ | ✅ Backend 提供 | Web 通过 fetch 调用 |
| **第三方 API** | ❌ | ✅ Backend 提供 | API Key 安全 |
| **API Key 管理** | ❌ | ✅ Backend 保管 | Web 只持有 authToken |

---

## 五、Agent 放 Web vs Backend 的决策依据

### 5.1 Agent 放 Web 的依据

```
┌─────────────────────────────────────────────────────────┐
│  核心依据：实时状态管理 + 用户交互                      │
│                                                         │
│  1. 实时状态机                                          │
│     idle → turn → compaction → branch_summary          │
│     ↓                                                   │
│     需要 UI 实时反映（用户可见）                        │
│                                                         │
│  2. Session Tree 导航                                   │
│     用户切换分支、时光机                                │
│     ↓                                                   │
│     需要用户交互触发                                    │
│                                                         │
│  3. Event Subscribe                                     │
│     harness.subscribe((event) => {                     │
│       updateUI(event);  // 实时更新 UI                 │
│     })                                                  │
│     ↓                                                   │
│     需要低延迟、实时响应                                │
│                                                         │
│  4. Compaction/Branch 触发                              │
│     上下文超限 → 可能需要用户确认                       │
│     ↓                                                   │
│     需要用户交互                                        │
│                                                         │
│  5. 低延迟                                              │
│     用户输入 → Agent 处理 → UI 更新                    │
│     ↓                                                   │
│     Web 本地处理，无网络延迟                            │
└─────────────────────────────────────────────────────────┘
```

### 5.2 Agent 放 Web 的适用场景

```
✅ 单用户应用
   用户只在单一浏览器使用
   无需跨设备、多用户管理

✅ 实时交互优先
   用户频繁交互、切换分支
   需要低延迟响应

✅ 简单 Session
   Session 不需要复杂持久化
   IndexedDB 或简单 Backend API 即可

✅ 离线不重要
   用户关闭浏览器，会话结束
   不需要 Backend 继续运行

✅ 安全要求不高
   Session 数据不敏感
   IndexedDB 可接受
```

### 5.3 Agent 放 Backend 的依据

```
┌─────────────────────────────────────────────────────────┐
│  适用场景                                                │
│                                                         │
│  1. 多用户应用                                          │
│     企业级应用、多用户协作                              │
│     需要集中管理 Session                               │
│                                                         │
│  2. 跨设备共享                                          │
│     用户在不同设备使用同一 Session                     │
│     Session 在 Backend 共享                            │
│                                                         │
│  3. 离线运行                                            │
│     用户关闭浏览器，Agent 继续执行任务                 │
│     长时间任务、后台处理                                │
│                                                         │
│  4. Session 持久化重要                                  │
│     Session 需要可靠持久化                              │
│     数据库、事务支持                                    │
│                                                         │
│  5. 安全性高                                            │
│     Session 数据敏感                                    │
│     不能暴露给浏览器                                    │
│                                                         │
│  6. 资源需求大                                          │
│     Compaction、Branch Summarization 需要大量内存       │
│     Backend 有更多资源                                  │
└─────────────────────────────────────────────────────────┘
```

### 5.4 对比表

| 维度 | Agent 在 Web | Agent 在 Backend |
|------|-------------|------------------|
| **状态管理** | IndexedDB（本地） | Database（服务器） |
| **实时交互** | ✅ 低延迟（本地） | ❌ 需网络传输 |
| **Session 持久化** | 手动（IndexedDB 或 API） | ✅ 自然（直接写 DB） |
| **跨设备** | ❌ 每设备独立 Session | ✅ Session 在 Backend 共享 |
| **离线运行** | ❌ 用户关闭浏览器停止 | ✅ Backend 可继续运行 |
| **资源限制** | ❌ 浏览器内存限制 | ✅ Backend 更多资源 |
| **安全性** | ❌ IndexedDB 可被篡改 | ✅ Backend 数据更安全 |
| **事件订阅** | ✅ 直连 UI | ❌ 需要 WebSocket/SSE |
| **多用户管理** | ❌ 每用户独立 | ✅ Backend 集中管理 |

---

## 六、streamProxy vs WebSocket 的关键区别

### 6.1 streamProxy 的本质角色

```
streamProxy 不是 WebSocket 的替代品
streamProxy 是 HTTP API 代理（解决 CORS + API Key 安全）

┌─────────────────────────────────────────────────────────┐
│  streamProxy 的核心角色                                  │
│                                                         │
│  问题：                                                  │
│    浏览器 CORS → 无法直接调用 Anthropic API            │
│    API Key 泄露 → 浏览器不能存真实 Key                  │
│                                                         │
│  解决：                                                  │
│    streamProxy → HTTP POST → Backend Proxy             │
│    Backend 持有真实 Key → 调用 Anthropic               │
│    SSE 流式返回 → 浏览器                               │
│                                                         │
│  层次：                                                  │
│    Web → streamProxy → HTTP → Backend → Anthropic      │
│                                                         │
│  本质：HTTP API 代理                                    │
└─────────────────────────────────────────────────────────┘
```

### 6.2 WebSocket 的角色

```
WebSocket 不是 streamProxy 的替代品
WebSocket 是实时双向通信（用于事件推送）

┌─────────────────────────────────────────────────────────┐
│  WebSocket 的核心角色                                    │
│                                                         │
│  问题：                                                  │
│    Agent 在 Backend → Web 需要实时接收事件              │
│    HTTP 请求/响应 → 无法实时推送                        │
│                                                         │
│  解决：                                                  │
│    Backend Agent.subscribe → WebSocket.send(event)     │
│    Web WebSocket.onmessage → updateUI(event)           │
│                                                         │
│  层次：                                                  │
│    Backend Agent → WebSocket → Web UI                  │
│                                                         │
│  本质：实时双向通信                                      │
└─────────────────────────────────────────────────────────┘
```

### 6.3 关键区别对比

```
┌─────────────────────────────────────────────────────────┐
│  streamProxy vs WebSocket                                │
│                                                         │
│  streamProxy：                                          │
│    ├─ 解决 CORS + API Key 安全                          │
│    ├─ 是 HTTP API 代理                                  │
│    ├─ Web → Backend（单向请求）                         │
│    ├─ SSE 流式响应（HTTP）                              │
│    └─ 用于 LLM API 调用                                 │
│                                                         │
│  WebSocket：                                            │
│    ├─ 解决实时事件推送                                  │
│    ├─ 是双向通信通道                                    │
│    ├─ Backend → Web（双向）                             │
│    ├─ 实时消息（WebSocket）                             │
│    └─ 用于 Agent 事件推送                               │
│                                                         │
│  它们不是替代品，而是不同层次的技术                     │
└─────────────────────────────────────────────────────────┘
```

### 6.4 如果 Agent 在 Backend

**关键理解**：Agent 在 Backend，**不需要 streamProxy**！

```
┌─────────────────────────────────────────────────────────┐
│  Agent 在 Backend 的架构                                 │
│                                                         │
│  Backend 不需要 streamProxy：                           │
│    ├─ Backend 无 CORS 问题（服务器可直接调用）          │
│    ├─ Backend 可持有真实 API Key（安全）                │
│    ├─ Backend 直接调用 streamSimple（原生）             │
│    └─ streamProxy 是给浏览器用的                       │
│                                                         │
│  Backend 需要什么：                                      │
│    ├─ streamSimple（直接调用 LLM API）                  │
│    ├─ WebSocket（推送事件给 Web）                       │
│    └─ Session 持久化（数据库）                          │
└─────────────────────────────────────────────────────────┘
```

### 6.5 对比总结表

| 维度 | Agent 在 Web | Agent 在 Backend |
|------|-------------|------------------|
| **streamProxy** | ✅ 需要（CORS + API Key 安全） | ❌ 不需要（Backend 直接调用） |
| **streamSimple** | ❌ Web 不能用（CORS） | ✅ Backend 用（原生调用） |
| **WebSocket** | ❌ 不需要（事件在 Web） | ✅ 需要（Backend → Web 推送） |
| **事件传递** | subscribe → 直接更新 UI | subscribe → WebSocket → Web |
| **API Key 位置** | Backend Proxy | Backend Agent |
| **Session** | IndexedDB 或 Backend API | Database（Backend） |
| **LLM 调用路径** | Web → streamProxy → Backend → Anthropic | Backend → streamSimple → Anthropic |

---

## 七、完整示例：浏览器版 AgentHarness

### 7.1 后端扩展（新增 shell/fs API）

```typescript
// backend/server.ts
import express from "express";
import Anthropic from "@anthropic-ai/sdk";
import { exec } from "child_process";
import fs from "fs/promises";

const app = express();
app.use(express.json());

const USERS = {
  "user-token-123": { apiKey: process.env.ANTHROPIC_API_KEY! }
};

// ========== LLM 代理 ==========
app.post("/api/stream", async (req, res) => {
  const authToken = req.headers.authorization?.replace("Bearer ", "");
  const user = USERS[authToken || ""];
  if (!user) return res.status(401).json({ error: "Unauthorized" });

  const anthropic = new Anthropic({ apiKey: user.apiKey });
  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");

  const stream = anthropic.messages.stream({
    model: req.body.model,
    max_tokens: req.body.max_tokens,
    messages: req.body.messages,
    system: req.body.system,
  });

  for await (const event of stream) {
    res.write(`data: ${JSON.stringify(event)}\n\n`);
  }
  res.end();
});

// ========== Shell 执行 ==========
app.post("/api/shell", async (req, res) => {
  const { command } = req.body;
  
  exec(command, (error, stdout, stderr) => {
    res.json({
      success: !error,
      stdout: stdout || "",
      stderr: stderr || error?.message || "",
    });
  });
});

// ========== 文件操作 ==========
app.post("/api/fs/read", async (req, res) => {
  const { path } = req.body;
  try {
    const content = await fs.readFile(path, "utf-8");
    res.json({ success: true, content });
  } catch (error) {
    res.json({ success: false, error: error.message });
  }
});

app.listen(3000, () => console.log("Backend running on http://localhost:3000"));
```

### 7.2 浏览器端 ExecutionEnv 实现

```typescript
// browser/BrowserExecutionEnv.ts
import type { ExecutionEnv } from "@earendil-works/pi-agent-core";

export class BrowserExecutionEnv implements ExecutionEnv {
  private proxyUrl: string;
  private authToken: string;

  constructor(proxyUrl: string, authToken: string) {
    this.proxyUrl = proxyUrl;
    this.authToken = authToken;
  }

  async runShellCommand(command: string): Promise<{ stdout: string; stderr: string }> {
    const res = await fetch(`${this.proxyUrl}/shell`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${this.authToken}`,
      },
      body: JSON.stringify({ command }),
    });
    const data = await res.json();
    return {
      stdout: data.stdout || "",
      stderr: data.stderr || "",
    };
  }

  async readFile(path: string): Promise<string> {
    const res = await fetch(`${this.proxyUrl}/fs/read`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${this.authToken}`,
      },
      body: JSON.stringify({ path }),
    });
    const data = await res.json();
    return data.content || "";
  }
}
```

### 7.3 AgentHarness 集成

```typescript
// browser/agent-setup.ts
import { AgentHarness, streamProxy } from "@earendil-works/pi-agent-core";
import { getModel } from "@earendil-works/pi-ai";
import { BrowserExecutionEnv } from "./BrowserExecutionEnv";
import { IndexedDBSession } from "./IndexedDBSession";

const proxyUrl = "http://localhost:3000";
const authToken = "user-token-123";

// 创建 AgentHarness
const harness = new AgentHarness({
  env: new BrowserExecutionEnv(proxyUrl, authToken),
  session: new IndexedDBSession(),
  
  // 🔥 使用 streamProxy
  streamFn: (model, context, options) =>
    streamProxy(model, context, {
      ...options,
      proxyUrl: `${proxyUrl}/stream`,
      authToken,
    }),

  model: getModel("anthropic", "claude-sonnet-4"),
  systemPrompt: "你是助手。",
});

// 监听事件
harness.subscribe((event) => {
  if (event.type === "message_update") {
    const delta = event.assistantMessageEvent?.delta || "";
    document.getElementById("output").innerHTML += delta;
  }
});
```

---

## 八、关键理解总结

### 8.1 Proxy 角色

> **Proxy = BFF (Backend for Frontend) + 安全隔离 + 环境适配 + 流式保持**
> 
> 浏览器 AgentHarness 通过 Proxy 获得 Node.js 的所有能力，同时保证 API Key 安全。

### 8.2 AgentTool 分工

> **定义在 Web**：`tools: [myTool]` 配置
> 
> **简单 execute**：Web 直接执行（计算、格式化、调用公开 API）
> 
> **复杂 execute**：fetch 调用 Backend（数据库、私有 API、Shell）

### 8.3 Agent 放置决策

> **Agent 在 Web**：实时交互、单用户、简单 Session
> 
> **Agent 在 Backend**：多用户、跨设备、离线运行、持久化重要、资源需求大
> 
> **核心依据**：**状态管理位置** + **实时交互需求**

### 8.4 streamProxy vs WebSocket

> **streamProxy 是 HTTP API 代理**（解决 CORS + API Key 安全）
> 
> **WebSocket 是实时双向通信**（解决事件推送）
> 
> **它们不是替代品，而是不同层次的技术**
> 
> **Agent 在 Web**：需要 streamProxy（LLM 调用）+ 不需要 WebSocket（事件本地）
> 
> **Agent 在 Backend**：不需要 streamProxy（直接调用）+ 需要 WebSocket（事件推送）

---

## 参考资料

- **源文件**：
  - `packages/agent/src/proxy.ts` - streamProxy 实现
  - `packages/agent/src/harness/agent-harness.ts` - AgentHarness 主流程
  - `packages/agent/src/types.ts` - AgentTool 定义
  - `packages/agent/src/harness/types.ts` - AgentHarnessOptions 定义

- **相关文档**：
  - `README.md` - Proxy 概念概述
  - `Agent Harness 与 Session 架构知识体系.md` - Session Entry 类型体系