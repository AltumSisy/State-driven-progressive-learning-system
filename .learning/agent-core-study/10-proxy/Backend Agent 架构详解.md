# Backend Agent 架构详解

> 本文档详细讲解 Agent Harness 在 Backend 的架构设计，包括为何不需要 streamProxy、WebSocket 事件推送、Session 持久化、以及完整的实现示例。

---

## 一、核心架构变化

### 1.1 Agent 在 Backend 的根本变化

```
┌─────────────────────────────────────────────────────────┐
│  Agent 在 Backend 的核心变化                             │
│                                                         │
│  1. 不需要 streamProxy                                  │
│     ├─ Backend 无 CORS 问题（服务器可直接调用）          │
│     ├─ Backend 可持有真实 API Key（安全）                │
│     ├─ Backend 直接调用 streamSimple（原生）             │
│     └─ streamProxy 是给浏览器用的                       │
│                                                         │
│  2. 需要 WebSocket                                      │
│     ├─ Backend Agent → Web UI 需要实时推送              │
│     ├─ HTTP 请求/响应 → 无法实时推送                    │
│     ├─ WebSocket → 双向实时通信                         │
│     └─ SSE 不够用（单向、只能流式响应）                  │
│                                                         │
│  3. Session 持久化更自然                                │
│     ├─ Backend 直接写数据库                             │
│     ├─ 无需 IndexedDB 或额外 API                       │
│     ├─ Session 在 Backend 共享                         │
│     └─ 跨设备、多用户支持                               │
│                                                         │
│  4. Web 端变成纯 UI                                     │
│     ├─ 无 Agent 实例                                    │
│     ├─ 无 Session 管理                                  │
│     ├─ 只做 UI 渲染                                     │
│     └─ WebSocket 监听事件                               │
└─────────────────────────────────────────────────────────┘
```

---

## 二、完整架构图

```
┌─────────────────────────────────────────────────────────┐
│                    WEB (UI Only)                         │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ 纯 UI 层                                         │   │
│  │                                                  │   │
│  │  - 渲染消息                                      │   │
│  │  - 用户输入                                      │   │
│  │  - WebSocket/SSE 监听事件                        │   │
│  │                                                  │   │
│  │  websocket.onmessage = (event) => {             │   │
│  │    updateUI(event);                              │   │
│  │  }                                               │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  fetch("/api/agent/prompt", { text: "Hello" })         │
│                                                         │
└─────────────────────────────────────────────────────────┘
                         │
                         │ WebSocket / SSE
                         ▼
┌─────────────────────────────────────────────────────────┐
│                    BACKEND (Agent)                       │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Agent 实例层                                     │   │
│  │                                                  │   │
│  │  AgentHarness                                    │   │
│  │      ├─ Session（直接写数据库）                  │   │
│  │      ├─ 状态机                                   │   │
│  │      ├─ Compaction/Branch                        │   │
│  │      ├─ Tools                                    │   │
│  │      └─ subscribe → WebSocket 推送               │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ API 端点                                         │   │
│  │                                                  │   │
│  │  POST /api/agent/prompt     → 开始对话          │   │
│  │  POST /api/agent/continue   → 继续              │   │
│  │  GET  /api/agent/session    → 获取 Session      │   │
│  │  POST /api/agent/navigate   → 切换分支          │   │
│  │  WebSocket /ws/agent        → 实时事件推送      │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ LLM 调用                                         │   │
│  │                                                  │   │
│  │  streamSimple(model, context)                    │   │
│  │      ├─ 无 CORS 问题                             │   │
│  │      ├─ API Key 在 Backend                       │   │
│  │      ├─ SSE 流式响应                             │   │
│  │      └─ subscribe → WebSocket → Web             │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
                         │
                         │ 直接调用（无 CORS）
                         ▼
┌─────────────────────────────────────────────────────────┐
│                    LLM API                               │
│                                                         │
│  Anthropic API                                          │
│      ├─ Backend 直接调用                               │
│      ├─ SSE 流式响应                                   │
│      └─ Backend subscribe → WebSocket → Web            │
└─────────────────────────────────────────────────────────┘
```

---

## 三、为何不需要 streamProxy

### 3.1 streamProxy 解决的问题在 Backend 不存在

