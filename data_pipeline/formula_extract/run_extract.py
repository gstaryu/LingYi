"""
古籍方剂提取 CLI - 跑通四本书的解析并输出 JSON。

产出（storage/extracted_formulas/）:
    {book}.json   每书候选方剂列表（含 flags 与原文摘录，供 Agent 校验）
    stats.json    各书统计

用法:
    python -m data_pipeline.formula_extract.run_extract            # 全部四本
    python -m data_pipeline.formula_extract.run_extract --book jufang
    python -m data_pipeline.formula_extract.run_extract --sample 3  # 每书抽样预览
"""

import argparse
import json
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from lingyi.config import get_settings

from data_pipeline.formula_extract.compose import load_herb_lexicon
from data_pipeline.formula_extract.extract import BOOKS, extract_book

logger = logging.getLogger(__name__)

_OUT_DIR = Path(__file__).resolve().parent.parent.parent / "storage" / "extracted_formulas"


def formula_to_dict(f) -> dict:
    """RawFormula → JSON dict。"""
    return {
        "name": f.name,
        "source": f.source,
        "category": f.category,
        "section": f.section,
        "indication": f.indication,
        "composition": [{"herb": c.herb, "dosage": c.dosage} for c in f.components],
        "coverage": round(f.coverage, 3),
        "source_excerpt": f.source_excerpt,
        "flags": f.flags,
    }


def main():
    """CLI 入口。"""
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description="四部古籍方剂提取")
    parser.add_argument("--book", choices=list(BOOKS), help="只跑指定书")
    parser.add_argument("--sample", type=int, default=0, help="每书抽样 N 首预览")
    args = parser.parse_args()

    db_path = str(get_settings().db_path)
    lexicon = load_herb_lexicon(db_path)
    logger.info("药材词表: %d 项", len(lexicon))

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    books = [args.book] if args.book else list(BOOKS)
    stats: dict[str, dict] = {}

    for key in books:
        formulas = extract_book(key, lexicon)
        records = [formula_to_dict(f) for f in formulas]
        if args.sample:
            step = max(1, len(records) // args.sample)
            for r in records[::step][: args.sample]:
                print(json.dumps(r, ensure_ascii=False, indent=1))
        out_path = _OUT_DIR / f"{key}.json"
        out_path.write_text(
            json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        flagged = sum(1 for r in records if r["flags"])
        stats[key] = {
            "source": BOOKS[key]["source"],
            "total": len(records),
            "flagged": flagged,
        }
        print(f"{BOOKS[key]['source']}: {len(records)} 首（含 flags {flagged} 首） -> {out_path.name}")

    stats_path = _OUT_DIR / "stats.json"
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n统计 -> {stats_path}")


if __name__ == "__main__":
    main()
