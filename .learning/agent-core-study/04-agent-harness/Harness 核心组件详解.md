# Harness 核心组件详解

> 本文档详细讲解 Agent Harness 的核心组件，包括 AgentHarness 主类、Messages 消息系统、Skills 技能系统、Prompt Templates 提示模板和 ExecutionEnv 环境抽象。

## 一、Harness 架构总览

### 1.1 组件关系图

```
┌─────────────────────────────────────────────────────────────┐
│                      AgentHarness                            │
│  (主入口：协调所有组件)                                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐              │
│  │ Session  │  │Messages  │  │System Prompt │              │
│  │(会话管理)│  │(消息转换)│  │(提示构建)    │              │
│  └──────────┘  └──────────┘  └──────────────┘              │
│                                                             │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────┐         │
│  │ Skills   │  │Prompt Templates│  │ExecutionEnv  │         │
│  │(技能系统)│  │(提示模板)     │  │(环境抽象)    │         │
│  └──────────┘  └──────────────┘  └───────────────┘         │
│                                                             │
│  ┌──────────────┐  ┌──────────────────────────────┐        │
│  │ Compaction   │  │ Branch Summarization         │        │
│  │ (上下文压缩) │  │ (分支摘要)                   │        │
│  └──────────────┘  └──────────────────────────────┘        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 组件职责

| 组件 | 职责 | 核心文件 |
|------|------|----------|
| **AgentHarness** | 主入口类，协调所有组件，管理对话流程 | `agent-harness.ts` |
| **Session** | 会话管理，Entry 树结构，持久化 | `session/session.ts` |
| **Messages** | 消息创建、转换、序列化 | `messages.ts` |
| **System Prompt** | 系统提示构建，Skills 格式化 | `system-prompt.ts` |
| **Skills** | 技能加载、验证、调用格式化 | `skills.ts` |
| **Prompt Templates** | 提示模板加载、参数替换 | `prompt-templates.ts` |
| **ExecutionEnv** | 环境抽象（文件、命令执行） | `env/nodejs.ts` |
| **Compaction** | 上下文压缩 | `compaction/compaction.ts` |
| **Branch Summarization** | 分支摘要 | `compaction/branch-summarization.ts` |

---

## 二、AgentHarness 主类

### 2.1 类定义

```typescript
// agent-harness.ts:174-178
export class AgentHarness<
  TSkill extends Skill = Skill,
  TPromptTemplate extends PromptTemplate = PromptTemplate,
  TTool extends AgentTool = AgentTool,
> {
  readonly env: ExecutionEnv;
  private session: Session;
  private phase: AgentHarnessPhase = "idle";
  ...
}
```

### 2.2 核心属性

```typescript
// agent-harness.ts:179-198
private session: Session;                    // 会话管理
private phase: AgentHarnessPhase;            // 当前状态（idle/turn/compaction/branch_summary）
private model: Model<any>;                   // 当前模型
private thinkingLevel: ThinkingLevel;        // 思考级别
private systemPrompt: string | Function;     // 系统提示
private streamOptions: AgentHarnessStreamOptions; // 流选项
private tools = new Map<string, TTool>();    // 工具集
private activeToolNames: string[];           // 活跃工具名
private steerQueue: UserMessage[];           // Steering 消息队列
private followUpQueue: UserMessage[];        // Follow-up 消息队列
private nextTurnQueue: AgentMessage[];       // 下一个 Turn 队列
private handlers = new Map<string, Set<AgentHarnessHandler>>(); // 事件处理器
```

### 2.3 Phase 状态

```
AgentHarnessPhase 状态流转：

idle ────→ turn ────→ idle
   │         │
   │         ↓
   │    compaction
   │         │
   │         ↓
   │    idle
   │
   ↓
branch_summary
   │
   ↓
