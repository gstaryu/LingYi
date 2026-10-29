"""
OpenAI 兼容模型实现。

面向任何提供 OpenAI 兼容接口的服务（OpenAI、DashScope、DeepSeek、Moonshot、
本地 vLLM / Ollama 等），通过 langchain-openai 的 ChatOpenAI / OpenAIEmbeddings
完成异步调用。厂商差异只体现在 base_url / model / 附加请求头上。
"""

import logging

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from lingyi.models.base import BaseEmbedding, BaseLLM

logger = logging.getLogger(__name__)


class OpenAICompatLLM(BaseLLM):
    """
    基于 OpenAI 兼容协议的 LLM 实现。

    使用 langchain-openai 的 ChatOpenAI 封装；换厂商只需改配置，不改代码。
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.7,
        timeout: int = 30,
        max_retries: int = 3,
        max_tokens: int = 8192,
        extra_headers: dict[str, str] | None = None,
        structured_output_method: str = "function_calling",
    ):
        """
        初始化 LLM。

        Args:
            api_key: API Key（无鉴权的本地服务可填任意占位值）
            base_url: OpenAI 兼容 API 的 Base URL
            model_name: 模型名称
            temperature: 默认温度参数
            timeout: API 超时时间（秒）
            max_retries: 最大重试次数
            max_tokens: 单次生成的最大 token 数（各厂商上限不同，由配置传入）
            extra_headers: 附加 HTTP 头（部分网关需专用头才能路由）
            structured_output_method: 结构化输出方式（function_calling / json_schema
                / json_mode），需与服务端能力匹配
        """
        self._model_name = model_name
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._structured_output_method = structured_output_method
        # Token 用量累计器（供评测/监控读取；reset_usage() 清零）
        self.total_usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0, "calls": 0}
        self._client = ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            max_retries=max_retries,
            default_headers=extra_headers or None,
        )
        logger.info(
            "OpenAICompatLLM 初始化完成: model=%s, base_url=%s, timeout=%ds, max_tokens=%d",
            model_name,
            base_url,
            timeout,
            max_tokens,
        )

    async def ainvoke(
        self,
        messages: list,
        temperature: float = 0.7,
        max_tokens: int = 8192,
    ) -> str:
        """
        异步调用 LLM。

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
                role = (
                    msg.get("role", "user")
                    if isinstance(msg, dict)
                    else getattr(msg, "type", "user")
                )
                content = (
                    msg.get("content", "")
                    if isinstance(msg, dict)
                    else getattr(msg, "content", "")
                )
                if role == "system":
                    lc_messages.append(SystemMessage(content=content))
                elif role in ("assistant", "ai"):
                    lc_messages.append(AIMessage(content=content))
                else:
                    lc_messages.append(HumanMessage(content=content))

        # 仅当请求参数与默认配置不同时绑定临时参数（LangChain 惯用 bind()）
        if temperature != self._temperature or max_tokens != self._max_tokens:
            client = self._client.bind(temperature=temperature, max_tokens=max_tokens)
        else:
            client = self._client

        response = await client.ainvoke(lc_messages)
        # 透出 Token 用量：累加到实例属性，供评测/监控读取（reset_usage 清零）
        usage = getattr(response, "usage_metadata", None)
        if usage:
            self.total_usage["input_tokens"] += usage.get("input_tokens", 0)
            self.total_usage["output_tokens"] += usage.get("output_tokens", 0)
            self.total_usage["calls"] += 1
        return response.content

    def reset_usage(self) -> None:
        """清零 Token 用量累计器（评测 harness 每次请求前调用）。"""
        self.total_usage = {"input_tokens": 0, "output_tokens": 0, "calls": 0}

    def with_structured_output(self, schema):
        """
        返回结构化输出 Runnable（ainvoke 返回 Pydantic 实例）。

        具体方式由 structured_output_method 决定：
        - function_calling（默认，兼容性最好）
        - json_schema（OpenAI 等支持严格 schema 的服务）
        - json_mode（仅支持 JSON 模式的服务）
        """
        return self._client.with_structured_output(
            schema, method=self._structured_output_method
        )


class OpenAICompatEmbedding(BaseEmbedding):
    """
    基于 OpenAI 兼容协议的 Embedding 实现。

    用于 RAG 检索时的文档和查询向量化。
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model_name: str = "text-embedding-3-small",
        extra_headers: dict[str, str] | None = None,
    ):
        """
        初始化 Embedding。

        Args:
            api_key: API Key（无鉴权的本地服务可填任意占位值）
            base_url: OpenAI 兼容 API 的 Base URL
            model_name: Embedding 模型名称
            extra_headers: 附加 HTTP 头（部分网关需专用头才能路由）

        check_embedding_ctx_length=False: 直接发送原始文本，避免 langchain-openai
        默认的 tiktoken 分词 + base64 编码流程——多数第三方兼容网关不支持该格式。
        """
        self._client = OpenAIEmbeddings(
            api_key=api_key,
            base_url=base_url,
            model=model_name,
            check_embedding_ctx_length=False,
            default_headers=extra_headers or None,
        )
        logger.info("OpenAICompatEmbedding 初始化完成: model=%s, base_url=%s", model_name, base_url)

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        """异步批量嵌入文档。"""
        return await self._client.aembed_documents(texts)

    async def aembed_query(self, text: str) -> list[float]:
        """异步嵌入查询文本。"""
        return await self._client.aembed_query(text)
