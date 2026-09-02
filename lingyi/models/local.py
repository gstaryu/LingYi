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
    默认使用 Qwen3-Embedding-0.6B（1024 维，instruction-aware）。

    Qwen3-Embedding 等 instruction-aware 模型要求查询侧使用 prompt_name="query"
    （自动套用 "Instruct: {task}\\nQuery: " 模板），文档侧不加 prompt。
    通过 query_prompt_name 参数控制；BGE-M3 等非 instruction 模型传 None。
    """

    def __init__(
        self,
        model_name: str = "Qwen/Qwen3-Embedding-0.6B",
        device: str = "cuda",
        hf_endpoint: str = "https://hf-mirror.com",
        query_prompt_name: str | None = None,
    ):
        """
        初始化本地 Embedding 模型。

        Args:
            model_name: HuggingFace 模型名称
            device: 计算设备（cuda / cpu）
            hf_endpoint: HuggingFace 镜像地址
            query_prompt_name: 查询嵌入的 prompt 名称（Qwen3-Embedding 用 "query"）；
                非 instruction 模型（如 BGE-M3）传 None
        """
        self._model_name = model_name
        self._device = device
        self._hf_endpoint = hf_endpoint
        self._query_prompt_name = query_prompt_name
        self._model = None

        logger.info(
            "LocalEmbedding 初始化: model=%s, device=%s, query_prompt=%s",
            model_name,
            device,
            query_prompt_name or "(none)",
        )

    def _ensure_model(self):
        """延迟加载模型（首次调用时才加载，避免启动时占用显存）。"""
        if self._model is not None:
            return

        # HF_ENDPOINT 必须在 import sentence_transformers 之前设置（国内镜像加速）
        import os

        os.environ["HF_ENDPOINT"] = self._hf_endpoint

        from sentence_transformers import SentenceTransformer

        def _load(device: str, local_only: bool):
            # 优先本地缓存加载（不发网络请求，免疫 hf-mirror 抖动），未命中再在线
            try:
                return SentenceTransformer(
                    self._model_name, device=device, local_files_only=local_only
                )
            except Exception:
                if local_only:
                    raise
                return SentenceTransformer(
                    self._model_name, device=device, local_files_only=True
                )

        try:
            self._model = _load(self._device, local_only=True)
            logger.info(
                "Embedding 模型加载成功（本地缓存）: %s (device=%s)",
                self._model_name, self._device,
            )
        except Exception as e:
            # 加载失败（缓存未命中或 device 不可用）：CUDA→先试 CPU 本地缓存，再在线
            logger.info("本地缓存加载失败: %s", e)
            candidates = []
            if self._device == "cuda":
                candidates.append(("cpu", True))
                candidates.append(("cpu", False))
            candidates.append((self._device, False))
            last_err = e
            for device, local_only in candidates:
                try:
                    self._model = _load(device, local_only)
                    self._device = device
                    logger.info("Embedding 模型回退加载成功: device=%s, local_only=%s", device, local_only)
                    break
                except Exception as e2:
                    last_err = e2
            else:
                raise last_err

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
        """
        异步嵌入查询文本。

        对于 instruction-aware 模型（Qwen3-Embedding），使用 prompt_name="query"
        套用查询指令模板；普通模型（BGE-M3）直接编码。
        """
        self._ensure_model()
        loop = asyncio.get_running_loop()
        if self._query_prompt_name:
            # prompt_name 需作为关键字参数传入，用 partial 绑定后在线程池执行
            import functools

            encode_fn = functools.partial(
                self._model.encode, prompt_name=self._query_prompt_name
            )
            embedding = await loop.run_in_executor(None, encode_fn, [text])
        else:
            embedding = await loop.run_in_executor(None, self._model.encode, [text])
        return embedding[0].tolist()
