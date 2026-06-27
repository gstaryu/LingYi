"""
DashScope / OpenAI 兼容模型实现。

支持阿里云 DashScope API 和任何 OpenAI 兼容接口。
通过 langchain-openai 的 ChatOpenAI 实现异步调用。
"""

import logging
from typing import Any

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from lingyi.models.base import BaseEmbedding, BaseLLM

logger = logging.getLogger(__name__)


class DashScopeLLM(BaseLLM):
    """
    DashScope / OpenAI 兼容 LLM。

    使用 langchain-openai 的 ChatOpenAI 封装，支持 DashScope 的 OpenAI 兼容模式。
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model_name: str = "qwen-max",
        temperature: float = 0.7,
        timeout: int = 30,
        max_retries: int = 3,
    ):
        """
        初始化 DashScope LLM。

        Args:
            api_key: API Key
            base_url: API Base URL
            model_name: 模型名称
            temperature: 默认温度参数
            timeout: API 超时时间（秒）
            max_retries: 最大重试次数
        """
        self._model_name = model_name
        self._temperature = temperature
        self._client = ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model_name,
            temperature=temperature,
            max_tokens=2048,
            timeout=timeout,
            max_retries=max_retries,
        )
        logger.info("DashScopeLLM 初始化完成: model=%s, base_url=%s, timeout=%ds", model_name, base_url, timeout)

    async def ainvoke(
        self,
        messages: list,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """
        异步调用 DashScope LLM。

        支持两种消息格式:
        - LangChain BaseMessage 对象列表（直接传递，无转换开销）
        - dict 格式 [{"role": "...", "content": "..."}]（自动转换）
        """
        from langchain_core.messages import BaseMessage

        # 如果已经是 BaseMessage 对象，直接使用；否则从 dict 转换
        if messages and isinstance(messages[0], BaseMessage):
            lc_messages = messages
        else:
            from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

            lc_messages = []
            for msg in messages:
                role = msg.get("role", "user") if isinstance(msg, dict) else getattr(msg, "type", "user")
                content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
                if role == "system":
                    lc_messages.append(SystemMessage(content=content))
                elif role in ("assistant", "ai"):
                    lc_messages.append(AIMessage(content=content))
                else:
                    lc_messages.append(HumanMessage(content=content))

        # 动态调整参数
        client = self._client
        if temperature != self._temperature or max_tokens != 2048:
            client = self._client.model_copy(
                update={"temperature": temperature, "max_tokens": max_tokens}
            )

        response = await client.ainvoke(lc_messages)
        return response.content


class DashScopeEmbedding(BaseEmbedding):
    """
    DashScope / OpenAI 兼容 Embedding 模型。

    用于 RAG 检索时的文档和查询向量化。
    """

    def __init__(self, api_key: str, base_url: str, model_name: str = "text-embedding-v3"):
        """
        初始化 DashScope Embedding。

        Args:
            api_key: API Key
            base_url: API Base URL
            model_name: Embedding 模型名称
        """
        self._client = OpenAIEmbeddings(
            api_key=api_key,
            base_url=base_url,
            model=model_name,
        )
        logger.info("DashScopeEmbedding 初始化完成: model=%s", model_name)

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        """异步批量嵌入文档。"""
        return await self._client.aembed_documents(texts)

    async def aembed_query(self, text: str) -> list[float]:
        """异步嵌入查询文本。"""
        return await self._client.aembed_query(text)
