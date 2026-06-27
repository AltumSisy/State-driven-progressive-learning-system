# AgentSession 会话创建与管理架构详解

## 概述

coding-agent 的会话系统采用分层架构，将**基础设施服务**与**会话实例**分离，通过服务工厂模式实现灵活的会话管理。

核心架构分为三层：
- **服务层**：`createAgentSessionServices` - 创建可复用的基础设施
- **会话层**：`createAgentSessionFromServices` - 从服务创建会话实例
- **运行层**：`AgentSession` - 实际的会话运行实例

---

## 一、createAgentSessionServices - 服务工厂

### 1.1 核心作用

创建与工作目录（cwd）绑定的**可复用运行时服务**。

### 1.2 创建的服务内容

```typescript
interface AgentSessionServices {
  cwd: string;                  // 工作目录
  agentDir: string;             // Agent 配置目录（~/.pi/agent）
  authStorage: AuthStorage;     // 认证存储（API keys）
  settingsManager: SettingsManager;  // 设置管理器
  modelRegistry: ModelRegistry;      // 模型注册表
  resourceLoader: ResourceLoader;    // 资源加载器（扩展、MCP）
  diagnostics: Diagnostic[];    // 创建过程中的诊断信息
}
```

### 1.3 服务特点

| 特性 | 说明 |
|------|------|
| **可复用** | 一次创建，可在多个会话间共享 |
| **cwd 绑定** | 与特定工作目录关联，cwd 改变需重建 |
| **会话无关** | 不包含会话特定的配置（模型、工具等） |
| **基础设施** | 提供"环境"而非"应用" |

### 1.4 创建流程

```typescript
async function createAgentSessionServices(options) {
  // 1. 初始化核心服务
  const authStorage = AuthStorage.create(agentDir + "auth.json");
  const settingsManager = SettingsManager.create(cwd, agentDir);
  const modelRegistry = ModelRegistry.create(authStorage, agentDir + "models.json");
  
  // 2. 创建资源加载器
  const resourceLoader = new DefaultResourceLoader({
    cwd,
    agentDir,
    settingsManager
  });
  await resourceLoader.reload(); // 加载扩展、MCP服务器
  
  // 3. 注册扩展提供的模型提供者
  for (const { name, config } of extensions.pendingProviderRegistrations) {
    modelRegistry.registerProvider(name, config);
  }
  
  // 4. 应用扩展标志值
  applyExtensionFlagValues(resourceLoader, options.extensionFlagValues);
  
  // 5. 返回服务集合
  return {
    cwd,
    agentDir,
    authStorage,
    settingsManager,
    modelRegistry,
    resourceLoader,
    diagnostics
  };
}
```

### 1.5 使用场景

```typescript
// 场景1：创建项目服务
const services = await createAgentSessionServices({
  cwd: "/project/path",
  extensionFlagValues: new Map([["debug", true]])
});

// 场景2：检查创建过程中的问题
if (services.diagnostics.some(d => d.type === "error")) {
  console.error("服务创建失败:", diagnostics);
  return;
}

// 场景3：服务可跨会话复用
const session1 = await createAgentSessionFromServices({ services, ... });
const session2 = await createAgentSessionFromServices({ services, ... });
```

---

## 二、createAgentSessionFromServices - 会话工厂

### 2.1 核心作用

基于已创建的服务，创建**会话特定的 AgentSession 实例**。

### 2.2 输入参数

```typescript
interface CreateAgentSessionFromServicesOptions {
  services: AgentSessionServices;  // 已创建的服务
  
  // 会话特定配置（每次可能不同）
  sessionManager?: SessionManager; // 会话管理器
  model?: Model;                   // 使用的模型
  thinkingLevel?: ThinkingLevel;   // 思考级别
  tools?: string[];                // 启用的工具列表
  noTools?: "all" | "builtin";     // 工具抑制模式
  customTools?: ToolDefinition[];  // 自定义工具
  sessionStartEvent?: SessionStartEvent; // 会话启动事件
}
```

### 2.3 内部实现

