"""
多智能体会诊图 - 并行专家会诊 + 综合合成的 LangGraph 编排。

替换 workflow 图中固定的 diagnosis->treatment 段为：
  dispatch_specialists -> [辨证/方剂/本草 专家并行] -> synthesis -> reviewer -> safety_check

设计要点:
- 复用 workflow 图的前置节点（reader/mem_recall/safety_guard/inquiry）和后置节点（summarize/writer）
- 诊断意图路由到 dispatch_specialists，用 Send 并行扇出到三个专家子图
- 专家各自用 create_agent 构建 ReAct 子图，返回 consultation_notes（_consultation_notes_reducer 归约）
- synthesis 节点汇总会诊笔记，生成 diagnosis + treatment_plan
- reviewer 节点（Phase 3 对抗审查者）智能审查处方，不通过则回 synthesis 重生成（≤ max_retries）
- safety_check 节点确定性硬校验（SafetyEngine 十八反/十九畏），不通过则回 synthesis 重生成（≤ max_retries）
- 双重防御: reviewer（智能层）+ safety_check（确定性层），SafetyEngine 为最终裁决者
- AGENT_MODE=multiagent 时由 app.py lifespan 调用此工厂
"""

import json
import logging
import re
import uuid
from typing import TYPE_CHECKING, Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from lingyi.agent.state import AgentState

if TYPE_CHECKING:
    from lingyi.config import Settings
    from lingyi.models.base import BaseLLM
    from lingyi.parsers.file_parser import FileParser
    from lingyi.rag.base import BaseRAGClient
    from lingyi.safety.rules import SafetyEngine
    from lingyi.storage.base import BaseProfileStore

logger = logging.getLogger(__name__)


# ==================== 阶段进度事件（自定义流） ====================

# 阶段 -> 中文标签映射（前端会诊时间线复用同一套标签）
STAGE_LABELS: dict[str, str] = {
    "inquiry": "问诊",
    "bianzheng": "辨证",
    "fangji": "方剂",
    "bencao": "本草",
    "synthesis": "综合",
    "reviewer": "安全审查",
    "safety_check": "安全校验",
}


def _emit_stage(stage: str, label: str, status: str = "start") -> None:
    """向 LangGraph 自定义流发送阶段进度事件。

    使用 get_stream_writer()（langgraph 1.2.6，contextvars 传播）。
    必须在图节点内部调用；直接调用节点（如单元测试）时无运行时上下文，
    get_stream_writer 会抛错，此处吞掉异常保证节点本身不受影响。
    """
    try:
        from langgraph.config import get_stream_writer

        get_stream_writer()({"type": "stage", "stage": stage, "label": label, "status": status})
    except Exception:  # noqa: BLE001 - 流上下文缺失时静默跳过
        pass


def _wrap_with_stage(stage: str, label: str, node_fn: Any):
    """包装图节点，在执行前后发送 stage start/done 事件。

    保留原节点函数名便于 LangGraph 追踪与日志。并行专家节点各自独立发送，
    前端时间线据此点亮对应阶段。
    """

    async def wrapped(state: dict[str, Any]) -> dict[str, Any]:
        _emit_stage(stage, label, "start")
        result = await node_fn(state)
        _emit_stage(stage, label, "done")
        return result

    wrapped.__name__ = getattr(node_fn, "__name__", f"node_{stage}")
    return wrapped


# ==================== 工具筛选 ====================

def _filter_tools(tools: list, names: set[str]) -> list:
    """从工具列表中按名称筛选子集。"""
    return [t for t in tools if t.name in names]


# ==================== 药材提取（与 TreatmentSkill._extract_herbs 逻辑一致） ====================

