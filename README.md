# 🎋 灵医 (LingYi) - 中医诊疗多智能体系统

![Python](https://img.shields.io/badge/Python-3.12-blue.svg)
![Framework](https://img.shields.io/badge/Framework-LangGraph%20%7C%20FastAPI-green.svg)
![LLM](https://img.shields.io/badge/LLM-MiMo--v2.5--Pro-red.svg)
![UI](https://img.shields.io/badge/UI-Streamlit-FF4B4B.svg)

**灵医 (LingYi)** 是一款基于 **LangGraph** 框架的中医诊疗多智能体系统，采用 **FastAPI 后端 + Streamlit 前端** 分层架构。

---

## ✨ 核心特性

- 🩺 **多轮问诊**：逐步收集症状，智能判断就诊意图
- 📚 **按需 RAG**：根据辨证需要动态检索中医古籍（伤寒论、金匮要略等）
- 🛡️ **双重安全护栏**：前置意图阻断 + 后置处方配伍校验（十八反/十九畏）
- 💾 **患者画像**：SQLite 持久化体质、过敏史、既往处方
- ⚡ **性能优化**：安全审查关键词预检、Writer 异步执行、画像条件加载

---

## 🚀 快速开始

```bash
# 安装
pip install -e ".[dev]"

# 配置
cp .env.example .env  # 填入 DASHSCOPE_API_KEY

# 数据初始化
python -m data_pipeline.ingest          # 切分古籍为 JSON
python -m data_pipeline.ingest --mode mock  # 生成 mock 数据

# 启动（两个终端）
uvicorn lingyi.api.app:app --reload --port 8000   # 终端 1：API
streamlit run lingyi/ui/app.py                     # 终端 2：前端

# 测试
pytest tests/ -v
```

---

## 📁 目录结构

```text
LingYi/
├── lingyi/                  # 主包
│   ├── config.py            # pydantic-settings 配置
│   ├── models/              # LLM/Embedding 抽象层
│   ├── agent/               # LangGraph 图 + 技能节点
│   ├── rag/                 # RAG 子系统（mock/chroma）
│   ├── safety/              # 配伍禁忌安全引擎
│   ├── storage/             # SQLite 持久化
│   ├── api/                 # FastAPI 后端
│   └── ui/                  # Streamlit 前端
├── data_pipeline/           # TCM 数据处理
├── tests/                   # pytest 测试
├── docs/                    # 文档
└── TCM_data/                # 中医古籍数据
```

---

## ⚠️ 免责声明

本项目仅供技术探索与学术研究，不具备临床执业资格。如有身体不适请就医。

## 📄 License

[MIT License](LICENSE)