```typescript
async function createAgentSessionFromServices(options) {
  // 解构服务
  const { cwd, agentDir, authStorage, settingsManager, 
          modelRegistry, resourceLoader } = options.services;
  
  // 调用 SDK 的 createAgentSession
  return createAgentSession({
    cwd,
    agentDir,
    authStorage,
    settingsManager,
    modelRegistry,
    resourceLoader,
    
    // 会话特定配置
    sessionManager: options.sessionManager,
    model: options.model,
    thinkingLevel: options.thinkingLevel,
    tools: options.tools,
    noTools: options.noTools,
    customTools: options.customTools,
    sessionStartEvent: options.sessionStartEvent
  });
}
```

### 2.4 实际创建逻辑（SDK 的 createAgentSession）

```typescript
async function createAgentSession(options) {
  // 1. 模型选择与恢复
  let model = options.model;
  if (!model && hasExistingSession) {
    // 从历史恢复模型
    model = modelRegistry.find(existingSession.model);
  }
  if (!model) {
    // 从设置或可用模型中选择
    model = await findInitialModel({ ... });
  }
  
  // 2. Thinking Level 处理
  let thinkingLevel = options.thinkingLevel;
  if (thinkingLevel === undefined && hasExistingSession) {
    // 从历史恢复
    thinkingLevel = existingSession.thinkingLevel;
  }
  // Clamp 到模型能力
  thinkingLevel = clampThinkingLevel(model, thinkingLevel);
  
  // 3. 工具初始化
  const defaultActiveTools = ["read", "bash", "edit", "write"];
  const initialActiveTools = options.tools ?? 
    (options.noTools === "all" ? [] : defaultActiveTools);
  
  // 4. 创建 Agent 实例（核心 AI 引擎）
  const agent = new Agent({
    initialState: {
      model,
      thinkingLevel,
      tools: []
    },
    streamFn: async (model, context, options) => {
      // 获取 API Key
      const auth = await modelRegistry.getApiKeyAndHeaders(model);
      // 调用模型 API
      return streamSimple(model, context, {
        apiKey: auth.apiKey,
        timeoutMs: retrySettings.timeoutMs,
        maxRetries: retrySettings.maxRetries
      });
    },
    // ... 其他配置
  });
  
  // 5. 恢复历史消息
  if (hasExistingSession) {
    agent.state.messages = existingSession.messages;
  }
  
  // 6. 创建 AgentSession 实例
  const session = new AgentSession({
    agent,
    sessionManager,
    settingsManager,
    cwd,
    modelRegistry,
    resourceLoader,
    initialActiveToolNames,
    customTools,
    // ...
  });
  
  // 7. 返回结果
  return {
    session,              // AgentSession 实例
    extensionsResult,     // 扩展加载结果
    modelFallbackMessage  // 模型降级警告
  };
}
```

---

## 三、两者的区别与联系

### 3.1 职责分离

| 层级 | 函数 | 职责 | 输出 | 类比 |
|------|------|------|------|------|
| **服务层** | `createAgentSessionServices` | 基础设施初始化 | 服务集合 | 建造厨房 |
| **会话层** | `createAgentSessionFromServices` | 会话实例创建 | AgentSession | 准备一顿饭 |

### 3.2 创建成本对比

| 项目 | Services 创建 | Session 创建 |
|------|--------------|--------------|
| **成本** | 高（读文件、加载扩展） | 低（主要是配置组装） |
| **频率** | 低（cwd 改变时） | 高（每个会话） |
| **复用性** | 高（跨会话共享） | 低（会话特定） |

### 3.3 依赖关系

```
createAgentSessionServices (服务工厂)
    ↓ 输出
AgentSessionServices (服务集合)
    ↓ 输入到
createAgentSessionFromServices (会话工厂)
    ↓ 调用
createAgentSession (SDK)
    ↓ 输出
AgentSession (会话实例)
```

### 3.4 为什么需要分离？

#### 原因 1：服务可复用

```typescript
// 一次创建服务
const services = await createAgentSessionServices({ cwd: "/project" });

// 多次创建会话，复用服务
const devSession = await createAgentSessionFromServices({
  services,
  model: devModel,
  tools: ["read", "bash"]
});

const testSession = await createAgentSessionFromServices({
  services,
  model: testModel,
  tools: ["read"]
});
```

#### 原因 2：依赖解析顺序

```typescript
// 先创建服务
const services = await createAgentSessionServices({ cwd });

// 查询服务状态，决定会话参数
const availableModels = services.modelRegistry.getAvailableModels();
const defaultModel = services.settingsManager.getDefaultModel();

// 再创建会话
const session = await createAgentSessionFromServices({
  services,
  model: chosenModel  // 基于服务状态选择
});
```

