"""
日志配置 — 统一使用 Python 标准 logging 模块。

设计原则:
- 每个模块用 logger = logging.getLogger(__name__)
- 日志格式: 时间 | 级别 | 模块名 | 消息
- 日志级别从 Settings.log_level 读取
- 不引入额外依赖（loguru/structlog）
"""

import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    """
    配置全局日志。

    Args:
        level: 日志级别，可选 DEBUG / INFO / WARNING / ERROR / CRITICAL
    """
    # 清除已有 handler，避免重复输出
    root = logging.getLogger()
    root.handlers.clear()

    # 设置日志格式
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 控制台输出
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    # 配置根 logger
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.addHandler(console_handler)

    # 第三方库日志降级，避免刷屏
    for noisy in ("httpx", "httpcore", "chromadb", "sentence_transformers", "uvicorn"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
