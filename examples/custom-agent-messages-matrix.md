# CustomAgentMessages 调用矩阵

## 场景 × 处理阶段矩阵

| 场景 | 插入时机 | convertToLlm | subscribe 处理 | 发给 LLM |
|------|---------|--------------|--------------|---------|
| **1. 加载状态** | 工具执行前 | `filter(m => m.role !== "loading")` | `message_start` → `ui.showSpinner()` | ❌ |
| **2. 文件附件** | 用户上传后 | `flatMap` 转为标准 user message | `message_start` → `ui.showAttachment()` | ✅ (转换后) |
| **3. 思考过程** | tool `onUpdate` 回调 | `filter` 或转为 system message | `message_update` → `ui.showThinking()` | ❌ / 可选 |
| **4. 系统通知** | transformContext 中 | `flatMap` 转为 user message | `message_start` → `ui.showNotice()` | ✅ (转换后) |
| **5. 协作标记** | 外部事件触发 | `flatMap` 转为 user message | `message_start` → `ui.showCollaborator()` | ✅ (转换后) |

---

## 详细调用流程图

### 场景 1: 加载状态 (UI-only)

```
┌─────────────────────────────────────────────────────────────┐
│  触发: 用户触发长时间操作 (如搜索大文件)                       │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 1: 插入 loading 消息                                    │
│  agent.state.messages.push({                                  │
│    role: "loading",                                          │
│    id: "search-files",                                       │
│    text: "正在搜索文件..."                                      │
│  });                                                          │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 2: 触发 message_start 事件                              │
│  agent.subscribe((event) => {                                 │
│    if (event.type === "message_start") {                      │
│      const msg = event.message;                               │
│      if (msg.role === "loading") {                            │
│        ui.showSpinner(msg.id, msg.text);  ◄── 渲染到 UI        │
│      }                                                        │
│    }                                                          │
│  });                                                          │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 3: LLM 调用前 (convertToLlm)                           │
│  convertToLlm: (messages) =>                                  │
│    messages.filter(m => m.role !== "loading")  ◄── 过滤掉       │
│                                                               │
│  结果: loading 消息不发给 LLM                                  │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 4: 工具执行完成                                        │
│  - 可选: 从 messages 中移除 loading 消息                        │
│  - 或保留在消息历史中供调试查看                                │
└─────────────────────────────────────────────────────────────┘
```

---

### 场景 2: 文件附件 (转换发送)

```
┌─────────────────────────────────────────────────────────────┐
│  触发: 用户上传文件                                           │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 1: 插入 attachment 消息                                 │
│  agent.state.messages.push({                                  │
│    role: "attachment",                                         │
│    fileName: "api.yaml",                                      │
│    content: "openapi: 3.0.0..."                               │
│  });                                                          │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 2: UI 显示附件                                          │
│  if (msg.role === "attachment") {                             │
│    ui.showAttachment(msg.fileName, msg.size);                 │
│  }                                                            │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 3: convertToLlm 转换                                    │
│  convertToLlm: (messages) => messages.flatMap(m => {          │
│    if (m.role === "attachment") {                              │
│      return [{                                                │
│        role: "user",                                          │
│        content: `我上传了 ${m.fileName}:\n${m.content}`         │
│      }];                                                      │
│    }                                                          │
│    return [m];                                                │
│  });                                                          │
│                                                               │
│  结果: 转为标准 user message 发给 LLM                          │
└─────────────────────────────────────────────────────────────┘
```

---

### 场景 3: 思考过程 (CoT) - 选择性发送

```
┌─────────────────────────────────────────────────────────────┐
│  触发: tool execute 中使用 onUpdate                           │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 1: tool 中发送 thinking                                 │
│  execute: async (id, params, signal, onUpdate) => {            │
│    onUpdate({                                                 │
│      content: [...],                                          │
│      details: {                                               │
│        type: "thinking",                                      │
│        thought: "首先检查函数签名..."                            │
│      }                                                        │
│    });                                                        │
│                                                               │
│    // 手动插入 thinking 消息                                  │
│    agent.state.messages.push({                                │
│      role: "thinking",                                         │
│      content: "首先检查函数签名...",                             │
│      visible: false  // LLM 不可见                            │
│    });                                                        │
│  }                                                            │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 2: 选择处理方式                                        │
│                                                               │
│  选项 A: 完全过滤 (不发给 LLM)                                  │
│    filter(m => m.role !== "thinking")                         │
│                                                               │
│  选项 B: 转换后发送 (LLM 能看到思考过程)                          │
│    if (m.role === "thinking") {                                │
│      return [{ role: "user", content: `[思考] ${m.content}` }]; │
│    }                                                          │
│                                                               │
│  选项 C: 摘要后发送                                            │
│    return [{ role: "user", content: summarize(m.content) }];   │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 3: UI 选择性显示                                         │
│  - visible=true:  显示在思考气泡中                              │
│  - visible=false: 只在调试面板显示                              │
└─────────────────────────────────────────────────────────────┘
```