#### 原因 3：工作目录切换

```typescript
// cwd 改变 → 服务重建
const newServices = await createAgentSessionServices({ cwd: newCwd });

// 但会话创建逻辑不变
const session = await createAgentSessionFromServices({
  services: newServices,
  // ... 其他配置
});
```

---

## 四、AgentSession 核心能力

AgentSession 是你操作 Agent 的**主接口**，封装了所有会话操作。

### 4.1 核心交互能力

```typescript
// 发送消息给 Agent
await session.prompt("帮我写一个函数", {
  images: [...],              // 图片附件
  streamingBehavior: "steer", // 中断当前执行
  source: "interactive"       // 来源标记
});

// 中断当前执行
await session.abort();
```

### 4.2 会话管理能力

```typescript
// 切换会话
await session.switchSession(sessionId, { loadIfExists: true });

// 创建分支（探索不同方案）
await session.branch({ name: "feature-branch" });

// 设置会话名称
session.setSessionName("my-session");

// 获取会话统计
const stats = session.getSessionStats();
// {
//   userMessages: 10,
//   assistantMessages: 8,
//   toolCalls: 15,
//   tokens: { input: 1000, output: 500, ... },
//   cost: 0.05,
//   contextUsage: { used: 50000, total: 200000 }
// }

// 导出会话
await session.exportSession(format: "html");
```

### 4.3 工具管理能力

```typescript
// 获取当前启用的工具
const activeTools = session.getActiveToolNames();

// 获取所有可用工具
const allTools = session.getAllTools();

// 设置启用的工具
session.setActiveToolsByName(["read", "bash", "edit"]);

// 获取工具定义
const toolDef = session.getToolDefinition("read");
```

### 4.4 模型管理能力

```typescript
// 切换模型（向前/向后）
const result = await session.cycleModel("forward");
// { model: newModel, thinkingLevel: "high", isScoped: true }

// 获取当前模型
const model = session.model;

// 获取思考级别
const level = session.getThinkingLevel();

// 设置思考级别
session.setThinkingLevel("high");

// 获取可用思考级别
const levels = session.getAvailableThinkingLevels();
```

### 4.5 压缩管理能力

```typescript
// 手动压缩上下文
const result = await session.compact("保留最近的代码修改");

// 中断压缩
session.abortCompaction();

// 启用/禁用自动压缩
session.setAutoCompactionEnabled(true);

// 获取上下文使用情况
const usage = session.getContextUsage();
// { usedTokens: 50000, maxTokens: 200000, percentage: 25 }
```

### 4.6 消息队列能力

```typescript
// 添加中断消息（立即执行）
session.queueSteeringMessage("换个方法实现");

// 添加后续消息（等当前完成后执行）
session.queueFollowUpMessage("继续下一个任务");

// 获取队列状态
const steering = session.getSteeringMessages();
const followUp = session.getFollowUpMessages();

// 清空队列
session.clearQueue();
```

### 4.7 Bash 执行能力

```typescript
// 执行 Bash 命令
const result = await session.executeBash("npm test", (chunk) => {
  console.log(chunk); // 实时输出
});
// { exitCode: 0, stdout: "...", stderr: "..." }

// 中断 Bash 执行
session.abortBash();
```

### 4.8 状态访问能力

```typescript
// 访问 Agent 状态
const state = session.state;
// {
//   messages: [...],
//   model: {...},
//   thinkingLevel: "medium",
//   tools: [...]
// }

// 获取工作目录
const cwd = session.cwd;

// 获取消息历史
const messages = session.messages;

// 获取最后的助手消息
const lastText = session.getLastAssistantText();
```

### 4.9 事件订阅能力

```typescript
// 订阅会话事件
const unsubscribe = session.subscribe((event) => {
  switch (event.type) {
    case "message_start":
      console.log("消息开始", event.message);
      break;
    case "message_update":
      console.log("消息更新", event.content);
      break;
    case "message_end":
      console.log("消息结束");
      break;
    case "tool_execution_start":
      console.log("工具执行", event.toolName);
      break;
    case "tool_execution_end":
      console.log("工具完成", event.result);
      break;
    case "compaction_start":
      console.log("开始压缩", event.reason);
      break;
    case "compaction_end":
      console.log("压缩完成", event.result);
      break;
    case "thinking_level_changed":
      console.log("思考级别改变", event.level);
      break;
    case "auto_retry_start":
      console.log("开始重试", event.attempt);
      break;
  }
});

// 取消订阅
unsubscribe();
```