def _extract_herbs(text: str) -> list[str]:
    """从治疗计划文本中提取药材名称列表。"""
    if not text:
        return []
    # 尝试从 ```json ... ``` 代码块中提取
    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            if isinstance(data, dict) and "herb_names" in data:
                return data["herb_names"]
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass
    # 尝试从文本中提取含 herb_names 的 JSON 对象
    json_match = re.search(r'\{[^{}]*"herb_names"[^{}]*\}', text, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
            return data.get("herb_names", [])
        except json.JSONDecodeError:
            pass
    return []


# ==================== JSON 解析 ====================

def _parse_json_content(content: str) -> dict | None:
    """解析 LLM 返回的 JSON（支持直接 JSON、代码块、嵌入 JSON）。"""
    if not content:
        return None
    try:
        result = json.loads(content)
        if isinstance(result, dict):
            return result
    except (json.JSONDecodeError, ValueError):
        pass
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group(1))
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, ValueError):
            pass
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group())
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, ValueError):
            pass
    return None


# ==================== 路由函数 ====================

def _master_router_multiagent(state: dict[str, Any]) -> str:
    """
    问诊后主路由（多智能体版）。

    diagnose -> dispatch_specialists（并行专家会诊）
    consult -> END（仅返回追问，不进入会诊；镜像 workflow 图 _master_router 的 consult 分支）
    chat/其他 -> summarize_condition（经 writer 结束）
    """
    intent = state.get("intent_type", "chat")
    if intent == "diagnose":
        return "dispatch"
    if intent in ("consult", "inquiry_more"):
        return "end"
    return "summarize"


def _fan_out_specialists(state: dict[str, Any]) -> list[Send]:
    """
    条件边函数 - 用 Send 并行扇出到三个专家节点。

    验证 API: from langgraph.types import Send（langgraph 1.2.6 确认可用）。
    Send 创建并行分支，每个专家获得完整状态副本，返回的 consultation_notes
    通过 _consultation_notes_reducer 归约器拼接。
    """
    return [
        Send("specialist_bianzheng", state),
        Send("specialist_fangji", state),
        Send("specialist_bencao", state),
    ]


async def _dispatch_passthrough(state: dict[str, Any]) -> dict[str, Any]:
    """dispatch_specialists 节点 - 在新 diagnose 流程开始时重置会诊专用状态，
    再作为 Send 扇出的锚点。

    重置字段（防止 checkpointer 跨轮次累积）:
    - consultation_notes -> None（触发 _consultation_notes_reducer 重置为 []）
    - synthesis_message_id -> None（防止新流程的 RemoveMessage 删除上一轮的辨证消息）
    - reviewer_retry_count / safety_retry_count -> 0
    - reviewer_approved -> False
    - safety_errors -> None
    - diagnosis / treatment_plan -> ""

    保留 messages / patient_profile / inquiry_count / symptoms 等跨轮次字段。
    """
    return {
        "consultation_notes": None,  # 重置（reducer 识别 None）
        "synthesis_message_id": None,
        "reviewer_retry_count": 0,
        "reviewer_approved": False,
        "safety_errors": None,
        "safety_retry_count": 0,
        "diagnosis": "",
        "treatment_plan": "",
    }


# ==================== 综合节点 ====================

