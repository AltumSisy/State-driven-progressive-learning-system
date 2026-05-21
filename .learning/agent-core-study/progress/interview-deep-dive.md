# Agent 包深度补充：面试与实战问题

## 概述

本文档补充面试高频问题和实战深度话题，与基础大纲配合使用。

---

## 1. Agent Loop 模式深度解析

### 1.1 ReAct、PlanAct、MultiAgent 本质

#### ReAct 模式（Reasoning + Acting）

```
Thought → Action → Observation → ... → Answer
   ↑__________________________________|
```

**在 pi-agent-core 中的体现**:

```typescript
// ReAct 循环 = Agent Loop 的一次迭代
// Thought: LLM 生成的推理
// Action: Tool Call
// Observation: Tool Result

// 代码体现
for await (const event of agentLoop([userMessage], context, config)) {
  if (event.type === "turn_end") {
    // Thought (assistant message) + Action (tool calls)
    // Observation (tool results) 已加入 context
    
    // 检查是否需要继续 ReAct 循环
    const hasToolCalls = event.toolResults.length > 0;
    const needsMoreReasoning = /* ... */;
    
    if (hasToolCalls || needsMoreReasoning) {
      // 自动继续下一轮（框架默认行为）
    }
  }
}
```

#### PlanAct 模式

```
Plan → Execute Steps → Verify → Answer
```

**实现方式**:

```typescript
// Plan 阶段：专用工具生成计划
const planTool: AgentTool = {
  name: "create_plan",
  execute: async (id, params) => {
    // 返回结构化计划
    return {
      content: [{ type: "text", text: JSON.stringify(steps) }],
      details: { steps, dependencies }
    };
  }
};

// 执行阶段：plan_then_execute skill
const planAndExecuteSkill: Skill = {
  name: "plan_then_execute",
  tools: [planTool, executeStepTool, verifyTool],
  promptTemplate: `
    First, create a plan for: {{userQuery}}
    Then execute each step sequentially.
    Verify after each step.
  `
};
```

#### MultiAgent 协作模式

**模式对比**:

| 模式 | 架构 | 适用场景 | 复杂度 |
|-----|------|---------|-------|
| Agent As Tool | Master → SubAgent (Tool) | 子任务独立 | 低 |
| Agent Handoff | Agent A → Agent B | 上下文切换 | 中 |
| Leader & Workers | Leader → N Workers | 并行子任务 | 中 |
| Agent2Agent | A ↔ B (双向) | 协作对话 | 高 |

**Agent As Tool 实现** (SubAgent 模式):

```typescript
// SubAgent 作为工具
const subAgentTool: AgentTool = {
  name: "delegate_to_specialist",
  parameters: Type.Object({
    agentType: Type.String(),  // "coder", "reviewer", "tester"
    task: Type.String(),
    context: Type.String(),
  }),
  execute: async (id, params) => {
    // 创建专门的 SubAgent
    const subAgent = createAgentForRole(params.agentType);
    
    // 设置上下文
    subAgent.state.systemPrompt = getPromptForRole(params.agentType);
    subAgent.state.tools = getToolsForRole(params.agentType);
    
    // 执行
    const results: string[] = [];
    subAgent.subscribe((event) => {
      if (event.type === "message_update") {
        results.push(event.assistantMessageEvent.delta);
      }
    });
    
    await subAgent.prompt(params.task);
    await subAgent.waitForIdle();
    
    return {
      content: [{ type: "text", text: results.join("") }],
      details: { agentType: params.agentType, task: params.task }
    };
  }
};

// Master Agent 配置
const masterAgent = new Agent({
  initialState: {
    tools: [subAgentTool, directAnswerTool],
    systemPrompt: "Route tasks to specialists or answer directly."
  }
});
```

**Agent Handoff 实现**:

```typescript
// 上下文传递
interface HandoffContext {
  sourceAgent: string;
  targetAgent: string;
  transferredContext: AgentContext;
  handoffReason: string;
}

const handoffTool: AgentTool = {
  name: "handoff_to_agent",
  parameters: Type.Object({
    targetAgent: Type.String(),
    reason: Type.String(),
  }),
  execute: async (id, params, signal, onUpdate, context) => {
    // 序列化当前上下文
    const serialized = serializeContext(context);
    
    // 触发 Handoff 事件（由框架处理）
    return {
      content: [{ type: "text", text: `Handing off to ${params.targetAgent}` }],
      details: { handoff: true, target: params.targetAgent },
      terminate: true  // 停止当前 Agent
    };
  }
};

// 在 Harness 层处理 Handoff
class MultiAgentHarness {
  private agents: Map<string, Agent>;
  
  async handleHandoff(from: string, to: string, context: AgentContext) {
    const targetAgent = this.agents.get(to);
    
    // 加载上下文
    targetAgent.state.messages = context.messages;
    targetAgent.state.systemPrompt = `${context.systemPrompt}\n\n[Handoff from ${from}]`;
    
    // 继续
    await targetAgent.continue();
  }
}
```

**Leader & Workers 实现**:

```typescript
// Leader Agent 使用 parallel 工具执行
const leaderAgent = new Agent({
  initialState: {
    tools: [
      {
        name: "assign_to_workers",
        parameters: Type.Object({
          subtasks: Type.Array(Type.String())
        }),
        execute: async (id, params, signal, onUpdate) => {
          // 创建多个 Worker Agent
          const workers = params.subtasks.map((task, i) => 
            createWorkerAgent(`worker-${i}`, task)
          );
          
          // 并行执行
          const results = await Promise.all(
            workers.map(w => w.executeAndReturn())
          );
          
          return {
            content: [{ type: "text", text: JSON.stringify(results) }],
            details: { parallelResults: results }
          };
        },
        // 关键：允许并发执行
        executionMode: "parallel"
      }
    ]
  }
});
```

