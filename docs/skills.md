# 技能开发指南

## 概述

灵医的每个功能节点都是一个 **Skill**，由 `.py`（逻辑）+ `.md`（prompt）组成。

## 创建新 Skill

### 1. 创建 Python 文件

在 `lingyi/agent/skills/` 下创建 `my_skill.py`：

```python
from lingyi.agent.skills.base import BaseSkill

class MySkill(BaseSkill):
    """我的技能。"""

    def __init__(self, llm=None):
        super().__init__(llm=llm)

    async def execute(self, state: dict) -> dict:
        messages = self.build_messages(state)
        response = await self.llm.ainvoke(messages)
        return {"messages": [{"role": "assistant", "content": response}]}
```

### 2. 创建 Prompt 文件

在同一目录创建 `my_skill.md`，内容为 system prompt。

### 3. 注册到图

在 `lingyi/agent/graph.py` 的 `create_agent()` 中添加：

```python
my_skill = MySkill(llm=llm)
workflow.add_node("my_skill", my_skill.node)
workflow.add_edge("previous_node", "my_skill")
```

## BaseSkill API

| 方法 | 说明 |
|---|---|
| `_load_prompt()` | 自动加载同名 .md 文件（CamelCase → snake_case） |
| `build_messages(state)` | 构建消息列表（可覆盖） |
| `execute(state)` | 抽象方法，实现业务逻辑 |
| `node(state)` | LangGraph 节点入口 |

## 现有技能列表

| 技能 | 文件 | Prompt | 说明 |
|---|---|---|---|
| InquirySkill | `inquiry.py` | `inquiry.md` | 问诊与意图识别 |
| DiagnosisSkill | `diagnosis.py` | `diagnosis.md` | 辨证论治 |
| TreatmentSkill | `treatment.py` | `treatment.md` | 处方建议 + 安全校验 |
| SafetyGuardSkill | `safety_guard.py` | `safety_guard.md` | 前置安全审查（关键词预检 + LLM） |
| RAGSearchSkill | `rag_search.py` | `rag_search.md` | RAG 检索 |
| RAGGraderSkill | `rag_search.py` | `rag_grader.md` | RAG 质量评估（可选） |
| RAGRewriteSkill | `rag_search.py` | `rag_rewrite.md` | 查询重写（可选） |
| ReaderSkill | `reader.py` | `reader.md` | 文档解析 |
| WriterSkill | `writer.py` | `writer.md` | 画像提取与持久化（异步） |
| MemRecallSkill | `writer.py` | - | 画像条件加载（无 LLM） |
