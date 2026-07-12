"""
模型抽象层 - LLM / Embedding 的抽象基类。

设计原则:
- 所有模型操作均为异步（async/await）
- 通过构造函数注入配置，不依赖全局单例
- 子类只需实现对应的抽象方法

注: RAG 重排器抽象 BaseReranker 已归属 RAG 领域，定义在 lingyi/rag/base.py。
"""

from abc import ABC, abstractmethod


class BaseLLM(ABC):
    """
    大语言模型抽象基类。

    所有 LLM 实现（DashScope、本地 vLLM 等）都继承此类。
    接受 LangChain BaseMessage 对象或 dict 格式的消息。
    """

    @abstractmethod
    async def ainvoke(
        self,
        messages: list,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """
        异步调用 LLM。

        Args:
            messages: 消息列表，支持两种格式:
                - LangChain BaseMessage 对象列表 (推荐)
                - dict 格式 [{"role": "system"|"user"|"assistant", "content": "..."}]
            temperature: 温度参数
            max_tokens: 最大生成 token 数

        Returns:
            LLM 生成的文本内容
        """

    def invoke(
        self,
        messages: list,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """
        同步调用 LLM。

        仅可在无事件循环的同步上下文中使用；若已在异步上下文中，应直接 await ainvoke()。
        """
        import asyncio

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError(
                "invoke() 不能在异步上下文中调用（asyncio.run 无法嵌套），请改用 await ainvoke()"
            )
        return asyncio.run(self.ainvoke(messages, temperature, max_tokens))

    def with_structured_output(self, schema):
        """
        返回一个 Runnable，ainvoke 时输出 schema 实例（Pydantic 对象）而非字符串。

        用于强制 LLM 返回结构化数据（如问诊意图分类），避免手写 JSON 解析。
        默认不支持；子类按需实现。调用方可捕获 NotImplementedError 回退到 JSON 解析。
        """
        raise NotImplementedError(f"{self.__class__.__name__} 不支持 with_structured_output")


class BaseEmbedding(ABC):
    """
    文本嵌入模型抽象基类。

    支持两种模式:
    - local: 本地 HuggingFace 模型（如 BGE-M3）
    - online: 第三方 API（如 DashScope Embedding API）
    """

    @abstractmethod
    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        """
        异步批量嵌入文档。

        Args:
            texts: 待嵌入的文本列表

        Returns:
            嵌入向量列表，与输入 texts 一一对应
        """

    @abstractmethod
    async def aembed_query(self, text: str) -> list[float]:
        """
        异步嵌入查询文本。

        Args:
            text: 查询文本

        Returns:
            嵌入向量
        """
