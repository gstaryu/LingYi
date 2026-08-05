# 测试报告 - LingYi 2.0 后端（2026-08）

## 概览

- **测试框架**：pytest 9.1 + pytest-asyncio（asyncio_mode=auto）
- **环境**：conda `lingyi`，Python 3.12.13，langgraph 1.2.6，langchain 1.3.11
- **结果**：`pytest tests/ -q` -> **101 passed, 1 warning**（~11s）
- **外部依赖**：全部 mock，无真实 LLM/向量库/API 调用

## 测试覆盖

| 测试文件 | 用例数 | 覆盖范围 |
|---|---|---|
| test_config.py | 6 | Settings 默认值、env 覆盖、api_key 回退、路径属性、缓存 |
| test_factory.py | 3 | create_llm / create_embeddings 工厂路由（local/online） |
| test_embedding.py | 10 | Qwen3 query_prompt_name 行为、factory 自动检测、StubEmbedding 维度 |
| test_chroma_ingest.py | 6 | ChromaDB 入库/查询嵌入空间一致性、空库、元数据保留 |
| test_rag_search.py | 2 | MockRAGClient 检索 |
| test_safety_rules.py | 1 | 十八反十九畏规则 |
| test_storage/test_sqlite_store.py | 7 | SQLite 用户/档案/线程存储 |
| test_json_parsing.py | 1 | JSON 容错解析 |
| test_parsers.py | 4 | 文件解析（pypdf/python-docx/txt） |
| test_inquiry.py / test_diagnosis.py / test_treatment.py / test_summarizer.py / test_profile_writer.py | 24 | 各 Skill 单元（mock LLM） |
| test_api/test_api_routes.py | 25 | API 端点（auth/chat/threads/profiles/health） |
| test_api/test_security.py | 8 | 认证强制、输入限制、敏感信息泄露 |
| test_api/test_performance.py | 2 | 响应时间基线、10 并发请求 |
| test_graph_flow.py | 5 | 图编译、checkpointer 持久化、多轮记忆、线程隔离、流式 |

## 按类别覆盖（对应 prompt 要求）

### 后端测试
- **单元测试**：工具函数（json_parsing）、节点/Skill（inquiry/diagnosis/treatment/summarizer/profile_writer）、模型工厂、配置 ✅
- **集成测试**：Graph 完整流程编译、状态流转（test_graph_flow） ✅
- **API 测试**：所有端点、认证流程、边界条件、错误处理（test_api_routes + test_security） ✅
- **性能测试**：并发（10 并发请求全部成功）、响应时间（<2s 基线）（test_performance） ✅
- **安全测试**：输入验证（max_length）、权限控制（401 未认证）、敏感信息泄露（无 traceback）（test_security） ✅

### LangGraph 特定测试
- 状态持久化和恢复（checkpointer）：同 thread_id 跨调用恢复历史 ✅
- 多轮对话记忆：两轮后消息累积（add_messages reducer） ✅
- 线程隔离：不同 thread_id 状态互不干扰 ✅
- 流式输出：`astream(stream_mode="messages")` 产出 chunk ✅
- 图编译：注入 checkpointer 后成功编译（验证 B1/B2） ✅

## 浏览器端到端测试（E2E，chrome-devtools 文本快照）

真实浏览器（Next.js dev :3000 + FastAPI :8000，RAG_MODE=mock，真实 LLM doubao-seed-2.0-mini）全程驱动：

| 步骤 | 结果 |
|---|---|
| 访问 / -> 重定向 /login（未认证） | ✅ |
| 注册 e2e_tester（POST /api/register 200） | ✅ |
| 自动登录（POST /api/login 200）-> 跳转 /chat | ✅ |
| 加载会话列表 + 患者档案（GET /api/threads, /api/profiles 200） | ✅ |
| 发送症状"胃脘冷痛..."（POST /api/chat?stream=true 200，SSE 流式） | ✅ |
| Agent 全流程：辨证（脾胃虚寒证）+ 治法 + 方剂（黄芪建中汤加减）+ 药材剂量 + 非药物建议 + 就医指引 | ✅ |
| 安全测试：发送"附子+半夏"配伍 -> safety_guard 识别十八反"乌头反半夏" -> 拦截，不生成处方 | ✅ |
| 线程持久化：重载 + 访问 /chat/{threadId} -> 完整历史（2 轮）恢复（checkpointer aget_state） | ✅ |
| 前端无 console error/warn | ✅ |
| TCM 设计系统渲染（标题/Markdown/医疗免责声明） | ✅ |