---

### 1.2 LoopSession 与 LoopTurn

#### LoopTurn 详细结构

```
LoopTurn
├── Model Call (LLM 推理)
│   ├── Input: Context (System + History)
│   ├── Output: AssistantMessage
│   └── Events: turn_start → message_start → message_update* → message_end
│
└── Tool Execution (可选)
    ├── Input: Tool Calls from Assistant
    ├── Process: Batch Execution (parallel/sequential)
    ├── Output: Tool Results
    └── Events: tool_execution_start → tool_execution_update* → tool_execution_end → turn_end
```

**关键代码**:

```typescript
// agent-loop.ts 中的 turn 处理
async function* runTurn(
  context: AgentContext,
  config: AgentLoopConfig
): AsyncGenerator<AgentEvent> {
  // 1. Model Call
  yield { type: "turn_start" };
  
  for await (const event of streamModel(context, config)) {
    yield event;  // message_start, message_update, message_end
  }
  
  // 2. Tool Execution (if any)
  const toolCalls = extractToolCalls(lastAssistantMessage);
  
  if (toolCalls.length > 0) {
    // Batch 执行
    const executionMode = determineExecutionMode(toolCalls, config);
    
    if (executionMode === "parallel") {
      // 并行执行
      const executingTools = toolCalls.map(tc => executeTool(tc, config));
      
      for await (const result of Promise.race(executingTools)) {
        yield { type: "tool_execution_end", ...result };
      }
    } else {
      // 顺序执行
      for (const tc of toolCalls) {
        yield { type: "tool_execution_start", toolCallId: tc.id, ... };
        const result = await executeTool(tc, config);
        yield { type: "tool_execution_end", ...result };
      }
    }
  }
  
  yield { type: "turn_end", message: lastAssistantMessage, toolResults };
}
```

#### LoopSession 控制点

```typescript
interface LoopSession {
  // Steering: 运行时干预
  steer(message: AgentMessage): void;
  clearSteeringQueue(): void;
  
  // Follow-up: 完成后追加
  followUp(message: AgentMessage): void;
  clearFollowUpQueue(): void;
  
  // Interrupt: 中止
  abort(): void;
  waitForIdle(): Promise<void>;
  
  // 状态
  state: AgentState;
}

// Steering 触发时机
// ┌─────────────────────────────────────────┐
// │ Turn N completes                       │
// │ tool calls finished                    │
// │ turn_end emitted                       │
// │                                        │
// │ Check: steeringQueue.hasItems()?       │
// │ Yes → drain queue → inject messages    │
// │      → continue to next turn           │
// │ No → check followUpQueue               │
// └─────────────────────────────────────────┘
```

---

### 1.3 LoopControl

#### ContextControl

```typescript
interface ContextControl {
  // 内容过滤/审查
  transformContext?: (messages: AgentMessage[], signal?: AbortSignal) => Promise<AgentMessage[]>;
  
  // 多模态数据处理
  convertToLlm: (messages: AgentMessage[]) => Message[];
  
  // 业务上下文加载
  beforeToolCall?: BeforeToolCallHook;
  afterToolCall?: AfterToolCallHook;
  
  // 长程任务上下文压缩
  shouldStopAfterTurn?: ShouldStopAfterTurnHook;
  prepareNextTurn?: PrepareNextTurnHook;
}

// 安全审查示例
const safetyControl: TransformContext = async (messages) => {
  return messages.filter(m => {
    if (m.role === "user") {
      const content = typeof m.content === "string" ? m.content : "";
      // PII 检测
      if (containsPII(content)) {
        return false;
      }
      // 有害内容检测
      if (containsHarmfulContent(content)) {
        throw new Error("Harmful content detected");
      }
    }
    return true;
  });
};

// 多模态数据处理
const multimodalConvert: ConvertToLlm = (messages) => {
  return messages.map(m => {
    if (m.role === "user" && Array.isArray(m.content)) {
      // 处理图片
      return {
        ...m,
        content: m.content.map(c => {
          if (c.type === "image") {
            // 转 base64 或 URL
            return { type: "image", source: { type: "base64", ... } };
          }
          return c;
        })
      };
    }
    return m;
  });
};
```

#### RunControl

```typescript
interface RunControl {
  // 停止原因
  stopReason: "stop" | "length" | "tool_calls" | "content_filter" | "error" | "abort" | "steering";
  
  // 执行控制
  shouldStopAfterTurn?: (ctx: ShouldStopAfterTurnContext) => boolean | Promise<boolean>;
  
  // 模式切换
  prepareNextTurn?: (ctx: PrepareNextTurnContext) => AgentLoopTurnUpdate | undefined;
}

// StopReason 处理
function handleStopReason(
  stopReason: string,
  context: AgentContext
): LoopAction {
  switch (stopReason) {
    case "tool_calls":
      // 自动继续（工具结果已加入上下文）
      return { action: "continue" };
      
    case "length":
      // 上下文太长，触发压缩
      return { action: "compact", strategy: "summary" };
      
    case "content_filter":
      // 内容被过滤，需要人工介入
      return { action: "human_in_the_loop", reason: "content_filtered" };
      
    case "error":
      // 错误恢复或终止
      return { action: "retry", maxRetries: 3 };
      
    case "abort":
      return { action: "terminate" };
      
    default:
      return { action: "continue" };
  }
}

// 思维模式切换
const modeSwitchingControl: PrepareNextTurn = async ({ context }) => {
  const lastMessages = context.messages.slice(-3);
  const reasoningNeeded = lastMessages.some(m => 
    m.content?.includes("think step by step")
  );
  
  if (reasoningNeeded) {
    return {
      model: getModel("anthropic", "claude-opus-4-20250514"),
      thinkingLevel: "high"
    };
  }
  
  // 默认使用轻量模型
  return {
    model: getModel("anthropic", "claude-haiku-4"),
    thinkingLevel: "off"
  };
};
```

