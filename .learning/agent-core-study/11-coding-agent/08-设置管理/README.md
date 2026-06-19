# 设置管理

## 学习目标

理解 Coding Agent 的配置持久化机制和设置管理。

## 核心源文件

- `settings-manager.ts` - 设置管理器（核心）
- `resolve-config-value.ts` - 配置值解析
- `defaults.ts` - 默认值定义

## 关键概念

### 1. SettingsManager 核心类

**职责**:
- 读取和写入设置
- 管理全局和项目设置
- 提供默认值
- 设置持久化

**设置文件位置**:
- 全局设置：`~/.claude/settings.json`
- 项目设置：`.claude/settings.json`
- 本地设置：`.claude/settings.local.json`

**核心方法**:
```typescript
class SettingsManager {
  // 初始化
  constructor(cwd: string);
  
  // 加载
  async reload(): Promise<void>;
  load(): void;
  
  // 模型相关
  getDefaultModelAndProvider(): { provider, modelId } | undefined;
  setDefaultModelAndProvider(provider, modelId): void;
  
  // 思维级别
  getDefaultThinkingLevel(): ThinkingLevel | undefined;
  setDefaultThinkingLevel(level): void;
  
  // 压缩设置
  getCompactionSettings(): CompactionSettings;
  setCompactionEnabled(enabled): void;
  getCompactionEnabled(): boolean;
  
  // 重试设置
  getRetrySettings(): RetrySettings;
  setRetryEnabled(enabled): void;
  getRetryEnabled(): boolean;
  
  // Steering/FollowUp 模式
  getSteeringMode(): 'all' | 'one-at-a-time';
  setSteeringMode(mode): void;
  getFollowUpMode(): 'all' | 'one-at-a-time';
  setFollowUpMode(mode): void;
  
  // Shell 设置
  getShellCommandPrefix(): string | undefined;
  setShellCommandPrefix(prefix): void;
  getShellPath(): string | undefined;
  
  // 图片设置
  getImageAutoResize(): boolean;
  
  // 钩子设置
  getHooks(): HooksConfig;
}
```

### 2. 设置优先级

**优先级顺序**（从高到低）:
1. 项目本地设置（`settings.local.json`）
2. 项目设置（`settings.json`）
3. 全局设置（`~/.claude/settings.json`）
4. 默认值（`defaults.ts`）

**合并策略**:
- 深度合并对象
- 数组直接覆盖
- undefined 使用下层值

### 3. 配置结构

**Settings 接口**:
```typescript
interface Settings {
  // 模型配置
  defaultModel?: {
    provider: string;
    modelId: string;
  };
  
  // 思维级别
  defaultThinkingLevel?: ThinkingLevel;
  
  // 压缩配置
  compaction?: {
    enabled: boolean;
    threshold: number;  // 百分比，如 80
  };
  
  // 重试配置
  retry?: {
    enabled: boolean;
    maxRetries: number;
    baseDelayMs: number;
  };
  
  // Steering/FollowUp 模式
  steeringMode?: 'all' | 'one-at-a-time';
  followUpMode?: 'all' | 'one-at-a-time';
  
  // Shell 配置
  shell?: {
    commandPrefix?: string;
    path?: string;
  };
  
  // 图片配置
  image?: {
    autoResize: boolean;
    maxWidth?: number;
    maxHeight?: number;
  };
  
  // 钩子配置
  hooks?: HooksConfig;
  
  // 权限配置
  allowedTools?: string[];
  permissions?: PermissionConfig;
  
  // 其他
  theme?: string;
  keybindings?: KeybindingsConfig;
}
```

### 4. 压缩设置

**CompactionSettings**:
```typescript
interface CompactionSettings {
  enabled: boolean;      // 是否启用自动压缩
  threshold: number;     // 触发阈值（百分比）
}
```

**默认值**（defaults.ts）:
```typescript
const DEFAULT_COMPACTION_SETTINGS = {
  enabled: true,
  threshold: 80  // 80% context window
};
```

### 5. 重试设置

**RetrySettings**:
```typescript
interface RetrySettings {
  enabled: boolean;
  maxRetries: number;
  baseDelayMs: number;
}
```

**默认值**:
```typescript
const DEFAULT_RETRY_SETTINGS = {
  enabled: true,
  maxRetries: 3,
  baseDelayMs: 1000  // 1秒
};
```

**重试策略**:
- 指数退避：delay = baseDelayMs * 2^(attempt-1)
- 最大重试次数：maxRetries
- 可独立启用/禁用

### 6. Steering/FollowUp 模式

**两种模式**:
- `'all'` - 所有消息一次性处理
- `'one-at-a-time'` - 一次处理一条消息

**Steering 模式**:
- 用户中断当前执行
- 立即插入新消息

**FollowUp 模式**:
- 等待当前执行完成
- 按顺序处理后续消息

### 7. Shell 配置

**commandPrefix**:
- Shell 启动时执行的前缀命令
- 例如：`shopt -s expand_aliases`（支持 alias）

**shellPath**:
- Shell 程序路径
- 默认：系统默认 shell

### 8. 图片设置

**autoResize**:
- 自动压缩图片尺寸
- 减少 token 消耗
- 保持图片质量

**maxWidth/maxHeight**:
- 最大宽度和高度
- 超出时自动缩放

### 9. 钩子配置（HooksConfig）

