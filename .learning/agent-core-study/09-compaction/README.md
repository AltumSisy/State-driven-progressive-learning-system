# L09: 上下文压缩

---

## 1. 心智模型构建

### 1.1 背景

#### Token 限制的挑战

```
早期处理:
├─ 直接截断: 丢弃旧消息
├─ 问题: 丢失重要上下文
├─ 手动选择: 保留哪些消息
└─ 无摘要: 无法压缩

中期需求:
├─ 自动判断 → Token 超限时触发
├─ 智能切割 → Turn 边界，不破坏对话
├─ 摘要生成 → LLM 生成压缩版本
├─ 保留原文 → 可追溯原始消息
└─ 配置灵活 → threshold/reserveTokens

→ Compaction 提供完整压缩方案
```

---

### 1.2 目标

#### 核心痛点

| 痛点 | 手动截断 | Compaction 系统 |
|------|---------|----------------|
| 触发判断 | 手动检查 | shouldCompact() 自动 |
| 切割位置 | 随意切割 | Turn 边界保证 |
| 摘要生成 | 无 | LLM 生成 summary |
| 原文保留 | 丢弃 | originalMessages |
| 配置管理 | 无 | CompactionSettings |

---

### 1.3 专家视角 - 概念网络

```
Compaction 概念网络:

配置:
├─ CompactionSettings
│   ├─ threshold: number ← Token 阈值 (默认 4000)
│   ├─ reserveTokens: number ← 保留 Token (默认 1000)
│   ├─ summaryModel?: Model ← 摘要模型 (可选)
│   └─ customInstructions?: string ← 自定义指令
│
├─ DEFAULT_COMPACTION_SETTINGS
│   ├─ threshold: 4000
│   ├─ reserveTokens: 1000
│   └─ summaryModel: undefined

准备:
├─ prepareCompaction()
│   ├─ 检查 Token 是否超限
│   ├─ 计算切割点
│   ├─ 生成 CompactionPreparation
│   └─ 返回 Result<Preparation | undefined, Error>
│
├─ CompactionPreparation
│   ├─ messagesToSummarize: AgentMessage[] ← 待压缩
│   ├─ messagesToKeep: AgentMessage[] ← 保留
│   ├─ cutPoint: number ← 切割位置
│   ├─ estimatedTokensBefore: number
│   ├─ estimatedTokensAfter: number
│   └─ summaryNeeded: boolean

执行:
├─ compact()
│   ├─ 调用 generateSummary()
│   ├─ 创建 SessionTreeEntry (带 summary)
│   ├─ 替换原始消息
│   └─ 返回 CompactionResult
│
├─ CompactionResult
│   ├─ summaryEntry: SessionTreeEntry ← 压缩条目
│   ├─ messagesRemoved: number ← 删除数量
│   ├─ tokensSaved: number ← 节省 Token
│   └─ summaryTokens: number ← 摘要 Token

切割策略:
├─ estimateTokens()
│   ├─ 粗略估算: 字符数 * 估算因子
│   └─ 用于快速判断
│
├─ calculateContextTokens()
│   ├─ 精确计算: 调用 LLM API
│   └─ 用于最终确认
│
├─ findCutPoint()
│   ├─ 计算 reserveTokens 位置
│   └─ 返回切割点索引
│
├─ findTurnStartIndex()
│   ├─ 确保切割点在 Turn 边界
│   ├─ 不破坏 user/assistant 对话完整性
│   └─ 回溯到 Turn 开始位置

摘要生成:
├─ generateSummary()
│   ├─ 调用 LLM 生成摘要
│   ├─ 使用 summaryModel 或默认 model
│   ├─ 可选 customInstructions
│   └─ 返回 summary 字符串
│
├─ 摘要模板
│   ├─ 系统提示: "Summarize the conversation..."
│   ├─ 用户消息: messagesToSummarize
│   └─ 返回: 简洁摘要文本
```

---

## 2. 结构化学习 (SQ3R)

### 2.1 Survey - Compaction 流程