idle
```

**状态说明**：

| Phase | 说明 | 可执行操作 |
|-------|------|-----------|
| `idle` | 空闲状态 | `prompt()`, `compact()`, `navigateTree()`, `setModel()` |
| `turn` | 正在执行 Turn | `steer()`, `followUp()`, `abort()` |
| `compaction` | 正在压缩 | 只能 `abort()` |
| `branch_summary` | 正在分支摘要 | 只能 `abort()` |

---

### 2.4 核心方法

#### prompt() - 发送用户提示

```typescript
// agent-harness.ts:630-643
async prompt(text: string, options?: { images?: ImageContent[] }): Promise<AssistantMessage> {
  if (this.phase !== "idle") throw new AgentHarnessError("busy", "AgentHarness is busy");
  this.phase = "turn";
  
  try {
    const turnState = await this.createTurnState();
    return await this.executeTurn(turnState, text, options);
  } finally {
    this.phase = "idle";
  }
}
```

#### skill() - 调用技能

```typescript
// agent-harness.ts:645-660
async skill(name: string, additionalInstructions?: string): Promise<AssistantMessage> {
  if (this.phase !== "idle") throw new AgentHarnessError("busy", "AgentHarness is busy");
  this.phase = "turn";
  
  try {
    const turnState = await this.createTurnState();
    const skill = (turnState.resources.skills ?? []).find((candidate) => candidate.name === name);
    if (!skill) throw new AgentHarnessError("invalid_argument", `Unknown skill: ${name}`);
    return await this.executeTurn(turnState, formatSkillInvocation(skill, additionalInstructions));
  } finally {
    this.phase = "idle";
  }
}
```

#### steer() - Steering 消息（干预正在运行的对话）

```typescript
// agent-harness.ts:679-683
async steer(text: string, options?: { images?: ImageContent[] }): Promise<void> {
  if (this.phase === "idle") throw new AgentHarnessError("invalid_state", "Cannot steer while idle");
  this.steerQueue.push(createUserMessage(text, options?.images));
  await this.emitQueueUpdate();
}
```

#### followUp() - Follow-up 消息（对话结束后追加）

```typescript
// agent-harness.ts:685-689
async followUp(text: string, options?: { images?: ImageContent[] }): Promise<void> {
  if (this.phase === "idle") throw new AgentHarnessError("invalid_state", "Cannot follow up while idle");
  this.followUpQueue.push(createUserMessage(text, options?.images));
  await this.emitQueueUpdate();
}
```

---

### 2.5 消息队列机制

```
三种消息队列：

1. steerQueue（Steering 消息）
   - 在对话运行时插入
   - 模式：one-at-a-time 或 all
   - 用途：实时干预、纠正方向

2. followUpQueue（Follow-up 消息）
   - 在 Turn 结束后追加
   - 模式：one-at-a-time 或 all
   - 用途：后续任务、追加指令

3. nextTurnQueue（下一个 Turn）
   - 在当前 Turn 完全结束后执行
   - 用途：预安排下一轮对话

队列处理流程：

Turn 执行中：
  → Steering 消息被注入到当前 Turn
  → AI 回应 Steering 消息
  
Turn 结束后：
  → Follow-up 消息被处理
  → 可能触发新的 Turn
  
Turn 完全结束（agent_end）：
  → nextTurnQueue 中的消息成为新 Turn 的起点
```

---

### 2.6 QueueMode

```typescript
// types.ts
type QueueMode = "one-at-a-time" | "all";

