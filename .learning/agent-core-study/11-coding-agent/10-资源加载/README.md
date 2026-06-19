# 资源加载

## 学习目标

理解 Coding Agent 的资源发现、加载和管理机制。

## 核心源文件

- `resource-loader.ts` - 资源加载器（核心）
- `source-info.ts` - 来源信息追踪

## 关键概念

### 1. ResourceLoader 核心类

**职责**:
- 发现和加载各种资源
- 管理资源来源
- 支持扩展注入资源
- 资源刷新和更新

**管理的资源类型**:
- Skills（技能）
- Prompts（提示词模板）
- Context Files（上下文文件）
- System Prompt（系统提示词）
- Extensions（扩展）
- Themes（主题）

**核心方法**:
```typescript
class ResourceLoader {
  constructor(cwd: string);
  
  // 技能
  getSkills(): { skills: Skill[] };
  
  // 提示词模板
  getPrompts(): { prompts: PromptTemplate[] };
  
  // 上下文文件
  getAgentsFiles(): { agentsFiles: ContextFile[] };
  
  // 系统提示词
  getSystemPrompt(): string | undefined;
  getAppendSystemPrompt(): string[];
  
  // 扩展
  getExtensions(): LoadExtensionsResult;
  
  // 主题
  getThemes(): Theme[];
  
  // 扩展注入
  extendResources(extensionPaths: ResourceExtensionPaths): void;
  
  // 重载
  async reload(): Promise<void>;
}
```

### 2. 资源发现机制

**发现流程**:
1. 扫描项目目录（`.claude/`）
2. 扫描用户目录（`~/.claude/`）
3. 查找特定文件名
4. 解析文件内容
5. 构建资源对象

**扫描目录**:
- `.claude/skills/` - 技能目录
- `.claude/prompts/` - 提示词模板目录
- `.claude/extensions/` - 扩展目录
- `.claude/themes/` - 主题目录
- 项目根目录 - 上下文文件（AGENTS.md、CLAUDE.md）

### 3. 技能发现（Skills）

**Skill 结构**:
```typescript
interface Skill {
  name: string;              // 技能名称
  description: string;       // 技能描述
  filePath: string;          // 文件路径
  baseDir: string;           // 基础目录
  sourceInfo: SourceInfo;    // 来源信息
}
```

**发现流程**:
1. 扫描 `.claude/skills/` 目录
2. 查找 `.md` 文件
3. 解析 frontmatter：
   ```markdown
   ---
   name: code-review
   description: Review code for bugs and improvements
   ---
   
   [技能内容]
   ```
4. 提取 name 和 description
5. 构建 Skill 对象

**来源追踪**:
- SourceInfo 记录来源：
  - `source: 'project'` - 项目技能
  - `source: 'user'` - 用户全局技能
  - `source: 'extension:xxx'` - 扩展技能

### 4. 提示词模板发现（Prompts）

**PromptTemplate 结构**:
```typescript
interface PromptTemplate {
  name: string;              // 模板名称（调用名）
  description: string;       // 模板描述
  filePath: string;          // 文件路径
  baseDir: string;           // 基础目录
  sourceInfo: SourceInfo;    // 来源信息
}
```

**发现流程**:
1. 扫描 `.claude/prompts/` 目录
2. 查找 `.md` 文件
3. 解析 frontmatter：
   ```markdown
   ---
   name: test
   description: Generate tests for code
   ---
   
   [模板内容]
   ```
4. 提取 name 和 description
5. 构建 PromptTemplate 对象

### 5. 上下文文件发现（Context Files）

**ContextFile 结构**:
```typescript
interface ContextFile {
  path: string;              // 文件路径
  content: string;           // 文件内容
  sourceInfo: SourceInfo;    // 来源信息
}
```

**发现文件**:
- `AGENTS.md` - 项目上下文说明
- `CLAUDE.md` - Claude Code 配置文件
- 其他配置文件

**加载流程**:
1. 查找文件路径
2. 读取文件内容
3. 构建 ContextFile 对象
4. 添加到系统提示词