def _make_synthesis_node(chat_model: Any, safety_engine: Any = None):
    """
    创建综合节点工厂。

    读取 consultation_notes + symptoms + profile + safety_errors，
    调用 LLM 生成 diagnosis + treatment_plan。
    safety_errors 非空时（安全重试），将其注入 prompt 要求修正。
    """

    SYSTEM_PROMPT = (
        "你是中医综合诊疗专家。根据三位专家（辨证、方剂、本草）的会诊笔记，"
        "综合给出最终的辨证结论和处方建议。\n\n"
        "输出要求（必须严格遵守）：\n"
        "1. 使用以下格式输出纯文本正文（不要输出JSON对象，不要在最外层包裹大括号）：\n\n"
        "【辨证结论】\n"
        "（此处写辨证分析，包括证候名称与病机解读，作为可读的段落文本）\n\n"
        "【处方建议】\n"
        "（此处写治法与处方说明，作为可读的段落文本。处方中每味药材须标注常用剂量，\n"
        '如「人参 3-9g」「干姜 3-10g」，便于前端解析展示克数）\n\n'
        "2. 在【处方建议】段落的最后，必须附加一个 JSON 代码块，列出处方中所有药材：\n"
        "```json\n"
        '{"herb_names": ["人参", "白术", ...]}\n'
        "```\n"
        "3. 如有安全校验失败反馈，必须删除或替换存在配伍禁忌的药材。\n"
        "4. 如有配伍禁忌规则，必须严格遵守。\n"
        "5. 【安全校验失败】反馈仅针对处方本身的配伍/剂量问题，"
        "不得据此编造或修改患者未提及的生理状态（如妊娠、年龄、性别）；"
        "患者事实以【患者画像】为准，修正方式仅限替换/删除药材。\n"
        "6. 若因用户新增过敏或反馈需调整既有处方，在【辨证结论】中简要说明调整原因"
        "（如「已规避砂仁」）。\n"
        "7. 【处方建议】末尾必须包含免责声明：「孕妇、哺乳期女性使用前需咨询专业中医师」。\n\n"
        "直接输出上述格式的正文，不要添加额外说明。"
    )

    async def synthesis_node(state: dict[str, Any]) -> dict[str, Any]:
        # 构建上下文
        notes = state.get("consultation_notes", [])
        notes_text = json.dumps(notes, ensure_ascii=False, indent=2)
        symptoms = state.get("symptoms", [])
        profile = state.get("patient_profile", {})
        safety_errors = state.get("safety_errors", "")

        context_parts: list[str] = [f"【会诊笔记】\n{notes_text}"]
        if symptoms:
            context_parts.append(f"【患者症状】{', '.join(symptoms)}")
        if profile:
            context_parts.append(
                f"【患者画像】体质: {profile.get('constitution', '未知')}, "
                f"过敏: {profile.get('allergies', '无')}"
            )
        if safety_errors:
            context_parts.append(
                f"【安全校验失败 - 必须修正】\n{safety_errors}\n"
                "请删除或替换存在配伍禁忌的药材，重新生成处方。"
            )
        # 注入安全规则
        if safety_engine:
            context_parts.append(
                f"【配伍禁忌规则 - 必须严格遵守】\n{safety_engine.get_rules_text()}"
            )

        context = "\n\n".join(context_parts)

        # 调用 LLM
        from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, SystemMessage

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=context),
        ]

        try:
            response = await chat_model.ainvoke(messages)
            content = response.content if hasattr(response, "content") else str(response)
        except Exception as e:  # noqa: BLE001
            logger.error("综合节点 LLM 调用失败: %s", e)
            return {
                "diagnosis": "综合分析失败",
                "treatment_plan": f"处方生成失败: {e}",
                "has_provided_treatment": False,
            }

        # 优先尝试 JSON 解析（向后兼容：旧桩或 LLM 偶尔输出 JSON 时仍可工作）
        data = _parse_json_content(content)
        if data and "diagnosis" in data:
            # JSON 格式（遗留路径）：提取字段并构造 prose 消息
            diagnosis = data.get("diagnosis", "")
            treatment_plan = data.get("treatment_plan", content)
            user_message = f"【辨证结论】\n{diagnosis}\n\n【处方建议】\n{treatment_plan}"
        else:
            # Prose 格式（新路径）：LLLM 直接输出可读正文
            # 流式 token 即此 prose，用户实时可见
            user_message = content
            # 从 prose 中正则提取 diagnosis（【辨证结论】与【处方建议】之间的文本）
            diag_match = re.search(
                r"【辨证结论】\s*(.*?)(?=【处方建议】|$)", content, re.DOTALL
            )
            diagnosis = diag_match.group(1).strip() if diag_match else ""
            # treatment_plan 为完整 prose（含 herb_names JSON 块，供 _extract_herbs 解析）
            treatment_plan = content

        # 构造带显式 id 的 AIMessage，便于重试时按 id 移除上一版被拒处方。
        # 重试时（reviewer/safety_check 拒绝后回 synthesis），state 中已有上一版的
        # synthesis_message_id：先用 RemoveMessage 移除旧处方消息，再追加新版，
        # 确保历史中只保留最终批准的处方，避免前端 mergeAssistantMessages 拼接出
        # 重复的【辨证结论】/【处方建议】及药材 chips。
        new_msg = AIMessage(content=user_message, id=str(uuid.uuid4()))
        prev_id = state.get("synthesis_message_id")
        messages_out: list = []
        if prev_id:
            messages_out.append(RemoveMessage(id=prev_id))
            logger.info("综合节点重试：移除上一版处方消息 id=%s", prev_id)
        messages_out.append(new_msg)

        logger.info("综合节点完成: diagnosis=%s... (retry=%s)", diagnosis[:50], bool(prev_id))
        return {
            "messages": messages_out,
            "diagnosis": diagnosis,
            "treatment_plan": treatment_plan,
            "has_provided_treatment": True,
            "synthesis_message_id": new_msg.id,
        }

    return synthesis_node