```
┌─────────────────────────────────────────────────────────┐
│  streamProxy 解决的问题                                  │
│                                                         │
│  问题 1: CORS                                           │
│    浏览器 → Anthropic API                              │
│    ❌ CORS 报错                                         │
│                                                         │
│  Backend → Anthropic API                               │
│    ✅ 无 CORS 问题（服务器不受 CORS 限制）              │
│                                                         │
│  问题 2: API Key 安全                                   │
│    浏览器 → 存储 API Key                               │
│    ❌ 泄露风险                                          │
│                                                         │
│  Backend → 存储 API Key                                │
│    ✅ 安全（环境变量、密钥管理）                        │
│                                                         │
│  结论：                                                  │
│    Backend 不需要 streamProxy                          │
│    Backend 直接用 streamSimple                         │
└─────────────────────────────────────────────────────────┘
```

### 3.2 Backend 直接调用 LLM API

```typescript
// Backend Agent（不用 streamProxy）
import { AgentHarness, streamSimple } from "@earendil-works/pi-agent-core";

const harness = new AgentHarness({
  env: new NodeExecutionEnv(),
  session: new DatabaseSession(userId),
  
  // 🔥 Backend 直接用 streamSimple（无 CORS 问题）
  streamFn: streamSimple,
  
  // 🔥 API Key 在 Backend（安全）
  getApiKeyAndHeaders: async (model) => {
    return {
      apiKey: process.env.ANTHROPIC_API_KEY,  // Backend 直接持有
    };
  },
  
  tools: [...],
  model: getModel("anthropic", "claude-sonnet-4"),
});
```

### 3.3 streamSimple vs streamProxy 对比

```
┌─────────────────────────────────────────────────────────┐
│  streamSimple（Backend 用）                              │
│                                                         │
│  直接调用：                                              │
│    Backend → Anthropic API                             │
│    ├─ 无 CORS 问题                                      │
│    ├─ API Key 在 Backend                               │
│    ├─ SSE 流式响应                                     │
│    └─ 原生调用                                         │
│                                                         │
│  适用：                                                  │
│    Backend Agent                                       │
│    Node.js 环境                                        │
│    服务器端应用                                         │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  streamProxy（Web 用）                                   │
│                                                         │
│  代理调用：                                              │
│    Web → streamProxy → Backend → Anthropic             │
│    ├─ 解决 CORS                                         │
│    ├─ authToken → Backend 验证                         │
│    ├─ SSE 流式响应                                     │
│    └─ HTTP 代理                                        │
│                                                         │
│  适用：                                                  │
│    Web Agent                                           │
│    Browser 环境                                        │
│    客户端应用                                           │
└─────────────────────────────────────────────────────────┘
```

---

## 四、WebSocket 的核心作用

### 4.1 WebSocket 解决的问题

```
┌─────────────────────────────────────────────────────────┐
│  Agent 在 Backend 的通信问题                             │
│                                                         │
│  问题：                                                  │
│    Backend Agent.subscribe((event) => { ... })        │
│    ↓                                                   │
│    如何让 Web UI 实时收到事件？                        │
│                                                         │
│  HTTP 不够用：                                          │
│    ├─ HTTP 请求/响应 → 无法实时推送                    │
│    ├─ HTTP 轮询 → 延迟高、效率低                       │
│    ├─ SSE → 单向（只能 Backend → Web）                 │
│    └─ SSE 无法 Web → Backend 通信                     │
│                                                         │
│  WebSocket 解决：                                       │
│    ├─ 双向实时通信                                     │
│    ├─ Backend → Web 推送事件                           │
│    ├─ Web → Backend 发送指令                           │
│    ├─ 低延迟                                           │
│    └─ 持久连接                                         │
└─────────────────────────────────────────────────────────┘
```

### 4.2 WebSocket vs SSE vs HTTP 轮询对比

| 技术 | 方向 | 实时性 | 效率 | 适用场景 |
|------|------|--------|------|----------|
| **HTTP 轮询** | 单向 | ❌ 高延迟 | ❌ 低效 | 不推荐 |
| **SSE** | 单向（Backend → Web） | ✅ 实时 | ✅ 高效 | Backend → Web 流式响应 |
| **WebSocket** | 双向 | ✅ 实时 | ✅ 高效 | Backend Agent ↔ Web UI |

### 4.3 WebSocket 在 Backend Agent 中的作用

