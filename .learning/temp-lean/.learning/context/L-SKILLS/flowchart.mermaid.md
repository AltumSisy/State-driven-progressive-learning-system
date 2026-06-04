# Claude Skills 知识结构流程图

> 本流程图与 README.md 内容结构对应，同时包含工程视角的结构图。

---

## 一、心智模型：核心概念网络（对应README 1.1）

```mermaid
flowchart TD
    %% 概念名称用圆形节点突出显示（与矩形定义节点区分）
    TITLE_S(("Skills"))
    TITLE_PD(("渐进式披露"))
    TITLE_DESC(("description"))
    TITLE_SCR(("脚本化"))
    TITLE_VAL(("验收标准"))

    TITLE_S --> S
    TITLE_PD --> PD
    TITLE_DESC --> DESC
    TITLE_SCR --> SCR
    TITLE_VAL --> VAL

    subgraph Concepts["核心概念定义"]
        S["程序化知识封装<br/>把'怎么做'固化成<br/>可版本化工程资产"]
        PD["发现→激活→执行<br/>分层加载<br/>不一次性暴露"]
        DESC["路由规则<br/>何时用+产出+触发词<br/>写太泛→死文件"]
        SCR["确定性交给程序<br/>双指标提升<br/>稳定性+成本可控"]
        VAL["可执行验证<br/>测试命令/格式校验<br/>不只'看起来对'"]
    end

    S -->|"依赖"| PD
    S -->|"依赖"| SCR
    PD -->|"触发"| DESC
    SCR -->|"双指标"| STAB["稳定性"]
    SCR -->|"双指标"| COST["成本可控"]
    VAL -->|"验证"| OUT["输出正确性"]

    style TITLE_S fill:#f3e5f5,stroke:#7b1fa2,stroke-width:3px,color:#7b1fa2
    style TITLE_PD fill:#e8f5e9,stroke:#2e7d32,stroke-width:3px,color:#2e7d32
    style TITLE_DESC fill:#fff3e0,stroke:#ef6c00,stroke-width:3px,color:#ef6c00
    style TITLE_SCR fill:#e8f5e9,stroke:#2e7d32,stroke-width:3px,color:#2e7d32
    style TITLE_VAL fill:#e8f5e9,stroke:#2e7d32,stroke-width:3px,color:#2e7d32
    style S fill:#f3e5f5
    style PD fill:#e8f5e9
    style DESC fill:#fff3e0
    style SCR fill:#e8f5e9
    style VAL fill:#e8f5e9
```

---

## 二、专家视角：共识与分歧（对应README 1.2）

```mermaid
flowchart TD
    subgraph Consensus["专家共识"]
        C1["Skills定位<br/>方法论做成资产<br/>不是更高级的prompt"]
        C2["加载机制<br/>渐进式披露是核心工程价值"]
        C3["验收标准<br/>必须可执行"]
        C4["脚本价值<br/>最被低估<br/>不进上下文"]
    end
    
    subgraph Divergence["专家分歧"]
        D1["入口文件长度<br/>500行 vs 实际需要更长"]
        D2["团队落地路径<br/>沉淀库 vs 个人技巧起步"]
    end
    
    C1 -->|"折中"| D1
    C2 -->|"折中"| D2
    
    style Consensus fill:#e8f5e9
    style Divergence fill:#fff3e0
```

---

## 三、深度测试：理解层级边界（对应README 1.3）

```mermaid
flowchart TD
    %% 问题标题放大显示
    TITLE1["# Q1: 为什么 Skills 不是更高级的提示词？"]
    TITLE2["# Q2: description 写太泛会发生什么？"]
    TITLE3["# Q3: 为什么脚本化是最被低估的部分？"]
    
    TITLE1 --> Q1
    
    subgraph Q1["理解层级"]
        L0_1["L0: 放在文件里"]
        L1_1["L1: 分层加载"]
        L2_1["L2: 脚本能力 + 工程资产<br/>把确定性交给程序<br/>形成可版本化可验收资产"]
    end
    
    TITLE2 --> Q2
    
    subgraph Q2["理解层级"]
        L0_2["L0: 不知道什么时候用"]
        L1_2["L1: 触发率低"]
        L2_2["L2: 路由失效→死文件<br/>必须写清何时用+产出+触发词"]
    end
    
    TITLE3 --> Q3
    
    subgraph Q3["理解层级"]
        L0_3["L0: 执行命令"]
        L1_3["L1: 减少工作量"]
        L2_3["L2: 双指标提升<br/>脚本不进上下文<br/>稳定性+成本可控"]
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

## 四、对抗测试：脆弱点与反事实（对应README 3.1-3.2）

```mermaid
flowchart TD
    subgraph Fragile["脆弱点诊断"]
        F1["验收 vs 确定性混淆<br/>风险:中"]
        F2["入口文件设计原则<br/>风险:中"]
        F3["渐进式披露偏差<br/>已修正"]
    end
    
    subgraph Fix["补救措施"]
        FIX1["明确验收→输出正确性<br/>确定性→脚本化"]
        FIX2["入口短 + 拆分引用<br/>+ 单一工作流"]
        FIX3["三层加载<br/>不一次性暴露"]
    end
    
    F1 -->|"补救"| FIX1
    F2 -->|"补救"| FIX2
    F3 -->|"已修正"| FIX3
    
    style F1 fill:#fff3e0
    style F2 fill:#fff3e0
    style F3 fill:#e8f5e9
