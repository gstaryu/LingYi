"""
画像写入技能测试 - 验证 fire-and-forget 非阻塞 与 flush 持久化。

关键: execute 应立即返回（不等 LLM），flush 后画像才落库。
"""

import asyncio
import time

import pytest
from langchain_core.messages import HumanMessage

from lingyi.agent.memory.profile_writer import ProfileWriterSkill


class _SlowLLM:
    """模拟延迟 LLM，用于验证 execute 不阻塞响应。"""

    def __init__(self, delay: float, response: str):
        self._delay = delay
        self._response = response

    async def ainvoke(self, messages, temperature=0.7, max_tokens=2048):
        await asyncio.sleep(self._delay)
        return self._response


class TestProfileWriterSkill:
    """ProfileWriterSkill 测试套件。"""

    async def test_execute_does_not_block(self, tmp_storage):
        """execute 应立即返回，不等待 LLM 完成（fire-and-forget）。"""
        await tmp_storage.init_db()
        llm = _SlowLLM(0.3, '{"constitution":"阳虚","allergies":"无","new_record":"风寒"}')
        writer = ProfileWriterSkill(llm=llm, storage=tmp_storage)
        state = {"messages": [HumanMessage(content="我怕冷", id="1")], "thread_id": "p1"}

        t0 = time.monotonic()
        result = await writer.execute(state)
        elapsed = time.monotonic() - t0

        assert result["profile_updated"] is True
        # 0.3s 的 LLM 调用不应阻塞 execute（远小于 0.3s 即返回）
        assert elapsed < 0.1, f"execute 阻塞了 {elapsed:.2f}s，预期立即返回"

    async def test_flush_persists_profile(self, tmp_storage):
        """flush 后画像应已写入数据库。"""
        await tmp_storage.init_db()
        llm = _SlowLLM(0.1, '{"constitution":"阳虚","allergies":"花粉","new_record":"测试"}')
        writer = ProfileWriterSkill(llm=llm, storage=tmp_storage)
        state = {"messages": [HumanMessage(content="我怕冷", id="1")], "thread_id": "p2"}

        await writer.execute(state)
        await writer.flush()  # 等待后台写入完成

        profile = await tmp_storage.get_profile("p2")
        assert profile.constitution == "阳虚"
        assert profile.allergies == "花粉"

    async def test_no_llm_returns_empty(self, tmp_storage):
        """未注入 LLM 时安全返回空，不调度后台任务。"""
        await tmp_storage.init_db()
        writer = ProfileWriterSkill(llm=None, storage=tmp_storage)
        result = await writer.execute({"messages": [HumanMessage(content="x", id="1")]})
        assert result == {}

    async def test_flush_empty_when_no_pending(self, tmp_storage):
        """无待完成任务时 flush 应安全无操作。"""
        await tmp_storage.init_db()
        writer = ProfileWriterSkill(llm=None, storage=tmp_storage)
        await writer.flush()  # 不应抛异常