```
┌─────────────────────────────────────────────────────────┐
│  WebSocket 的作用                                        │
│                                                         │
│  方向 1: Backend → Web（事件推送）                      │
│                                                         │
│    Backend Agent.subscribe((event) => {                │
│      ws.send(JSON.stringify(event));                   │
│    })                                                   │
│    ↓                                                   │
│    Web WebSocket.onmessage = (msg) => {                │
│      updateUI(msg);                                    │
│    }                                                   │
│                                                         │
│  方向 2: Web → Backend（用户指令）                      │
│                                                         │
│    Web ws.send({ type: "prompt", text: "..." })        │
│    ↓                                                   │
│    Backend ws.onmessage = (msg) => {                   │
│      agent.prompt(msg.text);                           │
│    }                                                   │
│                                                         │
│  关键：                                                  │
│    WebSocket 是 Backend Agent 必需的                   │
│    不是 streamProxy 的替代品                           │
│    它们解决不同层次的问题                               │
└─────────────────────────────────────────────────────────┘
```

---

## 五、Backend Agent 完整实现

### 5.1 Backend AgentServer

```typescript
// backend/agent-server.ts
import { AgentHarness, streamSimple } from "@earendil-works/pi-agent-core";
import { getModel } from "@earendil-works/pi-ai";
import WebSocket from "ws";

// ========== Backend 维护 Agent 实例 ==========
class AgentServer {
  private agents = new Map<string, AgentHarness>();  // userId → Agent
  private websockets = new Map<string, WebSocket>(); // userId → WebSocket
  
  // 用户连接时创建 Agent
  createAgent(userId: string, ws: WebSocket) {
    const harness = new AgentHarness({
      env: new NodeExecutionEnv(),
      session: new DatabaseSession(userId),  // 🔥 直接写数据库
      
      // 🔥 Backend 直接用 streamSimple（无 CORS）
      streamFn: streamSimple,
      
      // 🔥 API Key 在 Backend（安全）
      getApiKeyAndHeaders: async (model) => {
        return {
          apiKey: process.env.ANTHROPIC_API_KEY,
        };
      },
      
      tools: this.loadTools(userId),
      model: getModel("anthropic", "claude-sonnet-4"),
      systemPrompt: "你是助手。",
    });
    
    // 🔥 subscribe → WebSocket 推送给 Web
    harness.subscribe((event) => {
      const ws = this.websockets.get(userId);
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: "agent_event",
          data: event,
        }));
      }
    });
    
    this.agents.set(userId, harness);
    this.websockets.set(userId, ws);
  }
  
  // 用户断开时清理 Agent
  destroyAgent(userId: string) {
    const agent = this.agents.get(userId);
    if (agent) {
      // 可选：保存 Session 状态
      this.agents.delete(userId);
    }
    this.websockets.delete(userId);
  }
  
  // API 方法
  async prompt(userId: string, text: string) {
    const agent = this.agents.get(userId);
    if (!agent) throw new Error("Agent not found");
    await agent.prompt(text);  // Backend Agent 处理
  }
  
  async continue(userId: string) {
    const agent = this.agents.get(userId);
    if (!agent) throw new Error("Agent not found");
    await agent.continue();
  }
  
  async navigate(userId: string, targetId: string) {
    const agent = this.agents.get(userId);
    if (!agent) throw new Error("Agent not found");
    await agent.navigateTree(targetId);
  }
  
  async getSession(userId: string) {
    const agent = this.agents.get(userId);
    if (!agent) throw new Error("Agent not found");
    return await agent.session.getAllEntries();
  }
  
  private loadTools(userId: string) {
    // 加载用户的 tools
    return [...];
  }
}

// ========== 导出实例 ==========
export const agentServer = new AgentServer();
```

### 5.2 WebSocket 端点

```typescript
// backend/websocket.ts
import WebSocket from "ws";
import { agentServer } from "./agent-server";

const wss = new WebSocket.Server({ port: 8080 });

wss.on("connection", (ws, req) => {
  // 从请求中获取 userId（例如从 cookie 或 token）
  const userId = getUserIdFromRequest(req);
  
  // 🔥 用户连接时创建 Agent
  agentServer.createAgent(userId, ws);
  
  // 🔥 监听 Web 发送的指令
  ws.on("message", (msg) => {
    try {
      const { type, data } = JSON.parse(msg.toString());
      
      switch (type) {
        case "prompt":
          agentServer.prompt(userId, data.text);
          break;
          
        case "continue":
          agentServer.continue(userId);
          break;
          
        case "navigate":
          agentServer.navigate(userId, data.targetId);
          break;
          
        case "get_session":
          agentServer.getSession(userId).then((entries) => {
            ws.send(JSON.stringify({
              type: "session_response",
              data: entries,
            }));
          });
          break;
          
        default:
          ws.send(JSON.stringify({
            type: "error",
            data: { message: "Unknown message type" },
          }));
      }
    } catch (error) {
      ws.send(JSON.stringify({
        type: "error",
        data: { message: error.message },
      }));
    }
  });
  
  // 🔥 用户断开时清理 Agent
  ws.on("close", () => {
    agentServer.destroyAgent(userId);
  });
  
  // 连接成功通知
  ws.send(JSON.stringify({
    type: "connected",
    data: { userId },
  }));
});

function getUserIdFromRequest(req): string {
  // 从 cookie、token 或 URL 参数获取 userId
  // 实际应用中需要认证
  return "user-123";
}
```

