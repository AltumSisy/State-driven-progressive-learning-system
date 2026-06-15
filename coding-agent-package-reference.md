# @pi/coding-agent Package Reference

## 概述

`@pi/coding-agent` 是 **pi 项目的主应用包**，一个完整的 AI 驱动编码助手。它整合了 `@pi/ai`（LLM API）、`@pi/agent`（Agent 运行时）和 `@pi/tui`（终端 UI 渲染）三大核心模块。

- **定位**: 主应用 / 编码助手
- **依赖**: 
  - `@pi/ai` - 多提供商 LLM API
  - `@pi/agent` - Agent 运行时框架
  - `@pi/tui` - 终端 UI 渲染框架
- **模式**: Interactive（交互式）、Print（打印）、RPC（程序化）

---

## 核心架构

```
┌─────────────────────────────────────────────────────────┐
│                 @pi/coding-agent                        │
│                    (主应用层)                            │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │              Session 管理层                       │   │
│  │  ├─ AgentSession    # 单个会话实例                 │   │
│  │  ├─ SessionManager  # 会话管理器                   │   │
│  │  └─ AuthStorage     # 认证信息存储                 │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │              扩展系统 (Extension)                 │   │
│  │  ├─ Extension        # 扩展接口定义               │   │
│  │  ├─ ExtensionRuntime   # 扩展运行时              │   │
│  │  └─ 示例: auto-commit, custom-provider, etc.    │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │              具体工具实现                         │   │
│  │  ├─ read    # 读取文件                          │   │
│  │  ├─ write   # 写入文件                          │   │
│  │  ├─ edit    # 编辑文件                          │   │
│  │  ├─ bash    # 执行 shell 命令                   │   │
│  │  ├─ grep    # 搜索文本                          │   │
│  │  ├─ find    # 查找文件                          │   │
│  │  └─ ls      # 列出目录                          │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │              运行模式                             │   │
│  │  ├─ Interactive  # TUI 交互模式 (使用 @pi/tui)   │   │
│  │  ├─ Print       # 打印模式（非交互）              │   │
│  │  └─ RPC         # 程序化调用                     │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │              UI 组件 (基于 @pi/tui)              │   │
│  │  ├─ UserMessageComponent      # 用户消息         │   │
│  │  ├─ AssistantMessageComponent # AI 消息          │   │
│  │  ├─ ModelSelectorComponent    # 模型选择器        │   │
│  │  ├─ ToolExecutionComponent    # 工具执行展示      │   │
│  │  └─ ...                       # 其他组件          │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │              Compaction (上下文压缩)              │   │
│  │  ├─ compact()         # 压缩消息历史             │   │
│  │  └─ generateSummary()   # 生成对话摘要            │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
├─────────────────────────────────────────────────────────┤
│  @pi/tui (UI 渲染框架 - 通用终端 UI 组件库)              │
│  ├─ TUI, Component                                      │
│  ├─ Editor, Markdown, SelectList                        │
│  ├─ Input, Box, ScrollArea                              │
│  └─ ...                                                 │
├─────────────────────────────────────────────────────────┤
│  @pi/agent (Agent 运行时 - 通用 Agent 框架)             │
│  ├─ Agent, AgentLoop                                    │
│  ├─ Tool System, Event System                           │
│  └─ Session, Compaction                                 │
├─────────────────────────────────────────────────────────┤
│  @pi/ai (LLM API - 多提供商支持)                        │
│  └─ Claude, GPT, Gemini, etc.                           │
└─────────────────────────────────────────────────────────┘
```

---

## 核心导出

### Session 管理

