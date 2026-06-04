# @earendil-works/pi 包分析报告

> **子代理 3**: Coding Agent 应用层包分析
> **分析目标**: `D:\code\State-driven-progressive-learning-system\.learning\pi\packages\coding-agent`
> **生成时间**: 2026-05-29

---

## 📁 文件树结构

```
packages/coding-agent/
├── README.md                          # 主文档 - 项目概览
├── CHANGELOG.md                       # 版本变更日志
├── package.json                       # 包配置与依赖
├── npm-shrinkwrap.json               # 锁定依赖版本
├── tsconfig.build.json               # TypeScript构建配置
├── tsconfig.examples.json            # 示例代码配置
├── vitest.config.ts                   # 测试配置
│
├── docs/                               # 📚 完整文档库（25+ 文档）
│   ├── index.md                        # 文档入口
│   ├── quickstart.md                   # 快速入门
│   ├── usage.md                        # 使用指南
│   ├── settings.md                     # 配置设置
│   ├── models.md                       # 模型配置
│   ├── providers.md                    # 提供商配置
│   ├── skills.md                       # Skill 系统
│   ├── extensions.md                   # 扩展系统
│   ├── sessions.md                     # 会话管理
│   ├── session-format.md               # 会话格式
│   ├── tui.md                          # TUI 界面
│   ├── themes.md                       # 主题系统
│   ├── keybindings.md                  # 快捷键
│   ├── prompt-templates.md             # 提示词模板
│   ├── custom-provider.md              # 自定义提供商
│   ├── development.md                  # 开发指南
│   ├── compaction.md                   # 上下文压缩
│   ├── rpc.md                          # RPC 模式
│   ├── sdk.md                          # SDK 使用
│   ├── json.md                         # JSON 模式
│   ├── packages.md                     # 包管理
│   ├── shell-aliases.md                # Shell 别名
│   ├── terminal-setup.md               # 终端设置
│   ├── termux.md                       # Termux 支持
│   ├── tmux.md                         # tmux 集成
│   ├── windows.md                      # Windows 支持
│   └── images/                         # 文档图片
│
├── examples/                           # 📖 示例代码（70+ 示例）
│   ├── README.md
│   ├── extensions/                     # 扩展示例（60+）
│   │   ├── auto-commit-on-exit.ts
│   │   ├── bash-spawn-hook.ts
│   │   ├── bookmark.ts
│   │   ├── doom-overlay/                 # Doom 游戏扩展
│   │   ├── subagent/                     # 子代理扩展示例
│   │   ├── plan-mode/                    # 计划模式
│   │   └── ... (60+ more)
│   └── sdk/                             # SDK 示例（13个）
│       ├── 01-minimal.ts
│       ├── 02-custom-model.ts
│       ├── 03-custom-prompt.ts
│       ├── 04-skills.ts
│       ├── 05-tools.ts
│       ├── 06-extensions.ts
│       ├── 07-context-files.ts
│       ├── 08-prompt-templates.ts
│       ├── 09-api-keys-and-oauth.ts
│       ├── 10-settings.ts
│       ├── 11-sessions.ts
│       ├── 12-full-control.ts
│       └── 13-session-runtime.ts
│
├── scripts/                            # 🔧 脚本
│   └── migrate-sessions.sh              # 会话迁移脚本
│
├── src/                                # 📦 源代码（核心）
│   ├── index.ts                         # 包入口
│   ├── main.ts                          # CLI 入口
│   ├── cli.ts                           # CLI 实现
│   ├── bun/                             # Bun 运行时支持
│   │   ├── cli.ts
│   │   ├── register-bedrock.ts
│   │   └── restore-sandbox-env.ts
│   │
│   ├── cli/                             # CLI 子模块
│   │   ├── args.ts                      # 参数解析
│   │   ├── config-selector.ts          # 配置选择器
│   │   ├── file-processor.ts           # 文件处理
│   │   ├── initial-message.ts          # 初始消息
│   │   ├── list-models.ts              # 模型列表
│   │   └── session-picker.ts           # 会话选择器
│   │
│   ├── config.ts                        # 配置管理
│   │
│   ├── core/                            # 🎯 核心模块
│   │   ├── index.ts                     # 核心导出
│   │   ├── agent-session.ts             # Agent 会话
│   │   ├── agent-session-runtime.ts     # 会话运行时
│