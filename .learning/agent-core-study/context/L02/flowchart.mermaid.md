# L02 Flowchart: 类型系统完整流程图

## AgentState 访问流程

```mermaid
flowchart TD
    A[外部访问 agent.state] --> B{访问类型}
    
    B -->|配置属性| C[直接赋值修改]
    B -->|tools/messages| D{操作方式}
    B -->|只读属性| E[编译错误]
    
    C --> F[systemPrompt/model/thinkingLevel]
    
    D -->|getter 读取| G[返回内部数组引用]
    D -->|setter 赋值| H[触发 slice 浅拷贝]
    D -->|原地 push/pop| I[直接修改内部数组]
    
    G --> J[可继续原地修改<br/>但污染内部状态]
    H --> K[内外隔离<br/>新数组存储]
    I --> L[无保护<br/>设计上允许但不推荐]
    
    E --> M[isStreaming/streamingMessage<br/>pendingToolCalls/errorMessage<br/>框架维护]
```

## 浅拷贝 vs 深拷贝对比

```mermaid
flowchart TD
    subgraph 浅拷贝[浅拷贝 - 精准防御]
        A1[外部数组 initialTools] --> B1[slice 复制]
        B1 --> C1[内部数组 state._tools]
        C1 -.->|引用共享| D1[工具对象 weatherTool]
        A1 -.->|引用共享| D1
        
        D1 --> E1[修改 weatherTool.name]
        E1 --> F1[state.tools.name 同步变化 ✅]
        
        A1 --> G1[push 新工具到 initialTools]
        G1 --> H1[state.tools 不受影响 ✅]
    end
    
    subgraph 深拷贝[深拷贝 - 过度防御]
        A2[外部数组] --> B2[deepClone]
        B2 --> C2[内部数组<br/>所有对象都复制]
        C2 -.->|独立副本| D2[工具对象副本]
        
        D2 --> E2[修改原工具对象]
        E2 --> F2[state.tools 不变 ❌<br/>状态分裂 Bug]
        
        A2 --> G2[性能开销<br/>每个对象都复制]
    end
```

## AgentTool 执行完整流程

```mermaid
flowchart TD
    A[LLM 返回 toolCall] --> B[阶段1: prepareArguments shim]
    B --> C[阶段2: TypeBox schema 验证]
    C --> D{阶段3: beforeToolCall 钩子}
    
    D -->|返回 block:true| E[发出 error tool result]
    D -->|返回 undefined| F[阶段4: 执行 execute]
    
    subgraph execute_params[execute 四参数]
        F --> G1[toolCallId: 事件关联ID]
        F --> G2[params: 验证后类型安全参数]
        F --> G3[signal: AbortSignal 取消信号]
        F --> G4[onUpdate: 进度回调]
    end
    
    G1 --> H[返回 AgentToolResult]
    G2 --> H
    G3 --> H
    G4 --> H
    
    H --> I[阶段5: afterToolCall 钩子]
    I --> J{返回值处理}
    
    J -->|返回 content| K[完全替换原 content]
    J -->|返回 details| L[完全替换原 details<br/>无深度合并]
    J -->|返回 undefined| M[保持原值]
    
    K --> N[发出 tool_execution_end]
    L --> N
    M --> N
```

## parallel 执行模式三阶段详解

```mermaid
flowchart TD
    subgraph 预检阶段[预检阶段 - 顺序执行]
        direction TB
        A1[toolCall A] --> B1[prepareArguments]
        B1 --> C1[TypeBox 验证]
        C1 --> D1[beforeToolCall]
        D1 --> E1{block?}
        
        A2[toolCall B] --> B2[prepareArguments]
        B2 --> C2[TypeBox 验证]
        C2 --> D2[beforeToolCall]
        D2 --> E2{block?}
        
        A3[toolCall C] --> B3[prepareArguments]
        B3 --> C3[TypeBox 验证]
        C3 --> D3[beforeToolCall]
        D3 --> E3{block?}
        
        E1 -->|no| F1[允许执行]
        E2 -->|no| F2[允许执行]
        E3 -->|no| F3[允许执行]
    end
    
    subgraph 执行阶段[执行阶段 - 并发执行]
        direction TB
        F1 --> G1[A.execute]
        F2 --> G2[B.execute]
        F3 --> G3[C.execute]
        
        G1 -.->|并发| H[同时运行]
        G2 -.->|并发| H
        G3 -.->|并发| H
        
        H --> I1[A完成]
        H --> I2[B完成]
        H --> I3[C完成]
        
        I1 --> J[按完成顺序<br/>emit tool_execution_end]
        I2 --> J
        I3 --> J
    end
    
    subgraph 结果阶段[结果阶段 - 原序排列]
        direction TB
        J --> K1[收集所有结果]
        K1 --> K2[按 assistant 消息中的<br/>原始顺序排列]
        K2 --> L[生成 ToolResult 消息]
    end
```

## AgentLoopConfig 八大钩子时序

```mermaid
flowchart LR
    subgraph LLM调用前
        A1[transformContext<br/>整理官] --> A2[convertToLlm<br/>翻译官]
        A2 --> A3[getApiKey<br/>钥匙官]
    end
    
    A3 --> B[LLM 响应]
    B --> C[toolCall 解析]
    
    subgraph 工具执行前后
        C --> D1[beforeToolCall<br/>拦截官]
        D1 --> D2[execute]
        D2 --> D3[afterToolCall<br/>修改官]
    end
    
    D3 --> E[tool_execution_end]
    E --> F[turn_end]
    
    subgraph turn结束后
        F --> G1[shouldStopAfterTurn<br/>刹车官]
        G1 --> G2{是否停止?}
    end
    
    G2 -->|true| H[agent_end<br/>循环结束]
    G2 -->|false| I1[prepareNextTurn<br/>调参官]
    
    subgraph 下一轮前
        I1 --> I2[getSteeringMessages<br/>方向盘]
        I2 --> I3[getFollowUpMessages<br/>加餐官]
    end
    
    I3 --> A1
```

## 三者关系图

```mermaid
flowchart TD
    subgraph State[AgentState - 这一刻的"是什么"]
        S1[配置: systemPrompt/model/thinkingLevel]
        S2[对话内容: tools数组/messages数组]
        S3[运行状态: 4个只读属性]
    end
    
    subgraph Tool[AgentTool - 技能卡]
        T1[继承Tool: name/description/parameters]
        T2[新增: label/prepareArguments/execute/executionMode]
    end
    
    subgraph LoopConfig[AgentLoopConfig - 工作流程规则书]
        L1[必需: model/convertToLlm]
        L2[钩子: 8个可选钩子]
        L3[模式: toolExecution/QueueMode]
    end
    
    Tool -->|放在数组中| S2
    LoopConfig -->|创建时传入| Agent[Agent实例]
    State -->|运行时变化| Agent
```