```
Compaction 完整流程:

┌─────────────────────────────────────────────────────────┐
│                  COMPACTION FLOW                          │
└─────────────────────────────────────────────────────────┘

SessionTreeEntry[]
       │
       │ calculateContextTokens()
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│              TOKEN CHECK                                  │
│  totalTokens > threshold?                                 │
│      ├─ Yes → prepareCompaction                          │
│      └─ No  → 无需压缩                                    │
└─────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│              PREPARE                                       │
│  1. estimateTokens() 快速估算                            │
│  2. findCutPoint() 计算切割点                            │
│  3. findTurnStartIndex() 确保 Turn 边界                  │
│  4. 分割: messagesToSummarize / messagesToKeep           │
│  5. 返回 CompactionPreparation                           │
└─────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│              GENERATE SUMMARY                              │
│  1. 调用 LLM (summaryModel 或默认 model)                 │
│  2. 输入: messagesToSummarize                            │
│  3. 输出: summary 字符串                                  │
│  4. 可选: customInstructions                             │
└─────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│              CREATE ENTRY                                  │
│  1. 创建 SessionTreeEntry                                │
│  2. entry.summary = summary                              │
│  3. entry.originalMessages = messagesToSummarize         │
│  4. 替换 Session 中的原始消息                             │
└─────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│              RESULT                                        │
│  CompactionResult                                         │
│  ├─ summaryEntry                                          │
│  ├─ messagesRemoved                                       │
│  ├─ tokensSaved                                           │
│  └─ summaryTokens                                         │
└─────────────────────────────────────────────────────────┘
```

### 2.2 Question - 关键问题驱动

**Q1**: 为什么需要两种 Token 估算方法？
**Q2**: findTurnStartIndex 的作用是什么？
**Q3**: summaryModel 和默认 model 的选择逻辑？
**Q4**: originalMessages 保留的目的？

### 2.3 Read - 源代码映射

| 内容 | 源文件 | 行数 |
|------|--------|------|
| CompactionSettings | `harness/types.ts` | - |
| DEFAULT_COMPACTION_SETTINGS | `harness/compaction/compaction.ts` | - |
| compact() | `harness/compaction/compaction.ts` | - |
| prepareCompaction() | `harness/compaction/compaction.ts` | - |
| estimateTokens() | `harness/compaction/token-estimation.ts` | - |
| calculateContextTokens() | `harness/compaction/token-estimation.ts` | - |
| findCutPoint() | `harness/compaction/cut-point.ts` | - |
| findTurnStartIndex() | `harness/compaction/cut-point.ts` | - |
| generateSummary() | `harness/compaction/summary-generation.ts` | - |
| CompactionPreparation | `harness/types.ts` | - |
| CompactionResult | `harness/types.ts` | - |

### 2.4 Recite - 使用模板

#### Compaction 配置模板

```typescript
const harness = new AgentHarness({
  compactionSettings: {
    threshold: 6000,       // 6000 Token 时触发
    reserveTokens: 2000,   // 保留 2000 Token
    summaryModel: getModel("anthropic", "claude-haiku-4"),  // 用 Haiku 做摘要
    customInstructions: "Focus on key decisions and outcomes",
  },
});
```

#### 手动压缩模板

```typescript
import { compact, prepareCompaction } from "@earendil-works/pi-agent-core";

// 检查是否需要压缩
const preparation = prepareCompaction(entries, {
  threshold: 4000,
  reserveTokens: 1000,
});

if (preparation.value) {
  const result = await compact(
    preparation.value,
    model,
    apiKey,
    undefined,  // headers
    "Focus on decisions",  // customInstructions
    signal,
  );
  
  console.log(`Saved ${result.value.tokensSaved} tokens`);
}
```

### 2.5 Review - TODO清单 (渐进式披露)

> 📋 **渐进式学习**: 一次只显示一个TODO，完成后才解锁下一个。

#### 🔴 TODO-1: 掌握压缩流程 (当前激活)

**完成检查**:
- [ ] 列举 compact 的完整流程步骤
- [ ] 解释 threshold 和 reserveTokens 的作用

<details>
<summary>💡 提示</summary>

流程:
1. 检查 Token 是否超限
2. 计算切割点
3. 生成摘要
4. 创建 Entry（带 summary）
5. 替换原始消息

threshold: Token 阈值，触发压缩
reserveTokens: 保留 Token，保证最近对话
</details>

---

#### 🟡 TODO-2: 掌握切割策略 (待解锁)

**前置要求**: 完成 TODO-1

**完成检查**:
- [ ] 解释 estimateTokens 和 calculateContextTokens 的区别
- [ ] 解释 findTurnStartIndex 的作用

---

#### 🟡 TODO-3: 掌握摘要生成 (待解锁)

**前置要求**: 完成 TODO-2

**完成检查**:
- [ ] 解释 summaryModel 的选择逻辑
- [ ] 解释 customInstructions 的作用

---

#### 🟡 TODO-4: 掌握 Entry 结构 (待解锁)

**前置要求**: 完成 TODO-3

**完成检查**:
- [ ] 解释 summary 和 originalMessages 的关系
- [ ] 解释 Entry 压缩后的重建过程

---

## 📝 费曼检验 (必须完成)

在继续下一课之前，请用自己的话解释：

