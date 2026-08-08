"""
Agent 状态定义 — LangGraph StateGraph 的状态字典。

所有节点共享此状态，通过 TypedDict 保证类型安全。
"""

from typing import Annotated, Any, Optional
from operator import add

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


def _consultation_notes_reducer(left: list, right: Any) -> list:
    """会诊笔记归约器。

    - ``None`` → 重置为空列表（每次新 diagnose 流程开始时由 dispatch_specialists 触发，
      避免 operator.add 累积上一轮的笔记导致专家数翻倍）。
    - ``list`` → 追加（专家节点并行返回 ``[note]``，通过多次归约累积为 3 条）。
    """
    if right is None:
        return []
    return (left or []) + right


class AgentState(TypedDict, total=False):
    """
    灵医 Agent 状态。

    total=False 表示所有字段都是可选的，节点只需返回需要更新的字段。
    """

    # ==================== 对话 ====================
    messages: Annotated[list[BaseMessage], add_messages]
    """对话历史（自动合并消息）。"""

    # ==================== 文件 ====================
    input_files: list[str]
    """用户上传的文件路径列表。"""

    parsed_files: list[str]
    """已解析的文件路径（防重复解析）。"""

    extracted_file_content: str
    """文件解析后的纯文本内容。"""

    # ==================== 症状与意图 ====================
    symptoms: list[str]
    """结构化症状清单。"""

    intent_type: str
    """用户意图类型: chat / consult / diagnose / safety_rejected。"""

    # ==================== RAG ====================
    retrieved_docs: list[str]
    """RAG 检索到的文献片段。"""

    rag_retry_count: int
    """RAG 重试计数。"""

    rag_score: float
    """RAG 评估得分（0-1）。"""

    # ==================== 诊疗 ====================
    diagnosis: Optional[str]
    """辨证结论。"""

    treatment_plan: Optional[str]
    """处方建议。"""

    # ==================== 多智能体会诊 ====================
    consultation_notes: Annotated[list[dict], _consultation_notes_reducer]
    """会诊笔记列表（reducer: _consultation_notes_reducer - None 重置 / list 追加）。
    每个专家节点追加一条笔记；dispatch_specialists 在新 diagnose 流程开始时传 None 重置。"""

    # ==================== 安全 ====================
    safety_errors: Optional[str]
    """安全校验错误信息。"""

    safety_retry_count: int
    """安全重试计数。"""

    safety_violation_msg: Optional[str]
    """违规消息记录。"""

    # ==================== 对抗安全审查者（Phase 3） ====================
    reviewer_approved: bool
    """对抗审查者是否批准处方（智能审查层）。"""

    reviewer_retry_count: int
    """对抗审查者重试计数（与 safety_retry_count 独立）。"""

    synthesis_message_id: Optional[str]
    """综合节点生成的 AIMessage 的 ID；重试时据此 RemoveMessage 移除上一版被拒处方，
    避免历史中残留多版处方导致前端重复渲染辨证结论/处方建议。"""

    # ==================== 记忆 ====================
    patient_profile: dict[str, Any]
    """患者长期画像（体质、过敏史、既往史）。"""

    summary: str
    """上下文压缩摘要。"""

    summarized_until: int
    """已摘要到的消息索引。"""

    last_summarized_message_count: int
    """上次摘要时的消息数量。"""

    has_provided_treatment: bool
    """是否已提供治疗方案（用于后续跟进判断）。"""

    inquiry_count: int
    """问诊节点执行次数（控制追问轮数）。"""

    profile_updated: bool
    """画像是否已更新（触发重新加载）。"""

    thread_id: str
    """会话线程 ID。"""

    username: str
    """当前认证用户名（用作画像 key，跨会话共享）。"""
