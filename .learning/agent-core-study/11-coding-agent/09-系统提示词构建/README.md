# 系统提示词构建

## 学习目标

理解 Coding Agent 的系统提示词构建机制，包括技能、模板和系统提示词组装。

## 核心源文件

- `system-prompt.ts` - 系统提示词构建（核心）
- `prompt-templates.ts` - 提示词模板
- `skills.ts` - 技能系统
- `slash-commands.ts` - 斜杠命令信息

## 关键概念

### 1. 系统提示词结构

**整体结构**:
```
[基础系统提示词]
  +
[工具描述]
  +
[技能描述]
  +
[上下文文件]
  +
[自定义提示词]
  +
[追加提示词]
  +
[提示词指南]
```

### 2. buildSystemPrompt 函数

**核心函数**（system-prompt.ts）:
```typescript
function buildSystemPrompt(options: BuildSystemPromptOptions): string
```

**BuildSystemPromptOptions**:
```typescript
interface BuildSystemPromptOptions {
  cwd: string;                        // 工作目录
  
  skills?: Skill[];                   // 技能列表
  contextFiles?: ContextFile[];       // 上下文文件
  
  customPrompt?: string;              // 自定义系统提示词
  appendSystemPrompt?: string;        // 追加系统提示词
  
  selectedTools?: string[];           // 选中的工具
  toolSnippets?: Record<string, string>;  // 工具提示词片段
  promptGuidelines?: string[];        // 提示词指南
}
```

### 3. 提示词模板（prompt-templates.ts）

**PromptTemplate 接口**:
```typescript
interface PromptTemplate {
  name: string;              // 模板名称（如 /test）
  description: string;       // 模板描述
  filePath: string;          // 模板文件路径
  baseDir: string;           // 基础目录（相对路径解析）
  sourceInfo: SourceInfo;    // 来源信息
}
```

**模板发现**:
ResourceLoader 发现模板：
- 扫描 `.claude/prompts/` 目录
- 扫描扩展提供的模板
- 解析 frontmatter
- 构建 PromptTemplate 数组

**模板展开**:
```typescript
expandPromptTemplate(text: string, templates: PromptTemplate[]): string
```

展开流程：
1. 检测模板语法（如 `/test`）
2. 查找对应模板
3. 读取模板文件
4. 替换 frontmatter
5. 插入用户参数

**模板语法**:
```
/template_name [args]
```

例如：
```
/test --focus security
```

展开为：
```
<template name="test" location=".claude/prompts/test.md">
[模板内容]
</template>

[args]
```

### 4. 技能系统（skills.ts）

**Skill 接口**:
```typescript
interface Skill {
  name: string;              // 技能名称（如 skill:code-review）
  description: string;       // 技能描述
  filePath: string;          // 技能文件路径
  baseDir: string;           // 基础目录
  sourceInfo: SourceInfo;    // 来源信息
}
```

**技能发现**:
ResourceLoader 发现技能：
- 扫描 `.claude/skills/` 目录
- 扫描扩展提供的技能
- 解析 frontmatter
- 构建 Skill 数组

**技能调用语法**:
```
/skill:skill_name [args]
```

例如：
```
/skill:code-review --file src/auth.ts
```

**技能展开**:
AgentSession 的 `_expandSkillCommand()`:
1. 检测技能语法
2. 查找技能文件
3. 读取技能内容
4. 移除 frontmatter
5. 包装为 skill block：
```xml
<skill name="skill_name" location="path">
References are relative to baseDir.

[技能内容]
</skill>

[args]
```

### 5. 上下文文件

**上下文文件类型**:
- AGENTS.md - 项目上下文说明
- CLAUDE.md - Claude Code 配置文件
- 其他 markdown 文件

**加载机制**:
ResourceLoader 加载上下文文件：
- 扫描项目根目录
- 查找 AGENTS.md、CLAUDE.md
- 读取文件内容
- 添加到系统提示词

**在系统提示词中的位置**:
```
[上下文文件内容]
```

作为项目特定信息注入。

### 6. 自定义系统提示词

**customPrompt**:
用户自定义完整系统提示词：
- 来自 ResourceLoader
- 覆盖默认提示词
- 提供完全控制

**appendSystemPrompt**:
追加到系统提示词末尾：
- 来自 ResourceLoader
- 保留默认提示词
- 添加额外指令

### 7. 工具提示词片段

**toolSnippets**:
每个工具可提供提示词片段：
```typescript
toolSnippets: {
  'bash': 'Use bash for shell commands...',
  'edit': 'Use edit for file modifications...'
}
```

**在系统提示词中**:
```
[工具名称]: [提示词片段]
```

### 8. 提示词指南

**promptGuidelines**:
工具可提供使用指南：
```typescript
promptGuidelines: [
  'Always verify file paths before editing',
  'Use absolute paths for file operations',
  ...
]
```

**在系统提示词中**:
```
Guidelines:
- [指南 1]
- [指南 2]
```

### 9. Slash 命令信息（slash-commands.ts）

**SlashCommandInfo 接口**:
```typescript
interface SlashCommandInfo {
  name: string;              // 命令名称
  description: string;       // 命令描述
  source: 'extension' | 'prompt' | 'skill';  // 来源类型
  sourceInfo: SourceInfo;    // 来源信息
}
```

**命令类型**:
- Extension 命令 - 扩展注册的命令
- Prompt 模板 - 提示词模板
- Skill - 技能