**验证的 prompt 要求**：端到端完整用户流程、多轮对话记忆、条件路由（chat/diagnose/safety_rejected 三分支）、流式输出、安全测试（配伍禁忌拦截）、状态持久化与恢复。

## 未覆盖 / 待补充

| 项 | 原因 | 计划 |
|---|---|---|
| 前端组件单元测试 | ✅ 已完成：vitest + @testing-library，4 文件 14 用例（utils/auth/MessageBubble/stream SSE 解析） | - |
| 真实 LLM 条件路由四分支全覆盖 | E2E 已覆盖 chat/diagnose/safety_rejected；consult 追问分支未单独触发 | 可用更模糊症状触发追问 |
| WS 流式集成测试 | E2E 用 SSE（stream=true）；WS 鉴权+节点过滤已实现，集成测试待补 | 可后续补 |
| 真实 chroma 模式端到端 | ✅ 已完成：`scripts/chroma_smoke.py` 用真实 Qwen3-Embedding-0.6B 验证全链路（嵌入->入库->检索），查询"发热恶寒头项强痛"正确召回"太阳之为病...头项强痛而恶寒"(score 0.661, top-1)。全量 ingest(2616 chunk)在 CPU 上较慢，可分批或用 GPU 运行 | - |

## 安全审计（pip-audit）

| 包 | 修复前 | 修复后 | 状态 |
|---|---|---|---|
| pillow | 12.2.0（多 CVE） | 12.3.0 | ✅ 已修复 |
| gitpython | 3.1.50（2 CVE） | 3.1.57 | ✅ 已修复 |
| setuptools | 81.0.0（CVE） | 83.0.0 | ✅ 已修复 |
| pypdf2 | 3.0.1（CVE） | 替换为 pypdf 6.14.2 | ✅ 已修复 |
| torch | 2.12.1（PYSEC-2025-194） | - | ⏳ 延后（2GB 下载，运行时不依赖 setuptools） |

## 第二轮修复验证（画像合并 + 流式顺序 + RAG + 计时）

针对多轮 E2E 发现的问题修复后复测（118 单元测试 + 浏览器 E2E）：

| 修复项 | 验证结果 |
|---|---|
| **画像覆盖 Bug** | ✅ 过敏原跨多轮诊断（未提及过敏的轮次）仍保留"青霉素、海鲜"，不再被回退为"无"；体质更新+历史；新增 6 个合并语义单测 |
| **流式顺序** | ✅ SSE/WS 统一 `_STREAM_NODES` 过滤（修 WS 泄漏内部 token）；多轮流式顺序正确（分析->方->药->建议） |
| **每轮用时** | ✅ SSE/WS 记录 `elapsed_ms`，日志可见；E2E 各轮 1.2-22.8s，>30s 触发 WARN |
| **RAG 召回** | ✅ 生成 mock 数据后 RAG 返回 2 条结果，诊断引用《伤寒论》条文（来自检索）；新增 6 个 RAG 召回单测 |
| **文件读取链路** | ✅ ReaderSkill+FileParser 链路单测验证，文件内容流入 diagnosis 上下文 |
| **画像写入超时** | ✅ 提取超时 15s->25s，减少跳过 |

E2E 实测（用户 fix_test，6 轮穿插）：体质=阳虚体质、脾胃虚寒（中阳不振）；过敏史=青霉素、海鲜（跨轮保留）；安全拦截（附子反半夏）；RAG 命中（伤寒论）；各轮用时 1.2-22.8s。

## 结论

后端测试覆盖充分（**118 用例全绿**），核心路径（Embedding 一致性、LangGraph 持久化/流式、认证安全、性能基线、画像合并、RAG 召回）均已验证。两轮浏览器 E2E（21 轮穿插 + 6 轮修复验证）确认安全拦截、多会话记忆、画像累积、过敏感知、RAG 命中均正常。前端 vitest 组件级单测为后续可选补充。