// agent-harness.ts:409-419
private async drainQueuedMessages(queue: AgentMessage[], mode: QueueMode): Promise<AgentMessage[]> {
  const messages = mode === "all" 
    ? queue.splice(0)      // 取出全部
    : queue.splice(0, 1);  // 取出第一个
  ...
}
```

**QueueMode 说明**：

| Mode | 行为 | 适用场景 |
|------|------|----------|
| `one-at-a-time` | 每次处理一条消息 | 需要逐步控制、观察 AI 回应 |
| `all` | 批量处理所有消息 | 需要一次性处理多个指令 |

---

### 2.7 事件系统

#### subscribe() - 订阅所有事件

```typescript
// agent-harness.ts:1038-1048
subscribe(
  listener: (event: AgentHarnessEvent, signal?: AbortSignal) => Promise<void> | void,
): () => void {
  let handlers = this.handlers.get(SUBSCRIBER_EVENT_TYPE);
  if (!handlers) {
    handlers = new Set();
    this.handlers.set(SUBSCRIBER_EVENT_TYPE, handlers);
  }
  handlers.add(listener as AgentHarnessHandler);
  return () => handlers!.delete(listener as AgentHarnessHandler);  // 返回取消函数
}
```

#### on() - 订阅特定事件

```typescript
// agent-harness.ts:1050-1063
on<TType extends keyof AgentHarnessEventResultMap>(
  type: TType,
  handler: (event: Extract<AgentHarnessOwnEvent, { type: TType }>) => Promise<...>,
): () => void {
  let handlers = this.handlers.get(type);
  if (!handlers) {
    handlers = new Set();
    this.handlers.set(type, handlers);
  }
  handlers.add(handler as AgentHarnessHandler);
  return () => handlers!.delete(handler as AgentHarnessHandler);
}
```

---

### 2.8 Hook 事件类型

```typescript
// types.ts
interface AgentHarnessEventResultMap {
  before_agent_start: { messages?: AgentMessage[]; systemPrompt?: string };
  context: { messages: AgentMessage[] };
  tool_call: { block?: boolean; reason?: string };
  tool_result: { content?: string; details?: unknown; isError?: boolean; terminate?: boolean };
  session_before_compact: { cancel?: boolean; compaction?: CompactionResult };
  session_before_tree: { cancel?: boolean; summary?: { summary: string; details?: unknown } };
  before_provider_request: { streamOptions?: AgentHarnessStreamOptionsPatch };
  before_provider_payload: { payload: unknown };
}
```

**关键 Hook 说明**：

| Hook | 触发时机 | 可修改内容 |
|------|----------|-----------|
| `before_agent_start` | Turn 开始前 | messages, systemPrompt |
| `context` | 发送给 LLM 前 | messages（可过滤/修改） |
| `tool_call` | 工具调用前 | block（阻止执行）, reason |
| `tool_result` | 工具执行后 | content, isError, terminate |
| `session_before_compact` | 压缩前 | cancel, 自定义摘要 |
| `session_before_tree` | 分支导航前 | cancel, 自定义摘要 |
| `before_provider_request` | API 请求前 | streamOptions |
| `before_provider_payload` | Payload 发送前 | payload |

---

## 三、Messages 消息系统

### 3.1 消息类型扩展

```typescript
// messages.ts:19-61
// 标准消息类型（来自 @earendil-works/pi-ai）
// - UserMessage
// - AssistantMessage
// - ToolResultMessage

// 扩展消息类型
interface BashExecutionMessage {
  role: "bashExecution";
  command: string;
  output: string;
  exitCode: number | undefined;
  cancelled: boolean;
  truncated: boolean;
  fullOutputPath?: string;
  timestamp: number;
  excludeFromContext?: boolean;
}

interface CustomMessage<T = unknown> {
  role: "custom";
  customType: string;
  content: string | (TextContent | ImageContent)[];
  display: boolean;
  details?: T;
  timestamp: number;
}

interface BranchSummaryMessage {
  role: "branchSummary";
  summary: string;
  fromId: string;
  timestamp: number;
}

interface CompactionSummaryMessage {
  role: "compactionSummary";
  summary: string;
  tokensBefore: number;
  timestamp: number;
}
```

---

### 3.2 消息前缀常量

```typescript
// messages.ts:4-17
export const COMPACTION_SUMMARY_PREFIX = `The conversation history before this point was compacted into the following summary:

<summary>
`;

export const COMPACTION_SUMMARY_SUFFIX = `
</summary>`;

export const BRANCH_SUMMARY_PREFIX = `The following is a summary of a branch that this conversation came back from:

<summary>
`;