### 5.3 HTTP API 端点（可选）

```typescript
// backend/api.ts
import express from "express";
import { agentServer } from "./agent-server";

const app = express();
app.use(express.json());

// ========== 认证中间件 ==========
app.use((req, res, next) => {
  const userId = req.headers["x-user-id"];
  if (!userId) {
    return res.status(401).json({ error: "Unauthorized" });
  }
  req.userId = userId;
  next();
});

// ========== API 端点 ==========

// 开始对话
app.post("/api/agent/prompt", async (req, res) => {
  const userId = req.userId;
  const { text } = req.body;
  
  await agentServer.prompt(userId, text);
  
  // 实时事件通过 WebSocket 推送
  res.json({ success: true });
});

// 继续对话
app.post("/api/agent/continue", async (req, res) => {
  const userId = req.userId;
  
  await agentServer.continue(userId);
  
  res.json({ success: true });
});

// 切换分支
app.post("/api/agent/navigate", async (req, res) => {
  const userId = req.userId;
  const { targetId } = req.body;
  
  await agentServer.navigate(userId, targetId);
  
  res.json({ success: true });
});

// 获取 Session
app.get("/api/agent/session", async (req, res) => {
  const userId = req.userId;
  
  const entries = await agentServer.getSession(userId);
  
  res.json({ entries });
});

app.listen(3000, () => console.log("API running on http://localhost:3000"));
```

---

## 六、Web 端纯 UI 实现

### 6.1 Web 端 AgentUI

```typescript
// web/agent-ui.ts
class AgentUI {
  private ws: WebSocket;
  private outputElement: HTMLElement;
  private inputElement: HTMLInputElement;
  
  constructor() {
    this.outputElement = document.getElementById("output")!;
    this.inputElement = document.getElementById("input") as HTMLInputElement;
    
    // 🔥 WebSocket 连接 Backend Agent
    this.ws = new WebSocket("ws://localhost:8080");
    
    // 🔥 监听 Backend Agent 推送的事件
    this.ws.onmessage = (msg) => {
      try {
        const { type, data } = JSON.parse(msg.data);
        
        switch (type) {
          case "connected":
            console.log("Connected to Backend Agent:", data.userId);
            break;
            
          case "agent_event":
            this.handleAgentEvent(data);
            break;
            
          case "session_response":
            this.renderSessionTree(data);
            break;
            
          case "error":
            this.showError(data.message);
            break;
        }
      } catch (error) {
        console.error("Parse error:", error);
      }
    };
    
    this.ws.onopen = () => {
      console.log("WebSocket connected");
    };
    
    this.ws.onerror = (error) => {
      console.error("WebSocket error:", error);
    };
    
    this.ws.onclose = () => {
      console.log("WebSocket disconnected");
    };
  }
  
  // ========== 发送指令（通过 WebSocket）==========
  
  sendPrompt(text: string) {
    if (!text.trim()) return;
    
    this.ws.send(JSON.stringify({
      type: "prompt",
      data: { text },
    }));
    
    // 显示用户消息
    this.outputElement.innerHTML += `<b>用户:</b> ${text}<br>`;
  }
  
  sendContinue() {
    this.ws.send(JSON.stringify({
      type: "continue",
      data: {},
    }));
  }
  
  sendNavigate(targetId: string) {
    this.ws.send(JSON.stringify({
      type: "navigate",
      data: { targetId },
    }));
  }
  
  requestSession() {
    this.ws.send(JSON.stringify({
      type: "get_session",
      data: {},
    }));
  }
  
  // ========== 处理 Backend Agent 事件 ==========
  
  handleAgentEvent(event: AgentEvent) {
    switch (event.type) {
      case "message_start":
        this.outputElement.innerHTML += "<b>Agent:</b> ";
        break;
        
      case "message_update":
        const delta = event.assistantMessageEvent?.delta || "";
        this.outputElement.innerHTML += delta;
        break;
        
      case "message_end":
        this.outputElement.innerHTML += "<br><br>";
        break;
        
      case "turn_end":
        console.log("Turn ended");
        break;
        
      case "session_update":
        this.renderSessionTree(event.entries);
        break;
        
      case "compaction_complete":
        this.showCompactionNotification(event.entry);
        break;
        
      case "branch_summary_complete":
        this.showBranchSummaryNotification(event.entry);
        break;
        
      case "agent_end":
        console.log("Agent run ended");
        break;
    }
  }
  
  // ========== UI 渲染 ==========
  
  renderSessionTree(entries: SessionTreeEntry[]) {
    const sessionElement = document.getElementById("session")!;
    sessionElement.innerHTML = "";
    
    // 渲染 Session Tree
    entries.forEach((entry) => {
      const node = document.createElement("div");
      node.className = "session-node";
      node.textContent = `${entry.type} (${entry.id})`;
      node.onclick = () => this.sendNavigate(entry.id);
      sessionElement.appendChild(node);
    });
  }
  
  showCompactionNotification(entry: CompactionEntry) {
    this.outputElement.innerHTML += 
      `<div class="notification">Context compacted</div>`;
  }
  
  showBranchSummaryNotification(entry: BranchSummaryEntry) {
    this.outputElement.innerHTML += 
      `<div class="notification">Branch summarized</div>`;
  }
  
  showError(message: string) {
    this.outputElement.innerHTML += 
      `<div class="error">${message}</div>`;
  }
}
```

