/**
 * Demo: CustomAgentMessages - 加载状态指示器
 *
 * 展示如何使用 CustomAgentMessages 扩展机制实现 UI-only 的加载状态
 */

import { Agent } from "@earendil-works/pi-agent-core";
import { getModel } from "@earendil-works/pi-ai";
import { Type } from "typebox";

// ============================================================
// Step 1: 声明合并扩展 - 定义自定义消息类型
// ============================================================
declare module "@earendil-works/pi-agent-core" {
  interface CustomAgentMessages {
    // 加载状态消息 - 用于显示长时间操作的进度
    loading: {
      role: "loading";
      id: string;           // 唯一标识，用于更新/移除
      text: string;         // 显示的文本
      timestamp: number;    // 创建时间
      progress?: number;   // 可选：进度百分比 0-100
    };

    // 进度更新消息
    progress: {
      role: "progress";
      id: string;
      current: number;
      total: number;
      text: string;
    };
  }
}

// ============================================================
// Step 2: 模拟 UI 层
// ============================================================
const ui = {
  spinners: new Map<string, { text: string; progress?: number }>(),

  showSpinner(id: string, text: string) {
    this.spinners.set(id, { text });
    console.log(`🔄 [${id}] ${text}`);
  },

  updateProgress(id: string, current: number, total: number, text: string) {
    const percent = Math.round((current / total) * 100);
    this.spinners.set(id, { text, progress: percent });
    console.log(`⏳ [${id}] ${text} (${current}/${total} = ${percent}%)`);
  },

  removeSpinner(id: string) {
    this.spinners.delete(id);
    console.log(`✅ [${id}] 完成`);
  },

  showMessage(role: string, content: string) {
    const prefix = role === "user" ? "👤" : role === "assistant" ? "🤖" : "💬";
    console.log(`${prefix} ${content}`);
  }
};

// ============================================================
// Step 3: 创建 Agent
// ============================================================
const agent = new Agent({
  initialState: {
    systemPrompt: "你是一个帮助用户的助手。如果用户要求搜索文件，你会模拟一个长时间的搜索操作。",
    model: getModel("anthropic", "claude-sonnet-4-20250514"),
    messages: [],
    tools: [
      // 模拟长时间文件搜索工具
      {
        name: "search_files",
        description: "在项目中搜索文件（模拟长时间操作）",
        parameters: Type.Object({
          pattern: Type.String(),
          path: Type.String(),
        }),
        label: "搜索文件",
        execute: async (id, params, signal, onUpdate) => {
          const files = [
            "src/components/Button.tsx",
            "src/components/Input.tsx",
            "src/utils/helpers.ts",
            "src/hooks/useAuth.ts",
            "src/services/api.ts",
          ];

          // 模拟逐步搜索过程
          for (let i = 0; i < files.length; i++) {
            // 检查是否被中止
            if (signal?.aborted) {
              return {
                content: [{ type: "text", text: "搜索已取消" }],
                details: { cancelled: true },
              };
            }

            // 模拟延迟
            await new Promise(r => setTimeout(r, 300));

            // 发送进度更新（通过 onUpdate 回调）
            onUpdate?.({
              content: [{ type: "text", text: `搜索中: ${files[i]}` }],
              details: {
                currentFile: files[i],
                progress: ((i + 1) / files.length) * 100,
              },
            });
          }

          // 返回结果
          const matched = files.filter(f => f.includes(params.pattern.toLowerCase()));
          return {
            content: [{ type: "text", text: `找到 ${matched.length} 个匹配文件` }],
            details: { files: matched, total: files.length },
          };
        },
      },
    ],
  },

  // Step 4: convertToLlm - 过滤掉 UI-only 的自定义消息
  convertToLlm: (messages) => {
    return messages.flatMap((m) => {
      // 过滤 loading 和 progress 消息，不发给 LLM
      if (m.role === "loading" || m.role === "progress") {
        return []; // 返回空数组 = 过滤掉
      }
      // 标准消息透传
      return [m];
    });
  },
});