export const BRANCH_SUMMARY_SUFFIX = `</summary>`;
```

**用途**：
- 告诉 LLM 这是「摘要」，不是「当前对话」
- 使用 `<summary>` XML 标签便于解析

---

### 3.3 convertToLlm() - 消息转换

```typescript
// messages.ts:120-164
export function convertToLlm(messages: AgentMessage[]): Message[] {
  return messages
    .map((m): Message | undefined => {
      switch (m.role) {
        case "bashExecution":
          if (m.excludeFromContext) return undefined;  // 跳过
          return {
            role: "user",
            content: [{ type: "text", text: bashExecutionToText(m) }],
            timestamp: m.timestamp,
          };
        
        case "custom":
          return {
            role: "user",
            content: typeof m.content === "string" 
              ? [{ type: "text", text: m.content }] 
              : m.content,
            timestamp: m.timestamp,
          };
        
        case "branchSummary":
          return {
            role: "user",
            content: [{ type: "text", text: BRANCH_SUMMARY_PREFIX + m.summary + BRANCH_SUMMARY_SUFFIX }],
            timestamp: m.timestamp,
          };
        
        case "compactionSummary":
          return {
            role: "user",
            content: [{ type: "text", text: COMPACTION_SUMMARY_PREFIX + m.summary + COMPACTION_SUMMARY_SUFFIX }],
            timestamp: m.timestamp,
          };
        
        case "user":
        case "assistant":
        case "toolResult":
          return m;  // 直接返回
        
        default:
          return undefined;
      }
    })
    .filter((m): m is Message => m !== undefined);
}
```

**转换规则**：

| 原类型 | 转换后 | 处理方式 |
|--------|--------|----------|
| `bashExecution` | `user` | 格式化为文本 |
| `custom` | `user` | 保持 content |
| `branchSummary` | `user` | 加前缀和标签 |
| `compactionSummary` | `user` | 加前缀和标签 |
| `user` | `user` | 直接返回 |
| `assistant` | `assistant` | 直接返回 |
| `toolResult` | `toolResult` | 直接返回 |

---

### 3.4 bashExecutionToText() - Bash 消息格式化

```typescript
// messages.ts:63-79
export function bashExecutionToText(msg: BashExecutionMessage): string {
  let text = `Ran \`${msg.command}\`\n`;
  if (msg.output) {
    text += `\`\`\`\n${msg.output}\n\`\`\``;
  } else {
    text += "(no output)";
  }
  if (msg.cancelled) {
    text += "\n\n(command cancelled)";
  } else if (msg.exitCode !== null && msg.exitCode !== undefined && msg.exitCode !== 0) {
    text += `\n\nCommand exited with code ${msg.exitCode}`;
  }
  if (msg.truncated && msg.fullOutputPath) {
    text += `\n\n[Output truncated. Full output: ${msg.fullOutputPath}]`;
  }
  return text;
}
```

**格式化示例**：

```
Ran `npm install`

```
added 100 packages
```

Command exited with code 0

[Output truncated. Full output: /path/to/full-output.log]
```

---

## 四、System Prompt 系统提示

### 4.1 formatSkillsForSystemPrompt()

```typescript
// system-prompt.ts:3-25
export function formatSkillsForSystemPrompt(skills: Skill[]): string {
  const visibleSkills = skills.filter((skill) => !skill.disableModelInvocation);
  if (visibleSkills.length === 0) return "";

  const lines = [
    "The following skills provide specialized instructions for specific tasks.",
    "Read the full skill file when the task matches its description.",
    "When a skill file references a relative path, resolve it against the skill directory...",
    "",
    "<available_skills>",
  ];

  for (const skill of visibleSkills) {
    lines.push("  <skill>");
    lines.push(`    <name>${escapeXml(skill.name)}</name>`);
    lines.push(`    <description>${escapeXml(skill.description)}</description>`);
    lines.push(`    <location>${escapeXml(skill.filePath)}</location>`);
    lines.push("  </skill>");
  }

  lines.push("</available_skills>");
  return lines.join("\n");
}
```

**生成示例**：

```xml
The following skills provide specialized instructions for specific tasks.
Read the full skill file when the task matches its description.

<available_skills>
  <skill>
    <name>deep-research</name>
    <description>Deep research harness — fan-out web searches...</description>
    <location>/path/to/.claude/skills/deep-research/SKILL.md</location>
  </skill>
  <skill>
    <name>code-review</name>
    <description>Review the current diff for correctness bugs...</description>
    <location>/path/to/.claude/skills/code-review/SKILL.md</location>
  </skill>
</available_skills>
```

---

## 五、Skills 技能系统

### 5.1 Skill 数据结构

```typescript
// types.ts
interface Skill {
  name: string;           // 技能名（必须匹配父目录名）
  description: string;    // 技能描述（必须，用于触发）
  content: string;        // 技能内容（SKILL.md 的 body）
  filePath: string;       // 文件路径
  disableModelInvocation?: boolean;  // 禁止自动触发
}
```

---

### 5.2 Skills 加载流程

```
loadSkills(env, dirs) 流程：

1. 遍历目录
   ↓
2. 递归搜索 SKILL.md 文件
   ↓
3. 加载 .gitignore/.ignore/.fdignore 规则
   ↓
4. 解析 SKILL.md 的 YAML frontmatter
   ↓
5. 验证 name 和 description
   ↓
6. 返回 { skills, diagnostics }
```

---

### 5.3 SKILL.md 文件格式

```markdown
---
name: deep-research
description: Deep research harness — fan-out web searches, fetch sources, adversarially verify claims
disable-model-invocation: false
---

# Deep Research