**钩子类型**:
```typescript
interface HooksConfig {
  // 生命周期钩子
  SessionStart?: HookConfig;
  SessionEnd?: HookConfig;
  
  // 工具钩子
  PreToolUse?: HookConfig;
  PostToolUse?: HookConfig;
  
  // 消息钩子
  PrePrompt?: HookConfig;
  PostResponse?: HookConfig;
  
  // 其他钩子
  Notification?: HookConfig;
  Stop?: HookConfig;
}
```

**HookConfig**:
```typescript
interface HookConfig {
  type: 'command' | 'script';
  command?: string;   // Shell 命令
  path?: string;      // 脚本路径
  timeout?: number;   // 超时时间
}
```

### 10. 配置值解析（resolve-config-value.ts）

**resolveConfigValue 函数**:
```typescript
resolveConfigValue<T>(configs: ConfigValue<T>[]): T | undefined
```

**解析流程**:
1. 遍历配置值数组（按优先级）
2. 找到第一个非 undefined 值
3. 返回该值或 undefined

**应用场景**:
- 合并多个配置源
- 实现优先级逻辑
- 提供统一配置读取

## 重点阅读

### settings-manager.ts（最重要）

理解设置管理核心：
1. **构造函数** - 初始化和加载
2. **reload/load** - 重新加载设置
3. **getter 方法** - 各种设置读取
4. **setter 方法** - 各种设置写入
5. **持久化** - 如何保存设置

### defaults.ts

理解默认值定义：
1. **DEFAULT_COMPACTION_SETTINGS**
2. **DEFAULT_RETRY_SETTINGS**
3. **DEFAULT_THINKING_LEVEL**
4. 其他默认值

### resolve-config-value.ts

理解配置值解析：
1. **resolveConfigValue** - 解析逻辑
2. **优先级处理** - 多源合并
3. **类型安全** - TypeScript 类型

## 关键设计模式

### 分层配置模式
三层配置源：
- 全局配置（用户偏好）
- 项目配置（项目特性）
- 本地配置（临时设置）

### 合并模式
配置合并策略：
- 深度合并对象
- 优先级覆盖
- 保留非 undefined 值

### 默认值模式
提供合理默认值：
- 新用户无需配置
- 配置可选覆盖
- 保证核心功能

### 懒加载模式
设置懒加载：
- 按需读取配置
- 缓存配置值
- 支持动态更新

## 学习建议

### 阅读顺序

1. **defaults.ts** - 先理解默认值
2. **settings-manager.ts** - 理解设置管理
3. **resolve-config-value.ts** - 理解配置解析

### 重点理解

1. **配置优先级** - 三层配置如何合并
2. **持久化机制** - 如何保存设置
3. **默认值设计** - 合理默认值的选择
4. **类型安全** - TypeScript 类型定义
5. **配置验证** - 如何验证配置合法性

## 在 AgentSession 中的应用

### 模型管理
```typescript
// 设置模型
settingsManager.setDefaultModelAndProvider(model.provider, model.id);

// 获取默认模型
const defaultModel = settingsManager.getDefaultModelAndProvider();
```

### 思维级别管理
```typescript
// 设置思维级别
settingsManager.setDefaultThinkingLevel(level);

// 获取默认思维级别
const defaultLevel = settingsManager.getDefaultThinkingLevel();
```

### 压缩管理
```typescript
// 获取压缩设置
const compactionSettings = settingsManager.getCompactionSettings();

// 设置启用状态
settingsManager.setCompactionEnabled(enabled);
```

### 重试管理
```typescript
// 获取重试设置
const retrySettings = settingsManager.getRetrySettings();

// 设置启用状态
settingsManager.setRetryEnabled(enabled);
```

### Steering/FollowUp 模式
```typescript
// 设置 Steering 模式
setSteeringMode(mode: 'all' | 'one-at-a-time') {
  agent.steeringMode = mode;
  settingsManager.setSteeringMode(mode);
}

// 设置 FollowUp 模式
setFollowUpMode(mode: 'all' | 'one-at-a-time') {
  agent.followUpMode = mode;
  settingsManager.setFollowUpMode(mode);
}
```

### Shell 配置
```typescript
// 获取 shell 配置
const prefix = settingsManager.getShellCommandPrefix();
const shellPath = settingsManager.getShellPath();

// 创建 bash 工具
createBashTool(cwd, {
  commandPrefix: prefix,
  shellPath: shellPath
});
```

## 实际应用场景

### 1. 用户偏好设置
用户配置默认模型、思维级别等：
- 全局设置文件
- 跨项目共享
- 一键恢复

### 2. 项目特定配置
项目配置特殊设置：
- 项目设置文件
- 团队共享配置
- 项目特定工具限制

### 3. 临时配置
临时修改设置：
- 本地设置文件
- 不提交到 git
- 临时调试配置

### 4. 钩子配置
配置自动化钩子：
- SessionStart 钩子
- PreToolUse 钩子
- PostResponse 钩子

### 5. 权限配置
配置工具权限：
- allowedTools 白名单
- 权限提示设置
- 安全限制

## 扩展思考

### 配置验证
- 如何验证配置合法性
- 如何处理非法配置
- 如何提供配置错误提示

### 配置迁移
- 如何处理版本升级
- 如何迁移旧配置
- 如何保持向后兼容

### 配置加密
- 如何加密敏感配置
- 如何存储 API key
- 如何保护用户隐私

### 配置同步
- 如何同步多设备配置
- 如何共享团队配置
- 如何管理配置冲突