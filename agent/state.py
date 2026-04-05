from typing import Annotated, List, TypedDict, Optional, Dict, Any
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict, total=False):
    """
    灵医 2.0 的状态定义
    """
    messages: Annotated[List[BaseMessage], add_messages]
    symptoms: List[str]
    input_files: List[str]
    # 新增：用于跟踪已解析的文件列表，防重复解析
    parsed_files: List[str]
    # 新增：用于存储从文件中提取出的纯文本内容
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
    summary: str
    has_provided_treatment: bool