### 6.2 HTML 页面

```html
<!-- web/index.html -->
<!DOCTYPE html>
<html>
<head>
  <title>Backend Agent UI</title>
  <style>
    #output { height: 400px; overflow-y: scroll; border: 1px solid #ccc; }
    #session { height: 200px; overflow-y: scroll; border: 1px solid #ccc; }
    .session-node { cursor: pointer; padding: 5px; }
    .session-node:hover { background: #f0f0f0; }
    .notification { color: blue; font-style: italic; }
    .error { color: red; }
  </style>
</head>
<body>
  <h1>Backend Agent Demo</h1>
  
  <div id="session"></div>
  
  <div id="output"></div>
  
  <input type="text" id="input" placeholder="输入消息..." />
  <button onclick="send()">发送</button>
  <button onclick="continue()">继续</button>
  <button onclick="refreshSession()">刷新 Session</button>
  
  <script type="module">
    import { AgentUI } from "./agent-ui.ts";
    
    const ui = new AgentUI();
    
    window.send = () => {
      const text = document.getElementById("input").value;
      ui.sendPrompt(text);
      document.getElementById("input").value = "";
    };
    
    window.continue = () => {
      ui.sendContinue();
    };
    
    window.refreshSession = () => {
      ui.requestSession();
    };
  </script>
</body>
</html>
```

---

## 七、Session 持久化方案

### 7.1 DatabaseSession 实现

