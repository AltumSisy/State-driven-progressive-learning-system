# L10: Proxy 与浏览器支持

---

## 1. 心智模型构建

### 1.1 背景

#### 浏览器环境的挑战

```
Node.js 环境:
├─ 直接调用 LLM API
├─ fs/shell 本地操作
├─ 无认证限制
└─ 完全控制

浏览器环境问题:
├─ CORS 限制 → 无法直接调用 Anthropic API
├─ API Key 泄露 → 客户端存储危险
├─ fs/shell 缺失 → 无文件系统
├─ 安全限制 → 多种约束
└─ 需要代理后端

→ streamProxy 提供浏览器代理方案
```

---

### 1.2 目标

#### 核心痛点

| 痛点 | 直接浏览器调用 | streamProxy 方案 |
|------|--------------|-----------------|
| CORS | API 报错 | 代理服务器转发 |
| API Key 安全 | 泄露风险 | 后端保管 |
| 认证传递 | 无标准 | authToken 参数 |
| 环境差异 | 需适配 | 统一 API |

---

### 1.3 专家视角 - 概念网络

```
Proxy 概念网络:

核心函数:
├─ streamProxy()
│   ├─ 参数: model, context, options
│   ├─ options.proxyUrl: string ← 代理服务器 URL
│   ├─ options.authToken?: string ← 认证 Token
│   ├─ 返回: ReturnType<typeof streamSimple>
│   └─ 内部: 调用代理服务器转发请求
│
├─ ProxyOptions
│   ├─ proxyUrl: string ← 必需
│   ├─ authToken?: string ← 可选
│   ├─ headers?: Record<string, string>
│   └─ 继承 SimpleStreamOptions

后端实现:
├─ 代理服务器
│   ├─ 接收: POST /api/stream
│   ├─ 解析: authToken → 用户身份
│   ├─ 转发: 调用 Anthropic API
│   ├─ 流式返回: SSE 格式
│   └─ 错误处理: 认证失败、API 错误
│
├─ 认证流程
│   ├─ 浏览器发送 authToken
│   ├─ 后端验证 Token
│   ├─ 获取真实 API Key
│   └─ 调用 Anthropic API

浏览器配置:
├─ Agent 初始化
│   ├─ streamFn: 自定义 stream 函数
│   ├─ 使用 streamProxy
│   └─ 配置 proxyUrl, authToken
│
├─ ExecutionEnv
│   ├─ 浏览器版本: 依赖后端 fs/shell
│   ├─ 或: 实现虚拟 fs/shell
│   └─ 或: 不使用文件操作工具
```

---

## 2. 结构化学习 (SQ3R)

### 2.1 Survey - Proxy 架构

```
Proxy 架构流程:

┌─────────────────────────────────────────────────────────┐
│                    BROWSER                                │
│                                                           │
│  Agent                                                    │
│      │                                                    │
│      │ streamFn: streamProxy                             │
│      │                                                    │
│      ▼                                                    │
│  streamProxy(model, context, {                            │
│      proxyUrl: "https://backend/api/stream",             │
│      authToken: "user-token",                            │
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
│                                                           │
│  POST /api/stream                                         │
│      │                                                    │
│      │ 1. 验证 authToken                                 │
│      │ 2. 获取真实 API Key                               │
│      │ 3. 构建 Anthropic 请求                            │
│      │                                                    │
│      ▼                                                    │
│  Anthropic API                                            │
│      │                                                    │
│      │ SSE 流式返回                                       │
│      │                                                    │
│      ▼                                                    │
│  转发给 Browser (SSE)                                     │
└─────────────────────────────────────────────────────────┘
```

### 2.2 Question - 关键问题驱动

**Q1**: streamProxy 如何解决 CORS 问题？
**Q2**: authToken 的传递和验证流程？
**Q3**: 代理后端需要实现哪些功能？
**Q4**: node.ts 导出的用途？

### 2.3 Read - 源代码映射

| 内容 | 源文件 | 行数 |
|------|--------|------|
| streamProxy | `proxy.ts` | - |
| ProxyOptions | `proxy.ts` | - |
| node.ts 导出 | `node.ts` | - |

### 2.4 Recite - 使用模板

#### 浏览器使用模板

```typescript
import { Agent, streamProxy } from "@earendil-works/pi-agent-core";
import { getModel } from "@earendil-works/pi-ai";

const agent = new Agent({
  initialState: {
    systemPrompt: "You are helpful.",
    model: getModel("anthropic", "claude-sonnet-4"),
  },
  
  // 使用 streamProxy 替代默认 stream
  streamFn: (model, context, options) =>
    streamProxy(model, context, {
      ...options,
      proxyUrl: "https://your-backend.com/api/stream",
      authToken: localStorage.getItem("authToken"),
    }),
});

agent.subscribe((event) => {
  if (event.type === "message_update") {
    process.stdout.write(event.assistantMessageEvent.delta);
  }
});

await agent.prompt("Hello!");
```

#### 后端代理模板 (Express)

```typescript
import express from "express";
import Anthropic from "@anthropic-ai/sdk";

const app = express();

app.post("/api/stream", async (req, res) => {
  const authToken = req.headers.authorization;
  
  // 验证 Token
  const user = await verifyToken(authToken);
  if (!user) {
    return res.status(401).json({ error: "Unauthorized" });
  }
  
  // 获取用户关联的 API Key
  const apiKey = await getApiKey(user.id);
  
  // 构建 Anthropic 客户端
  const anthropic = new Anthropic({ apiKey });
  
  // 转发请求
  const stream = anthropic.messages.stream({
    model: req.body.model,
    max_tokens: req.body.max_tokens,
    messages: req.body.messages,
  });
  
  // SSE 流式返回
  res.setHeader("Content-Type", "text/event-stream");
  for await (const event of stream) {
    res.write(`data: ${JSON.stringify(event)}\n\n`);
  }
  res.end();
});
```

