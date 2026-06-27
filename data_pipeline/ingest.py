"""
TCM 数据入库脚本 — 读取古籍文本，切分为 Chunk，输出 JSON 或写入 ChromaDB。

用法:
    # 输出 JSON 到 storage/chunks/
    python -m data_pipeline.ingest

    # 写入 ChromaDB（需 embedding 模型）
    python -m data_pipeline.ingest --mode chroma
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# 添加项目根目录到 path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from data_pipeline.base import Chunk
from data_pipeline.chunkers.registry import get_chunker

logger = logging.getLogger(__name__)

# TCM 数据文件映射
TCM_FILES: dict[str, str] = {
    "伤寒论": "伤寒论_完整清洗版.txt",
    "金匮要略": "金匮要略_完整清洗版.txt",
    "温病条辨": "温病条辨_完整清洗版.txt",
    "神农本草经": "神农本草经_完整清洗版.txt",
    "脉经": "脉经_完整清洗版.txt",
    "黄帝内经-素问": "黄帝内经-素问_完整清洗版.txt",
}


def chunk_all_books(tcm_data_dir: str) -> dict[str, list[Chunk]]:
    """对所有古籍执行切分。"""
    all_chunks: dict[str, list[Chunk]] = {}

    for book_name, filename in TCM_FILES.items():
        filepath = os.path.join(tcm_data_dir, filename)
        if not os.path.exists(filepath):
            logger.warning("文件不存在: %s", filepath)
            continue

        logger.info("切分 %s ...", book_name)
        with open(filepath, encoding="utf-8") as f:
            text = f.read()

        chunker = get_chunker(book_name)
        chunks = chunker.chunk(text)
        all_chunks[book_name] = chunks
        logger.info("  %s: %d 个 chunk", book_name, len(chunks))

    return all_chunks


def save_chunks_json(all_chunks: dict[str, list[Chunk]], output_dir: str) -> None:
    """将切分结果保存为 JSON 文件。"""
    os.makedirs(output_dir, exist_ok=True)

    for book_name, chunks in all_chunks.items():
        data = [
            {"id": c.id, "content": c.content, "metadata": c.metadata}
            for c in chunks
        ]
        safe_name = book_name.replace("/", "_").replace(" ", "_")
        filepath = os.path.join(output_dir, f"{safe_name}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("保存: %s (%d 条)", filepath, len(data))


def generate_mock_data(all_chunks: dict[str, list[Chunk]], output_path: str) -> None:
    """从切分结果中采样生成 mock RAG 测试数据。"""
    import random
    random.seed(42)

    mock_queries: dict = {"queries": [], "default_results": []}

    for book_name, chunks in all_chunks.items():
        sample_size = min(2, len(chunks))
        sampled = random.sample(chunks, sample_size)
        for c in sampled:
            mock_queries["default_results"].append({
                "content": c.content[:500],
                "source": book_name,
                "score": 0.6,
            })

    mock_queries["queries"] = [
        {
            "query_pattern": "脾胃虚寒|腹胀|怕冷|拉肚子",
            "results": [
                {"content": "太阴之为病，腹满而吐，食不下，自利益甚，时腹自痛。", "source": "伤寒论", "score": 0.92},
                {"content": "自利不渴者，属太阴，以其脏有寒故也。当温之，宜服四逆辈。", "source": "伤寒论", "score": 0.85},
            ],
        },
        {
            "query_pattern": "感冒|发热|恶寒|头痛",
            "results": [
                {"content": "太阳之为病，脉浮，头项强痛而恶寒。", "source": "伤寒论", "score": 0.90},
                {"content": "太阳病，发热汗出恶风，脉缓者，名为中风。", "source": "伤寒论", "score": 0.88},
            ],
        },
    ]

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(mock_queries, f, ensure_ascii=False, indent=2)
    logger.info("Mock 数据已生成: %s", output_path)


def main():
    """主入口。"""
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description="TCM 数据入库脚本")
    parser.add_argument("--mode", choices=["json", "chroma", "mock"], default="json")
    parser.add_argument("--tcm-dir", default=str(_PROJECT_ROOT / "TCM_data"))
    parser.add_argument("--output-dir", default=str(_PROJECT_ROOT / "storage" / "chunks"))
    args = parser.parse_args()

    all_chunks = chunk_all_books(args.tcm_dir)
    total = sum(len(v) for v in all_chunks.values())
    print(f"\n总计: {len(all_chunks)} 本书, {total} 个 chunk\n")

    if args.mode == "json":
        save_chunks_json(all_chunks, args.output_dir)
        print(f"\nJSON 已保存到: {args.output_dir}")
    elif args.mode == "mock":
        mock_path = str(_PROJECT_ROOT / "storage" / "mock_rag_data.json")
        generate_mock_data(all_chunks, mock_path)
        print(f"\nMock 数据已保存到: {mock_path}")
    elif args.mode == "chroma":
        print("ChromaDB 入库需通过 lingyi/rag/chroma.py 的 add_documents() 接口")


if __name__ == "__main__":
    main()
