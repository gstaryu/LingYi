# 测试指南

## 概述

灵医项目包含后端和前端两套测试体系，全部使用桩（stub）离线运行，无需真实 LLM API。此外提供一套六维在线评测体系（需要 LLM API Key）。

| 端 | 框架 | 测试数 | 运行目录 |
|---|---|---|---|
| 后端 | pytest | 319 passed + 1 skipped | 项目根目录 |
| 前端 | vitest + @testing-library/react | 37 tests | `frontend/` |
| 评测 | evaluation/（LLM-in-the-loop） | 201 条标注数据 | 项目根目录 |

## 评测体系（evaluation/）

六维指标，每维 ≥30 条标注数据，运行器为 `python -m evaluation.runner`：

| 维度 | 指标 | 数据量 | 需要 chroma |
|---|---|---|---|
| rag | Recall@3/5、MRR、nDCG@5 | 46 条 golden 检索集 | 是 |
| faithfulness | 忠实度均分（1-5）、矛盾率 | 30 条经典问答 | 是 |
| quality | 辨证准确/完整性/清晰度/安全表达（LLM-judge 1-5） | 35 条标准证候病例 | 建议 chroma |
| router | 意图路由准确率（chat/consult/diagnose） | 30 条标注查询 | 否 |
| safety | SafetyEngine 规则准确率 + 端到端拦截率 | 20 药对 + 30 对抗用例 | 否 |
| performance | 端到端/分节点延迟 P50/P95、Token/请求 | 30 轮（15 chat + 15 diagnose） | 否 |
| performance | 端到端/分节点延迟 P50/P95、Token/请求 | 30 轮（15 chat + 15 diagnose） | 否 |

运行示例：

```bash
# RAG 相关评测（需 chroma 模式）
$env:RAG_MODE="chroma"; python -m evaluation.runner --only rag,faithfulness

# Agent 流程评测
python -m evaluation.runner --only quality,router,safety,performance

# 冒烟（每项前 N 条）
python -m evaluation.runner --only safety --limit 5
```

报告落 `evaluation/reports/`（JSON 明细 + summary.md 汇总），完整分析见 [evaluation_report.md](evaluation_report.md)。

## 后端测试

## 后端测试

### 运行

```bash
conda activate lingyi
pytest tests/ -v
```

### 目录结构

```
tests/
├── conftest.py                 # 公共 fixture
├── stubs.py                    # 测试桩定义（StubLLM, StubChatModel, StubRAGClient 等）
├── test_config.py              # 配置测试
├── test_factory.py             # 模型工厂测试
├── test_inquiry.py             # 问诊技能测试
├── test_diagnosis.py           # 辨证技能测试
├── test_treatment.py           # 处方技能测试
├── test_rag_search.py          # RAG 检索测试
├── test_rag_recall.py          # RAG 召回测试
├── test_rag_rerank.py          # RAG 重排测试
├── test_rag_hybrid.py          # 混合检索（BM25 + 向量 RRF）测试
├── test_chroma_ingest.py       # ChromaDB 入库测试
├── test_embedding.py           # Embedding 测试
├── test_graph_flow.py          # 工作流图流程测试
├── test_reader.py              # 文件解析测试
├── test_summarizer.py          # 上下文压缩测试
├── test_profile_writer.py      # 画像写入测试
├── test_profile_merge.py       # 画像合并测试
├── test_safety_guard_failclosed.py  # 安全拦截 fail-closed 测试
├── test_safety_rules.py        # SafetyEngine 规则测试
├── test_structured_output.py   # 结构化输出测试
├── test_json_parsing.py        # JSON 解析测试
├── test_parsers.py             # 文件解析器测试
├── test_session_naming.py      # 会话命名测试
├── test_tracing.py             # 链路追踪测试
├── test_api/
│   ├── conftest.py             # API 测试 fixture
│   ├── test_api_routes.py      # API 路由测试
│   ├── test_security.py        # 安全测试
│   ├── test_thread_authz.py    # 线程归属校验测试
│   └── test_performance.py     # 性能测试
├── test_multiagent/
│   ├── test_multiagent_graph.py    # 多智能体图测试
│   ├── test_specialists.py         # 专家节点测试
│   ├── test_safety_reviewer.py     # 对抗审查者测试
│   └── test_agent_mode_switch.py   # 模式切换测试
├── test_tools/
│   └── test_tools.py           # 工具层测试
├── test_knowledge/
│   └── test_kb_store.py        # 知识库存储测试
├── test_mcp/
│   └── test_mcp_server.py      # MCP 服务端测试
├── test_storage/
│   └── test_sqlite_store.py    # SQLite 存储测试
└── test_data_pipeline/
    └── (数据管道测试)
```

### 测试桩（stubs.py）

`tests/stubs.py` 定义所有测试桩，通过构造注入或 `app.dependency_overrides` 注入，不靠环境变量分支：

| 桩 | 替代 | 说明 |
|---|---|---|
| `StubLLM` | `DashScopeLLM` | 固定响应 LLM，支持 `with_structured_output` |
| `StubChatModel` | `ChatOpenAI` | 支持 `ainvoke` 和 `bind_tools` |
| `StubRAGClient` | `BaseRAGClient` | 返回预设检索结果 |
| `StubStorage` | `SQLiteStorage` | 内存字典模拟存储 |
| `StubReranker` | `BaseReranker` | 透传结果 |
| `StubEmbedding` | `BaseEmbedding` | 固定向量 |

### MCP 测试门控

部分测试需要 MCP 子进程（`web_search` 工具），通过 `LINGYI_TEST_MCP` 环境变量门控：

- 未设置或 `false`：跳过需 MCP 子进程的测试（1 skipped 的来源）
- `true`：执行完整 MCP 集成测试

### 测试原则

- **全离线**：所有测试用桩，无需真实 LLM API 或网络连接
- **构造注入**：桩通过构造函数参数注入，不靠环境变量分支
- **dependency_overrides**：API 层测试通过 `app.dependency_overrides` 注入桩实例
- **不使用全局单例**：`deps.py` 无模块级全局，测试可并行运行多实例

## 前端测试

### 运行

```bash
cd frontend
npm run test
```

### 测试框架

- **vitest**：测试运行器
- **@testing-library/react**：React 组件测试
- **jsdom**：DOM 模拟环境

### 测试文件

| 文件 | 测试内容 |
|---|---|
| `lib/__tests__/utils.test.ts` | 工具函数 |
| `lib/__tests__/stream.test.ts` | SSE 流解析 |
| `stores/__tests__/auth.test.ts` | 认证状态管理 |
| `components/chat/__tests__/MessageBubble.test.tsx` | 消息气泡组件 |
| `components/chat/__tests__/ChatWindow.test.ts` | 聊天窗口组件 |
| `components/chat/__tests__/ConsultationTimeline.test.tsx` | 会诊时间线组件 |
| `components/chat/__tests__/PrescriptionCard.test.tsx` | 处方卡片组件 |

### 测试覆盖范围

- **组件渲染**：验证组件正确渲染各种状态
- **用户交互**：点击、输入等交互行为
- **流解析**：SSE 事件流的 token 拼接与阶段进度处理
- **API 调用**：API 请求与响应处理
- **认证流程**：登录、登出、Token 管理
