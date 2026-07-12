"""
全局配置 — 基于 pydantic-settings 的配置管理。

设计原则:
- 纯数据类，不在模块级执行任何副作用（不调 load_dotenv，不设 os.environ）
- 通过 .env 文件自动加载环境变量
- 提供 get_settings() 工厂函数（带 lru_cache），全局只需一个实例
- 所有配置项有合理默认值，可通过环境变量覆盖
"""

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# 项目根目录（lingyi/ 的父目录）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """
    灵医全局配置。

    所有字段均可通过环境变量或 .env 文件覆盖。
    环境变量名与字段名一致（大写）。
    """

    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",  # 忽略 .env 中的未知字段
    )

    # ==================== 系统配置 ====================
    environment: str = Field(
        default="development",
        description="运行环境: development / testing / production",
    )
    log_level: str = Field(default="INFO", description="日志级别")

    # ==================== 路径配置 ====================
    base_dir: str = Field(default=str(_PROJECT_ROOT), description="项目根目录")
    storage_dir: str = Field(
        default=str(_PROJECT_ROOT / "storage"),
        description="运行时数据目录（SQLite、ChromaDB 等）",
    )

    # ==================== 大语言模型 (LLM) 配置 ====================
    dashscope_api_key: str = Field(
        default="",
        description="阿里云 DashScope API Key",
    )
    openai_api_key: str = Field(
        default="",
        description="OpenAI 兼容 API Key（DashScope 或其他兼容服务）",
    )
    openai_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        description="OpenAI 兼容 API 的 Base URL",
    )
    model_name: str = Field(
        default="qwen-max",
        description="LLM 模型名称",
    )
    llm_temperature: float = Field(default=0.7, description="LLM 温度参数")
    llm_timeout: int = Field(default=120, description="LLM API 超时时间（秒）")
    llm_max_retries: int = Field(default=3, description="LLM API 最大重试次数")

    # 本地模型（vLLM 等部署）
    local_model_name: str = Field(default="qwen-local", description="本地模型名称")
    local_model_url: str = Field(
        default="http://localhost:8000/v1",
        description="本地模型 API 地址",
    )

    # ==================== Embedding 配置 ====================
    embedding_mode: str = Field(
        default="local",
        description="Embedding 模式: local（HuggingFace BGE-M3）/ online（DashScope API）",
    )
    embedding_model_name: str = Field(
        default="BAAI/bge-m3",
        description="Embedding 模型名称",
    )
    embedding_device: str = Field(
        default="cuda",
        description="Embedding 设备: cuda / cpu",
    )

    # ==================== Reranker 配置 ====================
    rerank_model_name: str = Field(
        default="BAAI/bge-reranker-v2-m3",
        description="Cross-Encoder 重排模型名称",
    )

    # ==================== RAG 配置 ====================
    rag_mode: str = Field(
        default="mock",
        description="RAG 模式: mock（本地开发）/ chroma（生产向量检索）",
    )
    rag_recall_k: int = Field(default=15, description="粗排召回 Top-K 数量")
    rag_rerank_k: int = Field(default=5, description="精排截取 Top-K 数量")
    rag_score_threshold: float = Field(default=0.7, description="RAG 质量及格分数线")
    rag_max_retries: int = Field(default=3, description="RAG 搜索最大重试次数")
    rag_enable_evaluation: bool = Field(
        default=False,
        description="是否启用 RAG 检索质量评估（启用后会循环评估-重写，增加 LLM 调用次数）",
    )

    # ==================== Agent 工作流配置 ====================
    token_compression_threshold: int = Field(
        default=8000,
        description="上下文压缩触发阈值（字符数粗略折算）",
    )
    max_history_messages_inquiry: int = Field(
        default=5,
        description="问诊节点携带的历史对话轮次",
    )
    max_history_messages_diagnosis: int = Field(
        default=3,
        description="辨证节点携带的历史对话轮次",
    )
    max_history_messages_treatment: int = Field(
        default=2,
        description="处方节点携带的历史对话轮次",
    )
    safety_max_retries: int = Field(default=3, description="安全校验最大重试次数")

    # ==================== 认证配置 ====================
    jwt_secret_key: str = Field(
        default="lingyi-dev-secret-change-in-production",
        description="JWT 签名密钥（生产环境必须更换）",
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT 签名算法")
    jwt_expire_minutes: int = Field(default=1440, description="JWT Token 有效期（分钟）")

    # ==================== 便捷属性 ====================
    @property
    def effective_api_key(self) -> str:
        """获取有效的 API Key（优先 DashScope，回退 OpenAI）。"""
        return self.dashscope_api_key or self.openai_api_key

    @property
    def db_path(self) -> str:
        """SQLite 数据库文件路径。"""
        return os.path.join(self.storage_dir, "patient_profiles.db")

    @property
    def chroma_db_dir(self) -> str:
        """ChromaDB 持久化目录。"""
        return os.path.join(self.storage_dir, "chroma_db")

    @property
    def chunks_dir(self) -> str:
        """数据切分输出目录。"""
        return os.path.join(self.storage_dir, "chunks")

    @property
    def uploads_dir(self) -> str:
        """用户上传文件目录（病历等）。"""
        return os.path.join(self.storage_dir, "uploads")

    @property
    def hf_endpoint(self) -> str:
        """HuggingFace 镜像地址（解决国内下载缓慢问题）。"""
        return os.getenv("HF_ENDPOINT", "https://hf-mirror.com")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    获取全局配置单例。

    使用 lru_cache 保证全局只有一个 Settings 实例。
    测试时可通过 get_settings.cache_clear() 重置。
    """
    return Settings()
