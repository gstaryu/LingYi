"""四部古籍方剂入库（INSERT-only，库内已有方名跳过）。

数据源: storage/extracted_formulas/{book}.json，扣除 verify_{book}.json 的 drop 名单。
跨书同名按朝代优先级保留最早出处（千金 > 外台 > 局方 > 医方集解）。幂等。

用法: python -m data_pipeline.seed_formulas_classics [--db-path <路径>] [--dry-run]
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from lingyi.knowledge.models import Formula, FormulaComponent
from lingyi.storage.sqlite import SQLiteStorage

logger = logging.getLogger(__name__)

_EXTRACT_DIR = Path(__file__).resolve().parent.parent / "storage" / "extracted_formulas"
_PRIORITY = ["qianjin", "waitai", "jufang", "jifangjie"]
_MIN_COMPONENTS = 2


def _load_book(book: str) -> list[dict]:
    """读取单书提取结果。"""
    path = _EXTRACT_DIR / f"{book}.json"
    if not path.exists():
        logger.warning("缺少提取结果: %s", path)
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _load_drops(book: str) -> set[str]:
    """读取该校验 drop 名单，文件缺失时返回空集。"""
    path = _EXTRACT_DIR / f"verify_{book}.json"
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {d["name"] for d in data.get("drop", [])}
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning("读取 drop 名单失败 %s: %s", path, e)
        return set()


def _merge_cross_book() -> list[dict]:
    """四书合并 + drop 过滤 + 跨书同名按朝代优先级去重。"""
    seen: set[str] = set()
    merged: list[dict] = []
    for book in _PRIORITY:
        drops = _load_drops(book)
        for rec in _load_book(book):
            name = rec["name"]
            if name in drops or len(rec.get("composition", [])) < _MIN_COMPONENTS:
                continue
            if name in seen:
                continue
            seen.add(name)
            merged.append(rec)
    return merged


async def seed_formulas_classics(db_path: str, dry_run: bool = False) -> dict[str, int]:
    """将校验通过的方剂写入 formulas 表。"""
    storage = SQLiteStorage(db_path)
    await storage.init_db()
    merged = _merge_cross_book()

    inserted = 0
    for rec in merged:
        name = rec["name"]
        if not dry_run:
            if await storage.get_formula(name) is not None:
                continue  # INSERT-only：保护库内已有记录（含 22 首手工方）
            formula = Formula(
                name=name,
                source=rec["source"],
                composition=[
                    FormulaComponent(c["herb"], c.get("dosage", ""))
                    for c in rec["composition"]
                ],
                indication=rec["indication"],
                modifications="",
                contraindications="",
                category=rec["category"],
            )
            await storage.upsert_formula(formula)
        inserted += 1

    await storage.close()
    dropped = sum(len(_load_drops(b)) for b in _PRIORITY)
    logger.info(
        "古籍方剂入库完成: 候选 %d, 入库 %d, 校验剔除 %d%s",
        len(merged), inserted, dropped, "（dry-run 未写入）" if dry_run else "",
    )
    return {"candidates": len(merged), "inserted": inserted, "skipped_dropped": dropped}


def main():
    """CLI 入口。"""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="四部古籍方剂入库")
    parser.add_argument("--db-path", default=None, help="数据库路径（默认 settings.db_path）")
    parser.add_argument("--dry-run", action="store_true", help="只统计不写入")
    args = parser.parse_args()

    if args.db_path:
        db_path = args.db_path
    else:
        from lingyi.config import get_settings

        db_path = str(get_settings().db_path)

    print(f"数据库: {db_path}")
    counts = asyncio.run(seed_formulas_classics(db_path, dry_run=args.dry_run))
    print(
        f"入库完成: 候选 {counts['candidates']} 首, "
        f"入库 {counts['inserted']} 首, 校验剔除 {counts['skipped_dropped']} 首"
    )


if __name__ == "__main__":
    main()
