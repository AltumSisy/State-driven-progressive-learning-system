# 执行与诊断

## 学习目标

理解 Coding Agent 的 Bash 执行、通用执行、诊断信息和性能计时机制。

## 核心源文件

- `bash-executor.ts` - Bash 执行器（核心）
- `exec.ts` - 通用执行
- `diagnostics.ts` - 诊断信息
- `timings.ts` - 性能计时

## 关键概念

### 1. Bash Executor（bash-executor.ts）

**设计目的**:
- 执行 Bash 命令
- 支持流式输出
- 提供中止机制
- 管理执行结果

**核心函数**:
```typescript
executeBashWithOperations(
  command: string,
  operations: BashOperations,
  options?: BashExecutorOptions
): Promise<BashResult>
```

### 2. BashOperations 接口

**接口定义**:
```typescript
interface BashOperations {
  spawn(context: BashSpawnContext): Promise<BashSpawnHook>;
  write?(input: string): Promise<void>;
  kill?(): Promise<void>;
}
```

**BashSpawnContext**:
```typescript
interface BashSpawnContext {
  command: string;
  cwd: string;
  env?: Record<string, string>;
  signal?: AbortSignal;
  onChunk?: (chunk: string) => void;
}
```

**BashSpawnHook**:
```typescript
interface BashSpawnHook {
  onStdout?: (data: Buffer) => void;
  onStderr?: (data: Buffer) => void;
  onClose?: (code: number | null) => void;
}
```

### 3. BashResult 结构

**结果定义**:
```typescript
interface BashResult {
  stdout: string;        // 标准输出
  stderr: string;        // 错误输出
  exitCode: number;      // 退出码
  duration: number;      // 执行时长（ms）
  interrupted: boolean;  // 是否中断
}
```

### 4. 执行流程

**完整流程**:
1. 解析命令
2. 添加命令前缀（如配置）
3. 选择 Shell
4. spawn 进程
5. 收集输出（流式）
6. 处理中止信号
7. 等待进程结束
8. 返回结果

**流式输出**:
```typescript
onChunk?: (chunk: string) => void
```
实时接收输出片段，用于 UI 显示。

### 5. 中止机制

**AbortSignal 支持**:
```typescript
signal?: AbortSignal
```

**中止流程**:
1. 监听 AbortSignal
2. 收到中止信号
3. 调用 kill 方法
4. 标记 interrupted
5. 返回部分结果

### 6. 本地 Bash 操作

**createLocalBashOperations**:
```typescript
createLocalBashOperations(): BashOperations
```

**实现**:
- 使用 Node.js child_process.spawn
- 支持 stdio 流式
- 支持 signal 中止
- 支持 Windows 和 Unix

### 7. 命令前缀

**用途**:
- 在命令前执行初始化代码
- 例如：`shopt -s expand_aliases`（启用 alias）

**配置**:
```typescript
shellCommandPrefix?: string
```

**执行**:
```typescript
const resolvedCommand = prefix ? `${prefix}\n${command}` : command;
```

### 8. Shell 选择

**配置**:
```typescript
shellPath?: string
```

**默认**:
- Unix: `/bin/bash` 或 `$SHELL`
- Windows: `powershell.exe`

**执行**:
```typescript
spawn(shellPath, ['-c', command], { cwd });
```

### 9. 通用执行（exec.ts）

**设计目的**:
- 提供通用执行抽象
- 支持多种执行环境
- 统一执行接口

**核心接口**:
```typescript
interface ExecOptions {
  cwd?: string;
  env?: Record<string, string>;
  timeout?: number;
  signal?: AbortSignal;
}

interface ExecResult {
  stdout: string;
  stderr: string;
  exitCode: number;
}
```

**用途**:
- 简单命令执行
- 工具内部执行
- 辅助命令执行

### 10. 诊断信息（diagnostics.ts）

**设计目的**:
- 收集和报告诊断信息
- 帮助调试问题
- 提供系统信息

**诊断类型**:
- 系统信息（OS、Node 版本）
- 配置信息（设置、模型）
- 运行信息（会话状态）
- 错误信息（错误日志）

**收集方法**:
```typescript
collectDiagnostics(): DiagnosticInfo
```

**DiagnosticInfo 结构**:
```typescript
interface DiagnosticInfo {
  system: SystemInfo;
  config: ConfigInfo;
  runtime: RuntimeInfo;
  errors: ErrorLog[];
}
```

**应用场景**:
- 错误报告
- 性能分析
- 系统调试
- 用户支持

### 11. 性能计时（timings.ts）

**设计目的**:
- 测量性能指标
- 记录关键时间点
- 分析性能瓶颈

**核心类**:
```typescript
class Timings {
  private _timings: Map<string, TimingEntry>;
  
  start(name: string): void;
  end(name: string): void;
  get(name: string): TimingEntry;
  getAll(): TimingEntry[];
}
```

**TimingEntry**:
```typescript
interface TimingEntry {
  name: string;
  startTime: number;
  endTime?: number;
  duration?: number;
}
```

**关键测量点**:
- Agent 启动时间
- API 请求时间
- 工具执行时间
- 压缩时间
- UI 渲染时间

**应用场景**:
- 性能优化
- 瓶颈分析
- 用户反馈
- 自动化测试

### 12. 超时处理

**超时配置**:
```typescript
timeout?: number
```

**超时流程**:
1. 设置 timeout
2. 启动定时器
3. timeout 到期
4. 中止进程
5. 返回超时错误

**默认超时**:
- Bash 命令：120000ms（2分钟）
- 可自定义配置

### 13. 错误处理

