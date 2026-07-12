"""
LangGraph 图编排 — 灵医诊疗工作流的核心编排器。

设计原则:
- 所有节点通过依赖注入获取（不 import 全局单例）
- create_agent() 工厂函数组装完整图
- 路由逻辑保持不变
"""

import logging
from typing import Any

from langgraph.graph import END, START, StateGraph

from lingyi.agent.state import AgentState

logger = logging.getLogger(__name__)


def create_agent(
    llm: Any,
    rag_client: Any,
    storage: Any,
    safety_engine: Any,
    file_parser: Any = None,
    settings: Any = None,
) -> Any:
    """
    创建灵医诊疗 Agent 图。

    Args:
        llm: BaseLLM 实例
        rag_client: BaseRAGClient 实例
        storage: SQLiteStorage 实例
        safety_engine: SafetyEngine 实例
        file_parser: FileParser 实例（可选）
        settings: Settings 实例（可选）

    Returns:
        编译后的 StateGraph
    """
    from lingyi.agent.skills.diagnosis import DiagnosisSkill
    from lingyi.agent.skills.inquiry import InquirySkill
    from lingyi.agent.skills.rag_search import (
        RAGGraderSkill,
        RAGRewriteSkill,
        RAGSearchSkill,
        rag_decision_logic,
        rag_loop_logic,
    )
    from lingyi.agent.skills.reader import ReaderSkill
    from lingyi.agent.skills.safety_guard import SafetyGuardSkill
    from lingyi.agent.skills.treatment import TreatmentSkill, safety_check_logic
    from lingyi.agent.skills.writer import MemRecallSkill, WriterSkill
    from lingyi.agent.memory.summarizer import should_summarize

    # 读取配置
    max_retries = settings.safety_max_retries if settings else 3
    recall_k = settings.rag_recall_k if settings else 15
    score_threshold = settings.rag_score_threshold if settings else 0.7
    enable_evaluation = settings.rag_enable_evaluation if settings else False

    # 创建技能实例
    reader = ReaderSkill(file_parser=file_parser)
    mem_recall = MemRecallSkill(storage=storage)
    safety_guard = SafetyGuardSkill(llm=llm)
    inquiry = InquirySkill(
        llm=llm,
        max_history=settings.max_history_messages_inquiry if settings else 5,
    )
    rag_search = RAGSearchSkill(llm=llm, rag_client=rag_client, recall_k=recall_k)
    rag_grader = RAGGraderSkill(llm=llm)
    rag_rewrite = RAGRewriteSkill(llm=llm)
    diagnosis = DiagnosisSkill(
        llm=llm,
        max_history=settings.max_history_messages_diagnosis if settings else 3,
    )
    treatment = TreatmentSkill(
        llm=llm,
        safety_engine=safety_engine,
        max_history=settings.max_history_messages_treatment if settings else 2,
        max_retries=max_retries,
    )
    writer = WriterSkill(llm=llm, storage=storage)

    # ==================== 构建图 ====================
    workflow = StateGraph(AgentState)

    # 注册节点
    workflow.add_node("reader", reader.node)
    workflow.add_node("mem_recall", mem_recall.node)
    workflow.add_node("safety_guard", safety_guard.node)
    workflow.add_node("inquiry", inquiry.node)
    workflow.add_node("rag_search", rag_search.node)
    workflow.add_node("rag_grader", rag_grader.node)
    workflow.add_node("rag_rewrite", rag_rewrite.node)
    workflow.add_node("diagnosis", diagnosis.node)
    workflow.add_node("treatment", treatment.node)
    workflow.add_node("summarize_condition", _summarize_condition_node)
    workflow.add_node("writer", writer.node)

    # ==================== 边连接 ====================

    # 主流程: START -> reader -> mem_recall -> safety_guard
    workflow.add_edge(START, "reader")
    workflow.add_edge("reader", "mem_recall")
    workflow.add_edge("mem_recall", "safety_guard")

    # 安全审查后路由
    workflow.add_conditional_edges(
        "safety_guard",
        _safety_guard_router,
        {"safety_rejected": "summarize_condition", "pass": "inquiry"},
    )

    # 问诊后路由
    workflow.add_conditional_edges(
        "inquiry",
        lambda state: _master_router(state, rag_decision_logic),
        {"rag_search": "rag_search", "diagnosis": "diagnosis", "end": END},
    )

    # RAG 评估环路（可通过 rag_enable_evaluation 配置关闭）
    if enable_evaluation:
        # 启用评估: rag_search -> rag_grader -> (diagnosis | rag_rewrite -> rag_search)
        workflow.add_edge("rag_search", "rag_grader")
        workflow.add_conditional_edges(
            "rag_grader",
            lambda state: rag_loop_logic(state, score_threshold, max_retries),
            {"diagnose": "diagnosis", "rag_rewrite": "rag_rewrite"},
        )
        workflow.add_edge("rag_rewrite", "rag_search")
    else:
        # 关闭评估: rag_search 直接到 diagnosis
        workflow.add_edge("rag_search", "diagnosis")

    # 辨证 -> 处方
    workflow.add_edge("diagnosis", "treatment")

    # 处方安全校验路由
    workflow.add_conditional_edges(
        "treatment",
        lambda state: safety_check_logic(state, max_retries),
        {"re_treatment": "treatment", "safe_to_end": "summarize_condition"},
    )

    # 压缩判断 -> (summarize | writer)
    workflow.add_conditional_edges(
        "summarize_condition",
        lambda state: _summarize_decision(state, settings),
        {"summarize": "summarize_and_write", "write": "writer"},
    )

    # 压缩后写入
    workflow.add_node("summarize_and_write", _summarize_and_write_node(llm))
    workflow.add_edge("summarize_and_write", "writer")

    # 写入 -> END
    workflow.add_edge("writer", END)

    # ==================== 编译 ====================
    from lingyi.storage.checkpointer import create_checkpointer

    db_path = settings.db_path if settings else "storage/checkpoints.db"
    checkpointer = create_checkpointer(db_path)

    compiled = workflow.compile(checkpointer=checkpointer)
    logger.info("Agent 图编译完成")
    return compiled


