# Agentic Coding 知识结构流程图

> 本流程图与 README.md 内容结构对应，同时包含原文的工程视角结构图。

---

## 一、心智模型：核心概念网络（对应README 1.1）

```mermaid
flowchart TD
    %% 概念名称用圆形节点突出显示（与矩形定义节点区分）
    TITLE_P(("协作悖论"))
    TITLE_O(("编排者"))
    TITLE_S(("SDLC被压扁"))
    TITLE_SU(("监督规模化"))
    TITLE_PR(("协作协议"))

    TITLE_P --> P
    TITLE_O --> O
    TITLE_S --> SDLC
    TITLE_SU --> SUPER
    TITLE_PR --> PROTO

    subgraph Concepts["核心概念定义"]
        P["使用率60% vs 放手率0-20%<br/>悖论点：流程兜底不足<br/>不是能力不够"]
        O["任务编排<br/>拆分（输入输出边界验收）<br/>版本控制合并<br/>人工介入点"]
        SDLC["流程重叠：瀑布→并行<br/>边做边测边补文档<br/>周期周→小时<br/>双面性"]
        SUPER["审计≠审批<br/>常规审计自动化（AI）<br/>核心业务人review"]
        PROTO["角色：做什么不做什么<br/>输入：范围约束禁止项<br/>输出：交付什么<br/>同步点：何时对齐<br/>验收：可执行命令"]
    end

    P -->|"悖论原因"| FLOW["流程兜底<br/>验收前提<br/>举手阈值<br/>回滚机制"]
    O -->|"依赖"| PROTO
    O -->|"依赖"| SUPER
    SDLC -->|"双面性"| FAST["反馈快"]
    SDLC -->|"双面性"| RISK["错误规模变大"]

    style TITLE_P fill:#f3e5f5,stroke:#7b1fa2,stroke-width:3px,color:#7b1fa2
    style TITLE_O fill:#e8f5e9,stroke:#2e7d32,stroke-width:3px,color:#2e7d32
    style TITLE_S fill:#fff3e0,stroke:#ef6c00,stroke-width:3px,color:#ef6c00
    style TITLE_SU fill:#e8f5e9,stroke:#2e7d32,stroke-width:3px,color:#2e7d32
    style TITLE_PR fill:#e8f5e9,stroke:#2e7d32,stroke-width:3px,color:#2e7d32
    style P fill:#f3e5f5
    style O fill:#e8f5e9
    style SDLC fill:#fff3e0
    style SUPER fill:#e8f5e9
    style PROTO fill:#e8f5e9
```

---

## 二、深度测试：理解层级边界（对应README 1.3）

```mermaid
flowchart TD
    %% 问题标题放大显示
    TITLE1["# Q1: 为什么60%用AI但只有0-20%放手？"]
    TITLE2["# Q2: SDLC压扁压的是什么？"]
    TITLE3["# Q3: 监督规模化不是不review而是什么？"]
    
    TITLE1 --> Q1
    TITLE2 --> Q2
    TITLE3 --> Q3
    
    subgraph Q1["理解层级"]
        L0_1["L0: 能力不够不敢放手"]
        L1_1["L1: 需要流程设计"]
        L2_1["L2: 悖论本质<br/>放手前提是流程兜底<br/>验收前提+举手阈值+回滚机制<br/>使用率提升≠放手率提升"]
    end
    
    subgraph Q2["理解层级"]
        L0_2["L0: 周期变短"]
        L1_2["L1: 流程重叠"]
        L2_2["L2: 压的是流程边界<br/>瀑布式→并行<br/>需求/实现/测试/文档重叠<br/>双面性：反馈快+错误扩"]
    end
    
    subgraph Q3["理解层级"]
        L0_3["L0: 减少人的工作量"]
        L1_3["L1: 自动化审计"]
        L2_3["L2: 拆成两层<br/>常规审计自动化（AI）<br/>人类聚焦高风险（人）<br/>review everything→what matters"]
    end
    
    L0_1 -->|"问为什么"| L1_1 -->|"提炼原则"| L2_1
    L0_2 -->|"问为什么"| L1_2 -->|"提炼原则"| L2_2
    L0_3 -->|"问为什么"| L1_3 -->|"提炼原则"| L2_3
    
    style TITLE1 fill:#f3e5f5,stroke:#333,stroke-width:3px
    style TITLE2 fill:#f3e5f5,stroke:#333,stroke-width:3px
    style TITLE3 fill:#f3e5f5,stroke:#333,stroke-width:3px
    style L0_1 fill:#ffebee
    style L0_2 fill:#ffebee
    style L0_3 fill:#ffebee
    style L2_1 fill:#e8f5e9
    style L2_2 fill:#e8f5e9
    style L2_3 fill:#e8f5e9
```