### 问题 1: 压缩触发
> "什么时候触发压缩？threshold 和 reserveTokens 如何配合？"

你的解释：_______________________________________________

### 问题 2: 切割策略
> "为什么要找到 Turn 边界切割？findTurnStartIndex 做什么？"

你的解释：_______________________________________________

### 问题 3: 摘要保留
> "为什么要保留 originalMessages？summary 和原文的关系是什么？"

你的解释：_______________________________________________

<details>
<summary>✅ 检查你的理解</summary>

**问题 1 参考答案**:
- 当 calculateContextTokens > threshold 时触发
- reserveTokens: 保证保留最近对话的 Token 数
- 切割后应 <= threshold - reserveTokens

**问题 2 参考答案**:
- Turn 边界切割保证 user/assistant 对的完整性
- findTurnStartIndex: 回溯到当前 Turn 的开始位置
- 防止切割在消息中间，破坏对话逻辑

**问题 3 参考答案**:
- originalMessages 保留原文，用于追溯
- summary 是压缩后的摘要
- 压缩不丢失，可查看原文
</details>

---

## 3. 对抗性测试

### 3.1 边界问题

#### threshold 过低

```typescript
threshold: 500  // 太低
// 结果：几乎每次 prompt 都触发压缩
// 教训：threshold 应合理设置 (如 4000-8000)
```

#### reserveTokens 过高

```typescript
reserveTokens: 10000  // 太高，接近 threshold
// 结果：压缩后仍然超限
// 教训：reserveTokens 应小于 threshold
```

#### 切割点破坏对话

```typescript
// findCutPoint 返回在 assistant 消息中间
findTurnStartIndex()  // 回溯到 Turn 开始
// 结果：确保切割不破坏 user/assistant 对
```

### 3.2 反事实推理

**情境 1**: 如果所有消息都需要压缩？
```typescript
messagesToSummarize = entries  // 全部
messagesToKeep = []  // 空
// 结果：生成全对话摘要，丢失细节
// 教训：reserveTokens 应保证保留最近对话
```

**情境 2**: 如果 generateSummary 失败？
```typescript
// LLM 返回错误
// 结果：CompactionError，压缩不执行
// 教训：错误不影响原有消息，安全回退
```

**情境 3**: 如果 summaryModel 太弱？
```typescript
summaryModel: tinyModel  // 能力不足
// 结果：摘要质量差，丢失关键信息
// 教训：summaryModel 应足够强大
```

### 3.3 漏洞注入 - 常见错误

| 错误类型 | 示例 | 后果 |
|---------|------|------|
| threshold 过低 | threshold: 500 | 频繁压缩 |
| reserveTokens 过高 | reserveTokens: threshold | 压缩无效 |
| summaryModel 太弱 | tiny model | 摘要质量差 |
| 无 customInstructions | 摘要不聚焦 | 关键信息丢失 |
| 忽略 signal | 不检查中止 | 无法取消压缩 |

---

## 4. 思想与迁移

### 4.1 设计哲学

#### 双层估算

```
estimateTokens(): 粗略估算 → 快速判断
calculateContextTokens(): 精确计算 → 最终确认
```

**思想**: 快速决策 + 精确验证，平衡效率和准确性。

#### Turn 边界切割

```
findCutPoint(): 计算 Token 位置
findTurnStartIndex(): 回溯到 Turn 开始
```

**思想**: 保证对话完整性，不破坏 user/assistant 对。

#### 原文保留

```typescript
entry.summary = summary;
entry.originalMessages = [...original];  // 保留原文
```

**思想**: 压缩不丢失，可追溯原始内容。

### 4.2 可迁移思维

| 思想 | Compaction 应用 | 可迁移领域 |
|------|----------------|-----------|
| **双层估算** | 粗略 + 精确 | 缓存预热、性能优化 |
| **边界切割** | Turn 边界 | 日志切割、数据分片 |
| **原文保留** | summary + original | 数据压缩、版本控制 |
| **阈值触发** | threshold 检查 | 内存管理、队列长度 |
| **模型分离** | summaryModel 独立 | 任务分工、模型选择 |

---

## 源文件映射

| 内容 | 源文件 | 行数 |
|------|--------|------|
| Compaction 设置 | `harness/types.ts` | - |
| Compaction 函数 | `harness/compaction/compaction.ts` | - |
| Token 估算 | `harness/compaction/token-estimation.ts` | - |
| 切割策略 | `harness/compaction/cut-point.ts` | - |
| 摘要生成 | `harness/compaction/summary-generation.ts` | - |

---

## 下一步

→ [L10: Proxy 与浏览器支持](../10-proxy)