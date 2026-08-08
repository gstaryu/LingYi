"""
画像写入节点 - 会话结束时将诊疗信息持久化到患者画像。

属于"记忆"领域。原 WriterSkill 改名为 ProfileWriterSkill 以反映真实职责
（持久化画像，而非生成回复），并与 MemRecallSkill 配对（recall 加载、writer 写入）。

设计: 画像提取是一次 LLM 调用，属诊疗结束后的副作用持久化，不应阻塞响应。
      execute 用 asyncio.create_task 在后台调度（fire-and-forget），立即返回；
      任务存入 _pending 集合防 GC，应用关闭时由 flush() 统一等待避免丢写。
      MemRecallSkill 改为每轮重载（DB 单行 PK 查询廉价），保证后台写入的最终可见性。
"""

import asyncio
import json
import logging
import re
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from lingyi.agent.skills.base import BaseSkill

logger = logging.getLogger(__name__)

# 画像提取超时（秒）- 超时则跳过本次写入，不阻塞响应过久
# fire-and-forget 后台任务，适当放宽以减少跳过（不影响用户响应）
DEFAULT_EXTRACT_TIMEOUT = 25


class ProfileWriterSkill(BaseSkill):
    """
    画像写入技能节点。

    使用 LLM 从对话历史中提取体质和过敏史信息，
    然后通过 Storage 接口持久化到数据库。
    """

    def __init__(self, llm: Any = None, storage: Any = None, timeout: int = DEFAULT_EXTRACT_TIMEOUT):
        """
        初始化画像写入技能。

        Args:
            llm: LLM 实例，用于提取画像信息
            storage: BaseProfileStore 实例，用于持久化
            timeout: 单次画像提取超时（秒），超时则该任务取消
        """
        super().__init__(llm=llm)
        self.storage = storage
        self.timeout = timeout
        # 待完成的后台写入任务集合：防止任务被 GC，并在应用关闭时 flush
        self._pending: set[asyncio.Task] = set()

    async def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        调度后台画像提取与持久化（fire-and-forget，不阻塞响应）。

        画像提取是一次 LLM 调用，属于诊疗结束后的副作用持久化，不应让用户等待。
        因此用 create_task 在后台执行，execute 立即返回；任务存入 _pending 防 GC，
        并在应用关闭时由 flush() 统一等待，避免事件循环关闭导致丢写。

        Returns:
            {"profile_updated": True} 标记（MemRecallSkill 已改为每轮重载，此标记保留兼容）
        """
        if not self.llm or not self.storage:
            return {}

        messages = state.get("messages", [])
        if not messages:
            return {}

        # 复制消息列表，防止后台任务执行期间原引用被修改
        messages_snapshot = list(messages)
        patient_id = state.get("username") or state.get("thread_id", "default_user")

        # 后台执行提取+写库；用 timeout 包裹防止单任务无限挂起
        task = asyncio.create_task(
            self._run_with_timeout(patient_id, messages_snapshot)
        )
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

        return {"profile_updated": True}

    async def _run_with_timeout(self, patient_id: str, messages: list) -> None:
        """带超时的画像提取+持久化（后台任务体）。"""
        try:
            await asyncio.wait_for(
                self._extract_and_save(patient_id, messages),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("画像提取超时（%ds），跳过本次写入: %s", self.timeout, patient_id)
        except Exception as e:
            logger.warning("画像提取/写入失败: %s", e)

    async def flush(self) -> None:
        """
        等待所有待完成的画像写入完成（应用关闭时调用，防止丢写）。

        快照待处理任务后统一 gather；新加入的任务不会被误清。
        """
        if not self._pending:
            return
        tasks = list(self._pending)
        logger.info("等待 %d 个画像写入任务完成...", len(tasks))
        await asyncio.gather(*tasks, return_exceptions=True)
        self._pending.difference_update(tasks)
        logger.info("画像写入 flush 完成")

    def _build_extract_prompt(self, messages: list, current_allergies: str = "无") -> list[BaseMessage]:
        """构建画像提取 prompt（取最近 6 条消息）。

        Args:
            messages: 对话历史
            current_allergies: 当前患者的过敏史（用于判断移除）
        """
        recent_msgs = messages[-6:]
        conversation = "\n".join(
            f"{getattr(m, 'type', 'user')}: {getattr(m, 'content', '')}"
            for m in recent_msgs
        )

        return [
            SystemMessage(
                content=(
                    "你是一个医疗信息提取助手。从以下对话中提取患者的关键信息。\n"
                    "请以 JSON 格式输出：\n"
                    '{"constitution": "体质类型", "allergies": "新增过敏原", "allergies_remove": "要移除的过敏原", "new_record": "本次诊疗摘要"}\n'
                    "重要规则：\n"
                    "1. 如果某项信息未提及，对应字段留空字符串（体质和过敏原**不要**写'未知'或'无'）。\n"
                    "2. 过敏原只填物质名本身（如'青霉素'、'白芷'、'党参'），**不要**写成'白芷过敏'、'党参及相关制品'这类描述；体质用具体证型（如'阳虚体质'、'阴虚体质'）。\n"
                    f"3. 当前患者过敏史: {current_allergies}\n"
                    "4. 当患者表示不再对某物过敏时（如'我对党参不过敏了'、'我不再对白芷过敏'、'之前对X过敏现在好了'），"
                    "将需要移除的过敏原填入 allergies_remove 字段（只写物质名，如'党参'、'白芷'），**不要**填入 allergies。\n"
                    "5. allergies 字段只填**新增**的过敏原（患者新报告的过敏物）。\n"
                    "6. allergies_remove 和 allergies 可以同时有值（既有新增又有移除）。\n"
                    "7. 存储层会自动合并新增过敏原（只增不减）；allergies_remove 会从列表中移除对应项。"
                )
            ),
            HumanMessage(content=f"对话内容：\n{conversation}"),
        ]

    def _parse_profile(self, response: Any) -> dict[str, str]:
        """解析 LLM 返回的画像 JSON。

        兼容 ChatOpenAI（返回 AIMessage，需取 .content）与直接返回 str 的 LLM 包装。
        """
        text = response.content if hasattr(response, "content") else str(response)
        try:
            json_match = re.search(r"\{[^}]+\}", text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return {
                    k: v
                    for k, v in data.items()
                    if k in ("constitution", "allergies", "allergies_remove", "new_record") and v
                }
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass
        return {}

    @staticmethod
    def _normalize_allergy_item(item: str) -> str:
        """规范化过敏原名称：去除 LLM 常附加的冗余后缀，便于匹配/去重/移除。

        例: "白芷过敏" -> "白芷", "党参及相关制品" -> "党参", "茯苓类药物" -> "茯苓"。
        反复剥离尾部后缀以处理 "白芷及相关制品过敏" 这类多层堆叠。
        """
        s = (item or "").strip()
        prev = None
        while prev != s:
            prev = s
            s = re.sub(r"(及相关制品|及制品|相关制品|类药物|过敏)+$", "", s).strip()
        return s or (item or "").strip()

    @staticmethod
    def _parse_allergy_list(s: str) -> list[str]:
        """将过敏原字符串解析为列表（支持各种分隔符），并规范化每项名称。"""
        if not s or s.strip() in ("", "无", "未知"):
            return []
        parts = re.split(r"[、，,；;]\s*", s.strip())
        items = [
            ProfileWriterSkill._normalize_allergy_item(p)
            for p in parts
            if p.strip() and p.strip() not in ("无", "未知")
        ]
        return [i for i in items if i]

    @staticmethod
    def _detect_allergy_removal(messages: list[BaseMessage]) -> list[str]:
        """确定性检测：用户明确表示不再对某物过敏时，直接提取该过敏原。

        作为 LLM 提取的规则兜底——即使小模型把"我对白芷不过敏"误读为新增过敏，
        此处仍能可靠识别移除意图，配合 _normalize_allergy_item 完成移除。
        仅匹配明确的"不再过敏"语义，保守触发以避免误删。
        """
        latest_user_text = ""
        for m in reversed(messages[-4:]):
            if getattr(m, "type", "") == "human":
                c = getattr(m, "content", "")
                if isinstance(c, str):
                    latest_user_text = c
                    break
        if not latest_user_text:
            return []
        # 移除意图否定标记（"不过敏"需在子句边界，避免"不过敏药"等误触发）
        negation = r"不过敏了|不过敏(?=[。，,；;！？!?。\s]|$)|不再.{0,4}过敏|现在.{0,4}不过敏|过敏.{0,6}(好了|缓解|消失|没了)"
        if not re.search(negation, latest_user_text):
            return []
        # 物质名限定 2-6 个 CJK/字母/数字字符，避免误捕单字"不"
        token = r"[一-鿿A-Za-z0-9]{2,6}"
        excludes = ("我", "现在", "之前", "的", "不再")
        removes: list[str] = []
        # 1) 直接模式：不再对X过敏 / 对X不过敏（"对"锚定物质名，避免贪婪误捕前文）
        direct = [
            rf"不再对({token})过敏",
            rf"对({token})不过敏",
        ]
        for pat in direct:
            for m in re.finditer(pat, latest_user_text):
                item = ProfileWriterSkill._normalize_allergy_item(m.group(1))
                if item and "不" not in item and item not in excludes:
                    removes.append(item)
        # 2) 零指代回溯：句中有否定但物质名省略时（如"我对白芷过敏，现在不过敏了"），
        #    从"对X过敏"提取物质名（要求"对"锚定，避免贪婪吞掉前文）
        if not removes:
            for m in re.finditer(rf"对({token})过敏", latest_user_text):
                item = ProfileWriterSkill._normalize_allergy_item(m.group(1))
                if item and "不" not in item and item not in excludes:
                    removes.append(item)
        return list(dict.fromkeys(removes))

    async def _extract_and_save(self, patient_id: str, messages: list) -> None:
        """提取画像信息并持久化。"""
        # 加载当前画像，获取现有过敏史（用于判断移除）
        current = await self.storage.get_profile(patient_id)
        current_allergies = current.allergies if current else "无"

        extract_prompt = self._build_extract_prompt(messages, current_allergies)
        response = await self.llm.ainvoke(extract_prompt)
        profile_data = self._parse_profile(response)

        if not profile_data:
            return

        # 处理过敏原移除：LLM 提取 + 确定性规则兜底（规范化后去重）
        detected_removes = self._detect_allergy_removal(messages)
        allergies_remove = profile_data.pop("allergies_remove", "")
        remove_items = list(dict.fromkeys(
            self._parse_allergy_list(allergies_remove) + detected_removes
        ))

        if remove_items:
            # 有移除：重算完整过敏列表（现有 - 移除 + 新增），用 set_allergies 覆盖
            current_items = self._parse_allergy_list(current_allergies)
            add_items = self._parse_allergy_list(profile_data.get("allergies", ""))
            new_items = [i for i in current_items if i not in remove_items]
            for item in add_items:
                if item not in new_items and item not in remove_items:
                    new_items.append(item)

            new_allergies = "、".join(new_items) if new_items else "无"
            await self.storage.set_allergies(patient_id, new_allergies)
            # 已通过 set_allergies 处理过敏原，不再传给 update_profile
            profile_data.pop("allergies", None)
            logger.info(
                "过敏原移除: patient_id=%s, 移除=%s, 结果=%s",
                patient_id, "、".join(remove_items), new_allergies,
            )

        if profile_data:
            await self.storage.update_profile(patient_id, profile_data)
        logger.info("画像已更新: patient_id=%s", patient_id)
