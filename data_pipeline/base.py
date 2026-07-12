"""
数据管道基类 — 定义切分器抽象和 Chunk 数据结构。

每本古籍有独立的 Chunker 实现，通过策略模式统一调用。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Chunk:
    """切分后的文档片段。"""

    id: str
    """唯一标识（如 SHL_001, WBD_042）。"""

    content: str
    """文档正文内容。"""

    metadata: dict[str, Any] = field(default_factory=dict)
    """元数据（书名、章节、条文号等）。"""


class BaseChunker(ABC):
    """
    古籍切分器抽象基类。

    每本古籍实现一个 Chunker 子类，负责:
    1. clean(text) — 通用清洗（去页码、去重复等）
    2. chunk(text) — 按书特定策略切分为 Chunk 列表
    """

    book_name: str = ""
    """书名标识（如 '伤寒论', '温病条辨'）。"""

    @abstractmethod
    def chunk(self, text: str) -> list[Chunk]:
        """
        将文本切分为 Chunk 列表。

        Args:
            text: 清洗后的完整文本

        Returns:
            Chunk 列表
        """

    def clean(self, text: str) -> str:
        """
        通用文本清洗。

        默认实现调用 data_pipeline.cleaners 中的通用清洗函数。
        子类可覆盖以添加书特定的清洗逻辑。

        Args:
            text: 原始文本

        Returns:
            清洗后的文本
        """
        from data_pipeline.cleaners import clean_text

        return clean_text(text)
