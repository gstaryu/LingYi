"""
本地 HuggingFace 模型实现。

用于在本地 GPU/CPU 上运行 Embedding 模型（如 BGE-M3），
无需调用第三方 API，适合离线环境或数据隐私要求高的场景。
"""

import asyncio
import logging

from lingyi.models.base import BaseEmbedding

logger = logging.getLogger(__name__)


class LocalEmbedding(BaseEmbedding):
    """
    本地 HuggingFace Embedding 模型。

    使用 sentence-transformers 加载模型，支持 CUDA/CPU 自动回退。
    默认使用 BAAI/bge-m3 模型。
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-m3",
        device: str = "cuda",
        hf_endpoint: str = "https://hf-mirror.com",
    ):
        """
        初始化本地 Embedding 模型。

        Args:
            model_name: HuggingFace 模型名称
            device: 计算设备（cuda / cpu）
            hf_endpoint: HuggingFace 镜像地址
        """
        self._model_name = model_name
        self._device = device
        self._hf_endpoint = hf_endpoint
        self._model = None

        logger.info("LocalEmbedding 初始化: model=%s, device=%s", model_name, device)

    def _ensure_model(self):
        """延迟加载模型（首次调用时才加载，避免启动时占用显存）。"""
        if self._model is not None:
            return

        # HF_ENDPOINT 必须在 import sentence_transformers 之前设置（国内镜像加速）
        import os

        os.environ["HF_ENDPOINT"] = self._hf_endpoint

        from sentence_transformers import SentenceTransformer

        try:
            self._model = SentenceTransformer(self._model_name, device=self._device)
            logger.info("Embedding 模型加载成功: %s (device=%s)", self._model_name, self._device)
        except Exception as e:
            # CUDA 不可用时自动回退到 CPU
            if self._device == "cuda":
                logger.warning("CUDA 不可用，回退到 CPU: %s", e)
                self._model = SentenceTransformer(self._model_name, device="cpu")
                self._device = "cpu"
            else:
                raise

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        """
        异步批量嵌入文档。

        sentence-transformers 是同步库，用 asyncio.to_thread 包装为异步调用。
        """
        self._ensure_model()
        loop = asyncio.get_running_loop()
        embeddings = await loop.run_in_executor(None, self._model.encode, texts)
        return embeddings.tolist()

    async def aembed_query(self, text: str) -> list[float]:
        """异步嵌入查询文本。"""
        self._ensure_model()
        loop = asyncio.get_running_loop()
        embedding = await loop.run_in_executor(None, self._model.encode, [text])
        return embedding[0].tolist()
