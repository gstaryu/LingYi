"""Chunker 注册表 — 根据书名返回对应的 Chunker 实例。"""

from data_pipeline.base import BaseChunker
from data_pipeline.chunkers.shanghan import ShanghanChunker
from data_pipeline.chunkers.jingui import JinguiChunker
from data_pipeline.chunkers.wenbing import WenbingChunker
from data_pipeline.chunkers.shennong import ShennongChunker
from data_pipeline.chunkers.maijing import MaijingChunker
from data_pipeline.chunkers.suwen import SuwenChunker

CHUNKER_REGISTRY: dict[str, type[BaseChunker]] = {
    "伤寒论": ShanghanChunker,
    "金匮要略": JinguiChunker,
    "温病条辨": WenbingChunker,
    "神农本草经": ShennongChunker,
    "脉经": MaijingChunker,
    "黄帝内经-素问": SuwenChunker,
}


def get_chunker(book_name: str) -> BaseChunker:
    """根据书名返回对应的 Chunker 实例。"""
    cls = CHUNKER_REGISTRY.get(book_name)
    if not cls:
        raise ValueError(f"未知的书名: {book_name}")
    return cls()