When the user wants a deep, multi-source, fact-checked research report...
...
```

**Frontmatter 字段**：

| 字段 | 必需 | 说明 |
|------|------|------|
| `name` | 可选（默认用父目录名） | 必须匹配父目录名 |
| `description` | **必需** | 用于触发判断 |
| `disable-model-invocation` | 可选 | 禁止自动触发 |

---

### 5.4 Skills 加载规则

```typescript
// skills.ts:103-175
// 加载规则：
// 1. 目录中必须有 SKILL.md 文件
// 2. 根目录的 .md 文件也作为 Skills
// 3. 忽略规则：.gitignore, .ignore, .fdignore
// 4. 递归搜索子目录
// 5. 跳过 . 开头的文件和 node_modules

// 文件优先级：
// 1. SKILL.md（最高优先级）
// 2. 根目录的 .md 文件（第二优先级）
```

---

### 5.5 formatSkillInvocation() - 技能调用格式化

```typescript
// skills.ts:38-41
export function formatSkillInvocation(skill: Skill, additionalInstructions?: string): string {
  const skillBlock = `<skill name="${skill.name}" location="${skill.filePath}">
References are relative to ${dirnameEnvPath(skill.filePath)}.

${skill.content}
</skill>`;
  return additionalInstructions ? `${skillBlock}\n\n${additionalInstructions}` : skillBlock;
}
```

**生成示例**：

```xml
<skill name="deep-research" location="/path/to/skills/deep-research/SKILL.md">
References are relative to /path/to/skills/deep-research.

# Deep Research

When the user wants a deep, multi-source, fact-checked research report...
...
</skill>

Additional focus: Focus on AI safety research
```

---

### 5.6 Skills 验证规则

```typescript
// skills.ts:281-301
function validateName(name: string, parentDirName: string): string[] {
  const errors: string[] = [];
  
  // name 必须匹配父目录名
  if (name !== parentDirName) 
    errors.push(`name "${name}" does not match parent directory "${parentDirName}"`);
  
  // 最大长度 64
  if (name.length > MAX_NAME_LENGTH) 
    errors.push(`name exceeds ${MAX_NAME_LENGTH} characters`);
  
  // 只允许小写字母、数字、连字符
  if (!/^[a-z0-9-]+$/.test(name)) 
    errors.push("name contains invalid characters");
  
  // 不能以连字符开头或结尾
  if (name.startsWith("-") || name.endsWith("-")) 
    errors.push("name must not start or end with a hyphen");
  
  // 不能有连续连字符
  if (name.includes("--")) 
    errors.push("name must not contain consecutive hyphens");
  
  return errors;
}
```

---

## 六、Prompt Templates 提示模板

### 6.1 PromptTemplate 数据结构

```typescript
// types.ts
interface PromptTemplate {
  name: string;           // 模板名（文件名去掉 .md）
  description: string;    // 模板描述
  content: string;        // 模板内容
}
```

---

### 6.2 提示模板文件格式

```markdown
---
description: Run tests and fix any failures
argument-hint: test file path
---

Run the tests in $1 and fix any failures.

$ARGUMENTS
```

**占位符**：

| 占位符 | 说明 |
|--------|------|
| `$1`, `$2`, `$3`... | 第 N 个参数 |
| `$@` 或 `$ARGUMENTS` | 所有参数 |
| `${@:N}` | 从第 N 个参数开始的所有参数 |
| `${@:N:L}` | 从第 N 个参数开始的 L 个参数 |

---

### 6.3 substituteArgs() - 参数替换

```typescript
// prompt-templates.ts:249-262
export function substituteArgs(content: string, args: string[]): string {
  let result = content;
  
  // $1, $2, $3...
  result = result.replace(/\$(\d+)/g, (_, num: string) => args[parseInt(num, 10) - 1] ?? "");
  
  // ${@:N} 或 ${@:N:L}
  result = result.replace(/\$\{@:(\d+)(?::(\d+))?\}/g, (_, startStr: string, lengthStr?: string) => {
    let start = parseInt(startStr, 10) - 1;
    if (start < 0) start = 0;
    if (lengthStr) return args.slice(start, start + parseInt(lengthStr, 10)).join(" ");
    return args.slice(start).join(" ");
  });
  
  // $ARGUMENTS 或 $@
  const allArgs = args.join(" ");
  result = result.replace(/\$ARGUMENTS/g, allArgs);
  result = result.replace(/\$@/g, allArgs);
  
  return result;
}
```

**替换示例**：

```
模板内容：
  "Run the tests in $1 and fix any failures. $ARGUMENTS"

