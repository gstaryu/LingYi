"""
Agent 状态定义 — LangGraph StateGraph 的状态字典。

所有节点共享此状态，通过 TypedDict 保证类型安全。
"""

from typing import Annotated, Any, Optional

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


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

    # ==================== 安全 ====================
    safety_errors: Optional[str]
    """安全校验错误信息。"""

    safety_retry_count: int
    """安全重试计数。"""

    safety_violation_msg: Optional[str]
    """违规消息记录。"""

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