// ============================================================
// Step 5: 订阅事件流 - 处理自定义消息
// ============================================================
agent.subscribe((event) => {
  switch (event.type) {
    case "message_start": {
      const msg = event.message;

      // 处理 loading 消息
      if (msg.role === "loading") {
        ui.showSpinner(msg.id, msg.text);
        return;
      }

      // 处理 progress 消息
      if (msg.role === "progress") {
        ui.updateProgress(msg.id, msg.current, msg.total, msg.text);
        return;
      }

      // 处理标准消息
      if (msg.role === "user" || msg.role === "assistant") {
        const content = typeof msg.content === "string"
          ? msg.content
          : JSON.stringify(msg.content);
        ui.showMessage(msg.role, content.slice(0, 100));
      }
      break;
    }

    case "tool_execution_start": {
      // 工具开始执行时，插入 loading 消息
      agent.state.messages.push({
        role: "loading",
        id: `tool-${event.toolCallId}`,
        text: `正在执行 ${event.toolName}...`,
        timestamp: Date.now(),
      });
      ui.showSpinner(`tool-${event.toolCallId}`, `执行 ${event.toolName}...`);
      break;
    }

    case "tool_execution_end": {
      // 工具执行完成，移除 loading
      ui.removeSpinner(`tool-${event.toolCallId}`);
      break;
    }

    case "agent_end": {
      console.log("\n📋 会话结束，消息历史：");
      console.log("=".repeat(50));

      // 遍历消息历史，展示自定义消息
      for (const msg of event.messages) {
        if (msg.role === "loading") {
          console.log(`[LOADING] ${(msg as any).text}`);
        } else if (msg.role === "progress") {
          const p = msg as any;
          console.log(`[PROGRESS] ${p.text} (${p.current}/${p.total})`);
        } else if (msg.role === "user" || msg.role === "assistant") {
          const content = typeof msg.content === "string"
            ? msg.content.slice(0, 50)
            : "[复杂内容]";
          console.log(`[${msg.role.toUpperCase()}] ${content}...`);
        }
      }
    }
  }
});

// ============================================================
// Step 6: 使用示例
// ============================================================
async function main() {
  console.log("=== CustomAgentMessages Demo: 加载状态指示器 ===\n");

  // 示例 1: 手动添加 loading 消息
  console.log("示例 1: 手动插入 loading 消息");
  console.log("-".repeat(40));

  agent.state.messages.push({
    role: "loading",
    id: "manual-loading-1",
    text: "正在初始化...",
    timestamp: Date.now(),
  });

  // 模拟初始化完成
  await new Promise(r => setTimeout(r, 500));
  ui.removeSpinner("manual-loading-1");

  // 示例 2: 用户提问触发工具执行
  console.log("\n示例 2: 工具执行自动触发 loading");
  console.log("-".repeat(40));

  // 注意：这里模拟用户提问，实际会调用 LLM
  // 为了演示，我们直接模拟流程
  console.log("👤 用户: 搜索包含 'button' 的文件");
  console.log("");

  // 模拟工具执行过程
  const toolCallId = "tool-123";

  // 工具开始 - 自动插入 loading
  agent.state.messages.push({
    role: "loading",
    id: `tool-${toolCallId}`,
    text: "正在搜索文件...",
    timestamp: Date.now(),
  });
  ui.showSpinner(`tool-${toolCallId}`, "正在搜索文件...");

  // 模拟搜索进度
  const files = ["Button.tsx", "Button.test.tsx", "IconButton.tsx"];
  for (let i = 0; i < files.length; i++) {
    await new Promise(r => setTimeout(r, 300));

    // 更新为 progress 消息
    agent.state.messages.push({
      role: "progress",
      id: `tool-${toolCallId}-progress`,
      current: i + 1,
      total: files.length,
      text: `搜索: ${files[i]}`,
    });
    ui.updateProgress(`tool-${toolCallId}`, i + 1, files.length, `搜索: ${files[i]}`);
  }

  // 工具完成
  ui.removeSpinner(`tool-${toolCallId}`);
  console.log("\n🤖 助手: 找到 3 个包含 'button' 的文件");

  // 示例 3: 展示消息历史中的自定义消息
  console.log("\n\n示例 3: 消息历史快照");
  console.log("-".repeat(40));
  console.log("注意: loading/progress 消息在消息历史中，但不会发给 LLM");
  console.log("实际消息数量:", agent.state.messages.length);
  console.log("自定义消息数量:", agent.state.messages.filter(m =>
    m.role === "loading" || m.role === "progress"
  ).length);

  // 模拟 convertToLlm 的结果
  const llmMessages = agent.state.messages.filter(m =>
    m.role !== "loading" && m.role !== "progress"
  );
  console.log("发给 LLM 的消息数量:", llmMessages.length);
}

// 运行 demo
main().catch(console.error);
