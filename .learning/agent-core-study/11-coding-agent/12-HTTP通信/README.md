# HTTP 通信

## 学习目标

理解 Coding Agent 的 HTTP 请求分发和输出保护机制。

## 核心源文件

- `http-dispatcher.ts` - HTTP 请求分发
- `output-guard.ts` - 输出保护

## 关键概念

### 1. HTTP Dispatcher（http-dispatcher.ts）

**设计目的**:
- 统一 HTTP 请求分发
- 支持多种请求类型
- 管理请求配置
- 提供请求拦截点

**核心职责**:
- LLM API 请求分发
- OAuth 认证请求
- 工具 HTTP 请求
- 自定义 HTTP 请求

### 2. 请求类型

**LLM API 请求**:
- Anthropic API
- AWS Bedrock API
- 自定义 Provider API

**OAuth 认证请求**:
- 授权请求
- Token 交换
- Token 刷新

**工具 HTTP 请求**:
- WebFetch 工具
- MCP 工具
- 自定义工具 HTTP

### 3. 请求配置

**通用配置**:
```typescript
interface HttpRequestConfig {
  url: string;
  method: 'GET' | 'POST' | 'PUT' | 'DELETE';
  headers?: Record<string, string>;
  body?: any;
  timeout?: number;
  signal?: AbortSignal;
}
```

**LLM 请求配置**:
```typescript
interface LLMRequestConfig {
  provider: string;
  model: string;
  apiKey: string;
  headers?: Record<string, string>;
  body: LLMRequestBody;
  streamFn?: StreamFunction;
}
```

### 4. 请求分发流程

**通用流程**:
1. 构建请求配置
2. 添加认证 headers
3. 发送 HTTP 请求
4. 处理响应
5. 错误处理
6. 返回结果

**LLM API 流程**:
1. 获取 API key 和 headers
2. 构建 LLM 请求体
3. 选择 stream 函数
4. 发送 API 请求
5. 流式接收响应
6. 解析响应内容
7. 返回消息

### 5. Stream 函数

**StreamFunction 类型**:
```typescript
type StreamFunction = (
  request: Request,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal
) => Promise<void>
```

**两种 Stream 函数**:
- **streamSimple** - 简单流式（无需特殊环境）
- **streamRPC** - RPC 流式（通过 WebSocket）

**选择逻辑**:
```typescript
// 根据运行模式选择
if (mode === 'rpc') {
  streamFn = streamRPC;
} else {
  streamFn = streamSimple;
}
```

### 6. 请求拦截

**拦截点**:
- 请求前拦截（修改配置）
- 请求后拦截（处理响应）
- 错误拦截（处理错误）

**扩展集成**:
扩展可通过钩子拦截 HTTP 请求：
- `PreToolUse` - 工具使用前
- `PostToolUse` - 工具使用后

### 7. Output Guard（output-guard.ts）

**设计目的**:
- 保护输出内容
- 防止敏感信息泄露
- 验证输出格式
- 控制输出流向

**核心职责**:
- 输出内容验证
- 敏感信息过滤
- 输出截断控制
- 输出格式化

### 8. 输出验证

**验证类型**:
- 内容格式验证
- 大小限制验证
- 安全性验证
- 权限验证

**验证流程**:
1. 接收输出内容
2. 检查内容格式
3. 检查内容大小
4. 检查安全性
5. 过滤敏感信息
6. 返回验证结果

### 9. 敏感信息过滤

**过滤规则**:
- API key 过滤
- 密码过滤
- Token 过滤
- 路径过滤

**过滤方法**:
```typescript
function filterSensitiveInfo(content: string): string {
  // 移除 API key
  content = content.replace(/api[_-]?key[^:]*:\s*[^\s]+/gi, 'api_key: [REDACTED]');
  
  // 移除密码
  content = content.replace(/password[^:]*:\s*[^\s]+/gi, 'password: [REDACTED]');
  
  // 移除 token
  content = content.replace(/token[^:]*:\s*[^\s]+/gi, 'token: [REDACTED]');
  
  return content;
}
```

### 10. 输出截断

**截断规则**:
- 最大字节限制
- 最大行数限制
- 单行长度限制

**截断方法**:
使用 truncate.ts 的截断函数：
```typescript
const guardedOutput = truncateTail(output, maxBytes);
```

### 11. 输出格式化

**格式化类型**:
- ANSI 颜色转换
- Markdown 格式化
- HTML 格式化
- JSON 格式化