---

## 2. Skill 深度理解

### 2.1 Skill 的本质

```
Skill = Experience 的编排
       = Prompt Template + Tools + Context + Examples
```

**Skill vs Tool 区别**:

| 维度 | Tool | Skill |
|-----|------|-------|
| 粒度 | 单一功能 | 完整工作流 |
| 组成 | function | prompt + tools + logic |
| 状态 | 无状态 | 可维护状态 |
| 复用 | 函数级 | 任务级 |

**Skill 抽象层级**:

```
Level 0: Tool (原子操作)
  ↓ compose
Level 1: Micro Skill (单步任务)
  ↓ compose  
Level 2: Task Skill (多步流程)
  ↓ compose
Level 3: Workflow Skill (复杂场景)
```

### 2.2 Skill 演进与覆盖

```typescript
// Skill 版本管理
interface SkillVersion {
  version: string;
  baseVersion?: string;  // 继承基础
  overrides: SkillOverrides;
}

// Skill 演进：覆盖机制
const codeReviewSkillV2: Skill = {
  name: "code_review",
  version: "2.0",
  base: codeReviewSkillV1,  // 继承 V1
  
  // 覆盖 prompt
  promptTemplate: `
    {{base.prompt}}
    
    Additional rules for V2:
    - Check for security vulnerabilities
    - Verify test coverage
  `,
  
  // 覆盖 tools
  tools: [
    ...codeReviewSkillV1.tools,
    securityCheckTool,  // 新增
  ],
  
  // 覆盖参数
  parameters: {
    ...codeReviewSkillV1.parameters,
    strictness: { type: "string", enum: ["low", "medium", "high"] }
  }
};

// Skill 卸载
function unloadSkill(agent: Agent, skillName: string) {
  // 移除工具
  agent.state.tools = agent.state.tools.filter(
    t => !t.metadata?.skillName === skillName
  );
  
  // 清理上下文引用
  // ...
}
```

### 2.3 Skill 与上下文压缩

```typescript
interface SkillWithCompaction {
  name: string;
  
  // Skill 级别的压缩策略
  compactionStrategy: {
    // 保留关键示例
    preserveExamples: number;
    
    // 保留工具调用历史
    preserveToolHistory: boolean;
    
    // 自定义压缩提示
    summaryPrompt: string;
  };
}

// 上下文压缩时保留 Skill 关键信息
const skillAwareCompaction = async (
  messages: AgentMessage[],
  activeSkills: Skill[]
) => {
  // 1. 识别 Skill 相关消息
  const skillMessages = messages.filter(m => 
    hasSkillMetadata(m)
  );
  
  // 2. 保留策略
  const toPreserve = activeSkills.flatMap(skill => 
    extractCriticalMessages(skill, skillMessages)
  );
  
  // 3. 压缩其余
  const toCompact = messages.filter(m => 
    !toPreserve.includes(m)
  );
  
  const summary = await generateSummary(toCompact);
  
  return [...toPreserve, summary];
};
```

### 2.4 Skill 嵌套

```typescript
// Parent Skill 包含 Child Skill
const dataAnalysisSkill: Skill = {
  name: "data_analysis",
  tools: [
    // 嵌套的子 Skill
    {
      name: "data_cleaning",
      type: "skill",  // 标记为 Skill 类型
      skill: dataCleaningSkill
    },
    {
      name: "visualization", 
      type: "skill",
      skill: visualizationSkill
    }
  ],
  
  workflow: [
    { step: 1, skill: "data_cleaning", output: "cleaned_data" },
    { step: 2, skill: "analysis", input: "cleaned_data" },
    { step: 3, skill: "visualization", input: "analysis_result" }
  ]
};

// 嵌套 Skill 执行
async function executeNestedSkill(
  parentContext: SkillContext,
  childSkill: Skill
): Promise<SkillResult> {
  // 创建隔离的 Agent
  const childAgent = new Agent({
    initialState: {
      systemPrompt: childSkill.promptTemplate,
      tools: childSkill.tools,
      messages: []  // 隔离上下文
    }
  });
  
  // 注入父上下文（受控）
  childAgent.state.messages.push({
    role: "user",
    content: `Parent context: ${serializeContext(parentContext)}`,
    timestamp: Date.now()
  });
  
  // 执行
  await childAgent.prompt(childSkill.taskDescription);
  
  // 返回结果到父级
  return extractResult(childAgent.state.messages);
}
```

### 2.5 Skill 评估与改进