```typescript
// AgentSession - 单个会话实例
export class AgentSession {
  constructor(options: AgentSessionOptions);
  
  // 核心属性
  id: string;
  agent: Agent;                    // 底层 @pi/agent 实例
  messages: AgentMessage[];        // 消息历史
  state: SessionState;             // 会话状态
  
  // 核心方法
  async send(message: string, attachments?: Attachment[]): Promise<void>;
  async continue(): Promise<void>;
  async compact(): Promise<void>;   // 手动触发压缩
  
  // 事件
  onMessage: EventEmitter<AgentMessage>;
  onToolExecution: EventEmitter<ToolExecutionEvent>;
}

interface AgentSessionOptions {
  model?: string;                    // LLM 模型
  systemPrompt?: string;             // 系统提示词
  workingDirectory?: string;         // 工作目录
  tools?: AgentTool[];              // 自定义工具
  extensions?: Extension[];         // 加载的扩展
  enableCompaction?: boolean;       // 启用上下文压缩
  maxContextTokens?: number;        // 最大上下文 token
}
```

```typescript
// SessionManager - 会话管理器
export class SessionManager {
  constructor(storagePath?: string);
  
  // 会话 CRUD
  async createSession(options?: CreateSessionOptions): Promise<AgentSession>;
  async loadSession(sessionId: string): Promise<AgentSession>;
  async saveSession(session: AgentSession): Promise<void>;
  async deleteSession(sessionId: string): Promise<void>;
  
  // 会话列表
  async listSessions(): Promise<SessionSummary[]>;
  
  // 会话分支
  async forkSession(sessionId: string, messageIndex?: number): Promise<AgentSession>;
  async switchBranch(sessionId: string, branchId: string): Promise<void>;
  
  // 持久化
  private storage: SessionStorage;
}
```

```typescript
// AuthStorage - 认证信息存储
export class AuthStorage {
  constructor(configPath?: string);
  
  // API Key 管理
  async setApiKey(provider: string, apiKey: string): Promise<void>;
  async getApiKey(provider: string): Promise<string | undefined>;
  async removeApiKey(provider: string): Promise<void>;
  
  // 配置管理
  async setConfig(key: string, value: any): Promise<void>;
  async getConfig(key: string): Promise<any>;
  
  // 加密存储
  private encrypt(data: string): string;
  private decrypt(data: string): string;
}
```

---

## 扩展系统 (Extension)

### Extension 接口

```typescript
export interface Extension {
  name: string;
  version: string;
  
  // 生命周期钩子
  onActivate?(runtime: ExtensionRuntime): Promise<void>;
  onDeactivate?(): Promise<void>;
  
  // 会话钩子
  onSessionStart?(session: AgentSession): Promise<void>;
  onSessionEnd?(session: AgentSession): Promise<void>;
  onBeforeToolCall?(toolCall: ToolCall, session: AgentSession): Promise<boolean | void>;
  onAfterToolCall?(result: ToolResult, session: AgentSession): Promise<void>;
  
  // 自定义工具
  tools?: AgentTool[];
  
  // 自定义组件
  components?: Record<string, Component>;
  
  // 配置选项
  config?: Record<string, any>;
}

export interface ExtensionRuntime {
  // 注册工具
  registerTool(tool: AgentTool): void;
  unregisterTool(name: string): void;
  
  // 注册命令
  registerCommand(command: string, handler: CommandHandler): void;
  
  // 访问会话
  getActiveSession(): AgentSession | undefined;
  
  // UI 操作
  showNotification(message: string): void;
  showModal(component: Component): void;
  
  // 配置
  getConfig<T>(key: string, defaultValue?: T): T;
  setConfig(key: string, value: any): void;
}
```

### 扩展示例

```typescript
// examples/extensions/auto-commit-on-exit.ts
export const extension: Extension = {
  name: "auto-commit-on-exit",
  version: "1.0.0",
  
  async onSessionEnd(session: AgentSession) {
    // 会话结束时自动提交代码
    const git = simpleGit(session.workingDirectory);
    const status = await git.status();
    
    if (status.modified.length > 0) {
      await git.add(".");
      await git.commit("Auto-commit by coding-agent");
    }
  }
};
```

```typescript
// examples/extensions/custom-provider-anthropic.ts
export const extension: Extension = {
  name: "custom-provider-anthropic",
  version: "1.0.0",
  
  async onActivate(runtime: ExtensionRuntime) {
    // 注册自定义 provider
    const apiKey = runtime.getConfig<string>("anthropicApiKey");
    
    runtime.registerTool({
      name: "anthropic_custom",
      // ...
    });
  }
};
```

