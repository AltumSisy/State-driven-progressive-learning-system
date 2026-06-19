# 模型注册系统

## 学习目标

理解 Coding Agent 的模型发现、API 密钥管理和认证流程。

## 核心源文件

- `model-registry.ts` - 模型注册表（核心）
- `model-resolver.ts` - 模型解析器
- `provider-display-names.ts` - Provider 显示名称
- `auth-guidance.ts` - 认证引导
- `auth-storage.ts` - 认证存储

## 关键概念

### 1. ModelRegistry 核心类

**职责**:
- 模型发现和注册
- API 密钥管理
- OAuth 认证管理
- Provider 注册

**核心方法**:
```typescript
class ModelRegistry {
  // 模型发现
  async getAvailable(): Promise<Model[]>;
  find(provider, modelId): Model | undefined;
  
  // 认证管理
  async getApiKeyAndHeaders(model): Promise<AuthResult>;
  hasConfiguredAuth(model): boolean;
  isUsingOAuth(model): boolean;
  
  // Provider 管理
  registerProvider(name, config): void;
  unregisterProvider(name): void;
  
  // OAuth
  async authenticateOAuth(provider): Promise<void>;
  async clearOAuth(provider): Promise<void>;
}
```

### 2. 模型发现机制

**getAvailable 方法**:
1. 查询所有注册的 Provider
2. 获取每个 Provider 的模型列表
3. 过滤可用模型（有认证配置）
4. 返回可用模型数组

**模型来源**:
- 内置 Provider（Anthropic、AWS Bedrock）
- 用户自定义 Provider
- 扩展注册的 Provider

### 3. API 密钥管理

**getApiKeyAndHeaders 流程**:
1. 识别 Provider 类型
2. 查找认证配置：
   - 环境变量（如 ANTHROPIC_API_KEY）
   - 配置文件（settings.json）
   - OAuth token
3. 构建 headers
4. 返回 AuthResult

**AuthResult**:
```typescript
interface AuthResult {
  ok: boolean;
  apiKey?: string;
  headers?: Record<string, string>;
  error?: string;
}
```

### 4. OAuth 认证流程

**authenticateOAuth 流程**（auth-storage.ts）:
1. 发起 OAuth 授权请求
2. 用户授权
3. 接收授权码
4. 交换 token
5. 存储 token
6. 返回认证状态

**Token 存储**:
- 存储位置：`.claude/auth.json`
- 包含：access_token、refresh_token、expires_at
- 支持自动刷新

**Token 刷新**:
- 检查过期时间
- 自动刷新过期 token
- 更新存储

### 5. Provider 注册机制

**registerProvider**:
```typescript
registerProvider(name: string, config: ProviderConfig): void
```

**ProviderConfig**:
```typescript
interface ProviderConfig {
  models: Model[];            // Provider 的模型列表
  authenticate?: () => Promise<AuthConfig>;  // 认证函数
  displayName?: string;       // 显示名称
}
```

**应用场景**:
- 扩展注册自定义 Provider
- 动态添加模型支持
- 集成第三方服务

### 6. 模型解析（model-resolver.ts）

**resolveModel**:
```typescript
resolveModel(provider: string, modelId: string): Model | undefined
```

解析流程：
1. 查找 Provider
2. 查找模型
3. 验证认证配置
4. 返回 Model 或 undefined

### 7. Provider 显示名称

**provider-display-names.ts**:
```typescript
const PROVIDER_DISPLAY_NAMES: Record<string, string> = {
  'anthropic': 'Anthropic',
  'aws-bedrock': 'AWS Bedrock',
  // ...
};
```

**用途**:
- UI 显示友好名称
- 错误消息中使用
- 用户引导

### 8. 认证引导（auth-guidance.ts）

**formatNoApiKeyFoundMessage**:
```typescript
formatNoApiKeyFoundMessage(provider: string): string
```

生成认证引导消息：
- 环境变量配置方法
- 配置文件配置方法
- OAuth 认证方法

**formatNoModelSelectedMessage**:
```typescript
formatNoModelSelectedMessage(): string
```

生成模型选择引导：
- 如何选择模型
- 可用模型列表
- 快捷键提示

## 重点阅读

### model-registry.ts（最重要）