```typescript
// Skill 评估框架
interface SkillEvaluation {
  // 成功率
  successRate: number;
  
  // 平均 Turn 数
  avgTurns: number;
  
  // 工具使用效率
  toolEfficiency: number;
  
  // 用户满意度（如适用）
  userSatisfaction?: number;
  
  // 错误分布
  errorBreakdown: Record<ErrorType, number>;
}

// Skill 自适应改进
async function improveSkill(
  skill: Skill,
  evaluationResults: SkillEvaluation[]
) {
  // 1. 识别薄弱环节
  const weakPoints = analyzeWeakness(evaluationResults);
  
  // 2. 生成改进建议
  const improvementPlan = await generateImprovementPlan(skill, weakPoints);
  
  // 3. 创建新版本
  const improvedSkill: Skill = {
    ...skill,
    version: incrementVersion(skill.version),
    promptTemplate: await optimizePrompt(skill, improvementPlan),
    tools: await optimizeTools(skill, improvementPlan)
  };
  
  // 4. A/B 测试
  const testResult = await abTest(skill, improvedSkill);
  
  return testResult.improved ? improvedSkill : skill;
}

// Skill 评估指标
const skillMetrics = {
  // 完成任务成功率
  taskCompletionRate: (sessions: Session[]) => 
    sessions.filter(s => s.completed).length / sessions.length,
  
  // 平均工具调用次数（越少越好）
  avgToolCalls: (sessions: Session[]) =>
    sessions.reduce((sum, s) => sum + s.toolCalls.length, 0) / sessions.length,
  
  // 上下文压缩次数（越少越好）
  compactionFrequency: (sessions: Session[]) =>
    sessions.reduce((sum, s) => sum + s.compactionCount, 0) / sessions.length,
  
  // 用户修正次数（越少越好）
  correctionRate: (sessions: Session[]) =>
    sessions.filter(s => s.hadCorrection).length / sessions.length
};
```

### 2.6 Skill 与 Memory 的关系

```
Memory (长期)          Skill (能力)
    │                       │
    ├─ 用户偏好          ├─ 执行流程
    ├─ 历史上下文        ├─ 工具组合
    ├─ 学习到的模式      ├─ Prompt 模板
    │                       │
    └──────→ 个性化 Skill ←──┘
```

```typescript
// Memory 注入 Skill
interface PersonalizedSkill extends Skill {
  // 从 Memory 加载个性化
  personalization: {
    // 用户偏好的输出格式
    preferredOutputFormat: string;
    
    // 常用的参数默认值
    defaultParameters: Record<string, any>;
    
    // 历史修正学习
    learnedCorrections: Correction[];
  };
}

// 应用个性化
function personalizeSkill(
  baseSkill: Skill,
  userMemory: Memory
): PersonalizedSkill {
  return {
    ...baseSkill,
    promptTemplate: injectPreferences(
      baseSkill.promptTemplate,
      userMemory.preferences
    ),
    defaultParameters: userMemory.defaultParams
  };
}
```

---

## 3. Agent Framework 深度

### 3.1 SSE/Stream 实现原理

```typescript
// Server-Sent Events (SSE) 协议
// 
// HTTP Headers:
// Content-Type: text/event-stream
// Cache-Control: no-cache
// Connection: keep-alive
//
// Body format:
// event: message\n
// data: {"type": "text_delta", "delta": "Hello"}\n\n

// pi-agent-core 中的 Stream 实现
interface EventStream {
  // ReadableStream 包装
  [Symbol.asyncIterator](): AsyncIterator<StreamEvent>;
}

// Stream 事件类型
type StreamEvent =
  | { event: "message_start", data: MessageStart }
  | { event: "content_block_delta", data: ContentDelta }
  | { event: "message_delta", data: MessageDelta }
  | { event: "message_stop", data: MessageStop };

// 框架中的 Stream 消费
async function* streamEvents(
  response: Response
): AsyncGenerator<AgentEvent> {
  const reader = response.body?.getReader();
  if (!reader) throw new Error("No response body");
  
  const decoder = new TextDecoder();
  let buffer = "";
  
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    
    buffer += decoder.decode(value, { stream: true });
    
    // 解析 SSE 格式
    const events = parseSSE(buffer);
    buffer = events.remaining;
    
    for (const event of events.parsed) {
      yield transformToAgentEvent(event);
    }
  }
}
```

### 3.2 Loadout/Trajectory

```typescript
// Loadout: Agent 的完整配置快照
interface Loadout {
  version: string;
  timestamp: number;
  
  // 模型配置
  model: ModelConfig;
  
  // Skill 集合
  skills: Skill[];
  
  // 系统提示
  systemPrompt: string;
  
  // 工具配置
  toolConfig: {
    executionMode: ToolExecutionMode;
    timeout: number;
    retryPolicy: RetryPolicy;
  };
  
  // 上下文控制
  contextControl: ContextControlConfig;
  
  // 运行时参数
  runtimeParams: Record<string, any>;
}

// Trajectory: 执行轨迹
interface Trajectory {
  sessionId: string;
  startTime: number;
  endTime?: number;
  
  // 初始配置
  initialLoadout: Loadout;
  
  // 执行轨迹
  steps: TrajectoryStep[];
  
  // 最终结果
  result?: TrajectoryResult;
}

interface TrajectoryStep {
  turn: number;
  timestamp: number;
  
  // 输入
  input: AgentMessage[];
  
  // 输出
  output: AssistantMessage;
  
  // 工具执行
  toolCalls?: ToolCallRecord[];
  
  // 状态变更
  stateDelta?: StateChange;
  
  // 性能指标
  metrics: TurnMetrics;
}

// Loadout 保存与恢复
class LoadoutManager {
  async saveLoadout(loadout: Loadout, name: string): Promise<void> {
    await this.storage.write(`loadouts/${name}.json`, JSON.stringify(loadout));
  }
  
  async loadLoadout(name: string): Promise<Loadout> {
    const data = await this.storage.read(`loadouts/${name}.json`);
    return JSON.parse(data);
  }
  
  // 应用到 Agent
  applyToAgent(agent: Agent, loadout: Loadout): void {
    agent.state.model = loadout.model;
    agent.state.systemPrompt = loadout.systemPrompt;
    agent.state.tools = this.loadSkills(loadout.skills);
    // ...
  }
}

// Trajectory 回放
async function replayTrajectory(
  trajectory: Trajectory,
  agent: Agent
): Promise<void> {
  // 1. 恢复初始状态
  agent.reset();
  agent.state.messages = trajectory.steps[0].input;
  
  // 2. 逐步回放
  for (const step of trajectory.steps) {
    // 验证输入匹配
    assertDeepEqual(agent.state.messages, step.input);
    
    // 执行（或模拟）
    await agent.continue();
    
    // 验证输出
    const lastMessage = agent.state.messages[agent.state.messages.length - 1];
    assertDeepEqual(lastMessage, step.output);
  }
}
```

