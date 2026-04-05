from langgraph.graph import StateGraph, END, START
from agent.state import AgentState
from agent.skills.inquiry import inquiry_node
from agent.skills.safety_guard import safety_guard_node
from agent.skills.diagnosis import diagnosis_node
from agent.skills.rag_search import rag_search_node, rag_decision_logic, rag_grader_node, rag_rewrite_node, rag_loop_logic
from agent.skills.treatment import treatment_node, safety_check_logic
from agent.memory.summarizer import summarizer_node
from agent.memory.checkpointer import memory_saver
from agent.skills.reader import reader_node
from agent.skills.writer import mem_recall_node, writer_node
from config import config


def master_router(state: AgentState):
    """
    主路由：合并意图识别与 RAG 决策逻辑。
    """
    intent = state.get("intent_type", "chat")

    if intent == "diagnose":
        return rag_decision_logic(state)
    elif intent == "inquiry_more":
        return "end"

    return "end"


def summarizer_condition(state: AgentState):
    """
    判断是否需要触发 Summarizer
    """
    # 粗略计算 token 数量：按字符数粗略折算（1 token ≈ 2 字符，中文通常更短）
    # 或者直接按消息总和计算，这里简单实现：只要 messages 元素超过一定数量，或者通过某种方式判定
    total_length = sum(len(m.content) if m.content else 0 for m in state.get("messages", []))
    if total_length > config.TOKEN_COMPRESSION_THRESHOLD:
        return "summarize"
    return "writer"


# 构建图
def create_graph() -> StateGraph:
    """
    创建并返回完整的状态流图
    """
    workflow = StateGraph(AgentState)

    workflow.add_node("reader", reader_node)
    workflow.add_node("mem_recall", mem_recall_node)
    workflow.add_node("safety_guard", safety_guard_node)
    workflow.add_node("inquiry", inquiry_node)
    workflow.add_node("rag_search", rag_search_node)
    workflow.add_node("rag_grader", rag_grader_node)
    workflow.add_node("rag_rewrite", rag_rewrite_node)
    workflow.add_node("diagnosis", diagnosis_node)
    workflow.add_node("treatment", treatment_node)
    workflow.add_node("summarize", summarizer_node)
    workflow.add_node("writer", writer_node)

    workflow.add_edge(START, "reader")
    workflow.add_edge("reader", "mem_recall")
    workflow.add_edge("mem_recall", "safety_guard")

    def safety_router(state: AgentState):
        if state.get("intent_type") == "safety_rejected":
            return "summarize_condition_node"
        return "inquiry"

    workflow.add_conditional_edges("safety_guard", safety_router, {"summarize_condition_node": "summarize_condition_node", "inquiry": "inquiry"})

    workflow.add_conditional_edges(
        "inquiry",
        master_router, {
            "rag_search": "rag_search",
            "diagnosis": "diagnosis",
            "end": END
        })

    workflow.add_edge("rag_search", "rag_grader")

    # Important: The conditional edges return a string based on the state.
    # Because conditional edges execute immediately after the node, they DO have access to the correctly updated state dictionary.
    workflow.add_conditional_edges(
        "rag_grader",
        rag_loop_logic, {
            "diagnosis": "diagnosis",
            "rag_rewrite": "rag_rewrite"
        }
    )
    workflow.add_edge("rag_rewrite", "rag_search")

    workflow.add_edge("diagnosis", "treatment")

    workflow.add_conditional_edges(
        "treatment",
        safety_check_logic, {
            "re_treatment": "treatment",
            "safe_to_end": "summarize_condition_node"
        })

    # Dummy node to handle the branching to summarize or writer
    def pass_through(state: AgentState):
        return state

    workflow.add_node("summarize_condition_node", pass_through)

    workflow.add_conditional_edges(
        "summarize_condition_node",
        summarizer_condition, {
            "summarize": "summarize",
            "writer": "writer"
        })

    workflow.add_edge("summarize", "writer")
    workflow.add_edge("writer", END)

    return workflow


app = create_graph().compile(checkpointer=memory_saver)