# ==================== 路由函数 ====================

def _safety_guard_router(state: dict[str, Any]) -> str:
    """安全审查后路由。"""
    if state.get("intent_type") == "safety_rejected":
        return "safety_rejected"
    return "pass"


def _master_router(state: dict[str, Any], rag_decision_logic=None) -> str:
    """
    问诊后主路由 — 合并了意图路由和 RAG 决策。

    Returns:
        "rag_search" — 需要 RAG 检索
        "diagnosis" — 直接辨证
        "inquiry_more" — 继续问诊
        "end" — 结束
    """
    intent = state.get("intent_type", "chat")
    inquiry_count = state.get("inquiry_count", 0)

    if intent in ("consult", "inquiry_more"):
        if inquiry_count >= 2:
            # 已追问 2 次，强制进入诊断，不再追问
            logger.info("已追问 %d 次，强制进入诊断", inquiry_count)
            if rag_decision_logic:
                return rag_decision_logic(state)
            return "diagnosis"
        # 未超限，暂停图执行，返回追问给用户
        return "end"

    if intent == "diagnose":
        # 合并 RAG 决策逻辑
        if rag_decision_logic:
            return rag_decision_logic(state)
        return "diagnosis"

    return "end"


def _summarize_condition_node(state: dict[str, Any]) -> dict[str, Any]:
    """压缩判断节点 — 纯路由，不修改状态。"""
    return {}


def _summarize_decision(state: dict[str, Any], settings: Any = None) -> str:
    """判断是否需要压缩。"""
    from lingyi.agent.memory.summarizer import should_summarize
    threshold = settings.token_compression_threshold if settings else 8000
    if should_summarize(state, threshold):
        return "summarize"
    return "write"


def _summarize_and_write_node(llm: Any):
    """压缩并写入的组合节点。"""
    from lingyi.agent.memory.summarizer import summarize_node

    async def node(state: dict[str, Any]) -> dict[str, Any]:
        return await summarize_node(state, llm)

    return node
