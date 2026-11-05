# 自托管 Langfuse

灵医的链路追踪后端。每一次问诊请求在 Langfuse 中是一条 trace，下钻可见
LangGraph 节点链、每次 LLM 调用的 prompt / 回复 / token / 耗时、以及异常与重试。

## 组成

| 容器 | 作用 | 端口（仅本机） |
|---|---|---|
| `langfuse-web` | UI + 查询 API | 3001 |
| `langfuse-worker` | 异步摄取队列 | 3030 |
| `postgres` | 元数据（用户/项目/配置） | 5432 |
| `clickhouse` | trace 数据存储 | 8123 / 9000 |
| `redis` | 队列 | 6379 |
| `minio` | 对象存储（大 payload） | 9090 / 9091 |

常驻内存约 3–4 GB，首次启动需拉取镜像约 2–3 GB。

## 前置：安装 Docker

本机当前未安装 Docker，需先完成这一步（需管理员权限，手动操作）：

1. 确认 WSL2：`wsl --status`（内核已存在即可；`wsl -l -v` 无发行版不影响 Docker Desktop）
2. 下载并安装 Docker Desktop for Windows：https://www.docker.com/products/docker-desktop/
3. 安装时勾选 **Use WSL 2 based engine**
4. 安装后启动 Docker Desktop，等待左下角状态变为 `Engine running`
5. 验证：`docker --version` 与 `docker compose version`

## 启动

```bash
cd deploy/langfuse
cp .env.example .env
docker compose up -d
```

首次启动会自动建表并创建组织/项目/登录用户，约需 1–2 分钟。查看进度：

```bash
docker compose ps          # 等所有服务变成 healthy
docker compose logs -f langfuse-web
```

打开 http://localhost:3001 ，用 `.env` 中的账号登录：

- 邮箱：`admin@lingyi.local`
- 密码：`lingyi123456`

项目 `LingYi` 已自动创建，API Key 固定为：

| 键 | 值 |
|---|---|
| Public Key | `pk-lf-lingyi-local` |
| Secret Key | `sk-lf-lingyi-local` |

## 接入灵医

在项目根目录 `.env` 中加入：

```env
ENABLE_LANGFUSE=true
LANGFUSE_HOST=http://localhost:3001
LANGFUSE_PUBLIC_KEY=pk-lf-lingyi-local
LANGFUSE_SECRET_KEY=sk-lf-lingyi-local
```

重启后端后发一条问诊，Langfuse 的 `LingYi` 项目下即出现 trace。

## 验证清单

- [ ] 多智能体模式下，一条 trace 内可见 `dispatch_specialists` 的三个并行专家 span
- [ ] 每个节点的 LLM 调用显示 model / token / 延迟
- [ ] 安全拦截（`safety_rejected`）能在 trace 中看到
- [ ] SSE、WebSocket、非流式三条通道都能产生 trace
- [ ] UI 的 Sessions 列表按 `thread_id` 归并同一咨询线程的多轮对话

## 常见问题

**镜像拉取失败**（`docker.langfuse.com` / `cgr.dev` 在国内可能不通）
给 Docker Desktop 配置镜像加速器（Settings → Docker Engine → `registry-mirrors`），
或改用可访问的镜像源并相应修改 `docker-compose.yml` 中的 `image:` 字段。

**端口被占用**
宿主机 3000 已被前端占用时，修改 `docker-compose.yml` 中 `langfuse-web` 的端口映射
（如 `3001:3000`），同时更新 `.env` 的 `NEXTAUTH_URL` 与项目的 `LANGFUSE_HOST`。

**WSL 内存占用过高**
在 `C:\Users\<用户>\.wslconfig` 中限制：

```ini
[wsl2]
memory=6GB
```

**看不到 trace**
1. 确认后端日志出现 `Langfuse 追踪已启用`
2. 确认 `.env` 中 `ENABLE_LANGFUSE=true` 且两个 Key 非空
3. 停止后端时会自动 flush；运行中数据为批量上报，最长延迟数秒

## 数据与备份

数据保存在 Docker 命名卷中（`langfuse_postgres_data` / `langfuse_clickhouse_data` /
`langfuse_minio_data` / `langfuse_redis_data`）。`docker compose down` 不会删除它们，
`docker compose down -v` 会。

## 停止

```bash
docker compose stop      # 保留容器与数据
docker compose down      # 删除容器，保留数据卷
```