```typescript
// backend/database-session.ts
import type { Session, SessionTreeEntry } from "@earendil-works/pi-agent-core";
import { Pool } from "pg";  // PostgreSQL

export class DatabaseSession implements Session {
  private userId: string;
  private pool: Pool;
  
  constructor(userId: string, pool: Pool) {
    this.userId = userId;
    this.pool = pool;
  }
  
  async appendEntry(entry: SessionTreeEntry): Promise<void> {
    // 🔥 直接写入数据库
    await this.pool.query(`
      INSERT INTO session_entries (user_id, entry_id, entry_data, timestamp)
      VALUES ($1, $2, $3, $4)
    `, [
      this.userId,
      entry.id,
      JSON.stringify(entry),
      entry.timestamp,
    ]);
  }
  
  async getEntry(id: string): Promise<SessionTreeEntry | null> {
    const result = await this.pool.query(`
      SELECT entry_data FROM session_entries
      WHERE user_id = $1 AND entry_id = $2
    `, [this.userId, id]);
    
    if (result.rows.length === 0) return null;
    
    return JSON.parse(result.rows[0].entry_data);
  }
  
  async getAllEntries(): Promise<SessionTreeEntry[]> {
    const result = await this.pool.query(`
      SELECT entry_data FROM session_entries
      WHERE user_id = $1
      ORDER BY timestamp ASC
    `, [this.userId]);
    
    return result.rows.map((row) => JSON.parse(row.entry_data));
  }
  
  async getBranch(leafId: string | null): Promise<SessionTreeEntry[]> {
    // 从 leaf 往回走到 root
    const entries = await this.getAllEntries();
    const entryMap = new Map(entries.map((e) => [e.id, e]));
    
    const branch: SessionTreeEntry[] = [];
    let currentId = leafId;
    
    while (currentId) {
      const entry = entryMap.get(currentId);
      if (!entry) break;
      
      branch.unshift(entry);  // 往前插入
      
      // 如果是 leaf entry，继续找 targetId
      if (entry.type === "leaf") {
        currentId = entry.targetId;
      } else {
        currentId = entry.parentId;
      }
    }
    
    return branch;
  }
  
  async setLeafId(leafId: string | null): Promise<void> {
    // 创建 LeafEntry
    const entry: LeafEntry = {
      type: "leaf",
      id: generateEntryId(),
      parentId: null,  // LeafEntry 无 parentId
      timestamp: new Date().toISOString(),
      targetId: leafId,
    };
    
    await this.appendEntry(entry);
  }
  
  async getCurrentLeafId(): Promise<string | null> {
    const result = await this.pool.query(`
      SELECT entry_data FROM session_entries
      WHERE user_id = $1 AND entry_data->>'type' = 'leaf'
      ORDER BY timestamp DESC
      LIMIT 1
    `, [this.userId]);
    
    if (result.rows.length === 0) return null;
    
    const entry = JSON.parse(result.rows[0].entry_data) as LeafEntry;
    return entry.targetId;
  }
}
```

### 7.2 数据库表结构

```sql
-- PostgreSQL 表结构
CREATE TABLE session_entries (
  id SERIAL PRIMARY KEY,
  user_id VARCHAR(255) NOT NULL,
  entry_id VARCHAR(255) NOT NULL,
  entry_data JSONB NOT NULL,
  timestamp TIMESTAMP NOT NULL,
  
  UNIQUE(user_id, entry_id)
);

CREATE INDEX idx_session_entries_user ON session_entries(user_id);
CREATE INDEX idx_session_entries_timestamp ON session_entries(timestamp);
```

---

## 八、事件传递流程详解

### 8.1 Agent 在 Web 的事件传递

```
┌─────────────────────────────────────────────────────────┐
│  Agent 在 Web：事件传递                                  │
│                                                         │
│  Anthropic SSE                                          │
│      ↓                                                  │
│  Backend Proxy (/api/stream)                           │
│      ↓ SSE 转发                                        │
│  Web streamProxy                                       │
│      ↓                                                  │
│  Web AgentHarness                                      │
│      ↓ subscribe                                       │
│  Web UI                                                 │
│                                                         │
│  路径：Anthropic → Backend → Web → Agent → UI          │
│  技术：SSE（HTTP）                                      │
│  延迟：低（Web 本地处理）                               │
└─────────────────────────────────────────────────────────┘
```

### 8.2 Agent 在 Backend 的事件传递

```
┌─────────────────────────────────────────────────────────┐
│  Agent 在 Backend：事件传递                              │
│                                                         │
│  Anthropic SSE                                          │
│      ↓                                                  │
│  Backend AgentHarness (streamSimple)                   │
│      ↓ subscribe                                       │
│  Backend WebSocket.send(event)                         │
│      ↓                                                  │
│  Web WebSocket.onmessage                               │
│      ↓                                                  │
│  Web UI                                                 │
│                                                         │
│  路径：Anthropic → Backend Agent → WebSocket → Web UI  │
│  技术：SSE（Backend 内部） + WebSocket（Backend → Web） │
│  延迟：稍高（网络传输）                                 │
└─────────────────────────────────────────────────────────┘
```

### 8.3 关键对比

| 维度 | Agent 在 Web | Agent 在 Backend |
|------|-------------|------------------|
| **事件处理位置** | Web AgentHarness | Backend AgentHarness |
| **事件传递方式** | 直连 subscribe → UI | WebSocket → Web UI |
| **延迟** | 低（本地） | 稍高（网络） |
| **Session 存储** | IndexedDB | Database |
| **跨设备支持** | ❌ 不支持 | ✅ 支持 |
| **离线运行** | ❌ 不支持 | ✅ 支持 |