### 3.3 Middleware/Hook 机制

```typescript
// Hook 类型
interface AgentHooks {
  // 生命周期钩子
  beforeAgentStart?: (context: AgentContext) => Promise<void>;
  afterAgentEnd?: (result: AgentResult) => Promise<void>;
  
  // Turn 级钩子
  beforeTurn?: (context: AgentContext) => Promise<void>;
  afterTurn?: (result: TurnResult) => Promise<void>;
  
  // 消息钩子
  beforeMessage?: (message: AgentMessage) => Promise<AgentMessage>;
  afterMessage?: (message: AgentMessage) => Promise<void>;
  
  // 工具钩子
  beforeToolCall: BeforeToolCallHook;
  afterToolCall: AfterToolCallHook;
  
  // 上下文钩子
  transformContext: TransformContextHook;
  
  // 会话钩子
  sessionBeforeCompact?: (session: Session) => Promise<void>;
  sessionBeforeTree?: (tree: SessionTree) => Promise<void>;
}

// Hook 链执行
async function executeHookChain<T>(
  hooks: Array<(input: T) => Promise<T | void>>,
  input: T
): Promise<T> {
  let result = input;
  
  for (const hook of hooks) {
    const output = await hook(result);
    if (output !== undefined) {
      result = output;
    }
  }
  
  return result;
}

// 实际应用：权限检查
const permissionHook: BeforeToolCallHook = async ({ toolCall, args, context }) => {
  const requiredPermission = toolPermissions[toolCall.name];
  const userPermissions = context.user?.permissions || [];
  
  if (!userPermissions.includes(requiredPermission)) {
    return {
      block: true,
      reason: `Permission denied: ${requiredPermission} required for ${toolCall.name}`
    };
  }
};

// 日志 Hook
const loggingHook: AfterTurnHook = async ({ message, toolResults }) => {
  await logger.info({
    turn: currentTurn,
    messageTokens: estimateTokens(message),
    toolCalls: toolResults.length,
    duration: Date.now() - turnStartTime
  });
};

// 性能监控 Hook
const performanceHook: BeforeToolCallHook = async ({ toolCall }) => {
  performance.mark(`tool-${toolCall.id}-start`);
};

const performanceAfterHook: AfterToolCallHook = async ({ toolCall }) => {
  performance.mark(`tool-${toolCall.id}-end`);
  const duration = performance.measure(
    `tool-${toolCall.name}`,
    `tool-${toolCall.id}-start`,
    `tool-${toolCall.id}-end`
  );
  
  metrics.timing(`tool.${toolCall.name}.duration`, duration);
};
```

---

## 4. Human In The Loop (HITL)

### 4.1 HITL 架构

```
┌─────────────────────────────────────────────┐
│              Agent System                    │
│  ┌─────────────┐      ┌──────────────┐      │
│  │   Agent     │      │   Human      │      │
│  │   Loop      │◄────►│   Interface  │      │
│  └─────────────┘      └──────────────┘      │
│         │                                   │
│         ▼                                   │
│  ┌─────────────────────────────────────┐   │
│  │         Intervention Points          │   │
│  │  PreTurn → MidTurn → PostTurn        │   │
│  └─────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

### 4.2 StopReason 设计

```typescript
enum StopReason {
  // LLM 生成完成
  STOP = "stop",
  
  // 达到长度限制
  LENGTH = "length",
  
  // 调用工具（继续执行）
  TOOL_CALLS = "tool_calls",
  
  // 内容过滤
  CONTENT_FILTER = "content_filter",
  
  // 错误停止
  ERROR = "error",
  
  // 用户中止
  ABORT = "abort",
  
  // Steering 触发
  STEERING = "steering",
  
  // 需要人工审核
  HUMAN_REVIEW_REQUIRED = "human_review_required",
  
  // 上下文满
  CONTEXT_FULL = "context_full",
  
  // 超时
  TIMEOUT = "timeout",
  
  // 需要澄清
  CLARIFICATION_NEEDED = "clarification_needed",
  
  // 高风险操作
  HIGH_RISK = "high_risk"
}