参数：["test.ts", "verbose", "timeout=30"]

替换结果：
  "Run the tests in test.ts and fix any failures. verbose timeout=30"
```

---

### 6.4 formatPromptTemplateInvocation()

```typescript
// prompt-templates.ts:265-267
export function formatPromptTemplateInvocation(template: PromptTemplate, args: string[] = []): string {
  return substituteArgs(template.content, args);
}
```

---

### 6.5 提示模板加载

```typescript
// prompt-templates.ts:30-62
export async function loadPromptTemplates(
  env: ExecutionEnv,
  paths: string | string[],
): Promise<{ promptTemplates: PromptTemplate[]; diagnostics: PromptTemplateDiagnostic[] }> {
  // 遍历路径
  // 如果是目录 → 加载直接子目录的 .md 文件（非递归）
  // 如果是文件 → 加载该 .md 文件
  // 解析 YAML frontmatter
  // 返回 { promptTemplates, diagnostics }
}
```

---

## 七、ExecutionEnv 环境抽象

### 7.1 ExecutionEnv 接口

```typescript
// types.ts
interface ExecutionEnv {
  cwd: string;  // 当前工作目录
  
  // 路径操作
  absolutePath(path: string): Promise<Result<string, FileError>>;
  joinPath(parts: string[]): Promise<Result<string, FileError>>;
  canonicalPath(path: string): Promise<Result<string, FileError>>;
  exists(path: string): Promise<Result<boolean, FileError>>;
  
  // 文件操作
  readTextFile(path: string, abortSignal?: AbortSignal): Promise<Result<string, FileError>>;
  readTextLines(path: string, options?: { maxLines?: number; abortSignal?: AbortSignal }): Promise<Result<string[], FileError>>;
  readBinaryFile(path: string, abortSignal?: AbortSignal): Promise<Result<Uint8Array, FileError>>;
  writeFile(path: string, content: string | Uint8Array, abortSignal?: AbortSignal): Promise<Result<void, FileError>>;
  appendFile(path: string, content: string | Uint8Array): Promise<Result<void, FileError>>;
  fileInfo(path: string): Promise<Result<FileInfo, FileError>>;
  listDir(path: string, abortSignal?: AbortSignal): Promise<Result<FileInfo[], FileError>>;
  createDir(path: string, options?: { recursive?: boolean }): Promise<Result<void, FileError>>;
  remove(path: string, options?: { recursive?: boolean; force?: boolean }): Promise<Result<void, FileError>>;
  
  // 命令执行
  exec(command: string, options?: { ... }): Promise<Result<{ stdout, stderr, exitCode }, ExecutionError>>;
  
  // 临时文件
  createTempDir(prefix?: string): Promise<Result<string, FileError>>;
  createTempFile(options?: { prefix?: string; suffix?: string }): Promise<Result<string, FileError>>;
  
  // 清理
  cleanup(): Promise<void>;
}
```

---

### 7.2 NodeExecutionEnv 实现

```typescript
// env/nodejs.ts:217-528
export class NodeExecutionEnv implements ExecutionEnv {
  cwd: string;
  private shellPath?: string;
  private shellEnv?: NodeJS.ProcessEnv;
  
  constructor(options: { cwd: string; shellPath?: string; shellEnv?: NodeJS.ProcessEnv }) {
    this.cwd = options.cwd;
    this.shellPath = options.shellPath;
    this.shellEnv = options.shellEnv;
  }
  