---

## 九、多 LLM SDK 扩展

### 9.1 Backend 可扩展多 SDK

```typescript
// backend/llm-provider.ts
import Anthropic from "@anthropic-ai/sdk";
import OpenAI from "openai";

class LLMProvider {
  private anthropic: Anthropic;
  private openai: OpenAI;
  
  constructor() {
    this.anthropic = new Anthropic({
      apiKey: process.env.ANTHROPIC_API_KEY,
    });
    
    this.openai = new OpenAI({
      apiKey: process.env.OPENAI_API_KEY,
    });
  }
  
  async stream(model: any, context: any, options: any) {
    // 🔥 Backend 决定用哪个 SDK
    if (model.provider === "anthropic") {
      return this.streamAnthropic(model, context, options);
    }
    
    if (model.provider === "openai") {
      return this.streamOpenAI(model, context, options);
    }
    
    if (model.provider === "custom") {
      return this.streamCustom(model, context, options);
    }
    
    throw new Error("Unknown provider");
  }
  
  private async streamAnthropic(model, context, options) {
    const stream = this.anthropic.messages.stream({
      model: model.id,
      max_tokens: options.max_tokens || 4096,
      messages: context.messages,
      system: context.systemPrompt,
    });
    
    return stream;
  }
  
  private async streamOpenAI(model, context, options) {
    const stream = await this.openai.chat.completions.create({
      model: model.id,
      max_tokens: options.max_tokens || 4096,
      messages: this.convertToOpenAIFormat(context),
      stream: true,
    });
    
    return this.wrapOpenAIStream(stream);
  }
  
  private async streamCustom(model, context, options) {
    // 自定义 LLM SDK
    const customLLM = new CustomLLM({
      apiKey: process.env.CUSTOM_API_KEY,
    });
    
    return customLLM.stream(context);
  }
  
  private convertToOpenAIFormat(context) {
    // Anthropic 格式 → OpenAI 格式
    return context.messages.map((msg) => ({
      role: msg.role === "user" ? "user" : "assistant",
      content: msg.content,
    }));
  }
  
  private wrapOpenAIStream(stream) {
    // OpenAI stream → Anthropic-like stream
    // 需要适配格式
    return {
      async *[Symbol.asyncIterator]() {
        for await (const chunk of stream) {
          yield {
            type: "content_block_delta",
            delta: { text: chunk.choices[0]?.delta?.content || "" },
          };
        }
      },
    };
  }
}
```

### 9.2 AgentHarness 使用自定义 Provider

```typescript
// backend/agent-server.ts
import { AgentHarness } from "@earendil-works/pi-agent-core";
import { LLMProvider } from "./llm-provider";

const llmProvider = new LLMProvider();

const harness = new AgentHarness({
  env: new NodeExecutionEnv(),
  session: new DatabaseSession(userId),
  
  // 🔥 自定义 streamFn
  streamFn: async (model, context, options) => {
    return llmProvider.stream(model, context, options);
  },
  
  tools: [...],
  model: getModel("anthropic", "claude-sonnet-4"),
});
```

---

## 十、离线运行支持

### 10.1 Backend Agent 可离线运行

```typescript
// backend/offline-agent.ts
class OfflineAgentService {
  private agents = new Map<string, AgentHarness>();
  
  // 启动后台任务
  async startBackgroundTask(userId: string, task: string) {
    const harness = new AgentHarness({
      env: new NodeExecutionEnv(),
      session: new DatabaseSession(userId),
      streamFn: streamSimple,
      tools: [...],
      model: getModel("anthropic", "claude-sonnet-4"),
    });
    
    // 🔥 即使用户断开，Agent 仍可运行
    this.agents.set(userId, harness);
    
    // 开始任务
    await harness.prompt(task);
    
    // 任务完成后通知用户（通过邮件、通知等）
    this.notifyUser(userId, "Task completed");
  }
  
  // 用户重新连接时恢复 Agent
  async resumeAgent(userId: string, ws: WebSocket) {
    const harness = this.agents.get(userId);
    
    if (!harness) {
      // 🔥 从数据库恢复 Session
      harness = await this.restoreFromDatabase(userId);
    }
    
    // 🔥 重新订阅事件
    harness.subscribe((event) => {
      ws.send(JSON.stringify({
        type: "agent_event",
        data: event,
      }));
    });
    
    this.agents.set(userId, harness);
  }
  
  private async restoreFromDatabase(userId: string) {
    const session = new DatabaseSession(userId);
    const entries = await session.getAllEntries();
    
    // 从 entries 恢复 Agent 状态
    // ...
    
    return new AgentHarness({
      env: new NodeExecutionEnv(),
      session,
      streamFn: streamSimple,
      tools: [...],
      model: getModel("anthropic", "claude-sonnet-4"),
    });
  }
  
  private notifyUser(userId: string, message: string) {
    // 发送邮件、推送通知等
    console.log(`Notify user ${userId}: ${message}`);
  }
}
```