// StopReason 处理策略
const stopReasonHandlers: Record<StopReason, Handler> = {
  [StopReason.STOP]: async (ctx) => {
    // 检查是否有 follow-up
    if (ctx.followUpQueue.hasItems()) {
      return { action: "continue_with_followup" };
    }
    return { action: "complete" };
  },
  
  [StopReason.HUMAN_REVIEW_REQUIRED]: async (ctx) => {
    // 暂停等待人工审核
    await pauseForHumanReview(ctx);
    return { action: "wait_for_approval" };
  },
  
  [StopReason.HIGH_RISK]: async (ctx) => {
    // 高风险操作确认
    const confirmed = await confirmWithUser(ctx.riskAssessment);
    return confirmed 
      ? { action: "continue_with_escalation" }
      : { action: "abort_with_explanation" };
  },
  
  // ...
};
```

### 4.3 干预点设计

```typescript
// PreTurn 干预：在 LLM 调用前
interface PreTurnIntervention {
  point: "pre-turn";
  
  // 检查点
  checks: [
    { type: "safety", handler: SafetyCheck },
    { type: "cost", handler: CostEstimate },
    { type: "context", handler: ContextHealth }
  ];
  
  // 干预动作
  actions: {
    approve: () => void;
    modify: (newPrompt: string) => void;
    reject: (reason: string) => void;
    escalate: (to: string) => void;
  };
}

// MidTurn 干预：在生成过程中
interface MidTurnIntervention {
  point: "mid-turn";
  
  // 实时检查
  streamFilter: (delta: string) => FilterResult;
  
  // 干预能力
  actions: {
    steer: (message: string) => void;      // 发送 steering
    abort: () => void;                      // 中止生成
    pause: () => void;                     // 暂停等待
  };
}

// PostTurn 干预：在工具执行前
interface PostTurnIntervention {
  point: "post-turn";
  
  // 审核内容
  review: {
    assistantMessage: AssistantMessage;
    toolCalls: ToolCall[];
    toolResults?: ToolResult[];
  };
  
  // 决策
  actions: {
    approve: () => void;
    editTools: (newToolCalls: ToolCall[]) => void;
    skipTools: () => void;
    rerunWithContext: (additionalContext: string) => void;
  };
}

// 实现示例
class HITLController {
  async checkPreTurn(context: AgentContext): Promise<InterventionResult> {
    // 安全检查
    const safety = await this.safetyCheck(context.messages);
    if (!safety.safe) {
      return {
        requireIntervention: true,
        point: "pre-turn",
        reason: "safety_concern",
        details: safety.concerns
      };
    }
    
    // 成本预估
    const cost = await this.estimateCost(context);
    if (cost.estimated > COST_THRESHOLD) {
      return {
        requireIntervention: true,
        point: "pre-turn",
        reason: "high_cost",
        details: cost
      };
    }
    
    return { requireIntervention: false };
  }
  
  async handleMidTurn(delta: string, signal: AbortSignal): Promise<void> {
    // 实时内容过滤
    if (this.contentFilter.detect(delta)) {
      // 触发 steering
      this.agent.steer({
        role: "user",
        content: "Please avoid that topic.",
        timestamp: Date.now()
      });
    }
  }
}
```

### 4.4 两种 HITL 模式

#### 模式 A: Stop and Resume

```typescript
// 暂停当前 Agent，等待人工决策
interface StopAndResumeHITL {
  mode: "stop-and-resume";
  
  // 暂停点
  suspend: () => Promise<SuspensionPoint>;
  
  // 保存完整状态
  checkpoint: {
    context: AgentContext;
    toolQueue: ToolCall[];
    steeringQueue: AgentMessage[];
    timestamp: number;
  };
  
  // 等待人工输入
  awaitHumanInput: (options: HumanInputOptions) => Promise<HumanDecision>;
  
  // 恢复执行
  resume: (decision: HumanDecision) => Promise<void>;
}

// 使用场景：高风险操作确认
async function handleHighRiskOperation(
  toolCall: ToolCall,
  context: AgentContext
): Promise<void> {
  // 1. 暂停
  const suspension = await hitl.suspend({
    reason: "high_risk_operation",
    context: {
      toolName: toolCall.name,
      args: toolCall.args,
      riskLevel: "high"
    }
  });
  
  // 2. 等待人工确认
  const decision = await hitl.awaitHumanInput({
    type: "confirm",
    message: `Allow ${toolCall.name} with args: ${JSON.stringify(toolCall.args)}?`,
    options: ["approve", "reject", "modify"]
  });
  
  // 3. 处理决策
  switch (decision.choice) {
    case "approve":
      await suspension.resume({ action: "continue" });
      break;
    case "reject":
      await suspension.resume({ 
        action: "abort",
        reason: "User rejected high-risk operation"
      });
      break;
    case "modify":
      await suspension.resume({
        action: "modify",
        modifiedToolCall: decision.modifiedArgs
      });
      break;
  }
}
```

#### 模式 B: Hang & Wait for Decision

```typescript
// 挂起等待，不停止 Agent
interface HangAndWaitHITL {
  mode: "hang-and-wait";
  
  // 设置等待状态
  setWaitingState: (state: WaitingState) => void;
  
  // 非阻塞等待
  waitForDecision: () => Promise<HumanDecision>;
  
  // 后台保持连接
  keepAlive: () => void;
  
  // 决策后注入
  injectDecision: (decision: HumanDecision) => void;
}