# ==================== 安全校验节点 ====================

def _make_safety_check_node(safety_engine: Any):
    """
    创建安全校验节点工厂。

    从 treatment_plan 中提取药材，用 SafetyEngine 校验配伍禁忌。
    不通过则设置 safety_errors + 递增 safety_retry_count。
    通过则清除 safety_errors。

    Phase 3（对抗审查者）将插入在此节点之前：synthesis -> reviewer -> safety_check。
    """

    async def safety_check_node(state: dict[str, Any]) -> dict[str, Any]:
        treatment_plan = state.get("treatment_plan", "")
        herbs = _extract_herbs(treatment_plan)

        if not herbs:
            logger.info("安全校验：未提取到药材，跳过配伍检查")
            return {"safety_errors": None}

        is_safe, error_msg = safety_engine.check_prescription(herbs)
        if not is_safe:
            retry_count = state.get("safety_retry_count", 0)
            logger.warning("安全校验失败（第 %d 次）: %s", retry_count + 1, error_msg)
            return {
                "safety_errors": error_msg,
                "safety_retry_count": retry_count + 1,
            }

        logger.info("安全校验通过: %d 味药材", len(herbs))
        return {"safety_errors": None}

    return safety_check_node


# ==================== 主工厂函数 ====================

def create_multiagent_agent(
    llm: "BaseLLM",
    rag_client: "BaseRAGClient",
    storage: "BaseProfileStore",
    safety_engine: "SafetyEngine",
    checkpointer: BaseCheckpointSaver,
    tools: list,
    web_search_tool: Any = None,
    settings: "Settings | None" = None,
    file_parser: "FileParser | None" = None,
    specialist_chat_models: dict[str, Any] | None = None,
) -> tuple[Any, Any]:
    """
    创建多智能体会诊 Agent 图。

    复用 workflow 图的前置/后置节点，替换诊断-处方段为并行专家会诊+综合。

    Args:
        llm: BaseLLM 实例（DashScopeLLM），用于 reader/mem_recall/safety_guard/inquiry
        rag_client: BaseRAGClient 实例
        storage: BaseProfileStore 实例
        safety_engine: SafetyEngine 实例
        checkpointer: LangGraph 检查点
        tools: 完整工具列表（create_tools 返回值），按名称筛选给各专家
        web_search_tool: 可选的 web_search BaseTool（已包含在 tools 中时传 None）
        settings: Settings 实例
        file_parser: FileParser 实例（可选）
        specialist_chat_models: 可选的专家 chat_model 字典（测试注入桩），
            key: "bianzheng" / "fangji" / "bencao" / "synthesis" / "reviewer"，
            value: ChatOpenAI 或 BaseChatModel 实例。为 None 时从 settings 创建。

    Returns:
        (编译后的 StateGraph, ProfileWriterSkill) - writer 供 lifespan 关闭时 flush
    """
    # 复用 workflow 图的技能实例
    from lingyi.agent.memory.profile_writer import ProfileWriterSkill
    from lingyi.agent.memory.recall import MemRecallSkill
    from lingyi.agent.skills.inquiry import InquirySkill
    from lingyi.agent.skills.reader import ReaderSkill
    from lingyi.agent.skills.safety_guard import SafetyGuardSkill
    # 复用 workflow 图的路由/节点函数
    from lingyi.agent.graph import (
        _safety_guard_router,
        _summarize_and_write_node,
        _summarize_condition_node,
        _summarize_decision,
    )
    from lingyi.agent.skills.treatment import safety_check_logic
    from lingyi.agent.specialists import (
        SpecialistBencao,
        SpecialistBianzheng,
        SpecialistFangji,
    )
    from lingyi.models.factory import create_chat_model

    # 读取配置
    max_retries = settings.safety_max_retries if settings else 3
    reviewer_max_retries = settings.reviewer_max_retries if settings else 2
    safety_fail_mode = settings.safety_fail_mode if settings else "closed"

    # ---- 前置技能实例（与 graph.py 一致） ----
    reader = ReaderSkill(file_parser=file_parser)
    mem_recall = MemRecallSkill(storage=storage)
    safety_guard = SafetyGuardSkill(llm=llm, fail_mode=safety_fail_mode)
    inquiry = InquirySkill(
        llm=llm,
        max_history=settings.max_history_messages_inquiry if settings else 5,
        max_followups=settings.max_followups if settings else 1,
    )
    writer = ProfileWriterSkill(llm=llm, storage=storage)

    # ---- 专家 chat_model ----
    if specialist_chat_models is None:
        specialist_chat_models = {}
    chat_models = {}
    for role in ("bianzheng", "fangji", "bencao", "synthesis", "reviewer"):
        chat_models[role] = specialist_chat_models.get(role) or create_chat_model(settings, role)

    # ---- 工具筛选 ----
    bianzheng_tool_names = {"search_tcm_classics", "get_patient_profile"}
    fangji_tool_names = {"search_formulas", "lookup_herb", "search_tcm_classics"}
    bencao_tool_names = {"lookup_herb", "check_herb_safety", "web_search"}
    reviewer_tool_names = {"check_herb_safety", "lookup_herb"}

    bianzheng_tools = _filter_tools(tools, bianzheng_tool_names)
    fangji_tools = _filter_tools(tools, fangji_tool_names)
    bencao_tools = _filter_tools(tools, bencao_tool_names)
    reviewer_tools = _filter_tools(tools, reviewer_tool_names)

    logger.info(
        "专家工具筛选: 辨证=%d, 方剂=%d, 本草=%d, 审查者=%d",
        len(bianzheng_tools), len(fangji_tools), len(bencao_tools), len(reviewer_tools),
    )

    # ---- 专家实例 ----
    specialist_bianzheng = SpecialistBianzheng(
        chat_model=chat_models["bianzheng"],
        tools=bianzheng_tools,
    )
    specialist_fangji = SpecialistFangji(
        chat_model=chat_models["fangji"],
        tools=fangji_tools,
    )
    specialist_bencao = SpecialistBencao(
        chat_model=chat_models["bencao"],
        tools=bencao_tools,
    )

    # ---- 综合节点 + 安全校验节点 + 对抗审查者 ----
    synthesis_node = _make_synthesis_node(
        chat_model=chat_models["synthesis"],
        safety_engine=safety_engine,
    )
    safety_check_node = _make_safety_check_node(safety_engine)

    from lingyi.agent.safety_reviewer import SafetyReviewerAgent, reviewer_router

    reviewer_agent = SafetyReviewerAgent(
        chat_model=chat_models["reviewer"],
        tools=reviewer_tools,
    )

    # ==================== 构建图 ====================
    workflow = StateGraph(AgentState)

    # ---- 注册节点 ----
    workflow.add_node("reader", reader.node)
    workflow.add_node("mem_recall", mem_recall.node)
    workflow.add_node("safety_guard", safety_guard.node)
    workflow.add_node("inquiry", _wrap_with_stage("inquiry", "问诊", inquiry.node))
    workflow.add_node("dispatch_specialists", _dispatch_passthrough)
    workflow.add_node(
        "specialist_bianzheng",
        _wrap_with_stage("bianzheng", "辨证", specialist_bianzheng.node),
    )
    workflow.add_node(
        "specialist_fangji", _wrap_with_stage("fangji", "方剂", specialist_fangji.node)
    )
    workflow.add_node(
        "specialist_bencao", _wrap_with_stage("bencao", "本草", specialist_bencao.node)
    )
    workflow.add_node("synthesis", _wrap_with_stage("synthesis", "综合", synthesis_node))
    workflow.add_node("reviewer", _wrap_with_stage("reviewer", "安全审查", reviewer_agent.node))
    workflow.add_node(
        "safety_check", _wrap_with_stage("safety_check", "安全校验", safety_check_node)
    )
    workflow.add_node("summarize_condition", _summarize_condition_node)
    workflow.add_node("writer", writer.node)

    # ---- 边连接 ----

    # 主流程: START -> reader -> mem_recall -> safety_guard
    workflow.add_edge(START, "reader")
    workflow.add_edge("reader", "mem_recall")
    workflow.add_edge("mem_recall", "safety_guard")

    # 安全审查后路由（复用 workflow 图的路由）
    workflow.add_conditional_edges(
        "safety_guard",
        _safety_guard_router,
        {"safety_rejected": "summarize_condition", "pass": "inquiry"},
    )

    # 问诊后路由（多智能体版：diagnose -> dispatch, consult -> END, chat -> summarize）
    workflow.add_conditional_edges(
        "inquiry",
        _master_router_multiagent,
        {"dispatch": "dispatch_specialists", "summarize": "summarize_condition", "end": END},
    )

    # dispatch_specialists -> Send 并行扇出到三个专家
    # 验证 API: add_conditional_edges 接受返回 list[Send] 的函数（dive-into-langgraph ch9）
    workflow.add_conditional_edges(
        "dispatch_specialists",
        _fan_out_specialists,
        ["specialist_bianzheng", "specialist_fangji", "specialist_bencao"],
    )

    # 各专家 -> synthesis（LangGraph 屏障：等待所有专家完成后才执行 synthesis）
    workflow.add_edge("specialist_bianzheng", "synthesis")
    workflow.add_edge("specialist_fangji", "synthesis")
    workflow.add_edge("specialist_bencao", "synthesis")

    # synthesis -> reviewer -> safety_check（Phase 3: 双重防御 - 智能审查者 + 确定性硬校验）
    workflow.add_edge("synthesis", "reviewer")

    # 对抗审查者路由（审查通过 -> safety_check；不通过且未耗尽 -> synthesis 重生成）
    workflow.add_conditional_edges(
        "reviewer",
        lambda state: reviewer_router(state, reviewer_max_retries),
        {"safety_check": "safety_check", "synthesis": "synthesis"},
    )

    # 安全校验路由（复用 safety_check_logic）
    workflow.add_conditional_edges(
        "safety_check",
        lambda state: safety_check_logic(state, max_retries),
        {"re_treatment": "synthesis", "safe_to_end": "summarize_condition"},
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
    compiled = workflow.compile(checkpointer=checkpointer)
    logger.info("多智能体会诊图编译完成")
    return compiled, writer