**命令发现**:
AgentSession 的 `getCommands()`:
1. 收集扩展命令
2. 收集提示词模板
3. 收集技能
4. 返回 SlashCommandInfo 数组

## 重点阅读

### system-prompt.ts（最重要）

理解系统提示词构建：
1. **buildSystemPrompt** - 核心构建函数
2. **BuildSystemPromptOptions** - 构建选项
3. **各部分组装** - 技能、工具、上下文

### prompt-templates.ts

理解提示词模板：
1. **PromptTemplate 接口** - 模板结构
2. **expandPromptTemplate** - 模板展开
3. **模板发现** - ResourceLoader 发现模板

### skills.ts

理解技能系统：
1. **Skill 接口** - 技能结构
2. **技能发现** - ResourceLoader 发现技能
3. **技能使用** - AgentSession 展开技能

### slash-commands.ts

理解斜杠命令信息：
1. **SlashCommandInfo** - 命令信息
2. **命令类型** - extension/prompt/skill
3. **命令发现** - 收集所有命令

## 关键设计模式

### 组合模式
系统提示词由多个部分组合：
- 基础提示词
- 工具描述
- 技能内容
- 上下文文件
- 自定义/追加

### 模板模式
提示词模板和技能：
- 定义模板结构
- 参数化展开
- 统一调用语法

### 发现模式
自动发现各种资源：
- 模板发现
- 技能发现
- 上下文文件发现

### 优先级模式
多个提示词源的优先级：
- customPrompt 覆盖默认
- appendSystemPrompt 追加末尾
- 工具片段独立注入

## 学习建议

### 阅读顺序

1. **system-prompt.ts** - 理解系统提示词构建核心
2. **prompt-templates.ts** - 理解模板系统
3. **skills.ts** - 理解技能系统
4. **slash-commands.ts** - 理解命令信息

### 重点理解

1. **提示词结构** - 各部分的组装顺序
2. **模板展开** - 模板如何展开为实际内容
3. **技能调用** - 技能如何包装和注入
4. **上下文注入** - 项目上下文如何添加
5. **工具提示词** - 工具描述和指南如何注入

## 在 AgentSession 中的应用

### 系统提示词构建
```typescript
// 构建系统提示词
this._baseSystemPrompt = this._rebuildSystemPrompt(validToolNames);

function _rebuildSystemPrompt(toolNames: string[]): string {
  const toolSnippets = ...;
  const promptGuidelines = ...;
  
  const loaderSystemPrompt = this._resourceLoader.getSystemPrompt();
  const appendSystemPrompt = this._resourceLoader.getAppendSystemPrompt();
  const loadedSkills = this._resourceLoader.getSkills().skills;
  const loadedContextFiles = this._resourceLoader.getAgentsFiles().agentsFiles;
  
  return buildSystemPrompt({
    cwd: this._cwd,
    skills: loadedSkills,
    contextFiles: loadedContextFiles,
    customPrompt: loaderSystemPrompt,
    appendSystemPrompt,
    selectedTools: toolNames,
    toolSnippets,
    promptGuidelines
  });
}
```

### 模板展开
```typescript
async prompt(text: string, options?: PromptOptions): Promise<void> {
  // 展开模板
  let expandedText = text;
  if (expandPromptTemplates) {
    expandedText = expandPromptTemplate(expandedText, [...this.promptTemplates]);
  }
  
  // 展开技能
  expandedText = this._expandSkillCommand(expandedText);
}
```

### 技能展开
```typescript
function _expandSkillCommand(text: string): string {
  if (!text.startsWith('/skill:')) return text;
  
  const skillName = ...;
  const skill = this._resourceLoader.getSkills().skills.find(s => s.name === skillName);
  
  const content = readFileSync(skill.filePath, 'utf-8');
  const body = stripFrontmatter(content).trim();
  
  return `<skill name="${skill.name}" location="${skill.filePath}">
References are relative to ${skill.baseDir}.

${body}
</skill>`;
}
```

### 命令发现
```typescript
function getCommands(): SlashCommandInfo[] {
  const extensionCommands = runner.getRegisteredCommands().map(...);
  const templates = this.promptTemplates.map(...);
  const skills = this._resourceLoader.getSkills().skills.map(...);
  
  return [...extensionCommands, ...templates, ...skills];
}
```

## 实际应用场景

### 1. 项目定制提示词
项目添加 AGENTS.md：
- 项目架构说明
- 技术栈介绍
- 特殊规则
- 自动注入到系统提示词

### 2. 团队共享技能
团队创建技能文件：
- 代码审查技能
- 测试生成技能
- 文档编写技能
- 团队共享调用

### 3. 个人提示词模板
用户创建模板：
- 常用任务模板
- 参数化模板
- 快速调用
- 提升效率

### 4. 工具定制指南
工具提供提示词指南：
- 工具使用最佳实践
- 常见错误避免
- 效率提升技巧

### 5. 扩展注入资源
扩展提供技能/模板：
- 注册技能
- 注册模板
- 自动发现
- 用户可用

## 扩展思考

### 提示词优化
- 如何优化提示词结构
- 如何减少 token 消耗
- 如何提高提示词效果

### 模板设计
- 如何设计好的模板
- 如何参数化模板
- 如何组织模板库

### 技能设计
- 如何设计好的技能
- 如何组织技能库
- 如何维护技能

### 上下文管理
- 如何管理项目上下文
- 如何更新上下文文件
- 如何避免冗余