// 使用场景：澄清问题
async function handleClarificationNeeded(
  assistantMessage: AssistantMessage
): Promise<void> {
  // 1. 设置等待状态（UI 显示等待指示器）
  hitl.setWaitingState({
    status: "awaiting_clarification",
    message: assistantMessage.content,
    context: "Please clarify your intent"
  });
  
  // 2. 非阻塞等待（Agent 保持空闲）
  const clarification = await hitl.waitForDecision();
  
  // 3. 注入澄清作为 steering
  hitl.injectDecision({
    type: "steering",
    message: {
      role: "user",
      content: clarification.answer,
      timestamp: Date.now()
    }
  });
}
```

**模式对比**:

| 特性 | Stop and Resume | Hang & Wait |
|-----|-----------------|-------------|
| 状态 | Agent 完全停止 | Agent 挂起/空闲 |
| 资源 | 可释放 | 保持连接 |
| 适用 | 复杂决策、长时间等待 | 快速澄清、实时交互 |
| 恢复 | 从 checkpoint 恢复 | 直接注入 steering |
| 成本 | 低（可释放资源）| 高（保持连接）|

---

## 5. 评测与指标

### 5.1 Metric 体系

```typescript
// 评测指标分类
interface AgentMetrics {
  // ========== 功能性指标 ==========
  functional: {
    // 任务完成率
    taskCompletionRate: number;
    
    // 正确性（有标准答案时）
    accuracy: number;
    
    // 工具使用正确率
    toolUsageCorrectness: number;
    
    // 上下文理解准确率
    contextUnderstanding: number;
  };
  
  // ========== 效率指标 ==========
  efficiency: {
    // 平均 Turn 数
    avgTurns: number;
    
    // 平均 Token 消耗
    avgTokens: number;
    
    // 平均工具调用次数
    avgToolCalls: number;
    
    // 响应延迟（首 token 时间）
    timeToFirstToken: number;
    
    // 总执行时间
    totalExecutionTime: number;
    
    // 上下文压缩次数
    compactionCount: number;
  };
  
  // ========== 可靠性指标 ==========
  reliability: {
    // 成功率（无错误完成）
    successRate: number;
    
    // 错误恢复率
    recoveryRate: number;
    
    // 超时率
    timeoutRate: number;
    
    // 一致性（相同输入相同输出）
    consistency: number;
  };
  
  // ========== 用户体验指标 ==========
  ux: {
    // 用户满意度评分
    userSatisfaction: number;
    
    // 需要人工干预的比例
    humanInterventionRate: number;
    
    // 用户修正次数
    correctionRate: number;
    
    // 对话流畅度
    conversationFluency: number;
  };
  
  // ========== 安全指标 ==========
  safety: {
    // 有害内容生成率
    harmfulContentRate: number;
    
    // PII 泄露率
    piiLeakRate: number;
    
    // 权限越界率
    permissionViolationRate: number;
    
    // 高风险操作比例
    highRiskOperationRate: number;
  };
}
```

### 5.2 评测流程

#### Offline 评测

```typescript
// Offline 评测流程
async function offlineEvaluation(
  testCases: TestCase[],
  agentConfig: AgentConfig
): Promise<OfflineReport> {
  const results: TestResult[] = [];
  
  for (const testCase of testCases) {
    // 1. 准备 Agent
    const agent = new Agent(agentConfig);
    
    // 2. 运行测试
    const result = await runTestCase(agent, testCase);
    
    // 3. 评分
    const score = await scoreResult(result, testCase.expected);
    
    results.push({ testCase, result, score });
  }
  
  // 4. 生成报告
  return generateReport(results);
}

// 测试用例类型
interface TestCase {
  id: string;
  category: "single-turn" | "multi-turn" | "tool-use" | "safety";
  
  // 输入
  initialMessages: AgentMessage[];
  
  // 预期输出（多种匹配方式）
  expected?: {
    // 精确匹配
    exact?: AgentMessage[];
    
    // 包含检查
    contains?: string[];
    
    // 工具调用序列
    toolSequence?: string[];
    
    // 自定义验证
    validator?: (result: TestResult) => boolean;
  };
  
  // 评测标准
  criteria: EvaluationCriteria;
  
  // 元数据
  difficulty: "easy" | "medium" | "hard";
  tags: string[];
}

// 评测框架
class EvaluationFramework {
  // 单轮评测
  async evaluateSingleTurn(
    prompt: string,
    expected: string
  ): Promise<SingleTurnResult> {
    const response = await this.agent.prompt(prompt);
    
    return {
      exactMatch: response === expected,
      semanticMatch: await this.semanticSimilarity(response, expected),
      bleuScore: calculateBleu(response, expected),
      latency: measureLatency()
    };
  }
  
  // 多轮评测
  async evaluateMultiTurn(
    conversation: ConversationScript
  ): Promise<MultiTurnResult> {
    const agent = new Agent(this.config);
    
    for (const turn of conversation.turns) {
      await agent.prompt(turn.userMessage);
      
      // 验证助手回复
      const lastMessage = getLastAssistantMessage(agent);
      assertMatches(lastMessage, turn.expectedAssistantMessage);
      
      // 验证工具调用（如有）
      if (turn.expectedToolCalls) {
        assertToolCalls(agent, turn.expectedToolCalls);
      }
    }
    
    return {
      completed: true,
      turnCount: conversation.turns.length,
      metrics: extractMetrics(agent)
    };
  }
  