---

## 三、对抗测试：脆弱点与反事实（对应README 3.1-3.2）

```mermaid
flowchart TD
    subgraph Fragile["脆弱点诊断"]
        F1["协作悖论只说结果<br/>风险:中"]
        F2["SDLC压扁=风险提高<br/>风险:高"]
        F3["监督规模化用审批<br/>风险:中"]
        F4["举手阈值风险笼统<br/>风险:中"]
    end
    
    subgraph Fix["补救措施"]
        FIX1["悖论数据：60用0放<br/>悖论点=流程兜底不足"]
        FIX2["压扁=流程重叠<br/>瀑布→并行，双面性"]
        FIX3["审计=技术检查<br/>审批=业务开关"]
        FIX4["两类具体：<br/>业务风险+契约风险"]
    end
    
    F1 -->|"补救"| FIX1
    F2 -->|"补救"| FIX2
    F3 -->|"补救"| FIX3
    F4 -->|"补救"| FIX4
    
    style F1 fill:#fff3e0
    style F2 fill:#ffebee
    style F3 fill:#fff3e0
    style F4 fill:#fff3e0
    style FIX1 fill:#e8f5e9
    style FIX2 fill:#e8f5e9
    style FIX3 fill:#e8f5e9
    style FIX4 fill:#e8f5e9
```

---

## 四、反事实情境（对应README 3.2）

```mermaid
flowchart TD
    subgraph Scenario["反事实情境"]
        S1["情境1<br/>团队使用率80%放手率40%"]
        S2["情境2<br/>工程师只做验收自称编排者"]
        S3["情境3<br/>常规审计自动化但无举手阈值"]
    end
    
    subgraph Answer["L2答案"]
        A1["悖论被打破<br/>前提补齐：验收+举手+回滚"]
        A2["不算编排者<br/>缺四要素：编排/拆分/版本控制/介入点"]
        A3["两类错误扩大<br/>业务风险+契约风险<br/>阈值作用：风险前置到决策点"]
    end
    
    S1 -->|"测试悖论边界"| A1
    S2 -->|"测试编排者边界"| A2
    S3 -->|"测试阈值缺失"| A3
    
    style S1 fill:#fff3e0
    style S2 fill:#fff3e0
    style S3 fill:#fff3e0
    style A1 fill:#e8f5e9
    style A2 fill:#e8f5e9
    style A3 fill:#e8f5e9
```

---

## 五、工程视角：八大趋势（对应README 四）

```mermaid
flowchart TD
    subgraph Trends["八大趋势"]
        T1["01 SDLC被压扁<br/>流程重叠<br/>周期周→小时"]
        T2["02 编排者<br/>implementer→orchestrator"]
        T3["03 多智能体协作<br/>协作协议是门槛"]
        T4["04 长时运行<br/>状态管理+回滚成刚需"]
        T5["05 监督规模化<br/>review what matters"]
        T6["06 全栈扩展<br/>治理护栏跟上"]
        T7["07 经济学变化<br/>27%工作本来不会被做"]
        T8["08 安全双向<br/>防御与进攻同时增强"]
    end
    
    subgraph Action["行动"]
        A1["验收门槛前置"]
        A2["工程化写进流程"]
        A3["先写协作协议"]
        A4["状态管理+回滚"]
        A5["审计自动化"]
        A6["治理护栏"]
        A7["多产出而非省时间"]
        A8["安全架构前置"]
    end
    
    T1 --> A1
    T2 --> A2
    T3 --> A3
    T4 --> A4
    T5 --> A5
    T6 --> A6
    T7 --> A7
    T8 --> A8
    
    style T1 fill:#f3e5f5
    style T2 fill:#e8f5e9
    style T3 fill:#fff3e0
    style T4 fill:#fff3e0
    style T5 fill:#e8f5e9
    style T6 fill:#e1f5fe
    style T7 fill:#e1f5fe
    style T8 fill:#ffebee
```

