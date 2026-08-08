"""
工具工厂 - 通过依赖注入构造领域工具集。

设计要点（镜像 graph.py 的 DI 风格）:
- 工具以闭包形式捕获注入的 rag_client / storage / safety_engine，不持有模块级全局单例。
- 使用 StructuredTool.from_function(coroutine=fn, name=, description=, args_schema=...) 注册：
  闭包无法干净地配合 @tool 装饰器（装饰器在定义时绑定，拿不到运行时注入的依赖）。
- 所有工具返回 JSON 可序列化的 dict/list（给 LLM 消费），不返回 dataclass；
  Herb/Formula/UserProfile 等结构在边界处显式转 dict。
- web_search 工具有状态（MCP 子进程），不在此处构造；由 build_web_search_tool 异步构建后
  作为 web_search_client 传入，非 None 时附加到工具列表末尾。
"""

import logging
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool

from lingyi.tools.schemas import (
    CheckHerbSafetyInput,
    GetPatientProfileInput,
    LookupHerbInput,
    SavePatientProfileInput,
    SearchHerbsInput,
    SearchFormulasInput,
    SearchTcmClassicsInput,
)

logger = logging.getLogger(__name__)


def _herb_to_dict(herb: Any) -> dict:
    """Herb dataclass -> dict（LLM 友好）。"""
    return {
        "name": herb.name,
        "aliases": list(herb.aliases),
        "nature_flavor": herb.nature_flavor,
        "meridians": list(herb.meridians),
        "efficacy": herb.efficacy,
        "indications": list(herb.indications),
        "dosage": herb.dosage,
        "processing": herb.processing,
        "contraindications": herb.contraindications,
    }


def _formula_to_dict(formula: Any) -> dict:
    """Formula dataclass -> dict（仅暴露 name/source/composition/indication，按交付规范）。"""
    return {
        "name": formula.name,
        "source": formula.source,
        "composition": [
            {"herb": c.herb, "dosage": c.dosage} for c in formula.composition
        ],
        "indication": formula.indication,
    }


def _profile_to_dict(profile: Any) -> dict:
    """UserProfile dataclass -> dict（体质/过敏/既往史）。"""
    return {
        "patient_id": profile.patient_id,
        "constitution": profile.constitution,
        "allergies": profile.allergies,
        "past_history": list(profile.past_history),
    }