  // 回归测试
  async regressionTest(
    baseline: TestSuite,
    current: AgentConfig
  ): Promise<RegressionReport> {
    const baselineResults = await this.loadBaseline(baseline);
    const currentResults = await offlineEvaluation(
      baseline.testCases,
      current
    );
    
    return this.compareResults(baselineResults, currentResults);
  }
}
```

#### Online 评测

```typescript
// Online 评测（生产环境）
interface OnlineEvaluation {
  // A/B 测试
  abTest: {
    variantA: AgentConfig;
    variantB: AgentConfig;
    trafficSplit: [number, number];  // [0.5, 0.5]
    duration: number;  // 天数
    successMetric: string;
  };
  
  // 影子模式
  shadowMode: {
    production: AgentConfig;
    candidate: AgentConfig;
    compareMetrics: string[];
    sampleRate: number;  // 抽样比例
  };
  
  // 金丝雀发布
  canary: {
    stages: [
      { traffic: 0.01, duration: 86400 },   // 1%
      { traffic: 0.05, duration: 86400 },   // 5%
      { traffic: 0.2, duration: 172800 },  // 20%
      { traffic: 1.0, duration: 0 }         // 100%
    ];
    rollbackThreshold: {
      errorRate: 0.05,
      latencyP99: 5000,
    };
  };
}

// Online Metric 采集
class OnlineMetricsCollector {
  // 实时指标
  collectRealtimeMetrics(event: AgentEvent): void {
    switch (event.type) {
      case "turn_end":
        this.metrics.increment("turn.completed");
        this.metrics.timing("turn.duration", event.duration);
        this.metrics.gauge("turn.tool_calls", event.toolResults.length);
        break;
        
      case "tool_execution_end":
        if (event.isError) {
          this.metrics.increment("tool.errors");
        }
        this.metrics.timing(`tool.${event.toolName}.duration`, event.duration);
        break;
        
      case "agent_end":
        this.metrics.increment("session.completed");
        this.metrics.gauge("session.turns", event.messages.length);
        break;
    }
  }
  
  // 会话级指标
  collectSessionMetrics(session: Session): SessionMetrics {
    return {
      duration: session.endTime - session.startTime,
      turnCount: session.messages.filter(m => m.role === "assistant").length,
      toolCallCount: session.toolCalls.length,
      compactionCount: session.compactions.length,
      hadIntervention: session.interventions.length > 0,
      userRating: session.feedback?.rating
    };
  }
}
```

### 5.3 新特性上线评测

```typescript
// 新特性上线流程
interface FeatureReleaseProcess {
  // 阶段 1: 单元测试
  unitTests: {
    coverage: number;  // >80%
    pass: boolean;
  };
  
  // 阶段 2: 集成测试
  integrationTests: {
    scenarios: TestScenario[];
    allPass: boolean;
  };
  
  // 阶段 3: 沙盒评测
  sandboxEvaluation: {
    dataset: string;  // "internal-test-v2"
    metrics: {
      baseline: number;
      candidate: number;
      improvement: number;  // >5%
    };
  };
  
  // 阶段 4: A/B 测试
  abTest: {
    duration: number;  // 7 days
    sampleSize: number;
    pValue: number;  // <0.05
    significant: boolean;
  };
  
  // 阶段 5: 灰度发布
  gradualRollout: {
    stages: RolloutStage[];
    monitoring: AlertConfig;
  };
  
  // 阶段 6: 全量发布
  fullRelease: {
    date: Date;
    rollbackPlan: RollbackPlan;
  };
}

// 自动化评测流水线
async function runEvaluationPipeline(feature: Feature): Promise<PipelineResult> {
  // 1. 静态检查
  const staticCheck = await runStaticAnalysis(feature.code);
  if (!staticCheck.pass) return { stage: "static", status: "failed" };
  
  // 2. 单元测试
  const unitTest = await runUnitTests(feature.tests);
  if (unitTest.coverage < 0.8) return { stage: "unit", status: "failed" };
  
  // 3. 集成测试
  const integration = await runIntegrationTests(feature.scenarios);
  if (!integration.allPass) return { stage: "integration", status: "failed" };
  
  // 4. 沙盒评测
  const sandbox = await runSandboxEvaluation(feature);
  if (sandbox.metrics.improvement < 0.05) {
    return { stage: "sandbox", status: "needs_review" };
  }
  
  // 5. A/B 测试
  const abTest = await startABTest(feature);
  
  return { stage: "ab_test", status: "running", testId: abTest.id };
}
```

---

## 附录：面试常见问题速查

### Q1: ReAct 和 PlanAct 的区别？
**A**: ReAct 是 Thought → Action → Observation 的循环；PlanAct 是先 Plan 再 Execute。pi-agent-core 中 ReAct 是默认模式，PlanAct 可通过 `create_plan` 工具实现。

### Q2: MultiAgent 有哪些协作模式？
**A**: 四种：
1. Agent As Tool（SubAgent）
2. Agent Handoff（上下文传递）
3. Leader & Workers（并行分发）
4. Agent2Agent（双向对话）

### Q3: LoopControl 包含什么？
**A**: ContextControl（transformContext, convertToLlm, hooks）和 RunControl（shouldStopAfterTurn, prepareNextTurn）。

### Q4: Skill 是什么？
**A**: Experience 的编排 = Prompt + Tools + Context + Examples，比 Tool 粒度更大。

### Q5: HITL 两种模式区别？
**A**: Stop and Resume（完全停止，释放资源）vs Hang & Wait（挂起保持连接）。

### Q6: 主要评测指标？
**A**: 功能性（完成率、准确率）、效率（Turn 数、Token 数）、可靠性（成功率）、用户体验（满意度）、安全（有害内容率）。
