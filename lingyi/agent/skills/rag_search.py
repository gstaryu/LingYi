"""
RAG 知识检索技能 — 古籍文献检索、评估、重写环路。

实现按需知识检索:
1. 判断是否需要 RAG（路由逻辑）
2. 执行向量检索
3. LLM 评估检索质量
4. 若质量不达标，重写查询词重试
"""

import logging
from typing import Any

from lingyi.agent.skills.base import BaseSkill

logger = logging.getLogger(__name__)


class RAGSearchSkill(BaseSkill):
    """
    RAG 检索技能节点。

    通过构造函数注入 RAG client，执行向量检索。
    支持 mock/chroma 双模式（由注入的 RAG client 决定）。
    """

    def __init__(self, llm: Any = None, rag_client: Any = None, recall_k: int = 15):
        """
        初始化 RAG 检索技能。

        Args:
            llm: LLM 实例（用于查询重写）
            rag_client: BaseRAGClient 实例
            recall_k: 粗排召回数量
        """
        super().__init__(llm=llm)
        self.rag_client = rag_client
        self.recall_k = recall_k

    async def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        执行 RAG 检索。

        Args:
            state: AgentState

        Returns:
            retrieved_docs 字段
        """
        if not self.rag_client:
            return {"retrieved_docs": []}

        # 构建检索查询
        symptoms = state.get("symptoms", [])
        query = " ".join(symptoms) if symptoms else ""

        if not query:
            return {"retrieved_docs": []}

        try:
            # 执行检索
            results = await self.rag_client.hybrid_search(query, n_results=self.recall_k)
            docs = [r.content for r in results if r.content]
            logger.info("RAG 检索完成: 查询='%s', 返回 %d 条结果", query[:50], len(docs))
            return {"retrieved_docs": docs}
        except Exception as e:
            logger.error("RAG 检索失败: %s", e)
            return {"retrieved_docs": []}


class RAGGraderSkill(BaseSkill):
    """
    RAG 评估技能节点。

    使用 LLM 评估检索到的文献与当前症状的相关性。
    输出 0.0-1.0 的评分。
    """

    def __init__(self, llm: Any = None):
        super().__init__(llm=llm)

    def build_messages(self, state: dict[str, Any]) -> list[dict[str, str]]:
        """构建评估消息列表。"""
        symptoms = state.get("symptoms", [])
        docs = state.get("retrieved_docs", [])

        prompt = (
            "你是一位中医文献评估专家。请评估以下检索到的古籍文献与患者症状的关联度。\n\n"
            f"患者症状: {', '.join(symptoms)}\n\n"
            f"检索到的文献:\n"
        )
        for i, doc in enumerate(docs[:5], 1):
            prompt += f"\n--- 文献 {i} ---\n{doc}\n"

        prompt += (
            "\n\n请以 JSON 格式输出评估结果:\n"
            '{"score": 0.0-1.0, "reasoning": "评分理由"}\n'
            "评分标准: 0.8+ 直接相关, 0.6-0.8 部分相关, 0.6以下 关联较弱"
        )

        return [{"role": "user", "content": prompt}]

    async def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        """评估 RAG 检索质量，同时递增重试计数。"""
        if not self.llm:
            return {"rag_score": 0.5, "rag_retry_count": state.get("rag_retry_count", 0) + 1}

        messages = self.build_messages(state)
        try:
            response = await self.llm.ainvoke(messages)
            parsed = self.parse_json_response(response, fallback={"score": 0.5})
            score = float(parsed.get("score", 0.5))
            return {"rag_score": score, "rag_retry_count": state.get("rag_retry_count", 0) + 1}
        except Exception as e:
            logger.warning("RAG 评估失败: %s", e)

        return {"rag_score": 0.5, "rag_retry_count": state.get("rag_retry_count", 0) + 1}


class RAGRewriteSkill(BaseSkill):
    """
    RAG 查询重写技能节点。

    将口语化症状转化为专业中医术语，用于二次检索。
    """

    def __init__(self, llm: Any = None):
        super().__init__(llm=llm)

    async def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        """重写检索查询词。"""
        symptoms = state.get("symptoms", [])
        if not symptoms or not self.llm:
            return {}

        prompt = (
            "请将以下口语化症状描述转化为专业的中医术语检索词。\n"
            "例如: '肚子胀、怕冷、拉肚子' → '太阴病 腹满 自利 脾阳虚'\n\n"
            f"症状: {', '.join(symptoms)}\n\n"
            "只输出转化后的检索词，用空格分隔。"
        )

        try:
            response = await self.llm.ainvoke([{"role": "user", "content": prompt}])
            # 用重写后的查询替换症状列表
            rewritten = [s.strip() for s in response.split() if s.strip()]
            if rewritten:
                return {"symptoms": rewritten}
        except Exception as e:
            logger.warning("查询重写失败: %s", e)

        return {}


def rag_decision_logic(state: dict[str, Any]) -> str:
    """
    RAG 路由逻辑 — 判断是否需要启动知识检索。

    Args:
        state: AgentState

    Returns:
        "rag_search" — 需要检索
        "diagnose" — 直接辨证（跳过检索）
        "end" — 非就诊意图，结束
    """
    intent = state.get("intent_type", "chat")
    symptoms = state.get("symptoms", [])

    # 非就诊意图，直接结束
    if intent not in ("diagnose", "consult"):
        return "end"

    # 有症状且意图为 diagnose，启动 RAG
    if intent == "diagnose" and symptoms:
        return "rag_search"

    # 兜底：直接辨证
    return "diagnosis"


def rag_loop_logic(state: dict[str, Any], score_threshold: float = 0.7, max_retries: int = 3) -> str:
    """
    RAG 环路路由逻辑 — 判断是否需要重写查询重试。

    Args:
        state: AgentState
        score_threshold: 评分阈值
        max_retries: 最大重试次数

    Returns:
        "diagnose" — 评分达标或重试耗尽，进入辨证
        "rag_rewrite" — 评分不达标，重写查询
    """
    score = state.get("rag_score", 0.0)
    retries = state.get("rag_retry_count", 0)

    if score >= score_threshold or retries >= max_retries:
        return "diagnose"
    return "rag_rewrite"