---

### 场景 4: 系统通知 (上下文触发)

```
┌─────────────────────────────────────────────────────────────┐
│  触发: transformContext 检测到上下文过长                        │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 1: transformContext 中插入                               │
│  transformContext: async (messages) => {                      │
│    const tokens = estimateTokens(messages);                   │
│    if (tokens > 8000) {                                       │
│      messages.push({                                          │
│        role: "system_notice",                                  │
│        level: "warning",                                      │
│        message: "上下文已压缩，部分历史省略"                     │
│      });                                                      │
│    }                                                          │
│    return messages;                                           │
│  }                                                            │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 2: convertToLlm 转换通知                                  │
│  if (m.role === "system_notice") {                             │
│    return [{                                                  │
│      role: "user",                                            │
│      content: `[系统] ${m.message}`                            │
│    }];                                                        │
│  }                                                            │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 3: UI 根据 level 显示不同样式                            │
│  - "info": 蓝色信息条                                          │
│  - "warning": 黄色警告条                                       │
│  - "error": 红色错误条                                          │
└─────────────────────────────────────────────────────────────┘
```

---

### 场景 5: 协作标记 (外部事件)

```
┌─────────────────────────────────────────────────────────────┐
│  触发: WebSocket 收到协作事件                                   │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 1: WebSocket handler                                    │
│  ws.onmessage = (event) => {                                  │
│    const data = JSON.parse(event.data);                       │
│    if (data.type === "collaborator_joined") {                 │
│      agent.state.messages.push({                              │
│        role: "collaborator",                                   │
│        userName: data.userName,                               │
│        action: "joined"                                        │
│      });                                                      │
│    }                                                          │
│  };                                                           │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 2: convertToLlm 转换                                     │
│  if (m.role === "collaborator") {                              │
│    return [{                                                  │
│      role: "user",                                            │
│      content: `${m.userName} ${m.action === "joined" ? "加入" : "离开"了对话` │
│    }];                                                        │
│  }                                                            │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 3: UI 显示协作状态                                        │
│  - 顶部显示在线用户列表                                         │
│  - 消息气泡显示加入/离开标记                                     │
└─────────────────────────────────────────────────────────────┘
```

---

## 决策树: 选择处理方式

```
                    自定义消息
                        │
            ┌───────────┴───────────┐
            │                       │
      纯 UI 状态?              需要 LLM 知道?
            │                       │
      ┌────┴────┐              ┌───┴───┐
      │         │              │       │
     是        否             是       否
      │         │              │       │
      ▼         ▼              ▼       ▼
  ┌────────┐ ┌──────────┐ ┌────────┐ ┌────────┐
  │ 过滤   │ │ 转为标准 │ │ 转为   │ │ 过滤   │
  │ filter │ │ message  │ │ 摘要   │ │        │
  └────────┘ └──────────┘ └────────┘ └────────┘
     │            │           │        │
     ▼            ▼           ▼        ▼
  不发给 LLM   发给 LLM    发给 LLM  不发给 LLM
  仅 UI 可见   (完整)      (简化)   仅 UI 可见

例: loading    例: 附件    例: thinking  例: 调试信息
    spinner       内容      摘要后发送
```

---

## 代码模板速查

### 模板 1: UI-only (过滤)
```typescript
declare module "@earendil-works/pi-agent-core" {
  interface CustomAgentMessages {
    spinner: { role: "spinner"; id: string; text: string };
  }
}

// convertToLlm: 过滤
convertToLlm: (messages) => messages.filter(m => m.role !== "spinner")

// subscribe: 渲染
if (event.message.role === "spinner") ui.showSpinner(event.message.text);
```

### 模板 2: 转换后发送
```typescript
declare module "@earendil-works/pi-agent-core" {
  interface CustomAgentMessages {
    attachment: { role: "attachment"; fileName: string; content: string };
  }
}

// convertToLlm: 转换
convertToLlm: (messages) => messages.flatMap(m => {
  if (m.role === "attachment") {
    return [{ role: "user", content: `File ${m.fileName}:\n${m.content}` }];
  }
  return [m];
})
```

### 模板 3: 条件性处理
```typescript
// 根据某些条件决定是否发给 LLM
convertToLlm: (messages) => messages.flatMap(m => {
  if (m.role === "thinking") {
    // 根据用户设置决定
    return settings.shareThinkingWithLLM 
      ? [{ role: "user", content: m.thought }]
      : [];
  }
  return [m];
})
```