```

```mermaid
flowchart TD
    subgraph Scenario["反事实情境"]
        S1["情境1<br/>无验收但流程详细"]
        S2["情境2<br/>代码审查未触发"]
        S3["情境3<br/>10个任务塞进一个Skill"]
    end
    
    subgraph Answer["L2答案"]
        A1["不算好Skill<br/>输出可能缺字段/格式错误"]
        A2["description路由失效<br/>写太泛"]
        A3["入口太长→约束淹没<br/>违反单一职责"]
    end
    
    S1 -->|"测试验收边界"| A1
    S2 -->|"测试触发边界"| A2
    S3 -->|"测试设计原则"| A3
    
    style S1 fill:#fff3e0
    style S2 fill:#fff3e0
    style S3 fill:#fff3e0
    style A1 fill:#e8f5e9
    style A2 fill:#e8f5e9
    style A3 fill:#e8f5e9
```

---

## 五、验证体系（对应README 四）

```mermaid
flowchart TD
    subgraph Deterministic["确定性流程"]
        D["脚本化验证"]
        D --> D1["测试命令"]
        D --> D2["格式校验"]
        D --> D3["输出字段检查"]
    end
    
    subgraph NonDet["非确定性流程"]
        N["四种验证方案"]
        N --> N1["输出结构化<br/>验证结构不验证内容"]
        N --> N2["中间检查点<br/>每步有验收标准"]
        N --> N3["Hook拦截<br/>Harness层面防护"]
        N --> N4["人工确认<br/>关键决策交给用户"]
    end
    
    subgraph Apply["适用场景"]
        A1["报告类/分析类"]
        A2["多步骤流程"]
        A3["安全敏感操作"]
        A4["关键决策点"]
    end
    
    N1 --> A1
    N2 --> A2
    N3 --> A3
    N4 --> A4
    
    style D fill:#e8f5e9
    style N fill:#fff3e0
```

---

## 六、工程结构：Skills核心结构（工程视角）

```mermaid
flowchart TD
    subgraph Skill["Skill 目录结构"]
        SM["SKILL.md<br/>入口指令"]
        REF["references/<br/>规范/模板/清单"]
        SCR["scripts/<br/>可执行脚本"]
    end
    
    SM -->|"需要细节"| REF
    SM -->|"确定性执行"| SCR
    
    subgraph SKILL_MD["SKILL.md 内部结构"]
        YAML["YAML头部<br/>name + description"]
        BODY["正文<br/>流程 + 边界 + 验收"]
    end
    
    YAML -->|"路由规则"| TRIGGER["触发匹配"]
    BODY -->|"执行指引"| EXEC["执行流程"]
    
    style SM fill:#f3e5f5
    style YAML fill:#fff3e0
    style BODY fill:#e8f5e9
```

---

## 七、工程结构：渐进式披露机制（工程视角）

```mermaid
flowchart LR
    subgraph Phase1["阶段1: 发现"]
        D1["启动时<br/>只加载"]
        D2["name<br/>标识"]
        D3["description<br/>路由规则"]
        D1 --> D2 --> D3
        D3 --> CAT["能力目录"]
    end
    
    subgraph Phase2["阶段2: 激活"]
        A1["意图匹配"]
        A2["加载<br/>SKILL.md正文"]
        A1 --> A2
    end
    
    subgraph Phase3["阶段3: 执行"]
        E1["需要细节"]
        E2["读<br/>references/"]
        E3["运行<br/>scripts/"]
        E1 --> E2
        E1 --> E3
    end
    
    CAT -->|"用户意图匹配"| A1
    A2 -->|"按需"| E1
    
    style Phase1 fill:#e1f5fe
    style Phase2 fill:#fff3e0
    style Phase3 fill:#e8f5e9
