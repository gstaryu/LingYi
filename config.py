import os
from dotenv import load_dotenv

os.environ["CUDA_VISIBLE_DEVICES"] = "1"

# 加载 .env 环境变量
load_dotenv(override=True)

# 恢复 HuggingFace 镜像加速 (解决首次下载模型非常缓慢的问题)
os.environ["HF_ENDPOINT"] = os.getenv("HF_ENDPOINT", "https://hf-mirror.com")

class Config:
    """
    全局参数配置类，所有硬编码的阈值、模型参数、路径等统一定义在此处。
    """
    # ============== 系统与路径配置 ==============
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    STORAGE_DIR = os.path.join(BASE_DIR, "storage")
    CHROMA_DB_DIR = os.path.join(STORAGE_DIR, "chroma_db")
    DB_PATH = os.path.join(STORAGE_DIR, "patient_profiles.db")

    # ============== 大语言模型 (LLM) 配置 ==============
    LLM_API_KEY = os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENAI_API_KEY")
    LLM_BASE_URL = os.getenv("OPENAI_BASE_URL")
    LLM_MODEL_NAME = os.getenv("MODEL_NAME", "qwen-max")
    LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", 0.7))

    LOCAL_MODEL_NAME = os.getenv("LOCAL_MODEL_NAME", "qwen-local")
    LOCAL_MODEL_URL = os.getenv("LOCAL_MODEL_URL", "http://localhost:8000/v1")

    # ============== 向量/嵌入模型 (Embedding) 配置 ==============
    EMBEDDING_STRATEGY = os.getenv("EMBEDDING_STRATEGY", "local").lower()
    EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "BAAI/bge-m3")
    EMBEDDING_DEVICE = os.getenv("EMBEDDING_DEVICE", "cuda")

    # 重排模型 (Cross-Encoder)
    RERANK_MODEL_NAME = os.getenv("RERANK_MODEL_NAME", "BAAI/bge-reranker-v2-m3")

    # ============== RAG 检索引擎配置 ==============
    RAG_RECALL_K = int(os.getenv("RAG_RECALL_K", 15))               # 粗排召回 Top-K 数量
    RAG_RERANK_K = int(os.getenv("RAG_RERANK_K", 5))                # 精排截取 Top-K 数量
    RAG_SCORE_THRESHOLD = float(os.getenv("RAG_SCORE_THRESHOLD", 0.7)) # RAG 质量及格分数线
    RAG_MAX_RETRIES = int(os.getenv("RAG_MAX_RETRIES", 3))          # RAG 搜索最大重试次数

    # ============== Agent 工作流与上下文配置 ==============
    # Token 上下文压缩阈值 (字符数粗略折算)
    TOKEN_COMPRESSION_THRESHOLD = int(os.getenv("TOKEN_COMPRESSION_THRESHOLD", 8000))

    # 各种技能节点携带的历史对话轮次 (保证效率，截断过长历史)
    MAX_HISTORY_MESSAGES_INQUIRY = int(os.getenv("MAX_HISTORY_MESSAGES_INQUIRY", 5))
    MAX_HISTORY_MESSAGES_DIAGNOSIS = int(os.getenv("MAX_HISTORY_MESSAGES_DIAGNOSIS", 3))
    MAX_HISTORY_MESSAGES_TREATMENT = int(os.getenv("MAX_HISTORY_MESSAGES_TREATMENT", 2))

    # 安全尝试最大次数
    SAFETY_MAX_RETRIES = int(os.getenv("SAFETY_MAX_RETRIES", 3))

# 实例化全局配置对象供其他模块导入
config = Config()
