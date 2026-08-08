# API 参考

## 概述

灵医后端基于 FastAPI 构建，所有路由挂载在 `/api` 前缀下。认证采用 JWT Bearer Token（HS256 签名），除登录、注册和健康检查外，所有端点均需认证。

| 项目 | 值 |
|---|---|
| 基础路径 | `/api` |
| 认证方式 | JWT Bearer Token（`Authorization: Bearer <token>`） |
| 签名算法 | HS256 |
| Token 有效期 | 1440 分钟（24 小时，`JWT_EXPIRE_MINUTES` 可配置） |
| CORS 来源 | `http://localhost:3000,http://localhost:8501`（`CORS_ORIGINS` 可配置） |

## 认证

### POST /api/register

注册新用户。

**请求体**：
```json
{
  "username": "string",
  "password": "string  (最少 6 位)"
}
```

**响应**（200）：
```json
{
  "status": "ok",
  "message": "注册成功"
}
```

**错误**：
| 状态码 | 说明 |
|---|---|
| 400 | 用户名已存在 |

### POST /api/login

用户登录，验证密码后返回 JWT Token。

**请求体**：
```json
{
  "username": "string",
  "password": "string"
}
```

**响应**（200）：
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer"
}
```

**错误**：
| 状态码 | 说明 |
|---|---|
| 401 | 用户名或密码错误 |

## 健康检查

### GET /api/health

无需认证。

**响应**（200）：
```json
{
  "status": "ok",
  "version": "2.0.0",
  "rag_mode": "mock"
}
```

## 聊天

### POST /api/chat

发送消息，调用 Agent 处理。需认证。

**请求头**：
```
Authorization: Bearer <token>
```

**请求体**：
```json
{
  "message": "string  (最长 10000 字符)",
  "thread_id": "string  (为空时自动创建)",
  "files": ["string"]  (最多 10 个文件路径)
}
```

**查询参数**：
| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `stream` | `bool` | `false` | 是否使用 SSE 流式响应 |

#### 非流式响应（stream=false）

**响应**（200）：
```json
{
  "response": "AI 回复内容",
  "thread_id": "会话线程 ID",
  "intent_type": "chat",
  "symptoms": ["症状1", "症状2"]
}
```

#### SSE 流式响应（stream=true）

设置 `Accept: text/event-stream`，返回 `text/event-stream` 流。SSE 事件契约：

| 事件 | 格式 | 说明 |
|---|---|---|
| Token | `{"token": "..."}` | LLM token（仅 diagnosis/treatment/synthesis 节点） |
| 阶段进度 | `{"type":"stage","stage":"bianzheng","label":"辨证","status":"start"}` | 会诊阶段进度（多智能体模式） |
| 完成 | `{"done":true,"thread_id":"...","elapsed_ms":123,"notes":[...],"diagnosis":"..."}` | 完成事件（notes=会诊笔记，仅多智能体） |
| 错误 | `{"error":"..."}` | 错误事件 |

**流式 token 过滤**：仅推送 `diagnosis`、`treatment`、`synthesis` 节点的 LLM token（用户可见的理法方药），过滤 `safety_guard`、`inquiry`、`rag_search` 等内部 LLM 调用。

**递归深度上限**：50（`_RECURSION_LIMIT`），为多智能体会诊图的重试循环留足余量。

### WS /api/ws/chat

WebSocket 流式聊天端点。

**鉴权**：通过 query 参数 `?token=<JWT>` 传入，复用 `decode_access_token` 校验。拒绝匿名连接（关闭码 4401）。

**客户端发送**：
```json
{
  "message": "用户消息",
  "thread_id": "会话线程 ID（为空时自动创建）"
}
```

**服务端推送**：
| 类型 | 格式 | 说明 |
|---|---|---|
| Token | `{"type":"token","content":"..."}` | LLM token |
| 阶段进度 | `{"type":"stage","stage":"...","label":"...","status":"..."}` | 会诊阶段进度 |
| 完成 | `{"type":"done","thread_id":"...","elapsed_ms":123,"notes":[...]}` | 完成事件 |
| 错误 | `{"type":"error","message":"..."}` | 错误事件 |

## 会话线程管理

### GET /api/threads

获取当前认证用户的所有会话线程。需认证。

**响应**（200）：
```json
[
  {
    "thread_id": "uuid",
    "title": "会话标题",
    "created_at": "ISO 时间戳"
  }
]
```

### POST /api/threads

创建新会话线程，归属当前认证用户。需认证。

**请求体**：
```json
{
  "title": "新对话"  (最长 100 字符)
}
```

**响应**（200）：
```json
{
  "thread_id": "uuid",
  "title": "新对话",
  "created_at": ""
}
```

### PUT /api/threads/{thread_id}

重命名会话线程。仅限归属用户。需认证。

**请求体**：
```json
{
  "new_title": "新标题"  (最长 100 字符)
}
```

**响应**（200）：
```json
{
  "status": "ok"
}
```

**错误**：
| 状态码 | 说明 |
|---|---|
| 404 | 线程不存在或不归属当前用户 |

### DELETE /api/threads/{thread_id}

删除会话线程。仅限归属用户。需认证。

**响应**（200）：
```json
{
  "status": "ok"
}
```

**错误**：
| 状态码 | 说明 |
|---|---|
| 404 | 线程不存在或不归属当前用户 |

### GET /api/threads/{thread_id}/messages

获取指定会话的消息历史。需认证。通过公开 `agent.aget_state(config)` 读取。

**响应**（200）：
```json
[
  {
    "role": "user",
    "content": "用户消息"
  },
  {
    "role": "assistant",
    "content": "AI 回复"
  }
]
```

## 患者画像

### GET /api/profiles/{patient_id}

获取患者画像。需认证。

**响应**（200）：
```json
{
  "patient_id": "string",
  "constitution": "阳虚体质",
  "allergies": "无",
  "past_history": ["既往诊疗记录"]
}
```

### PATCH /api/profiles/{patient_id}

更新患者画像。需认证，仅限本人编辑（`patient_id` 必须等于当前用户名）。

**请求体**（部分更新）：
```json
{
  "constitution": "阴虚体质",  (留空不修改)
  "allergies": "青霉素、白芷"  (完整覆盖，非合并)
}
```

**响应**（200）：
```json
{
  "patient_id": "string",
  "constitution": "阴虚体质",
  "allergies": "青霉素、白芷",
  "past_history": []
}
```

**错误**：
| 状态码 | 说明 |
|---|---|
| 403 | 只能修改自己的画像 |

### GET /api/profiles

列出所有患者画像（按最后更新时间降序）。需认证。

**响应**（200）：
```json
[
  {"patient_id": "...", "constitution": "...", "allergies": "...", ...}
]
```

## 文件上传

### POST /api/upload

上传单个文件，返回服务端路径，供 `/api/chat` 的 `files` 字段使用。需认证。

**请求**：`multipart/form-data`
| 字段 | 类型 | 说明 |
|---|---|---|
| `file` | File | 上传的文件 |

**支持的文件类型**：`.pdf`、`.docx`、`.txt`

**大小限制**：10MB

**响应**（200）：
```json
{
  "path": "服务端绝对路径",
  "filename": "原始文件名"
}
```

**错误**：
| 状态码 | 说明 |
|---|---|
| 400 | 未提供文件名 / 不支持的文件类型 |
| 413 | 文件过大（上限 10MB） |

**安全设计**：保存名使用 UUID + 已校验的扩展名，不含用户提供的文件名，防止路径穿越攻击。

## 错误格式

所有错误响应统一格式：

```json
{
  "detail": "错误描述信息"
}
```

## 状态码汇总

| 状态码 | 含义 | 触发场景 |
|---|---|---|
| 200 | 成功 | 正常请求 |
| 400 | 请求错误 | 注册用户名已存在 / 上传文件类型不支持 |
| 401 | 未认证 | 未提供 Token / Token 无效 / 用户名或密码错误 |
| 403 | 禁止操作 | 修改他人画像 |
| 404 | 不存在 | 线程不存在或不归属当前用户 |
| 413 | 请求体过大 | 上传文件超过 10MB |
| 422 | 校验错误 | 请求体不符合 Pydantic 模型约束 |
| 503 | 服务不可用 | Agent 未初始化（未配置 API Key） |

## 依赖注入

API 层采用依赖注入架构：

- **重型实例**在 `lifespan` 中创建并存入 `app.state`（storage、safety_engine、rag_client、agent、checkpointer 等）
- **请求级**通过 `Depends` 读取（`get_storage`、`get_agent`、`get_current_user` 等）
- `lingyi/api/deps.py` 不含模块级全局单例
- 测试通过 `app.dependency_overrides` 注入桩实例

### 关键依赖函数

| 函数 | 返回 | 说明 |
|---|---|---|
| `get_current_user` | `str` | 解码 Bearer JWT，返回用户名 |
| `get_storage` | `SQLiteStorage` | 从 app.state 获取存储实例 |
| `get_agent` | CompiledGraph | 从 app.state 获取 Agent 图（未初始化时返回 503） |
| `decode_access_token` | `str` | 解码 JWT token（HTTP 与 WebSocket 共用） |
