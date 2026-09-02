"""
2015 版《中国药典》本草批量导入脚本 - 扩充 herbs 表。

数据来源：《2015版中国药典-药性信息.xlsx》（外部只读数据源，不随项目提交）。
字段映射：
  - nature_flavor  = 五味，四气（+毒性，非"无"时追加）
  - meridians      = 归经按"、"切分
  - efficacy       = 【功能与主治】中"用于/外用治"之前的功效部分
  - indications    = 【功能与主治】中"用于/外用治"之后的主治，按标点切分
  - dosage         = 【用法与用量】（全角"～"统一为"-"）
  - aliases / processing / contraindications = 留空（药典无此数据，
    禁忌由 SafetyEngine 十八反十九畏规则引擎兜底）

去重策略：跳过 seed_knowledge.HERBS 中已有的药名及其别名（如 杏仁↔苦杏仁），
再跳过目标库中已存在的药名。幂等 upsert，可重复运行。

用法:
    python -m data_pipeline.seed_pharmacopoeia
    python -m data_pipeline.seed_pharmacopoeia --xlsx <路径>
    python -m data_pipeline.seed_pharmacopoeia --db-path /tmp/test.db --dry-run
"""

import argparse
import asyncio
import logging
import re
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from lingyi.knowledge.models import Herb
from lingyi.storage.sqlite import SQLiteStorage

logger = logging.getLogger(__name__)

# 默认 xlsx 路径（外部只读数据源，不随项目提交）
DEFAULT_XLSX = Path(r"D:\My\111本科\本科毕设\文件\2015版中国药典-药性信息.xlsx")


def _split_efficacy_indications(text: str) -> tuple[str, list[str]]:
    """
    拆分【功能与主治】为 (功效, 主治列表)。

    典型格式: "清热解毒，疏散风热。用于喉痹，乳蛾，咽喉肿痛。"
    变体: 无"用于"（如 天南星"散结消肿。外用治痈肿，蛇虫咬伤。"）。
    """
    text = re.sub(r"\s+", "", text or "")
    # 在"用于"/"外用治"/"治"引导的主治部分处切分（取最早出现的引导词）
    m = re.search(r"(?:。|;|；)(用于|外用治|治)", text)
    if m:
        efficacy = text[: m.start()].rstrip("。；;")
        rest = text[m.start() + 1 :]  # 跳过切分用的句读
        rest = re.sub(r"^(?:用于|外用治|治)", "", rest)
        # 按标点切分主治，去掉空段
        indications = [s for s in re.split(r"[。；;，,]", rest) if s.strip()]
        if efficacy and indications:
            return efficacy, indications
    # 兜底：第一句为功效，其余按标点切分为主治
    sentences = [s for s in text.split("。") if s.strip()]
    if not sentences:
        return "", []
    return sentences[0], [
        s for s in sentences[1:] for s in re.split(r"[，,]", s) if s.strip()
    ]


def _to_herb(row: tuple) -> Herb | None:
    """将药典 xlsx 行映射为 Herb。row: (名称, 五味, 四气, 毒性, 归经, number, 功能主治, 用法用量)。"""
    values = [str(c).strip() if c is not None else "" for c in row]
    while len(values) < 8:
        values.append("")
    name, wuwei, siqi, toxicity, meridians, _num, functions, usage = values[:8]
    if not name or not functions:
        return None

    nature_flavor = f"{wuwei}，{siqi}" if wuwei and siqi else (wuwei or siqi)
    if toxicity and toxicity != "无":
        nature_flavor = f"{nature_flavor}；{toxicity}" if nature_flavor else toxicity

    efficacy, indications = _split_efficacy_indications(functions)
    dosage = usage.replace("～", "-") if usage else ""

    return Herb(
        name=name,
        aliases=[],
        nature_flavor=nature_flavor,
        meridians=[m for m in re.split(r"[、,，]", meridians) if m.strip()]
        if meridians
        else [],
        efficacy=efficacy,
        indications=indications,
        dosage=dosage,
        processing="",
        contraindications="",
    )


async def seed_pharmacopoeia(
    db_path: str,
    xlsx_path: Path = DEFAULT_XLSX,
    dry_run: bool = False,
) -> dict[str, int]:
    """
    读取药典 xlsx，去重后写入 herbs 表。

    Returns:
        {"total": 药典总行数, "inserted": 新增, "skipped_existing": 跳过重名}
    """
    import openpyxl

    from data_pipeline.seed_knowledge import HERBS

    wb = openpyxl.load_workbook(xlsx_path, read_only=True)
    ws = wb["总表"]
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    wb.close()

    # 已有药名集合 = seed_knowledge 手工数据（正名 + 别名）+ 常见异名归并
    known_names: set[str] = {"苦杏仁", "北杏", "杭芍", "熟地", "云苓"}
    for h in HERBS:
        known_names.add(h.name)
        known_names.update(h.aliases)

    storage = SQLiteStorage(db_path)
    await storage.init_db()

    inserted, skipped_existing, skipped_malformed = 0, 0, 0
    for row in rows:
        herb = _to_herb(row)
        if herb is None:
            skipped_malformed += 1
            continue
        if herb.name in known_names:
            skipped_existing += 1
            continue
        if not dry_run:
            await storage.upsert_herb(herb)
        known_names.add(herb.name)  # 防止药典内部重名重复写入
        inserted += 1

    await storage.close()
    logger.info(
        "药典导入完成: 总 %d 行, 新增 %d 味, 跳过已有 %d 味, 异常 %d 行%s",
        len(rows),
        inserted,
        skipped_existing,
        skipped_malformed,
        "（dry-run 未写入）" if dry_run else "",
    )
    return {
        "total": len(rows),
        "inserted": inserted,
        "skipped_existing": skipped_existing,
        "skipped_malformed": skipped_malformed,
    }


def main():
    """CLI 入口。"""
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description="2015 版药典本草批量导入")
    parser.add_argument("--xlsx", default=str(DEFAULT_XLSX), help="药典 xlsx 路径")
    parser.add_argument("--db-path", default=None, help="数据库路径（默认 settings.db_path）")
    parser.add_argument("--dry-run", action="store_true", help="只统计不写入")
    args = parser.parse_args()

    if args.db_path:
        db_path = args.db_path
    else:
        from lingyi.config import get_settings

        db_path = str(get_settings().db_path)

    print(f"数据库: {db_path}")
    print(f"药典:   {args.xlsx}")
    counts = asyncio.run(seed_pharmacopoeia(db_path, Path(args.xlsx), dry_run=args.dry_run))
    print(
        f"\n导入完成:\n"
        f"  药典总行数: {counts['total']}\n"
        f"  新增:       {counts['inserted']} 味\n"
        f"  跳过已有:   {counts['skipped_existing']} 味\n"
        f"  异常跳过:   {counts['skipped_malformed']} 行"
    )


if __name__ == "__main__":
    main()