  // 实现所有 ExecutionEnv 方法
  // 使用 Node.js 的 fs, fs/promises, child_process
}
```

---

### 7.3 Shell 配置

```typescript
// env/nodejs.ts:147-182
async function getShellConfig(customShellPath?: string): Promise<Result<{ shell: string; args: string[] }, ExecutionError>> {
  if (customShellPath) {
    if (await pathExists(customShellPath)) {
      return ok({ shell: customShellPath, args: ["-c"] });
    }
    return err(new ExecutionError("shell_unavailable", `Custom shell path not found`));
  }
  
  // Windows 平台
  if (process.platform === "win32") {
    // 尝试 Git Bash
    const candidates = [
      `${process.env.ProgramFiles}\\Git\\bin\\bash.exe`,
      `${process.env["ProgramFiles(x86)"]}\\Git\\bin\\bash.exe`,
    ];
    for (const candidate of candidates) {
      if (await pathExists(candidate)) {
        return ok({ shell: candidate, args: ["-c"] });
      }
    }
    // 尝试 PATH 中的 bash
    const bashOnPath = await findBashOnPath();
    if (bashOnPath) return ok({ shell: bashOnPath, args: ["-c"] });
    return err(new ExecutionError("shell_unavailable", "No bash shell found"));
  }
  
  // Unix 平台
  if (await pathExists("/bin/bash")) {
    return ok({ shell: "/bin/bash", args: ["-c"] });
  }
  const bashOnPath = await findBashOnPath();
  if (bashOnPath) return ok({ shell: bashOnPath, args: ["-c"] });
  return ok({ shell: "sh", args: ["-c"] });
}
```

---

### 7.4 命令执行实现

```typescript
// env/nodejs.ts:236-351
async exec(command: string, options?: { ... }): Promise<Result<{ stdout, stderr, exitCode }, ExecutionError>> {
  const cwd = options?.cwd ? resolvePath(this.cwd, options.cwd) : this.cwd;
  const shellConfig = await getShellConfig(this.shellPath);
  
  return await new Promise((resolvePromise) => {
    let stdout = "";
    let stderr = "";
    let child: ReturnType<typeof spawn> | undefined;
    
    // spawn 命令
    child = spawn(shellConfig.value.shell, [...shellConfig.value.args, command], {
      cwd,
      detached: process.platform !== "win32",
      env: getShellEnv(this.shellEnv, options?.env),
      stdio: ["ignore", "pipe", "pipe"],
    });
    
    // 收集输出
    child.stdout?.on("data", (chunk: string) => {
      stdout += chunk;
      options?.onStdout?.(chunk);
    });
    child.stderr?.on("data", (chunk: string) => {
      stderr += chunk;
      options?.onStderr?.(chunk);
    });
    
    // 处理结束
    child.on("close", (code) => {
      if (timedOut) settle(err(new ExecutionError("timeout", ...)));
      if (options?.abortSignal?.aborted) settle(err(new ExecutionError("aborted", ...)));
      settle(ok({ stdout, stderr, exitCode: code ?? 0 }));
    });
  });
}
```

---

## 八、组件协作流程

### 8.1 prompt() 完整流程

```
用户调用 prompt("帮我分析这段代码")

↓
AgentHarness.prompt()
  │
  ├─→ 检查 phase === "idle"
  ├─→ 设置 phase = "turn"
  ├─→ createTurnState()
  │     │
  │     ├─→ session.buildContext() → messages
  │     ├─→ getResources() → skills, promptTemplates
  │     ├─→ 构建 systemPrompt
  │     └─→ 返回 TurnState
  │
  ├─→ executeTurn(turnState, text)
  │     │
  │     ├─→ createUserMessage(text)
  │     ├─→ emitHook("before_agent_start") → 可修改 messages
  │     ├─→ runAgentLoop()
  │     │     │
  │     │     ├─→ createContext() → { systemPrompt, messages, tools }
  │     │     ├─→ emitHook("context") → 可修改 messages
  │     │     ├─→ streamFn() → 调用 LLM
  │     │     │     │
  │     │     │     ├─→ emitBeforeProviderRequest()
  │     │     │     ├─→ streamSimple()
  │     │     │     └─→ emitBeforeProviderPayload()
  │     │     │
  │     │     ├─→ 处理 tool calls
  │     │     │     ├─→ emitHook("tool_call") → 可阻止
  │     │     │     ├─→ 执行工具
  │     │     │     └─→ emitHook("tool_result") → 可修改
  │     │     │
  │     │     ├─→ 处理 steering/followUp 队列
  │     │     └─→ 返回 AssistantMessage
  │     │
  │     ├─→ handleAgentEvent("message_end") → session.appendMessage()
  │     ├─→ handleAgentEvent("turn_end") → flushPendingSessionWrites()
  │     └─→ handleAgentEvent("agent_end")
  │
  ├─→ 设置 phase = "idle"
  └─→ 返回 AssistantMessage
```

---

### 8.2 skill() 流程

```
用户调用 skill("deep-research", "Focus on AI safety")

