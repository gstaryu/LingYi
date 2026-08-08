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
    llm_specialist_max_retries: int = Field(
        default=1,
        description="专家/综合/审查者 LLM API 最大重试次数（低于 llm_max_retries，"
        "避免网关抖动时静默 3x 重试风暴拖慢会诊）",
    )

    # 多智能体专家模型配置（留空则回退到 model_name）
    model_name_bianzheng: str = Field(
        default="",
        description="辨证专家模型名（留空回退到 model_name）",
    )
    model_name_fangji: str = Field(
        default="",
        description="方剂专家模型名（留空回退到 model_name）",
    )
    model_name_bencao: str = Field(
        default="",
        description="本草专家模型名（留空回退到 model_name）",
    )

    # 本地模型（vLLM 等部署）
    local_model_name: str = Field(default="qwen-local", description="本地模型名称")
    local_model_url: str = Field(
        default="http://localhost:8000/v1",
        description="本地模型 API 地址",
    )

    # ==================== Embedding 配置 ====================
    embedding_mode: str = Field(
        default="local",
        description="Embedding 模式: local（本地 HuggingFace，默认 Qwen3-Embedding-0.6B）/ online（DashScope API）",
    )
    embedding_model_name: str = Field(
        default="Qwen/Qwen3-Embedding-0.6B",
        description="本地 Embedding 模型名称（HuggingFace）。默认 Qwen3-Embedding-0.6B（1024 维，instruction-aware）",
    )
    embedding_online_model_name: str = Field(
        default="text-embedding-v4",
        description="online 模式下的 DashScope Embedding 模型名（text-embedding-v3 / v4）",
    )
    embedding_query_prompt_name: str = Field(
        default="",
        description="查询嵌入的 sentence-transformers prompt 名称；Qwen3-Embedding 需 'query'。留空则按模型名自动检测",
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
    agent_mode: str = Field(
        default="workflow",
        description="Agent 模式: workflow（单 Agent 工作流，默认）/ multiagent（多智能体会诊）",
    )
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
    max_followups: int = Field(
        default=1,
        description="最大追问轮数（达到后强制进入诊断）；1 = 仅追问一次，用户回答后即辨证",
    )
    safety_max_retries: int = Field(default=3, description="安全校验最大重试次数")
    reviewer_max_retries: int = Field(
        default=2,
        description="对抗审查者最大重试次数（耗尽后交由 SafetyEngine 硬校验裁决）",
    )
    safety_fail_mode: str = Field(
        default="closed",
        description="前置安全审查 LLM 异常时的失败策略: closed（默认，拒绝请求）/ open（放行）",
    )

    # ==================== 追踪配置 ====================
    enable_tracing: bool = Field(default=False, description="是否启用 LangSmith 链路追踪")
    langsmith_api_key: str = Field(default="", description="LangSmith API Key")
    langsmith_project: str = Field(default="lingyi", description="LangSmith 项目名")

    # ==================== 网络搜索配置 ====================
    web_search_enabled: bool = Field(
        default=True,
        description="是否启用 web_search 工具（复用 RivalSearchMCP 服务，失败时按 fallback 策略处理）",
    )
    rivalsearch_mcp_command: str = Field(
        default="C:/Users/start/mcp-servers/RivalSearchMCP/.venv/Scripts/python.exe",
        description="RivalSearchMCP stdio 启动命令（解释器路径）",
    )
    rivalsearch_mcp_script: str = Field(
        default="C:/Users/start/mcp-servers/RivalSearchMCP/server.py",
        description="RivalSearchMCP server.py 脚本路径（作为 stdio 启动参数）",
    )
    web_search_fallback_to_ddgs: bool = Field(
        default=False,
        description="MCP 连接失败时是否回退到 DuckDuckGo（需安装 ddgs/langchain-community）；False 则优雅省略 web_search 工具",
    )

    # ==================== 认证配置 ====================
    jwt_secret_key: str = Field(
        default="lingyi-dev-secret-change-in-production",
        description="JWT 签名密钥（生产环境必须更换）",
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT 签名算法")
    jwt_expire_minutes: int = Field(default=1440, description="JWT Token 有效期（分钟）")

    # ==================== CORS 配置 ====================
    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:8501",
        description="允许的 CORS 来源（逗号分隔）；生产环境通过环境变量设置",
    )

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
    def checkpoints_db_path(self) -> str:
        """LangGraph 检查点 SQLite 文件路径（与业务库分离）。"""
        return os.path.join(self.storage_dir, "checkpoints.db")

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