---

## 十一、对比总结表

### 11.1 架构对比

| 维度 | Agent 在 Web | Agent 在 Backend |
|------|-------------|------------------|
| **Agent 位置** | Web Browser | Backend Server |
| **streamProxy** | ✅ 需要 | ❌ 不需要 |
| **streamSimple** | ❌ 不能用 | ✅ 直接用 |
| **WebSocket** | ❌ 不需要 | ✅ 必需要 |
| **Session 存储** | IndexedDB | Database |
| **事件传递** | 直连 subscribe → UI | WebSocket → Web |
| **实时性** | ✅ 低延迟 | ❌ 网络延迟 |
| **跨设备** | ❌ 不支持 | ✅ 支持 |
| **离线运行** | ❌ 不支持 | ✅ 支持 |
| **多用户** | ❌ 不支持 | ✅ 支持 |
| **资源限制** | ❌ 浏览器限制 | ✅ Backend 丰富 |
| **安全性** | ❌ IndexedDB 可篡改 | ✅ Backend 安全 |
| **多 LLM SDK** | ❌ Web 无权 | ✅ Backend 可扩展 |

### 11.2 适用场景对比

| 场景 | Agent 在 Web | Agent 在 Backend |
|------|-------------|------------------|
| **单用户应用** | ✅ 推荐 | ❌ 过度设计 |
| **实时交互优先** | ✅ 推荐 | ❌ 延迟高 |
| **简单 Session** | ✅ IndexedDB 可用 | ❌ 过度设计 |
| **离线不重要** | ✅ 推荐 | ❌ 过度设计 |
| **多用户应用** | ❌ 不支持 | ✅ 推荐 |
| **跨设备共享** | ❌ 不支持 | ✅ 推荐 |
| **离线运行** | ❌ 不支持 | ✅ 推荐 |
| **Session 持久化重要** | ❌ 不够可靠 | ✅ 推荐 |
| **安全性高** | ❌ IndexedDB 不安全 | ✅ 推荐 |
| **资源需求大** | ❌ 浏览器限制 | ✅ 推荐 |

---

## 十二、关键理解总结

### 12.1 Backend Agent 的核心变化

> **Agent 在 Backend = 不需要 streamProxy + 需要 WebSocket + Session 直接写数据库**
> 
> - **不需要 streamProxy**：Backend 无 CORS、API Key 安全
> - **需要 WebSocket**：Backend → Web 实时事件推送
> - **Session 持久化**：直接写数据库，跨设备共享

### 12.2 WebSocket 不是 streamProxy 的替代

> **WebSocket 和 streamProxy 解决不同问题**
> 
> - **streamProxy**：Web → Backend（LLM API 代理）
> - **WebSocket**：Backend → Web（事件推送）
> 
> **Agent 在 Web**：需要 streamProxy，不需要 WebSocket
> 
> **Agent 在 Backend**：不需要 streamProxy，需要 WebSocket

### 12.3 Web 端变成纯 UI

> **Backend Agent 的 Web 端**
> 
> - 无 Agent 实例
> - 无 Session 管理
> - 只做 UI 渲染
> - WebSocket 监听事件
> - WebSocket 发送指令

### 12.4 Backend Agent 的优势

> **多用户、跨设备、离线运行、持久化可靠、安全性高、资源丰富、多 LLM SDK 扩展**

---

## 参考资料

- **源文件**：
  - `packages/agent/src/agent.ts` - Agent 类定义
  - `packages/agent/src/harness/agent-harness.ts` - AgentHarness 主流程
  - `packages/agent/src/harness/types.ts` - AgentHarnessOptions 定义

- **相关文档**：
  - `浏览器版 Agent 架构详解.md` - Agent 在 Web 的架构
  - `Agent Harness 与 Session 架构知识体系.md` - Session Entry 类型体系