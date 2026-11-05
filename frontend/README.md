# 灵医前端（Next.js）

灵医 (LingYi) 的 Web 前端：中医问诊对话、多智能体会诊过程时间线、处方卡片、咨询人管理与患者画像编辑。

## 技术栈

| 项 | 版本 |
|---|---|
| Next.js | 16.2（App Router + Turbopack） |
| React | 19 |
| Tailwind CSS | v4 |
| 组件 | @base-ui/react + shadcn 风格组件 |
| 数据请求 | @tanstack/react-query |
| 状态 | zustand |
| 测试 | vitest + @testing-library/react |

## 环境要求

- Node.js **20.9+**（Next.js 16 的最低要求）
- 后端 FastAPI 已启动（默认 `http://localhost:8000`）

## 安装与启动

```bash
npm ci          # 按 package-lock.json 安装
npm run dev     # 开发服务器，默认 http://localhost:3000
```

生产构建：

```bash
npm run build
npm run start
```

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `BACKEND_URL` | `http://localhost:8000` | 服务端 `rewrites` 代理目标；把 `/api/*` 转发到后端，浏览器侧同源调用，免 CORS |
| `NEXT_PUBLIC_API_URL` | （空） | 浏览器直连后端时的前缀；留空表示走同源代理（推荐） |

后端换端口或换机器时，改 `BACKEND_URL` 即可：

```bash
BACKEND_URL=http://localhost:8010 npm run dev
```

## 目录结构

```
frontend/
├── src/app/                  # App Router 页面
│   ├── page.tsx              # 首页（登录态跳转）
│   ├── login/page.tsx        # 登录 / 注册
│   └── chat/
│       ├── page.tsx          # 新对话（threadId 为空）
│       └── [threadId]/page.tsx  # 历史会话
├── src/components/
│   ├── chat/                 # ChatWindow、消息气泡、会诊过程面板
│   ├── layout/               # AppShell、侧边栏、咨询人管理
│   └── ui/                   # 基础组件
├── src/hooks/useChat.ts      # 会话状态、SSE 流式接收
├── src/lib/                  # api 客户端、stream、类型
└── src/stores/               # zustand（认证、当前咨询人）
```

## 与后端联调要点

- 流式回复走 SSE：`POST /api/chat?stream=true`，逐 token 渲染，阶段事件用 `type: "stage"`。
- 会话在发出首条消息后由后端创建；`/chat` 页面本身不带 `threadId`。
- 新增会话前会先检查当前会话是否有消息，空会话不会重复创建。
- 咨询人（成员）上下文随每次请求的 `member_id` 传递：`null` = 主成员本人，`""` = 不结合画像。

## 测试

```bash
npm test          # vitest run
npm run test:watch
```

## 注意

- 本目录的 `AGENTS.md` 说明：Next.js 16 与训练数据中的版本存在差异，改动前请先查阅
  `node_modules/next/dist/docs/` 下的官方文档。