```typescript
// examples/extensions/border-status-editor.ts
export const extension: Extension = {
  name: "border-status-editor",
  version: "1.0.0",
  
  components: {
    StatusBar: createStatusBarComponent()
  },
  
  async onSessionStart(session: AgentSession) {
    // 添加状态栏到编辑器
  }
};
```

---

## 工具实现 (Tools)

### 文件操作工具

```typescript
// read - 读取文件
interface ReadParams {
  path: string;           // 文件路径（相对或绝对）
  offset?: number;        // 起始行号（1-based）
  limit?: number;         // 最大读取行数
}

interface ReadResult {
  content: string;        // 文件内容
  lines: number;          // 总行数
  totalLines: number;     // 文件总行数
}

// 支持图片文件读取
// 自动检测 .jpg, .png, .gif, .webp 等格式
// 返回 base64 编码的图像数据作为 attachment
```

```typescript
// write - 写入文件
interface WriteParams {
  path: string;           // 文件路径
  content: string;        // 写入内容
}

// 特性：
// - 自动创建父目录
// - 覆盖已有文件
// - 支持流式写入大文件
```

```typescript
// edit - 编辑文件
interface EditParams {
  path: string;
  edits: Array<{
    oldText: string;      // 精确匹配的旧文本
    newText: string;      // 替换的新文本
  }>;
}

// 特性：
// - 必须精确匹配 oldText
// - 支持多行替换
// - 每个 edit 独立匹配（非增量）
// - 失败时返回错误，不修改文件
```

### 系统工具

```typescript
// bash - 执行 shell 命令
interface BashParams {
  command: string;        // 要执行的命令
  timeout?: number;       // 超时时间（秒）
  cwd?: string;          // 工作目录
}

interface BashResult {
  stdout: string;         // 标准输出
  stderr: string;         // 标准错误
  exitCode: number;       // 退出码
  truncated: boolean;     // 是否被截断
}

// 特性：
// - 默认 300 秒超时
// - 支持管道和重定向
// - 自动检测并提示危险命令
```

```typescript
// grep - 搜索文本
interface GrepParams {
  pattern: string;        // 搜索模式（正则或字符串）
  path?: string;         // 搜索路径（默认当前目录）
  include?: string;      // 包含的文件模式
  exclude?: string;      // 排除的文件模式
}

interface GrepResult {
  matches: Array<{
    file: string;
    line: number;
    column: number;
    content: string;
  }>;
  totalFiles: number;
  totalMatches: number;
}

// 特性：
// - 基于 ripgrep 实现
// - 支持正则表达式
// - 自动忽略 .gitignore 文件
```

```typescript
// find - 查找文件
interface FindParams {
  pattern: string;        // 文件名模式（支持 glob）
  path?: string;         // 搜索路径
  type?: "file" | "directory"; // 文件类型
}

// ls - 列出目录
interface LsParams {
  path: string;          // 目录路径
}

interface LsResult {
  entries: Array<{
    name: string;
    type: "file" | "directory";
    size?: number;
    modified?: Date;
  }>;
}
```

---

## 运行模式

### Interactive 模式（交互式）

```typescript
// src/modes/interactive/

export class InteractiveMode {
  constructor(options: InteractiveModeOptions);
  
  async start(): Promise<void>;
  async stop(): Promise<void>;
  
  // TUI 组件
  private tui: TUI;
  private mainLayout: Box;
  private messageList: ScrollArea;
  private inputBox: Input;
  private statusBar: Box;
}

interface InteractiveModeOptions {
  session?: AgentSession;
  theme?: Theme;
  keybindings?: Keybindings;
}

// 使用 @pi/tui 组件
import { 
  TUI, 
  Box, 
  Editor, 
  Markdown, 
  SelectList, 
  Input,
  ScrollArea 
} from "@pi/tui";
```

### Print 模式（打印）