### 2.5 Review - TODO清单 (渐进式披露)

> 📋 **渐进式学习**: 一次只显示一个TODO，完成后才解锁下一个。

#### 🔴 TODO-1: 掌握 streamProxy (当前激活)

**完成检查**:
- [ ] 列举 streamProxy 的核心参数
- [ ] 解释 proxyUrl 和 authToken 的作用

<details>
<summary>💡 提示</summary>

核心参数:
- model, context, options
- proxyUrl: 代理服务器地址
- authToken: 用户认证凭证

authToken 传递到后端，用于获取真实 API Key
</details>

---

#### 🟡 TODO-2: 掌握后端实现 (待解锁)

**前置要求**: 完成 TODO-1

**完成检查**:
- [ ] 解释后端代理的认证流程
- [ ] 解释 SSE 流式返回的实现

---

#### 🟡 TODO-3: 掌握环境差异 (待解锁)

**前置要求**: 完成 TODO-2

**完成检查**:
- [ ] 解释浏览器与 Node.js 的关键差异
- [ ] 解释 ExecutionEnv 的适配方案

---

## 📝 费曼检验 (必须完成)

在继续下一课之前，请用自己的话解释：

### 问题 1: Proxy 架构
> "streamProxy 解决了什么问题？为什么浏览器不能直接调用 Anthropic API？"

你的解释：_______________________________________________

### 问题 2: 认证流程
> "authToken 和真实 API Key 的关系是什么？为什么不在浏览器存 API Key？"

你的解释：_______________________________________________

### 问题 3: 流式保持
> "代理如何保持流式体验？SSE 和一次性 JSON 返回有什么区别？"

你的解释：_______________________________________________

<details>
<summary>✅ 检查你的理解</summary>

**问题 1 参考答案**:
- 解决 CORS 限制
- 浏览器不能存 API Key（泄露风险）
- 通过代理服务器中转请求

**问题 2 参考答案**:
- authToken: 用户凭证（可刷新）
- API Key: 真实调用凭证（后端保管）
- 后端用 authToken 验证身份，获取对应 API Key

**问题 3 参考答案**:
- SSE (Server-Sent Events): 流式推送
- 代理将 Anthropic 的 SSE 转发给浏览器
- 一次性 JSON: 等待完整响应，体验差
</details>

---

## 3. 对抗性测试

### 3.1 边界问题

#### authToken 失效

```typescript
authToken: "expired-token"
// 结果：后端返回 401 Unauthorized
// 教训：处理认证失败，刷新 Token
```

#### proxyUrl 不可达

```typescript
proxyUrl: "https://nonexistent-backend.com"
// 结果：网络错误，无法调用 LLM
// 教训：配置正确的代理地址
```

### 3.2 反事实推理

**情境 1**: 如果后端不支持 SSE？
```typescript
// 后端返回一次性 JSON
res.json(result);
// 结果：无法流式处理，体验差
// 教训：必须支持 SSE 流式返回
```

**情境 2**: 如果 authToken 泄露？
```typescript
authToken: "leaked-token"  // 在 URL 或 localStorage 泄露
// 结果：攻击者可冒用身份
// 教训：Token 应加密存储，定期刷新
```

**情境 3**: 如果代理服务器慢？
```typescript
// 后端转发耗时 10秒
// 结果：用户等待久，体验差
// 教训：代理服务器应高性能
```

### 3.3 漏洞注入 - 常见错误

| 错误类型 | 示例 | 后果 |
|---------|------|------|
| authToken 泄露 | URL 参数传递 | 安全风险 |
| proxyUrl 错误 | 无效地址 | 无法调用 |
| 不处理 401 | 认证失败未处理 | 请求失败 |
| 后端不支持 SSE | 返回 JSON | 无法流式 |
| CORS 仍报错 | 代理未配置 CORS | 请求失败 |

---

## 4. 思想与迁移

### 4.1 设计哲学

#### 代理转发

```
Browser → Proxy → Anthropic API
         (认证、转发、流式)
```

**思想**: 分离客户端和 API，中间层处理安全和适配。

#### 认证分离

```typescript
// 浏览器: authToken (用户凭证)
// 后端: apiKey (真实 API Key)
```

**思想**: 用户凭证不暴露真实 API Key，后端负责转换。

#### 流式保持

```
Anthropic SSE → Backend SSE → Browser SSE
```

**思想**: 代理不破坏流式体验，端到端保持 SSE。

### 4.2 可迁移思维

| 思想 | Proxy 应用 | 可迁移领域 |
|------|-----------|-----------|
| **代理转发** | streamProxy | API Gateway、BFF |
| **认证分离** | authToken/apiKey | OAuth、JWT |
| **流式保持** | SSE 转发 | WebSocket 代理、实时数据 |
| **环境适配** | Browser vs Node | 跨平台应用 |
| **安全隔离** | Token 不暴露 | 密钥管理、安全设计 |

---

## 源文件映射

| 内容 | 源文件 | 行数 |
|------|--------|------|
| streamProxy | `src/proxy.ts` | - |
| node.ts 导出 | `src/node.ts` | - |

---

## 下一步

→ [L11: coding-agent 实例分析](../11-coding-agent)