### 6. 系统提示词加载

**两种类型**:
- **customSystemPrompt** - 自定义完整提示词
  - 文件：`.claude/system-prompt.md`
  - 覆盖默认提示词
  
- **appendSystemPrompt** - 追加提示词
  - 文件：`.claude/append-system-prompt.md`
  - 追加到默认提示词末尾

**加载方法**:
```typescript
getSystemPrompt(): string | undefined
getAppendSystemPrompt(): string[]
```

### 7. 扩展发现（Extensions）

**Extension 结构**:
```typescript
interface Extension {
  path: string;              // 扩展路径
  factory: ExtensionFactory; // 工厂函数
  sourceInfo: SourceInfo;    // 来源信息
  flags?: ExtensionFlag[];   // 扩展标记
}
```

**发现流程**:
1. 扫描 `.claude/extensions/` 目录
2. 查找 `.ts` 或 `.js` 文件
3. 加载模块
4. 提取 factory 函数
5. 构建 Extension 对象

**扩展标记**:
- `builtin` - 内置扩展
- `user` - 用户扩展
- `project` - 项目扩展

### 8. 主题发现（Themes）

**Theme 结构**:
```typescript
interface Theme {
  name: string;              // 主题名称
  path: string;              // 主题文件路径
  sourceInfo: SourceInfo;    // 来源信息
}
```

**发现流程**:
1. 扫描 `.claude/themes/` 目录
2. 查找主题文件
3. 构建 Theme 对象
4. 提供主题选择

### 9. 来源信息追踪（source-info.ts）

**SourceInfo 接口**:
```typescript
interface SourceInfo {
  source: string;            // 来源类型
  path?: string;             // 来源路径
  scope?: 'project' | 'user' | 'temporary';  // 作用域
  origin?: 'top-level' | 'nested';  // 来源层级
  baseDir?: string;          // 基础目录
}
```

**来源类型**:
- `project` - 项目资源
- `user` - 用户全局资源
- `extension:xxx` - 扩展资源
- `builtin` - 内置资源
- `sdk` - SDK 注册

**作用域**:
- `project` - 项目级别
- `user` - 用户全局
- `temporary` - 临时（扩展注入）

**用途**:
- 追踪资源来源
- 显示资源信息
- 管理资源优先级
- 支持资源过滤

### 10. 扩展注入资源

**extendResources 方法**:
```typescript
extendResources(extensionPaths: ResourceExtensionPaths): void
```

**ResourceExtensionPaths**:
```typescript
interface ResourceExtensionPaths {
  skillPaths: Array<{ path, metadata }>;
  promptPaths: Array<{ path, metadata }>;
  themePaths: Array<{ path, metadata }>;
}
```

**注入流程**:
1. 扩展通过 `resources_discover` 事件提供路径
2. ResourceLoader 接收路径
3. 加载资源内容
4. 构建资源对象
5. 添加到资源列表（scope: 'temporary'）

### 11. 资源重载

**reload 方法**:
```typescript
async reload(): Promise<void>
```

**重载流程**:
1. 清空当前资源
2. 重新扫描目录
3. 重新加载文件
4. 重新解析内容
5. 重新构建资源对象

**触发时机**:
- 用户手动重载（`/reload`）
- 设置变更
- 扩展重载

## 重点阅读

### resource-loader.ts（最重要）

理解资源加载核心：
1. **构造函数** - 初始化和首次加载
2. **getSkills** - 技能发现和加载
3. **getPrompts** - 模板发现和加载
4. **getAgentsFiles** - 上下文文件加载
5. **getSystemPrompt** - 系统提示词加载
6. **getExtensions** - 扩展发现
7. **extendResources** - 扩展注入
8. **reload** - 重载机制

### source-info.ts

理解来源信息：
1. **SourceInfo 接口** - 来源信息结构
2. **createSyntheticSourceInfo** - 创建合成来源
3. **来源类型** - 各种来源标记

## 关键设计模式

