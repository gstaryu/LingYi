from typing import Annotated, List, TypedDict, Optional, Dict, Any
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict, total=False):
    """
    灵医 的状态定义
    """
    messages: Annotated[List[BaseMessage], add_messages]
    symptoms: List[str]
    input_files: List[str]
    # 用于跟踪已解析的文件列表，防重复解析
    parsed_files: List[str]
    # 用于存储从文件中提取出的纯文本内容
    extracted_file_content: str
    retrieved_docs: List[str]
    intent_type: str
    rag_retry_count: int
    rag_score: float
    diagnosis: Optional[str]
    treatment_plan: Optional[str]
    safety_errors: Optional[str]
    safety_retry_count: int
    safety_violation_msg: Optional[str]
    patient_profile: Dict[str, Any]

    # ====== 上下文压缩 / 摘要记忆 ======
    # 对话历史摘要（病历纪要）
    summary: str
    # 已经被纳入 summary 的 messages 下标边界（不包含该下标本身），通常会指向 len(messages)-KEEP_LAST_N
    summarized_until: int
    # 上一次进行摘要时的 messages 总数，用于冷却判断
    last_summarized_message_count: int

    has_provided_treatment: bool