**错误类型**:
- 进程启动失败
- 命令执行失败（exitCode != 0）
- 超时错误
- 中止错误
- Shell 不存在

**错误处理**:
- 记录 stderr
- 返回 BashResult
- 标记 isError
- 提示用户

### 14. 输出处理

**输出收集**:
- stdout 收集
- stderr 收集
- 流式回调
- 完整输出

**输出截断**:
- 使用 truncate.ts
- 防止输出过大
- 提供截断提示

## 重点阅读

### bash-executor.ts（最重要）

理解 Bash 执行：
1. **executeBashWithOperations** - 执行函数
2. **BashOperations** - 操作接口
3. **BashSpawnContext** - 启动上下文
4. **BashResult** - 结果结构
5. **流式输出** - onChunk 回调
6. **中止机制** - AbortSignal 处理

### exec.ts

理解通用执行：
1. **ExecOptions** - 执行选项
2. **ExecResult** - 执行结果
3. **简单执行** - 辅助执行

### diagnostics.ts

理解诊断信息：
1. **DiagnosticInfo** - 诊断结构
2. **collectDiagnostics** - 收集方法
3. **诊断类型** - 各种诊断信息

### timings.ts

理解性能计时：
1. **Timings 类** - 计时管理
2. **start/end** - 开始/结束
3. **TimingEntry** - 计时条目
4. **性能分析** - 瓶颈识别

## 关键设计模式

### 操作抽象模式
BashOperations 抽象执行：
- 统一执行接口
- 支持多种实现
- 本地/远程执行

### 流式处理模式
流式输出处理：
- 实时接收输出
- UI 实时显示
- 完整输出收集

### 中止模式
AbortSignal 中止：
- 统一中止机制
- 传播中止信号
- 清理资源

### 测量模式
性能计时测量：
- 关键点测量
- 持续时间记录
- 性能分析

## 学习建议

### 阅读顺序

1. **bash-executor.ts** - 理解 Bash 执行核心
2. **exec.ts** - 理解通用执行
3. **diagnostics.ts** - 理解诊断信息
4. **timings.ts** - 理解性能计时

### 重点理解

1. **Bash 执行流程** - 如何执行 Bash 命令
2. **BashOperations** - 操作接口设计
3. **流式输出** - 如何实时接收输出
4. **中止机制** - AbortSignal 处理
5. **错误处理** - 各种错误情况
6. **性能计时** - 如何测量性能

## 在 AgentSession 中的应用

### Bash 命令执行
```typescript
async executeBash(
  command: string,
  onChunk?: (chunk: string) => void,
  options?: { excludeFromContext?: boolean; operations?: BashOperations }
): Promise<BashResult> {
  this._bashAbortController = new AbortController();
  
  const prefix = this.settingsManager.getShellCommandPrefix();
  const shellPath = this.settingsManager.getShellPath();
  const resolvedCommand = prefix ? `${prefix}\n${command}` : command;
  
  const operations = options?.operations ?? createLocalBashOperations();
  
  const result = await executeBashWithOperations(
    resolvedCommand,
    operations,
    {
      cwd: this._cwd,
      shellPath,
      signal: this._bashAbortController.signal,
      onChunk,
      ...
    }
  );
  
  return result;
}
```

### 中止 Bash
```typescript
abort(): Promise<void> {
  this._bashAbortController?.abort();
  await this.agent.waitForIdle();
}
```

### 性能计时
```typescript
// AgentSession 可集成 timings
const timings = new Timings();

timings.start('agent_prompt');
await agent.prompt(messages);
timings.end('agent_prompt');

const duration = timings.get('agent_prompt').duration;
```

### 诊断收集
```typescript
// 发生错误时收集诊断
const diagnostics = collectDiagnostics();
console.log('System info:', diagnostics.system);
console.log('Runtime info:', diagnostics.runtime);
console.log('Errors:', diagnostics.errors);
```

## 实际应用场景

### 1. 执行构建命令
```typescript
const result = await session.executeBash('npm run build');
if (result.exitCode !== 0) {
  console.error('Build failed:', result.stderr);
}
```

### 2. 执行测试命令
```typescript
const result = await session.executeBash('npm test', (chunk) => {
  console.log(chunk);  // 实时显示测试输出
});
```

### 3. 执行 Git 命令
```typescript
const result = await session.executeBash('git status');
console.log(result.stdout);
```

### 4. 中止长时间命令
```typescript
const abortController = new AbortController();

// 用户中止
abortController.abort();

// Bash 命令会中止
```

### 5. 远程执行（通过自定义 Operations）
```typescript
const remoteOperations: BashOperations = {
  spawn: async (context) => {
    // 通过 SSH 或其他方式执行
    return { ... };
  },
  write: async (input) => {
    // 写入输入
  },
  kill: async () => {
    // 中止远程进程
  }
};

await executeBashWithOperations(command, remoteOperations, options);
```

### 6. 性能分析
```typescript
const timings = new Timings();

timings.start('compaction');
await compact();
timings.end('compaction');

console.log(`Compaction took ${timings.get('compaction').duration}ms`);
```

## 扩展思考

### 执行环境
- 如何支持更多执行环境
- 如何实现远程执行
- 如何支持容器执行

### 性能优化
- Bash 执行性能优化
- 流式输出优化
- 并发执行管理

### 安全考虑
- 命令验证和过滤
- 权限控制
- 安全执行环境

### 诊断增强
- 更详细的诊断信息
- 自动化诊断分析
- 诊断报告生成

### 计时扩展
- 更多测量点
- 自动性能分析
- 性能报告生成