---

## 六、工程视角：四个优先级（对应README 四）

```mermaid
flowchart LR
    subgraph Priority["四优先级"]
        P1["优先级1<br/>多智能体协作"]
        P2["优先级2<br/>监督规模化"]
        P3["优先级3<br/>扩展到工程之外"]
        P4["优先级4<br/>安全架构前置"]
    end
    
    subgraph Meaning["含义"]
        M1["用编排解决复杂度"]
        M2["自动化审计+人看关键点"]
        M3["领域专家在护栏内自己解决"]
        M4["权限/审计/隔离/回滚写进系统"]
    end
    
    P1 --> M1
    P2 --> M2
    P3 --> M3
    P4 --> M4
    
    style P1 fill:#f3e5f5
    style P2 fill:#e8f5e9
    style P3 fill:#fff3e0
    style P4 fill:#ffebee
```

---

## 七、工程视角：举手阈值规则（对应README 五.1）

```mermaid
flowchart TD
    OPS["操作类型"] --> Q1{"改权限/账务/资金/合规？"}
    
    Q1 -->|"是"| R1["必须举手<br/>业务风险最高"]
    Q1 -->|"否"| Q2{"改公共API/schema？"}
    
    Q2 -->|"是"| R2["先举手对齐<br/>接口契约影响其他服务"]
    Q2 -->|"否"| R3["先做再提验收报告<br/>低风险，快速回归"]
    
    style OPS fill:#f3e5f5
    style R1 fill:#ffebee
    style R2 fill:#fff3e0
    style R3 fill:#e8f5e9
```

---

## 八、工程视角：监督两层拆分（对应README 五.2）

```mermaid
flowchart TD
    subgraph Layer1["第一层：常规审计自动化"]
        L1["AI执行"]
        L1 --> L1A["格式检查"]
        L1 --> L1B["静态检查"]
        L1 --> L1C["单测"]
        L1 --> L1D["依赖风险扫描"]
        L1 --> L1E["明显漏洞检测"]
    end
    
    subgraph Layer2["第二层：人类注意力聚焦"]
        L2["人执行"]
        L2 --> L2A["高风险diff"]
        L2 --> L2B["边界条件"]
        L2 --> L2C["策略决策"]
        L2 --> L2D["不确定点"]
        L2 --> L2E["业务风险判断"]
    end
    
    Layer1 -->|"通过后"| Layer2
    
    style L1 fill:#e8f5e9
    style L2 fill:#fff3e0
```

---

## 九、工程视角：协作协议五要素（对应README 五.3）

```mermaid
flowchart TD
    subgraph Protocol["协作协议"]
        E1["角色<br/>做什么/不做什么<br/>谁能改公共文件"]
        E2["输入<br/>资料范围/约束条件/禁止项"]
        E3["输出<br/>补丁/PR/设计文档<br/>风险清单/测试报告"]
        E4["同步点<br/>何时对齐接口<br/>先产出API.md"]
        E5["验收<br/>可执行验收命令<br/>检查清单"]
    end
    
    E1 --> E2 --> E3 --> E4 --> E5
    
    style E1 fill:#f3e5f5
    style E2 fill:#fff3e0
    style E3 fill:#e8f5e9
    style E4 fill:#fff3e0
    style E5 fill:#e8f5e9
```