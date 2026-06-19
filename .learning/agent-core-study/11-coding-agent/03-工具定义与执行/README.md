# 工具定义与执行

## 学习目标

理解 Coding Agent 的工具系统架构，掌握 7 个核心工具的定义和执行机制。

## 核心源文件

### 工具注册中心
- `tools/index.ts` - 工具系统入口，统一注册

### 7 个核心工具
- `tools/bash.ts` - Bash 命令执行
- `tools/read.ts` - 文件读取
- `tools/write.ts` - 文件写入
- `tools/edit.ts` - 文件编辑
- `tools/grep.ts` - 内容搜索
- `tools/find.ts` - 文件查找
- `tools/ls.ts` - 目录列表

## 关键概念

### 1. ToolDefinition 接口

工具定义的核心接口：

```typescript
interface ToolDefinition<TInput, TDetails> {
  name: string;                  // 工具名称
  description: string;           // 工具描述
  parameters: JSONSchema;        // 参数 schema
  
  // 可选扩展
  promptSnippet?: string;        // 提示词片段
  promptGuidelines?: string[];   // 提示词指南
  
  // 执行相关
  operations: TOperations;       // 操作接口
  buildDetails?: (input) => TDetails;  // 构建详情
}
```

### 2. 工具类型分类

**写入类工具**（Coding Tools）:
- read - 读取文件
- bash - 执行命令
- edit - 编辑文件
- write - 写入文件

**只读类工具**（Read-Only Tools）:
- read - 读取文件
- grep - 搜索内容
- find - 查找文件
- ls - 列目录

**全工具集**（All Tools）:
包含所有 7 个工具

### 3. 工具工厂函数

每种工具都有两个工厂函数：
- `createXxxToolDefinition(cwd, options)` - 创建定义
- `createXxxTool(cwd, options)` - 创建实例

例如：
```typescript
createBashToolDefinition(cwd, options)
createBashTool(cwd, options)
```

### 4. 统一注册函数

`tools/index.ts` 提供：
```typescript
createToolDefinition(toolName, cwd, options)
createTool(toolName, cwd, options)
createCodingToolDefinitions(cwd, options)
createReadOnlyToolDefinitions(cwd, options)
createAllToolDefinitions(cwd, options)
```

## 各工具详解

### bash.ts - Bash 命令执行

**核心功能**:
- 执行 shell 命令
- 流式输出支持
- 超时控制
- 中止支持

**关键选项**:
- `commandPrefix` - 命令前缀（如 alias 支持）
- `shellPath` - Shell 路径
- `timeout` - 超时时间

**BashOperations 接口**:
- `spawn()` - 启动进程
- `write()` - 写入输入
- `kill()` - 终止进程

### read.ts - 文件读取

**核心功能**:
- 读取文件内容
- 图片读取和压缩
- PDF 文件读取
- Jupyter notebook 读取

**关键选项**:
- `autoResizeImages` - 自动压缩图片
- `maxBytes` - 最大字节限制
- `maxLines` - 最大行数限制

**特殊处理**:
- 图片转换为 base64
- PDF 按页读取
- Notebook 按单元格读取

### write.ts - 文件写入

**核心功能**:
- 创建或覆盖文件
- UTF-8 编码
- 绝对路径验证

**安全机制**:
- 必须先 Read 文件才能 Write（防止误覆盖）
- 路径必须在 cwd 内

### edit.ts - 文件编辑

**核心功能**:
- 精确字符串替换
- 多处替换支持
- 行号验证

**关键方法**:
- `old_string` - 要替换的字符串
- `new_string` - 新字符串
- `replace_all` - 全局替换

**验证机制**:
- 必须先 Read 文件
- old_string 必须精确匹配
- 必须唯一（除非 replace_all）

### grep.ts - 内容搜索

**核心功能**:
- 正则表达式搜索
- 文件类型过滤
- 输出模式选择

**输出模式**:
- `content` - 显示匹配行
- `files_with_matches` - 仅显示文件名
- `count` - 显示匹配数

**高级选项**:
- `-i` - 忽略大小写
- `-n` - 显示行号
- `-C` - 显示上下文

### find.ts - 文件查找

**核心功能**:
- Glob 模式匹配
- 递归搜索
- 按修改时间排序

**Glob 模式**:
- `*` - 单层匹配
- `**` - 多层匹配
- `*.ts` - 扩展名匹配

### ls.ts - 目录列表

**核心功能**:
- 列出目录内容
- 显示文件信息
- 支持详细模式

## 学习建议

### 阅读顺序

1. **tools/index.ts** - 理解工具系统架构
2. **bash.ts** - 最复杂的工具，理解执行机制
3. **read.ts** - 理解文件读取和特殊格式处理
4. **edit.ts** - 理解精确替换机制
5. 其他工具按需阅读

### 重点理解

1. **ToolDefinition 接口** - 工具定义的统一抽象
2. **Operations 模式** - 操作接口与工具实例分离
3. **参数验证** - JSONSchema 验证机制
4. **输出处理** - truncate、formatSize 等辅助函数
5. **路径安全** - cwd 验证、绝对路径要求

## 关键设计模式

### Definition-first 模式
先定义工具，再创建实例：
```typescript
const definition = createBashToolDefinition(cwd, options);
const tool = createBashTool(cwd, options);
```

### Operations 抽象模式
工具执行通过 Operations 接口：
- 本地执行：createLocalBashOperations()
- 远程执行：自定义 Operations
- 支持多种执行环境

### 输出截断模式
大输出自动截断：
- truncateHead - 截断头部
- truncateTail - 截断尾部
- truncateLine - 截断行

## 实际应用场景

1. **代码编辑** - read + edit 组合
2. **代码搜索** - grep + find 组合
3. **命令执行** - bash 执行测试/构建
4. **文件管理** - ls + read + write 组合