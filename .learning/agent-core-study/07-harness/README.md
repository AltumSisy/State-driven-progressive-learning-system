# L07: Harness 基础

## 学习目标

- 🔴 掌握 AgentHarness 类结构
- 🔴 理解 AgentHarnessResources (skills, promptTemplates)
- 🟠 理解 ExecutionEnv (fs, shell) 抽象
- 🟠 掌握 prompt() / skill() / promptFromTemplate() 方法
- 🟡 理解 Steering/Follow-up/NextTurn 队列管理

---

## 源文件

`src/harness/agent-harness.ts` (~1000行)

---

## 1. AgentHarness 类结构

```typescript
// agent-harness.ts:164-205

export class AgentHarness<TSkill, TPromptTemplate, TTool> {
  readonly env: ExecutionEnv;
  private session: Session;
  private phase: AgentHarnessPhase = "idle";
  private model: Model<any>;
  private thinkingLevel: ThinkingLevel;
  private systemPrompt: AgentHarnessOptions["systemPrompt"];
  private streamOptions: AgentHarnessStreamOptions;
  private resources: AgentHarnessResources<TSkill, TPromptTemplate>;
  private tools = new Map<string, TTool>();
  private steerQueue: UserMessage[] = [];
  private followUpQueue: UserMessage[] = [];
  private nextTurnQueue: AgentMessage[] = [];
  private handlers = new Map<string, Set<AgentHarnessHandler>>();
  
  constructor(options: AgentHarnessOptions) { ... }
}
```

---

## 2. AgentHarnessOptions

```typescript
// harness/types.ts

interface AgentHarnessOptions {
  env: ExecutionEnv;                     // 执行环境
  session: Session;                      // 会话管理
  model: Model<any>;                     // 当前模型
  thinkingLevel?: ThinkingLevel;         // 推理级别
  systemPrompt?: string | SystemPromptFn;  // 系统提示
  streamOptions?: AgentHarnessStreamOptions;
  tools?: TTool[];
  activeToolNames?: string[];
  resources?: AgentHarnessResources;
  steeringMode?: QueueMode;
  followUpMode?: QueueMode;
  getApiKeyAndHeaders?: (model) => Promise<{ apiKey, headers }>;
}
```

---

## 3. AgentHarnessResources

```typescript
// harness/types.ts

interface AgentHarnessResources<TSkill, TPromptTemplate> {
  skills?: TSkill[];
  promptTemplates?: TPromptTemplate[];
}
```

### Skill 定义

```typescript
interface Skill {
  name: string;
  description: string;
  promptTemplate?: string;
  tools?: AgentTool[];
  additionalInstructions?: string;
}
```

### PromptTemplate 定义

```typescript
interface PromptTemplate {
  name: string;
  description: string;
  template: string;
  args?: string[];
}
```

---

## 4. ExecutionEnv 抽象

```typescript
// harness/types.ts

interface ExecutionEnv {
  fs: FileSystem;    // 文件系统抽象
  shell: Shell;      // Shell 抽象
}
```

### FileSystem

```typescript
interface FileSystem {
  readFile(path: string): Promise<string>;
  writeFile(path: string, content: string): Promise<void>;
  readdir(path: string): Promise<string[]>;
  stat(path: string): Promise<FileStat>;
  exists(path: string): Promise<boolean>;
  mkdir(path: string): Promise<void>;
}
```

### Node.js 实现

源文件：`harness/env/nodejs.ts`

---

## 5. 核心方法

### 5.1 prompt()

```typescript
// agent-harness.ts:603-616

async prompt(text: string, options?: { images?: ImageContent[] }): Promise<AssistantMessage> {
  if (this.phase !== "idle") throw new AgentHarnessError("busy");
  this.phase = "turn";
  const turnState = await this.createTurnState();
  return await this.executeTurn(turnState, text, options);
}
```

### 5.2 skill()

```typescript
// agent-harness.ts:618-633

async skill(name: string, additionalInstructions?: string): Promise<AssistantMessage> {
  const skill = turnState.resources.skills?.find(s => s.name === name);
  if (!skill) throw new AgentHarnessError("invalid_argument");
  return await this.executeTurn(turnState, formatSkillInvocation(skill, additionalInstructions));
}
```

### 5.3 promptFromTemplate()

```typescript
// agent-harness.ts:635-650

async promptFromTemplate(name: string, args: string[] = []): Promise<AssistantMessage> {
  const template = turnState.resources.promptTemplates?.find(t => t.name === name);
  return await this.executeTurn(turnState, formatPromptTemplateInvocation(template, args));
}
```

---

## 6. 队列管理

### steer / followUp / nextTurn

```typescript
// agent-harness.ts:652-667

async steer(text: string, options?: { images }): Promise<void> {
  if (this.phase === "idle") throw new AgentHarnessError("invalid_state");
  this.steerQueue.push(createUserMessage(text, options?.images));
  await this.emitQueueUpdate();
}

async followUp(text: string, options?: { images }): Promise<void> {
  this.followUpQueue.push(createUserMessage(text, options?.images));
  await this.emitQueueUpdate();
}

async nextTurn(text: string, options?: { images }): Promise<void> {
  this.nextTurnQueue.push(createUserMessage(text, options?.images));
  await this.emitQueueUpdate();
}
```

---

## 7. 事件订阅

### subscribe()

```typescript
// agent-harness.ts:969-978

subscribe(
  listener: (event: AgentHarnessEvent, signal?: AbortSignal) => Promise<void> | void
): () => void {
  handlers.get("*").add(listener);
  return () => handlers.delete(listener);
}
```

### on() - 特定事件

```typescript
// agent-harness.ts:981-994

on<TType extends keyof AgentHarnessEventResultMap>(
  type: TType,
  handler: (event) => Promise<AgentHarnessEventResultMap[TType]>
): () => void;
```

**支持的事件类型**：
- `before_agent_start`
- `tool_call` / `tool_result`
- `context`
- `session_before_compact` / `session_before_tree`
- `before_provider_request` / `before_provider_payload`

---

## TODO 清单

### TODO-1: 掌握 AgentHarness 结构 (🔴)
**完成检查**:
- [ ] 列举构造函数的核心参数
- [ ] 列举三种队列 (steerQueue, followUpQueue, nextTurnQueue)

### TODO-2: 掌握 Resources (🔴)
**完成检查**:
- [ ] 列举 Skill 的 5 个字段
- [ ] 列举 PromptTemplate 的 4 个字段

### TODO-3: 掌握 ExecutionEnv (🟠)
**完成检查**:
- [ ] 列举 FileSystem 的 6 个方法

---

## 下一步

→ [L08: Session 管理](./08-session)