### 4.10 扩展系统能力

```typescript
// 重载扩展
await session.reloadExtensions();

// 检查是否有扩展处理器
const hasHandler = session.hasExtensionHandlers("tool_call");
```

---

## 五、SessionManager 在 AgentSession 中的定位

### 5.1 架构位置

```
┌─────────────────────────────────────────────────────────────┐
│                      AgentSession                            │
│  (业务层：处理对话、工具调用、压缩、扩展等)                    │
│                                                              │
│  ├─ agent: Agent          ← AI 模型交互引擎                  │
│  ├─ sessionManager ──────→│ 持久化层：会话历史、分支、存储    │
│  ├─ settingsManager       ← 配置管理                         │
│  └─ resourceLoader        ← 资源加载                         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 SessionManager 核心职责

```typescript
class SessionManager {
  // 1. 持久化状态
  private sessionId: string;
  private sessionFile: string;      // 会话文件路径
  private fileEntries: FileEntry[]; // 所有历史条目
  
  // 2. 树结构状态（支持分支）
  private byId: Map<string, SessionEntry>;  // ID → 条目映射
  private leafId: string | null;             // 当前叶子节点
  
  // 3. 主要方法
  appendMessage()           // 追加消息到历史
  appendModelChange()       // 记录模型切换
  appendThinkingLevelChange() // 记录思考级别变化
  appendCompaction()        // 记录压缩操作
  
  getBranch()               // 获取当前分支路径
  buildSessionContext()     // 构建发送给 LLM 的上下文
  
  branch()                  // 创建新分支
  branchWithSummary()       // 带摘要的分支
  createBranchedSession()   // 创建分支会话文件
}
```

### 5.3 AgentSession 如何使用 SessionManager

从代码追踪来看，SessionManager 在 AgentSession 中扮演**持久化管理器**的角色：

#### 1️⃣ 持久化消息历史

```typescript
// AgentSession 收到消息后，调用 SessionManager 保存
sessionManager.appendMessage(event.message);
```

#### 2️⃣ 记录状态变化

```typescript
// 切换模型时记录
sessionManager.appendModelChange("anthropic", "claude-sonnet-4");

// 改变思考级别时记录
sessionManager.appendThinkingLevelChange("high");
```

#### 3️⃣ 管理压缩

```typescript
// 压缩后记录摘要
sessionManager.appendCompaction(
  summary, 
  firstKeptEntryId, 
  tokensBefore
);

// 获取最新压缩条目
const compactionEntry = getLatestCompactionEntry(
  sessionManager.getBranch()
);
```

#### 4️⃣ 构建 LLM 上下文

```typescript
// 从历史条目构建发送给 LLM 的上下文
const sessionContext = sessionManager.buildSessionContext();
// {
//   messages: [...],  // 发送给模型的消息
//   model: {...},     // 当前模型信息
//   thinkingLevel: "medium"
// }
```

#### 5️⃣ 分支管理

```typescript
// 创建分支（用于会话树导航）
const summaryId = sessionManager.branchWithSummary(
  branchFromId, 
  summary, 
  details
);

