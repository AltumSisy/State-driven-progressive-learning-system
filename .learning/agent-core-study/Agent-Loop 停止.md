runLoop
│
├─ 外层（while true）—— **followUp 控制**
│   │
│   │  停止
│   │  └─ followUp无 → break → agent_end
│   │
│   │  继续
│   │  └─ followUp有 → continue → 注入pending → 重进内层
│   │
│   └───────────────────────────────────────
│
├─ 内层 Turn（**hasTool & pendingMessage**）
│   │
│   │  停止
│   │  ├─ 异常结束: stopReason(error/aborted) → agent_end
│   │  │
│   │  └─ 非异常结束
│   │      ├─ 用户刹车: hook:全terminal / shouldStop → agent_end
│   │      ├─ LLM自然: toolCalls=[] &pendingMessage=[]→ 进入外层
│   │      └─ 全terminate → 进入外层
│   │
│   │  继续
│   │  └─ steering注入 → pending有值 → while满足 → 继续
│   │
│   └───────────────────────────────────────
│
└───────────────────────────────────────

---
一句话

**外层停止**: followUp无→break→agent_end
**外层继续**: followUp有→continue→注入pending→重进内层

**内层Turn停止**: 异常→直接结束 | 用户刹车→直接结束 | LLM自然/全terminate→进入外层
**内层Turn继续**: steering注入→pending有值→while满足