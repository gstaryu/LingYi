"""
统一异常层次 — 所有灵医业务异常的基类与子类。

设计原则:
- 所有业务异常继承 LingYiError，便于统一捕获
- FastAPI 层通过 @app.exception_handler(LingYiError) 统一返回 JSON 错误
- Agent 层抛 LingYiError 子类，由调用方决定如何处理
"""


class LingYiError(Exception):
    """灵医系统所有业务异常的基类。"""

    def __init__(self, message: str = "", *, detail: str = ""):
        self.message = message
        self.detail = detail or message
        super().__init__(self.message)


class ConfigError(LingYiError):
    """配置错误 — 缺少必要的环境变量或配置值无效。"""


class ModelCallError(LingYiError):
    """模型调用失败 — LLM API 超时、限流或返回异常。"""

    def __init__(self, message: str = "", *, provider: str = "", status_code: int = 0):
        self.provider = provider
        self.status_code = status_code
        super().__init__(message)


class SafetyViolationError(LingYiError):
    """安全违规 — 检测到配伍禁忌（十八反/十九畏）。"""

    def __init__(self, message: str = "", *, violations: list[str] | None = None):
        self.violations = violations or []
        super().__init__(message)


class RAGSearchError(LingYiError):
    """RAG 检索失败 — 向量数据库连接异常或检索无结果。"""


class ParseError(LingYiError):
    """解析错误 — LLM 输出的 JSON 格式不符合预期。"""


class StorageError(LingYiError):
    """存储错误 — SQLite 操作失败。"""
