# 学习进度追踪

## 项目信息

- **目标包**: `@earendil-works/pi-agent-core`
- **版本**: 0.75.4
- **开始时间**: 2026-05-22
- **学习方法**: FastLearn (Method 4)

## 完成清单

- [x] 项目初始化和目录结构
- [x] 01 - 架构概览
- [x] 02 - 核心类型系统
- [x] 03 - Agent 类
- [x] 04 - Agent 循环
- [x] 05 - 工具系统
- [x] 06 - 事件流
- [x] 07 - Harness 系统
- [x] 08 - 实践示例

## 核心概念总结

### 架构
```
Application → Agent → agentLoop → pi-ai (LLM Provider)
                  ↓
               Events → UI Updates
```

### 关键类型
- `AgentMessage`: 可扩展的消息类型
- `AgentTool`: 工具定义（TypeBox 参数）
- `AgentEvent`: 生命周期事件
- `AgentState`: 状态管理

### 两种使用模式
1. **Agent 类**: 高级 API，自动等待订阅者，适合 UI
2. **agentLoop**: 低级 API，观察性流，适合批处理

### 事件序列
```
agent_start → turn_start → message_* → turn_end → agent_end
                    ↓
            tool_execution_* (if tools)
```

### 工具执行
- **Parallel**: 并发执行，默认
- **Sequential**: 顺序执行

### Harness 功能
- Session 管理（持久化）
- 上下文压缩
- 技能管理
- UUID 生成

## 下一步行动

1. [ ] 阅读源代码深入理解实现
2. [ ] 构建简单示例应用
3. [ ] 学习 `@earendil-works/pi-ai` 依赖包
4. [ ] 查看测试文件了解使用模式

## 文件映射

| 学习文档 | 源文件 |
|---------|--------|
| 01-overview | README.md, package.json |
| 02-core-types | src/types.ts |
| 03-agent-class | src/agent.ts |
| 04-agent-loop | src/agent-loop.ts |
| 05-tool-system | src/types.ts (AgentTool) |
| 06-event-flow | src/types.ts (AgentEvent) |
| 07-harness | src/harness/ |
| 08-examples | - |

## 学习时间

- 文档创建: ~30 分钟
- 预计深入学习: 2-3 小时

---

**状态**: 基础学习完成，准备深入实践
