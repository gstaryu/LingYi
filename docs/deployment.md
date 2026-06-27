# 部署指南

## 环境要求

- Python ≥ 3.12
- Conda 环境: `lingyi`

## 安装

```bash
git clone <repo-url>
cd LingYi
pip install -e ".[dev]"
cp .env.example .env
# 编辑 .env，填入 DASHSCOPE_API_KEY
```

## 数据初始化

```bash
python -m data_pipeline.ingest          # 输出 JSON
python -m data_pipeline.ingest --mode mock  # 生成 mock 数据
```

## 启动服务

```bash
# 终端 1：FastAPI 后端
uvicorn lingyi.api.app:app --reload --port 8000

# 终端 2：Streamlit 前端
streamlit run lingyi/ui/app.py --server.port 8501
```

## 运行测试

```bash
pytest tests/ -v
```

## 环境变量

| 变量 | 说明 | 默认值 |
|---|---|---|
| `DASHSCOPE_API_KEY` | API Key | - |
| `MODEL_NAME` | LLM 模型 | `qwen-max` |
| `RAG_MODE` | RAG 模式 | `mock` |
| `RAG_ENABLE_EVALUATION` | RAG 质量评估循环 | `false` |
| `EMBEDDING_MODE` | Embedding | `local` |
| `LOG_LEVEL` | 日志级别 | `INFO` |
| `ENVIRONMENT` | 运行环境 | `development` |

## 性能优化说明

- **安全审查关键词预检**：用户消息无药材相关词汇时，跳过 LLM 调用（节省 ~40s）
- **Writer 异步执行**：画像提取在后台运行，不阻塞响应返回（节省 ~40s）
- **画像条件加载**：仅在首轮或画像更新后从数据库加载（减少 DB 查询）
- **RAG 评估开关**：默认关闭，检索后直接进入辨证（减少 LLM 调用）