```typescript
// src/modes/print/

export class PrintMode {
  constructor(options: PrintModeOptions);
  
  async run(input: string): Promise<void>;
  
  // 非交互式，直接输出到 stdout
  // 适合脚本调用、CI/CD 等场景
}

interface PrintModeOptions {
  session?: AgentSession;
  output?: "json" | "markdown" | "plain";
}
```

### RPC 模式（程序化）

```typescript
// src/modes/rpc/

export class RPCMode {
  constructor(options: RPCModeOptions);
  
  async start(port?: number): Promise<void>;
  async stop(): Promise<void>;
  
  // JSON-RPC 接口
  // 可以被其他程序调用
}

interface RPCModeOptions {
  session?: AgentSession;
  transport?: "stdio" | "http" | "websocket";
}

// RPC 方法
interface RPCMethods {
  "agent/send": (params: { message: string }) => Promise<void>;
  "agent/getMessages": () => Promise<AgentMessage[]>;
  "agent/clear": () => Promise<void>;
  "agent/compact": () => Promise<void>;
  
  "tools/list": () => Promise<AgentTool[]>;
  "tools/execute": (params: { name: string; params: any }) => Promise<ToolResult>;
  
  "session/save": () => Promise<void>;
  "session/load": (params: { id: string }) => Promise<void>;
}
```

---

## UI 组件详解

### 基于 @pi/tui 的组件

```typescript
// src/modes/interactive/components/

// UserMessageComponent - 用户消息展示
export class UserMessageComponent extends Component {
  constructor(message: AgentMessage);
  
  render(): VNode {
    return Box({
      children: [
        Text({ content: "You:", style: "bold" }),
        Markdown({ content: this.message.content })
      ]
    });
  }
}

// AssistantMessageComponent - AI 消息展示
export class AssistantMessageComponent extends Component {
  constructor(message: AgentMessage, options?: AssistantOptions);
  
  render(): VNode {
    return Box({
      children: [
        Text({ content: "Assistant:", style: "bold.cyan" }),
        Markdown({ content: this.message.content }),
        // 流式更新通过事件触发重新渲染
      ]
    });
  }
}

// ModelSelectorComponent - 模型选择器
export class ModelSelectorComponent extends Component {
  constructor(models: ModelInfo[], selected?: string);
  
  render(): VNode {
    return SelectList({
      items: this.models.map(m => ({ label: m.name, value: m.id })),
      selected: this.selected,
      onSelect: (value) => this.emit("select", value)
    });
  }
}

// ToolExecutionComponent - 工具执行展示
export class ToolExecutionComponent extends Component {
  constructor(toolCall: ToolCall, result?: ToolResult);
  
  render(): VNode {
    return Box({
      border: true,
      borderColor: this.result?.isError ? "red" : "green",
      children: [
        Text({ content: `Tool: ${this.toolCall.name}` }),
        Collapsible({
          title: "Parameters",
          content: JSON.stringify(this.toolCall.params, null, 2)
        }),
        this.result && Text({ 
          content: this.result.result,
          style: this.result.isError ? "red" : undefined
        })
      ]
    });
  }
}
```

---

## Compaction（上下文压缩）

### 配置选项

```typescript
interface CompactionConfig {
  // 是否启用自动压缩
  enabled: boolean;
  
  // 触发压缩的 token 阈值
  triggerTokens: number;
  
  // 压缩策略
  strategy: "summarize" | "truncate" | "hybrid";
  
  // 保留最近的消息数
  preserveRecent: number;
  
  // 摘要模型
  summaryModel?: string;
}

// 默认配置
const defaultCompactionConfig: CompactionConfig = {
  enabled: true,
  triggerTokens: 8000,
  strategy: "hybrid",
  preserveRecent: 10,
  summaryModel: "claude-3-haiku-20240307"
};
```

### 压缩过程

```
┌─────────────────────────────────────────┐
│        Compaction Process               │
├─────────────────────────────────────────┤
│                                         │
│  1. Check Token Count                   │
│     │                                   │
│     ▼                                   │
│  2. If > triggerTokens:                 │
│     │                                   │
│     ├─ Preserve recent N messages       │
│     │                                   │
│     ├─ Select old messages to compact │
│     │                                   │
│     ├─ Generate summary (LLM)          │
│     │                                   │
│     └─ Replace old messages with       │
│        summary message                  │
│                                         │
│  3. Update message history              │
│                                         │
│  4. Emit compaction event                │
│                                         │
└─────────────────────────────────────────┘
```

