"""会话命名 - 首次对话后异步生成简短中文标题。

设计要点:
- 会话首次对话后，若标题仍为默认（"新对话"/空），fire-and-forget 调用 LLM 生成 ≤10 字标题
- 复用 ProfileWriter 的 create_task 模式：不阻塞响应，任务存入 _pending 防 GC
- 标题由首条用户消息 + 诊断结论归纳，避免泄漏完整病历
- 失败静默（命名是体验优化，非关键路径）
"""

import asyncio
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

# 命名 LLM 超时（秒）- fire-and-forget，超时则保留默认标题
DEFAULT_NAMING_TIMEOUT = 15
DEFAULT_THREAD_TITLE = "新对话"


def _build_naming_prompt(first_message: str, diagnosis: str) -> list:
    """构建会话命名 prompt（取首条消息 + 诊断结论摘要）。"""
    diagnosis_brief = (diagnosis or "")[:200]
    return [
        SystemMessage(
            content=(
                "你是一个会话命名助手。根据患者的首条消息和诊断结论，"
                "生成一个简短的中文会话标题。\n\n"
                "要求：\n"
                "1. 不超过 10 个汉字\n"
                "2. 概括核心症状或证候（如'胃脘冷痛问诊'、'脾胃虚寒调理'）\n"
                "3. 不要包含标点符号、引号或解释\n"
                "4. 不要以'对话'、'会话'结尾\n"
                "只输出标题文本，不要输出任何其他内容。"
            )
        ),
        HumanMessage(
            content=f"患者首条消息：{first_message[:300]}\n诊断结论：{diagnosis_brief}"
        ),
    ]


def _clean_title(raw: str) -> str:
    """清理 LLM 返回的标题：去引号/换行/标点，截断到 10 字。"""
    if not raw:
        return ""
    title = raw.strip().strip("\"'""''「」【】").strip()
    # 去除换行与多余空白
    title = re.sub(r"\s+", "", title)
    # 截断到 10 个字符（按字符计数，兼容中文）
    if len(title) > 10:
        title = title[:10]
    return title


async def generate_session_title(
    llm: Any, first_message: str, diagnosis: str = ""
) -> str | None:
    """调用 LLM 生成会话标题（≤10 字中文）。

    Args:
        llm: 支持 ainvoke 的 LLM 实例（DashScopeLLM / ChatOpenAI）
        first_message: 本会话首条用户消息
        diagnosis: 诊断结论（可选，提升标题质量）

    Returns:
        清理后的标题字符串；失败时返回 None
    """
    if not first_message:
        return None
    try:
        messages = _build_naming_prompt(first_message, diagnosis)
        response = await asyncio.wait_for(llm.ainvoke(messages), timeout=DEFAULT_NAMING_TIMEOUT)
        content = response.content if hasattr(response, "content") else str(response)
        title = _clean_title(content)
        logger.info("会话命名完成: '%s'", title)
        return title or None
    except asyncio.TimeoutError:
        logger.warning("会话命名超时（%ds）", DEFAULT_NAMING_TIMEOUT)
        return None
    except Exception as e:  # noqa: BLE001 - 命名失败不应影响主流程
        logger.warning("会话命名失败: %s", e)
        return None


def schedule_session_rename(
    llm: Any,
    storage: Any,
    thread_id: str,
    username: str,
    first_message: str,
    diagnosis: str = "",
    pending: set[asyncio.Task] | None = None,
) -> asyncio.Task | None:
    """fire-and-forget 调度会话重命名（不阻塞响应）。

    生成标题后调用 storage.rename_thread(thread_id, title, username)。
    任务存入 pending 集合防 GC（与 ProfileWriter 模式一致）。

    Args:
        llm: LLM 实例
        storage: BaseProfileStore 实例（含 rename_thread）
        thread_id: 会话 ID
        username: 归属用户（rename_thread 需校验归属）
        first_message: 首条用户消息
        diagnosis: 诊断结论
        pending: 任务集合（防 GC），通常复用 ProfileWriter._pending

    Returns:
        创建的 asyncio.Task；llm/storage 缺失时返回 None
    """
    if not llm or not storage or not first_message:
        return None

    async def _rename():
        title = await generate_session_title(llm, first_message, diagnosis)
        if title:
            try:
                await storage.rename_thread(thread_id, title, username)
                logger.info("会话已重命名: thread=%s title='%s'", thread_id, title)
            except Exception as e:  # noqa: BLE001
                logger.warning("会话重命名写入失败: %s", e)

    task = asyncio.create_task(_rename())
    if pending is not None:
        pending.add(task)
        task.add_done_callback(pending.discard)
    return task