### 发现模式
自动发现资源：
- 扫描目录
- 查找文件
- 解析内容
- 构建对象

### 来源追踪模式
追踪资源来源：
- SourceInfo 记录来源
- 支持来源过滤
- 显示来源信息

### 分层加载模式
多来源资源加载：
- 项目资源
- 用户资源
- 扩展资源
- 按优先级合并

### 前端matter 解析模式
解析文件 frontmatter：
- 提取元数据
- 提取内容
- 构建资源对象

### 动态注入模式
扩展动态注入资源：
- 扩展提供路径
- ResourceLoader 加载
- 临时作用域

## 学习建议

### 阅读顺序

1. **source-info.ts** - 理解来源信息
2. **resource-loader.ts** - 理解资源加载核心

### 重点理解

1. **资源类型** - Skills、Prompts、ContextFiles 等
2. **发现机制** - 如何扫描和发现资源
3. **加载流程** - 如何解析和加载资源
4. **来源追踪** - SourceInfo 的作用
5. **扩展注入** - 扩展如何注入资源
6. **重载机制** - 如何刷新资源

## 在 AgentSession 中的应用

### 获取资源
```typescript
// 获取技能
const skills = this._resourceLoader.getSkills().skills;

// 获取提示词模板
const prompts = this.promptTemplates;

// 获取上下文文件
const contextFiles = this._resourceLoader.getAgentsFiles().agentsFiles;

// 获取系统提示词
const systemPrompt = this._resourceLoader.getSystemPrompt();
const appendPrompt = this._resourceLoader.getAppendSystemPrompt();
```

### 构建系统提示词
```typescript
buildSystemPrompt({
  cwd: this._cwd,
  skills: loadedSkills,
  contextFiles: loadedContextFiles,
  customPrompt: loaderSystemPrompt,
  appendSystemPrompt,
  ...
});
```

### 扩展注入
```typescript
async extendResourcesFromExtensions(reason: 'startup' | 'reload'): Promise<void> {
  const { skillPaths, promptPaths, themePaths } = 
    await this._extensionRunner.emitResourcesDiscover(this._cwd, reason);
  
  const extensionPaths: ResourceExtensionPaths = {
    skillPaths: this.buildExtensionResourcePaths(skillPaths),
    promptPaths: this.buildExtensionResourcePaths(promptPaths),
    themePaths: this.buildExtensionResourcePaths(themePaths),
  };
  
  this._resourceLoader.extendResources(extensionPaths);
}
```

### 重载
```typescript
async reload(): Promise<void> {
  await this.settingsManager.reload();
  await this._resourceLoader.reload();
  
  // 重建运行时
  this._buildRuntime(...);
  
  // 重新注入扩展资源
  await this.extendResourcesFromExtensions("reload");
}
```

## 实际应用场景

### 1. 项目技能库
项目创建技能目录：
- `.claude/skills/code-review.md`
- `.claude/skills/test-generation.md`
- 团队共享技能
- 自动发现

### 2. 用户提示词模板
用户创建模板目录：
- `~/.claude/prompts/explain.md`
- `~/.claude/prompts/refactor.md`
- 个人常用模板
- 全局可用

### 3. 项目上下文文件
项目添加 AGENTS.md：
- 项目架构说明
- 技术栈介绍
- 团队规范
- 自动加载

### 4. 扩展提供资源
扩展通过事件提供资源：
- 扩展技能
- 扩展模板
- 扩展主题
- 动态注入

### 5. 动态重载
用户修改资源后重载：
- 添加新技能
- 更新模板
- 修改上下文
- 立即生效

## 扩展思考

### 资源缓存
- 如何缓存资源内容
- 如何检测资源变更
- 如何优化加载性能

### 资源优先级
- 多来源资源冲突
- 如何决定优先级
- 如何合并资源

### 资源验证
- 如何验证资源格式
- 如何处理无效资源
- 如何提示错误

### 资源管理
- 如何组织资源目录
- 如何维护资源库
- 如何清理废弃资源