```

---

## 八、工程结构：三问题三方案（工程视角）

```mermaid
flowchart TD
    subgraph Problems["三个核心问题"]
        P1["一致性问题<br/>同一任务反复发明prompt"]
        P2["验收缺失<br/>输出只'看起来对'"]
        P3["上下文成本<br/>规则塞进对话越用越慢"]
    end
    
    subgraph Solutions["对应解决方案"]
        S1["固化成Skill<br/>可版本化共享"]
        S2["验收写进流程<br/>可执行验证"]
        S3["渐进式披露<br/>按需加载"]
    end
    
    P1 -->|"解决"| S1
    P2 -->|"解决"| S2
    P3 -->|"解决"| S3
    
    style P1 fill:#ffebee
    style P2 fill:#ffebee
    style P3 fill:#ffebee
    style S1 fill:#e8f5e9
    style S2 fill:#e8f5e9
    style S3 fill:#e8f5e9
```

---

## 九、生命周期管理：四步闭环（对应README 七）

```mermaid
flowchart LR
    subgraph Lifecycle["生命周期四步"]
        L1["宣贯本质<br/>资产工程化<br/>30分钟行动"]
        L2["分级落盘<br/>P0-P3分级<br/>GitLab+PR"]
        L3["落地检查<br/>8项清单<br/>Agent Review"]
        L4["债务治理<br/>5种债务<br/>月度盘点"]
    end
    
    L1 -->|"让团队理解"| L2
    L2 -->|"让Skill有归属"| L3
    L3 -->|"让验收可执行"| L4
    L4 -->|"让资产持续健康"| L1
    
    style L1 fill:#e8f5e9
    style L2 fill:#fff3e0
    style L3 fill:#fff3e0
    style L4 fill:#ffebee
```

---

## 十、生命周期管理：分级标准（对应README 七.2）

```mermaid
flowchart TD
    NEW["新Skill"] --> Q1{"影响代码/系统变更?"}
    
    Q1 -->|"是"| P0["P0-工程级<br/>测试命令必须通过"]
    Q1 -->|"否"| Q2{"影响系统稳定性?"}
    
    Q2 -->|"是"| P1["P1-故障级<br/>复盘草稿完整"]
    Q2 -->|"否"| Q3{"影响团队协作?"}
    
    Q3 -->|"是"| P2["P2-进度级<br/>字段完整即可"]
    Q3 -->|"否"| P3["P3-辅助级<br/>格式符合标准"]
    
    style NEW fill:#f3e5f5
    style P0 fill:#ffebee
    style P1 fill:#fff3e0
    style P2 fill:#e1f5fe
    style P3 fill:#e8f5e9
```

---

## 十一、生命周期管理：命中率等级（对应README 七.3）

```mermaid
flowchart TD
    HIT["命中率"] --> H1{"≥80%?"}
    
    H1 -->|"是"| HEALTH["✅ 健康<br/>继续维护"]
    H1 -->|"否"| H2{"50-80%?"}
    
    H2 -->|"是"| WARN["⚠️ 需关注<br/>优化description"]
    H2 -->|"否"| DEAD["❌ 死文件<br/>修复或删除"]
    
    style HIT fill:#f3e5f5
    style HEALTH fill:#e8f5e9
    style WARN fill:#fff3e0
    style DEAD fill:#ffebee
```

---

## 十二、生命周期管理：债务类型（对应README 七.4）

```mermaid
flowchart TD
    subgraph Debts["五种债务"]
        D1["验收债务<br/>不通过率≥20%"]
        D2["触发债务<br/>命中率<50%"]
        D3["重复债务<br/>重叠数≥2"]
        D4["过期债务<br/>>90天"]
        D5["错误债务<br/>错误率≥10%"]
    end
    
    subgraph Fix["治理时限"]
        F1["P0/P1 24小时"]
        F2["7天"]
        F3["14天"]
        F4["30天"]
        F5["P0/P1 24小时"]
    end
    
    D1 -->|"高风险"| F1
    D2 -->|"中风险"| F2
    D3 -->|"中风险"| F3
    D4 -->|"低风险"| F4
    D5 -->|"高风险"| F5
    
    style D1 fill:#ffebee
    style D2 fill:#fff3e0
    style D3 fill:#fff3e0
    style D4 fill:#e1f5fe
    style D5 fill:#ffebee
    style F1 fill:#ffebee
    style F5 fill:#ffebee
```