---

## 技能系统 (Skills)

### Skill 结构

```typescript
// skills/types.ts

export interface Skill {
  // 元数据
  name: string;
  description: string;
  version: string;
  author?: string;
  
  // 工具
  tools?: AgentTool[];
  
  // 提示词模板
  prompts?: {
    system?: string;
    context?: string;
    [key: string]: string | undefined;
  };
  
  // 配置
  config?: Record<string, any>;
  
  // 激活时执行
  onActivate?: (context: SkillContext) => Promise<void>;
}

export interface SkillContext {
  session: AgentSession;
  registerTool: (tool: AgentTool) => void;
  registerPrompt: (name: string, prompt: string) => void;
  getConfig: <T>(key: string, defaultValue?: T) => T;
}
```

### 使用技能

```typescript
// 加载技能
import { loadSkill } from "@pi/coding-agent/skills";

const gitSkill = await loadSkill("./skills/git");
await session.useSkill(gitSkill);

// 技能目录结构
skills/
├── git/
│   ├── skill.json       # 技能元数据
│   ├── index.ts         # 主入口
│   ├── tools.ts         # 工具定义
│   └── prompts.ts       # 提示词模板
│
└── docker/
    ├── skill.json
    ├── index.ts
    └── ...
```

---

## 配置文件

### 全局配置

```typescript
// ~/.config/pi/config.json

interface Config {
  // LLM 配置
  llm: {
    defaultModel: string;
    providers: Record<string, ProviderConfig>;
  };
  
  // Agent 配置
  agent: {
    maxContextTokens: number;
    enableCompaction: boolean;
    compactionStrategy: "summarize" | "truncate" | "hybrid";
  };
  
  // UI 配置
  ui: {
    theme: "dark" | "light";
    editor: "vim" | "emacs" | "nano";
    keybindings: Keybindings;
  };
  
  // 扩展配置
  extensions: {
    enabled: string[];
    config: Record<string, any>;
  };
  
  // 工具配置
  tools: {
    bash: {
      timeout: number;
      allowedCommands: string[];
      blockedCommands: string[];
    };
  };
}
```

### 会话配置

```typescript
// .pi/session.json (项目级)

interface SessionConfig {
  // 工作目录
  workingDirectory: string;
  
  // 忽略文件
  ignore: string[];
  
  // 系统提示词
  systemPrompt: string;
  
  // 启用的技能
  skills: string[];
  
  // 启用的扩展
  extensions: string[];
  
  // 自定义工具
  customTools: string[];
}
```

---

## CLI 使用

### 命令行参数

```bash
# 交互模式
pi                          # 启动交互模式
pi --interactive            # 同上
pi -i

# 打印模式
pi "解释这段代码"            # 单次查询
pi -p "解释这段代码"         # 显式指定打印模式

echo "const x = 1;" | pi    # 从 stdin 读取

# RPC 模式
pi --rpc                    # 启动 RPC 服务器
pi --rpc-port 3000          # 指定端口

# 会话管理
pi --list-sessions          # 列出会话
pi --resume <session-id>    # 恢复会话
pi --new-session            # 创建新会话

# 模型选择
pi --model claude-3-opus    # 指定模型
pi --list-models            # 列出可用模型

# 其他选项
pi --working-dir ./project  # 指定工作目录
pi --skill ./skills/git     # 加载技能
pi --extension ./exts/my-ext # 加载扩展
pi --verbose                # 详细输出
pi --version                # 显示版本
pi --help                   # 显示帮助
```

---

## 与 agent 包的关系

```
┌─────────────────────────────────────────┐
│        @pi/coding-agent                  │
│  (本包 - 主应用层)                        │
├─────────────────────────────────────────┤
│  ├─ AgentSession    # Session + Agent   │
│  ├─ SessionManager  # 高级会话管理       │
│