def create_tools(
    rag_client: Any,
    storage: Any,
    safety_engine: Any,
    web_search_client: BaseTool | None = None,
) -> list[BaseTool]:
    """
    构建领域工具集。工具闭包捕获注入的依赖（镜像 graph.py DI）。

    Args:
        rag_client: BaseRAGClient，提供 hybrid_search(query, n_results)。
        storage: SQLiteStorage（或桩），提供 get_herb/search_formulas/get_profile/
            update_profile 等。
        safety_engine: SafetyEngine，提供 check_prescription(herb_list)。
        web_search_client: 可选的预构建 web_search BaseTool（来自 build_web_search_tool）。
            为 None 时省略 web_search 工具，Agent 仍可运行。

    Returns:
        BaseTool 列表（6 个闭包工具 + 可选的 web_search）。
    """

    # ---------- 1. search_tcm_classics ----------
    async def _search_tcm_classics(query: str) -> list[str]:
        results = await rag_client.hybrid_search(query, n_results=8)
        return [r.content for r in results]

    search_tcm_classics = StructuredTool.from_function(
        coroutine=_search_tcm_classics,
        name="search_tcm_classics",
        description="检索中医经典古籍（伤寒论/金匮要略等）中与查询相关的条文。",
        args_schema=SearchTcmClassicsInput,
    )

    # ---------- 2. lookup_herb ----------
    async def _lookup_herb(name: str) -> dict:
        herb = await storage.get_herb(name)
        if herb is None:
            return {"error": "未找到"}
        return _herb_to_dict(herb)

    lookup_herb = StructuredTool.from_function(
        coroutine=_lookup_herb,
        name="lookup_herb",
        description="按药材正名精确查询本草信息（性味、归经、功效、主治、用量、禁忌）。",
        args_schema=LookupHerbInput,
    )

    # ---------- 3. search_formulas ----------
    async def _search_formulas(query: str) -> list[dict]:
        formulas = await storage.search_formulas(query)
        return [_formula_to_dict(f) for f in formulas]

    search_formulas = StructuredTool.from_function(
        coroutine=_search_formulas,
        name="search_formulas",
        description="按证候或关键词搜索方剂，返回方剂列表（名称、出处、组成、主治）。",
        args_schema=SearchFormulasInput,
    )

    # ---------- 3.5 search_herbs ----------
    async def _search_herbs(query: str) -> list[dict]:
        herbs = await storage.search_herbs(query)
        return [_herb_to_dict(h) for h in herbs]

    search_herbs = StructuredTool.from_function(
        coroutine=_search_herbs,
        name="search_herbs",
        description="按关键词（症状/功效/药名）模糊搜索本草，返回药材列表（性味、归经、功效、用量、禁忌）。",
        args_schema=SearchHerbsInput,
    )

    # ---------- 4. check_herb_safety ----------
    async def _check_herb_safety(herbs: list[str]) -> dict:
        # 十八反/十九畏 配伍禁忌（SafetyEngine 物理规则引擎）
        is_safe, error_msg = safety_engine.check_prescription(herbs)
        if is_safe:
            violations: list[str] = []
        else:
            # SafetyEngine 用 '；' 连接多条冲突，拆分还原为列表
            violations = [v for v in (error_msg or "").split("；") if v]

        return {"safe": is_safe, "violations": violations, "warnings": []}

    check_herb_safety = StructuredTool.from_function(
        coroutine=_check_herb_safety,
        name="check_herb_safety",
        description=(
            "校验药方配伍安全：检查十八反/十九畏配伍禁忌。"
            "返回 {safe, violations, warnings}。"
        ),
        args_schema=CheckHerbSafetyInput,
    )

    # ---------- 5. get_patient_profile ----------
    async def _get_patient_profile(patient_id: str) -> dict:
        profile = await storage.get_profile(patient_id)
        return _profile_to_dict(profile)

    get_patient_profile = StructuredTool.from_function(
        coroutine=_get_patient_profile,
        name="get_patient_profile",
        description="获取患者画像（体质类型、过敏史、既往诊疗记录）。",
        args_schema=GetPatientProfileInput,
    )

    # ---------- 6. save_patient_profile ----------
    async def _save_patient_profile(
        patient_id: str, constitution: str = "", allergies: str = ""
    ) -> dict:
        # 仅传入非空字段才更新（update_profile 接受 dict，upsert 语义）
        data: dict[str, Any] = {}
        if constitution.strip():
            data["constitution"] = constitution.strip()
        if allergies.strip():
            data["allergies"] = allergies.strip()
        if data:
            await storage.update_profile(patient_id, data)
        return {"saved": True}

    save_patient_profile = StructuredTool.from_function(
        coroutine=_save_patient_profile,
        name="save_patient_profile",
        description="保存/更新患者画像（体质、过敏史）；仅传入非空字段才更新。",
        args_schema=SavePatientProfileInput,
    )

    tools: list[BaseTool] = [
        search_tcm_classics,
        lookup_herb,
        search_formulas,
        search_herbs,
        check_herb_safety,
        get_patient_profile,
        save_patient_profile,
    ]

    # ---------- 7. web_search（可选，由 build_web_search_tool 预构建后注入） ----------
    if web_search_client is not None:
        tools.append(web_search_client)
        logger.info("工具集已附加 web_search 工具（共 %d 个）", len(tools))
    else:
        logger.info("web_search 工具未注入，工具集共 %d 个", len(tools))

    return tools