**格式化方法**:
- ansi-to-html.ts - ANSI 转 HTML
- render-utils.ts - 渲染工具

### 12. 错误处理

**HTTP 错误**:
- 网络错误
- 服务器错误（500, 502, 503, 504）
- 认证错误
- 速率限制（429）

**处理策略**:
- 自动重试（可重试错误）
- 错误提示（不可重试错误）
- 中止处理（用户中止）

**可重试错误判断**:
```typescript
function isRetryableError(error: Error): boolean {
  // 网络错误
  // 服务器错误
  // 速率限制
  return /network|500|502|503|504|429/i.test(error.message);
}
```

## 重点阅读

### http-dispatcher.ts

理解 HTTP 分发：
1. **请求类型** - 不同类型的请求
2. **配置构建** - 如何构建请求配置
3. **请求发送** - 如何发送 HTTP 请求
4. **响应处理** - 如何处理响应
5. **错误处理** - 如何处理错误
6. **Stream 函数** - 流式请求处理

### output-guard.ts

理解输出保护：
1. **验证逻辑** - 输出验证
2. **过滤规则** - 敏感信息过滤
3. **截断控制** - 输出截断
4. **格式化** - 输出格式化

## 关键设计模式

### 分发模式
统一请求分发：
- 不同请求类型统一处理
- 配置统一管理
- 错误统一处理

### 拦截模式
请求拦截点：
- 请求前拦截
- 请求后拦截
- 错误拦截

### 保护模式
输出保护机制：
- 验证
- 过滤
- 截断
- 格式化

### 重试模式
错误重试策略：
- 可重试错误识别
- 指数退避
- 最大重试次数

## 学习建议

### 阅读顺序

1. **http-dispatcher.ts** - 理解 HTTP 分发
2. **output-guard.ts** - 理解输出保护

### 重点理解

1. **请求分发** - 如何统一处理不同请求
2. **Stream 函数** - 流式请求的处理机制
3. **错误处理** - HTTP 错误处理策略
4. **输出验证** - 输出内容验证逻辑
5. **敏感信息过滤** - 过滤规则和方法
6. **输出截断** - 截断策略和限制

## 在 AgentSession 中的应用

### LLM API 请求
```typescript
// Agent 使用 http-dispatcher 发送 API 请求
await agent.prompt(messages);

// 内部流程
const streamFn = this.agent.streamFn;
const { apiKey, headers } = await this._getRequiredRequestAuth(model);
await streamFn(request, onEvent, signal);
```

### OAuth 认证请求
```typescript
// ModelRegistry 使用 http-dispatcher 进行 OAuth
await modelRegistry.authenticateOAuth(provider);

// 内部流程
// 发送授权请求
// 接收授权码
// 交换 token
```

### WebFetch 工具
```typescript
// WebFetch 工具使用 HTTP 请求
const result = await webFetch(url);

// 内部使用 http-dispatcher
await dispatcher.fetch(url, config);
```

### 输出保护
```typescript
// 工具结果经过 output-guard
const result = await tool.execute(input);
const guardedResult = outputGuard.protect(result);

// 应用截断
const truncatedResult = truncateTail(guardedResult, maxBytes);
```

## 实际应用场景

### 1. LLM API 调用
发送消息到 LLM：
- 构建请求体
- 获取认证
- 流式接收
- 处理响应

### 2. OAuth 认证流程
用户进行 OAuth：
- 发起授权
- 接收授权码
- 交换 token
- 存储 token

### 3. 工具 HTTP 请求
工具发送 HTTP 请求：
- WebFetch
- MCP 工具
- 自定义工具

### 4. 输出保护
工具结果保护：
- 过滤敏感信息
- 截断大输出
- 格式化输出

### 5. 错误重试
HTTP 错误重试：
- 网络错误重试
- 服务器错误重试
- 速率限制重试

## 扩展思考

### 性能优化
- HTTP 请求性能优化
- 流式响应性能
- 并发请求管理

### 安全考虑
- HTTPS 强制
- 认证信息保护
- 敏感信息过滤

### 扩展性
- 支持更多 HTTP 功能
- 支持自定义拦截器
- 支持自定义 Stream 函数

### 错误处理
- 更多错误类型识别
- 更精细的重试策略
- 更友好的错误提示

### 监控和日志
- HTTP 请求日志
- 性能监控
- 错误追踪