↓
AgentHarness.skill()
  │
  ├─→ 检查 phase === "idle"
  ├─→ 设置 phase = "turn"
  ├─→ createTurnState()
  ├─→ 找到 skill = resources.skills.find(name === "deep-research")
  ├─→ formatSkillInvocation(skill, "Focus on AI safety")
  │     └─→ 生成：<skill name="deep-research" ...>...</skill>
  │
  ├─→ executeTurn(turnState, formattedSkillInvocation)
  │     └─→ 与 prompt() 流程相同
  │
  └─→ 返回 AssistantMessage
```

---

## 九、关键设计模式

### 9.1 事件驱动架构

```
特点：
  - 所有操作通过事件通知
  - 支持订阅特定事件或全部事件
  - Hook 可以修改行为（before_agent_start, tool_call 等）

优势：
  - 松耦合：组件间通过事件通信
  - 可扩展：通过 Hook 自定义行为
  - 可观测：订阅所有事件实现监控
```

---

### 9.2 队列机制

```
三种队列解决不同场景：

1. steerQueue：实时干预
   - 对话进行中插入消息
   - 纠正方向、提供额外信息

2. followUpQueue：后续任务
   - Turn 结束后追加任务
   - 预安排下一步工作

3. nextTurnQueue：下一轮对话
   - 完全结束后开始新 Turn
   - 预安排多轮对话

设计优势：
  - 分离不同干预时机
  - 支持批量或逐个处理
  - 可取消和清理
```

---

### 9.3 状态机设计

```
Phase 状态机：

idle ────→ turn ────→ idle
   │         │
   │         ↓
   │    compaction
   │         │
   │         ↓
   │    idle
   │
   ↓
branch_summary
   │
   ↓
idle

状态保护：
  - 每个操作只能在特定状态执行
  - 状态转换有明确规则
  - 防止并发冲突
```

---

### 9.4 环境抽象

```
ExecutionEnv 设计：

抽象接口：
  - 文件操作（read, write, list）
  - 命令执行
  - 路径操作

具体实现：
  - NodeExecutionEnv（Node.js 环境）
  - 可扩展其他环境（浏览器、远程等）

优势：
  - 环境无关性
  - 测试友好（可 mock）
  - 统一错误处理
```

---

## 十、总结

### 10.1 组件职责速查表

| 组件 | 核心职责 | 关键 API |
|------|----------|----------|
| **AgentHarness** | 主入口，协调所有组件 | `prompt()`, `skill()`, `steer()`, `subscribe()` |
| **Session** | 会话管理，Entry 树 | `getBranch()`, `appendMessage()`, `buildContext()` |
| **Messages** | 消息转换 | `convertToLlm()`, `bashExecutionToText()` |
| **System Prompt** | 提示构建 | `formatSkillsForSystemPrompt()` |
| **Skills** | 技能加载调用 | `loadSkills()`, `formatSkillInvocation()` |
| **Prompt Templates** | 模板加载替换 | `loadPromptTemplates()`, `substituteArgs()` |
| **ExecutionEnv** | 环境抽象 | `exec()`, `readTextFile()`, `listDir()` |
| **Compaction** | 上下文压缩 | `prepareCompaction()`, `compact()` |
| **Branch Summarization** | 分支摘要 | `collectEntriesForBranchSummary()`, `generateBranchSummary()` |

---

### 10.2 学习路径建议

```
已掌握：
  ✓ Session Entry 类型体系
  ✓ Compaction 流程详解
  ✓ Branch Summarization 对比

建议继续学习：
  1. agent-loop.ts - Agent 循环核心逻辑
  2. session/jsonl-repo.ts - Session 持久化
  3. types.ts - 完整类型定义
  4. 实际调试：观察事件流和 Hook 行为
```

---

## 参考资料

- **源文件**：
  - `packages/agent/src/harness/agent-harness.ts` - 主入口类
  - `packages/agent/src/harness/messages.ts` - 消息系统
  - `packages/agent/src/harness/system-prompt.ts` - 系统提示
  - `packages/agent/src/harness/skills.ts` - 技能系统
  - `packages/agent/src/harness/prompt-templates.ts` - 提示模板
  - `packages/agent/src/harness/env/nodejs.ts` - 环境实现
  - `packages/agent/src/harness/types.ts` - 类型定义

- **相关文档**：
  - `Agent Harness 与 Session 架构知识体系.md` - Session 详解
  - `Compaction 流程详解.md` - Compaction 详解
  - `Branch Summarization 与 Compaction 对比详解.md` - 分支摘要对比