// 获取当前分支的所有条目
const branchEntries = sessionManager.getBranch();
```

#### 6️⃣ 暴露信息给外部

```typescript
// AgentSession 暴露 SessionManager 的只读访问
get sessionId() { return sessionManager.getSessionId(); }
get sessionName() { return sessionManager.getSessionName(); }
get sessionFile() { return sessionManager.getSessionFile(); }
```

### 5.4 组件职责对比

| 组件 | 职责 | 类比 |
|------|------|------|
| **AgentSession** | 业务逻辑层 | 浏览器标签页 |
| **SessionManager** | 持久化层 | 历史记录管理器 |
| **Agent** | AI 引擎 | 渲染引擎 |

### 5.5 类比说明

```
浏览器标签页
├─ 渲染引擎 ← 对应 Agent（执行 AI 交互）
├─ 历史记录 ← 对应 SessionManager（存储历史）
└─ 用户界面 ← 对应 AgentSession（协调所有操作）
```

**具体场景：**

1. **发送消息**
   - AgentSession: 协调流程
   - Agent: 发送给 LLM
   - SessionManager: 保存到文件

2. **切换模型**
   - AgentSession: 处理切换逻辑
   - Agent: 更新模型
   - SessionManager: 记录变更

3. **创建分支**
   - AgentSession: 协调分支逻辑
   - SessionManager: 创建新分支、保存树结构

4. **压缩上下文**
   - AgentSession: 触发压缩
   - SessionManager: 保存压缩摘要、修剪历史

### 5.6 关系总结

**SessionManager = 会话历史的数据库**

- AgentSession 是**操作接口**（你调用它的方法）
- SessionManager 是**存储引擎**（AgentSession 调用它来持久化）
- 两者是**组合关系**（AgentSession 拥有一个 SessionManager）

```typescript
// 你使用 AgentSession
await session.prompt("hello");

// 内部流程
session.prompt() 
  → agent.stream()           // Agent 处理
  → sessionManager.append()  // SessionManager 保存
```

---

## 六、完整使用示例

### 6.1 标准创建流程

```typescript
// 1. 创建服务（基础设施）
const services = await createAgentSessionServices({
  cwd: "/project/path",
  extensionFlagValues: new Map([["debug", true]])
});

// 2. 检查诊断信息
if (services.diagnostics.some(d => d.type === "error")) {
  console.error("服务创建失败");
  return;
}

// 3. 创建会话管理器
const sessionManager = SessionManager.create(cwd, sessionDir);

// 4. 从服务创建会话
const { session, extensionsResult, modelFallbackMessage } = 
  await createAgentSessionFromServices({
    services,
    sessionManager,
    model: services.modelRegistry.find("anthropic", "claude-sonnet-4"),
    thinkingLevel: "high",
    tools: ["read", "bash", "edit", "write"]
  });

// 5. 检查模型降级警告
if (modelFallbackMessage) {
  console.warn(modelFallbackMessage);
}

// 6. 订阅事件
const unsubscribe = session.subscribe((event) => {
  if (event.type === "message_update") {
    process.stdout.write(event.content);
  }
});

// 7. 发送消息
await session.prompt("分析这个项目的架构");

// 8. 切换模型
await session.cycleModel();

// 9. 执行命令
const result = await session.executeBash("npm run build");

// 10. 压缩上下文（如果接近上限）
if (session.getContextUsage().percentage > 80) {
  await session.compact("保留最近的代码修改");
}

// 11. 创建分支探索不同方案
await session.branch({ name: "alternative-approach" });

// 12. 清理
unsubscribe();
await session.shutdown();
```

### 6.2 多会话共享服务

```typescript
// 一次创建服务
const services = await createAgentSessionServices({ cwd: "/project" });

// 创建多个会话，复用同一套服务
const devSession = await createAgentSessionFromServices({
  services,
  model: devModel,
  tools: ["read", "bash", "edit", "write"]
});

const testSession = await createAgentSessionFromServices({
  services,
  model: testModel,
  tools: ["read"]  // 只读模式
});

const docSession = await createAgentSessionFromServices({
  services,
  model: docModel,
  tools: ["read", "write"]  // 文档编写
});
```

---

## 七、总结

### 架构设计理念

1. **服务与会话分离**
   - 服务层：可复用的基础设施
   - 会话层：会话特定的配置和实例

2. **职责清晰划分**
   - `createAgentSessionServices`: 创建环境
   - `createAgentSessionFromServices`: 创建应用
   - `AgentSession`: 运行应用
   - `SessionManager`: 持久化历史

3. **灵活性与复用**
   - 服务可在多个会话间共享
   - 会话可以有不同的模型、工具配置
   - 工作目录切换时只需重建服务

### 关键要点

- **Services** = 环境（水电气、设备），建一次用很久
- **Session** = 应用（食材、菜谱），每次可能不同
- **AgentSession** = 主接口，你所有操作都通过它
- **SessionManager** = 持久化引擎，AgentSession 调用它保存历史

这种分层架构让 coding-agent 能够灵活地支持：
- 多模型切换
- 工具动态配置
- 会话分支与合并
- 上下文压缩
- 扩展系统集成

同时保持服务层的稳定和可复用。