理解模型注册核心：
1. **构造函数** - 初始化 Provider
2. **getAvailable** - 模型发现
3. **getApiKeyAndHeaders** - 认证获取
4. **registerProvider/unregisterProvider** - Provider 管理
5. **OAuth 相关方法**

### auth-storage.ts

理解认证存储：
1. **Token 存储** - 如何存储 token
2. **Token 读取** - 如何读取 token
3. **Token 刷新** - 如何刷新 token
4. **OAuth 流程** - 认证步骤

### auth-guidance.ts

理解用户引导：
1. **认证引导消息**
2. **模型选择引导**
3. **错误提示格式**

### model-resolver.ts

理解模型解析：
1. **resolveModel** - 解析逻辑
2. **Provider 查找**
3. **模型查找**

### provider-display-names.ts

理解显示名称映射。

## 关键设计模式

### 注册表模式
ModelRegistry 作为中心注册表：
- 维护 Provider 列表
- 管理认证配置
- 提供模型查询

### Provider 模式
不同 Provider 有不同认证方式：
- Anthropic：API Key
- AWS Bedrock：AWS Credentials
- 自定义：OAuth 或自定义认证

### 缓存模式
认证信息缓存：
- 减少认证检查次数
- 快速提供 headers
- 自动刷新过期 token

### 发现模式
模型发现机制：
- 动态发现可用模型
- 过滤已配置认证的模型
- 支持扩展注册

## 学习建议

### 阅读顺序

1. **model-registry.ts** - 理解核心注册逻辑
2. **auth-storage.ts** - 理解认证存储和 OAuth
3. **auth-guidance.ts** - 理解用户引导
4. **model-resolver.ts** - 理解模型解析
5. **provider-display-names.ts** - 理解显示名称

### 重点理解

1. **模型发现** - getAvailable 的完整流程
2. **认证获取** - getApiKeyAndHeaders 的多种来源
3. **OAuth 流程** - authenticateOAuth 的步骤
4. **Provider 注册** - registerProvider 的机制
5. **Token 管理** - 存储、读取、刷新

## 在 AgentSession 中的应用

### 模型选择
```typescript
// 检查认证配置
if (!modelRegistry.hasConfiguredAuth(model)) {
  throw new Error(formatNoApiKeyFoundMessage(model.provider));
}

// 获取认证
const { apiKey, headers } = await modelRegistry.getApiKeyAndHeaders(model);
```

### 模型切换
```typescript
async setModel(model: Model): Promise<void> {
  // 验证认证
  if (!modelRegistry.hasConfiguredAuth(model)) {
    throw new Error(`No API key for ${model.provider}/${model.id}`);
  }
  
  // 设置模型
  agent.state.model = model;
  
  // 持久化
  sessionManager.appendModelChange(model.provider, model.id);
  settingsManager.setDefaultModelAndProvider(model.provider, model.id);
}
```

### Provider 注册
```typescript
// 扩展注册 Provider
runner.bindCore({
  registerProvider: (name, config) => {
    modelRegistry.registerProvider(name, config);
  },
  unregisterProvider: (name) => {
    modelRegistry.unregisterProvider(name);
  }
});
```

## 实际应用场景

### 1. 模型选择
用户选择模型：
- 检查认证配置
- 显示可用模型
- 设置默认模型

### 2. API 调用
发送 API 请求：
- 获取 API key
- 构建 headers
- 发起请求

### 3. OAuth 认证
用户进行 OAuth 认证：
- 发起授权
- 接收授权码
- 存储 token

### 4. 扩展集成
扩展注册自定义 Provider：
- 提供模型列表
- 提供认证函数
- 注册到 ModelRegistry

### 5. 模型切换
用户切换模型：
- 验证认证
- 更新设置
- 持久化变更

## 扩展思考

### 安全考虑
- API key 存储安全
- Token 过期处理
- 认证信息加密

### 多 Provider 支持
- 如何支持更多 Provider
- 如何统一认证接口
- 如何处理 Provider 差异

### 性能优化
- 认证信息缓存策略
- Token 刷新时机
- 模型发现性能

### 扩展性
- 如何注册自定义认证方式
- 如何支持非标准 OAuth
- 如何集成企业认证