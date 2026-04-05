import os
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
# 从对应的库获取 Embeddings
try:
    from langchain_huggingface import HuggingFaceBgeEmbeddings
except ImportError:
    from langchain_community.embeddings import HuggingFaceBgeEmbeddings

from config import config

load_dotenv(override=True)

class ModelProvider:
    def __init__(self):
        self._reranker = None
        self._embeddings = None

    def get_model(self, use_local: bool = False):
        if use_local:
            return ChatOpenAI(
                model=config.LOCAL_MODEL_NAME,
                api_key="EMPTY",  # type: ignore
                base_url=config.LOCAL_MODEL_URL
            )

        return ChatOpenAI(
            model=config.LLM_MODEL_NAME,
            api_key=config.LLM_API_KEY,
            base_url=config.LLM_BASE_URL,
            temperature=config.LLM_TEMPERATURE
        )

    def get_embeddings(self):
        """
        根据环境变量 EMBEDDING_STRATEGY 切换模型。
        可选值: 'local' (BGE-M3), 'online' (DashScope)
        """
        if self._embeddings is not None:
            return self._embeddings

        strategy = config.EMBEDDING_STRATEGY

        if strategy == "local":
            # 本地部署 BGE-M3
            model_name = config.EMBEDDING_MODEL_NAME
            encode_kwargs = {'normalize_embeddings': True}
            print(f"📦 正在加载本地向量模型: {model_name}...")

            # 使用环境变量判断设备，如果没有则默认尝试 cuda，或者降级为 cpu
            device = config.EMBEDDING_DEVICE

            try:
                self._embeddings = HuggingFaceBgeEmbeddings(
                    model_name=model_name,
                    model_kwargs={'device': device},
                    encode_kwargs=encode_kwargs
                )
            except Exception as e:
                print(f"⚠️ 无法使用 {device} 加载模型，尝试降级到 CPU。({e})")
                self._embeddings = HuggingFaceBgeEmbeddings(
                    model_name=model_name,
                    model_kwargs={'device': 'cpu'},
                    encode_kwargs=encode_kwargs
                )
        else:
            # 引入在线 Embeddings 如果需要
            from langchain_community.embeddings import DashScopeEmbeddings
            self._embeddings = DashScopeEmbeddings()

        return self._embeddings

    def get_reranker(self):
        """
        获取一个交叉编码器 (CrossEncoder) 用于知识重排。
        """
        if self._reranker is not None:
            return self._reranker

        strategy = config.EMBEDDING_STRATEGY

        if strategy == "local":
            try:
                from sentence_transformers import CrossEncoder
                import torch
                # 清理缓存，避免显存不足
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                print(f"📦 正在加载跨编码器重排模型: {config.RERANK_MODEL_NAME}...")

                device = config.EMBEDDING_DEVICE
                try:
                    # 尝试加载 Reranker 模型
                    self._reranker = CrossEncoder(config.RERANK_MODEL_NAME, device=device)
                except Exception as e:
                    print(f"⚠️ 无法使用 {device} 加载重排模型，尝试加载 CPU。({e})")
                    self._reranker = CrossEncoder(config.RERANK_MODEL_NAME, device='cpu')
            except ImportError:
                print("❌ 缺少 'sentence-transformers' 库。请执行 `pip install sentence-transformers` 以开启重排功能。")
                return None
        return self._reranker

model_manager = ModelProvider()