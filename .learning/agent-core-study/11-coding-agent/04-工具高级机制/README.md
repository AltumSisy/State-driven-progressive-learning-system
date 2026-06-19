# 工具高级机制

## 学习目标

理解工具系统的进阶机制，包括工具包装、文件修改队列、输出处理等。

## 核心源文件

- `tools/tool-definition-wrapper.ts` - 工具定义包装
- `tools/file-mutation-queue.ts` - 文件修改队列
- `tools/output-accumulator.ts` - 输出累积器
- `tools/path-utils.ts` - 路径工具函数
- `tools/render-utils.ts` - 渲染工具函数
- `tools/truncate.ts` - 内容截断策略

## 关键概念

### 1. 工具定义包装（tool-definition-wrapper.ts）

**核心功能**:
将 AgentTool 转换为 ToolDefinition：
```typescript
createToolDefinitionFromAgentTool(tool: AgentTool): ToolDefinition
```

**应用场景**:
- baseToolsOverride 时包装外部工具
- 统一工具注册机制
- Definition-first 架构支持

### 2. 文件修改队列（file-mutation-queue.ts）

**核心功能**:
队列化处理文件修改：
```typescript
withFileMutationQueue(cwd, operations): Promise<void>
```

**设计目的**:
- 防止并发文件修改冲突
- 保证修改顺序
- 支持原子性操作

**应用场景**:
- edit 工具批量修改
- 多文件同时编辑
- 文件修改事务

### 3. 输出累积器（output-accumulator.ts）

**核心功能**:
累积流式输出：
- 收集输出片段
- 合并输出
- 提供完整结果

**应用场景**:
- bash 命令流式输出
- 大文件读取分段
- 工具结果合并

### 4. 路径工具函数（path-utils.ts）

**核心功能**:
路径安全处理：
- 相对路径验证
- 绝对路径转换
- cwd 限制检查
- 路径规范化

**安全机制**:
```typescript
validatePath(path: string, cwd: string): boolean
resolvePath(path: string, cwd: string): string
```

### 5. 渲染工具函数（render-utils.ts）

**核心功能**:
工具结果渲染：
- 格式化输出
- HTML 渲染
- ANSI 颜色转换

**应用场景**:
- UI 显示工具结果
- HTML 导出
- 日志格式化

### 6. 内容截断策略（truncate.ts）

**核心常量**:
```typescript
DEFAULT_MAX_BYTES = 256 * 1024    // 256KB
DEFAULT_MAX_LINES = 2000          // 2000 行
```

**截断函数**:

#### truncateHead
截断头部，保留尾部：
```typescript
truncateHead(content, maxBytes): TruncationResult
```
适用：日志文件、历史记录

#### truncateTail
截断尾部，保留头部：
```typescript
truncateTail(content, maxBytes): TruncationResult
```
适用：源代码、配置文件

#### truncateLine
截断单行：
```typescript
truncateLine(line, maxBytes): TruncationResult
```
适用：长行截断

**TruncationResult**:
```typescript
interface TruncationResult {
  content: string;        // 截断后的内容
  truncated: boolean;     // 是否截断
  originalSize: number;   // 原始大小
  finalSize: number;      // 最终大小
}
```

**格式化辅助**:
```typescript
formatSize(bytes: number): string
// 例：256KB, 1MB
```

## 重点阅读

### tool-definition-wrapper.ts

理解如何将 AgentTool 包装为 ToolDefinition：
1. 提取工具名称、描述
2. 从 AgentTool 提取参数 schema
3. 创建 ToolDefinition 结构
4. 保持工具执行能力

### file-mutation-queue.ts

理解文件修改队列机制：
1. 队列初始化
2. 操作入队
3. 顺序执行
4. 错误处理
5. 完成回调

### truncate.ts

理解截断策略：
1. 截断触发条件
2. 截断位置选择
3. 截断提示信息
4. 保留内容优化

## 关键设计模式

### 包装器模式（Wrapper）
tool-definition-wrapper.ts 实现：
- 将 AgentTool 包装为 ToolDefinition
- 保持原始工具功能
- 统一接口适配

### 队列模式（Queue）
file-mutation-queue.ts 实现：
- 操作入队
- 顺序执行
- 错误隔离
- 结果回调

### 策略模式（Strategy）
truncate.ts 实现：
- truncateHead 策略
- truncateTail 策略
- truncateLine 策略
- 根据场景选择策略

## 实际应用场景

### 1. 工具包装
```typescript
// 包装外部 AgentTool
const definition = createToolDefinitionFromAgentTool(customTool);
// 焱入注册系统
toolRegistry.set(definition.name, definition);
```

### 2. 文件批量修改
```typescript
await withFileMutationQueue(cwd, async (queue) => {
  await queue.enqueue(editOperation1);
  await queue.enqueue(editOperation2);
  await queue.enqueue(editOperation3);
});
```

### 3. 大输出截断
```typescript
const result = truncateTail(output, DEFAULT_MAX_BYTES);
if (result.truncated) {
  console.log(`截断了 ${formatSize(result.originalSize - result.finalSize)}`);
}
```

## 与 AgentSession 的关系

这些工具机制在 AgentSession 中使用：
1. `_buildRuntime()` 使用 tool-definition-wrapper
2. edit 工具使用 file-mutation-queue
3. 所有工具使用 truncate 处理输出
4. 所有工具使用 path-utils 验证路径

## 学习建议

1. **理解包装器**先读 tool-definition-wrapper.ts
2. **理解队列**读 file-mutation-queue.ts
3. **理解截断**读 truncate.ts
4. **理解路径安全**读 path-utils.ts
5. **理解渲染**读 render-utils.ts
6. **理解累积**读 output-accumulator.ts

## 扩展思考

### 性能优化
- 文件修改队列的性能影响
- 截断策略对大文件的处理
- 输出累积的内存占用

### 安全性
- 路径验证防止目录遍历攻击
- 文件修改队列防止竞态条件
- 截断策略防止资源耗尽

### 扩展性
- 如何添加新的截断策略
- 如何自定义文件修改队列行为
- 如何扩展路径验证规则