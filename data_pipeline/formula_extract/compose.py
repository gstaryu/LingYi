"""
方剂组成解析器 - 从古籍组成文本段提取 药材+剂量 列表。

核心策略:
1. 换行删除（古籍定宽排版会在药名/括号内断行），空格保留为 token 分隔符
2. 优先扫描「药材（注释）」模式，注释中提取 基数+单位 作为剂量
3. 「各X两」分组剂量分配给当前无剂量的药材串
4. 药材词表（herbs 表正名+别名）做确定性校验，计算覆盖率作为可信度
"""

import json
import logging
import re
import sqlite3
from dataclasses import dataclass, field

from lingyi.knowledge.models import FormulaComponent

from data_pipeline.formula_extract.clean import clean_ocr

logger = logging.getLogger(__name__)

_NUM = r"[一二三四五六七八九十百千零半\d]+"

# 剂量单位（古籍常见）
_UNITS = "两|分|钱|斤|升|合|枚|颗|个|寸|匕|字|铢|盏|粒|条|张|片|尺|挺|握|把|束|铤|茎|斗|石"
_DOSAGE_RE = re.compile(rf"{_NUM}(?:{_UNITS})")
_HERB_ANNOT_RE = re.compile(r"([一-龥·]{1,6})（([^（）]{1,32})）")
_CJK_RE = re.compile(r"^[一-龥·]{1,6}$")

# 制法/服法动词——出现即认为组成段结束
_PREP_MARKERS = (
    "咀", "捣筛", "为末", "为丸", "为散", "炼蜜", "每服",
    "以水", "以醋", "以酒", "煮取", "去滓", "温服", "分服", "空心", "研令",
    "右件", "合和", "捣罗", "不见火", "锉散", "研为", "杵为", "服之",
)
_PREP_COUNT_RE = re.compile(rf"[上右]{_NUM}味")

# 明显不是药材的 CJK token
_STOP_TOKENS = {
    "方", "主之", "治", "疗", "主", "兼主", "右", "上", "各", "等分", "并等分",
    "又方", "一方", "亦可", "名", "同名", "以上", "生用", "炒用", "汤成",
}
# 加减法/附方/经义注释模式（医方集解常见）：加X、去X、名XX汤、此X药也
_STOP_TOKEN_RE = re.compile(
    r"^(?:加|去)[一-龥]{0,4}$|名[一-龥]{1,6}(?:汤|丸|散|膏|丹|饮)$|此[一-龥]{0,12}药也"
    r"|^(?:故|以)为[君臣佐使]$|^治[一-龥]{0,8}$|^主[一-龥]{0,6}$"
)


@dataclass
class ParsedComposition:
    """组成解析结果。"""

    components: list[FormulaComponent] = field(default_factory=list)
    coverage: float = 0.0  # 词表命中率 (0-1)，作为可信度


def load_herb_lexicon(db_path: str) -> set[str]:
    """从 herbs 表加载药材词表（正名 + 别名），并补充常见古籍异名。"""
    conn = sqlite3.connect(db_path)
    try:
        names = {r[0] for r in conn.execute("SELECT name FROM herbs")}
        for (aliases_json,) in conn.execute("SELECT aliases FROM herbs"):
            try:
                names.update(json.loads(aliases_json))
            except (json.JSONDecodeError, TypeError):
                continue
    finally:
        conn.close()
    # 常见古籍异名补充（仅用于校验，不改变入库药名）
    names.update({
        "桂心", "芍药", "栝蒌", "瓜蒌", "蒌根", "天花粉", "地黄", "生地黄", "干地黄",
        "薯蓣", "山萸肉", "萸肉", "茱萸", "橘皮", "青橘皮", "香豉", "豉",
        "葱白", "薤白", "饴糖", "胶饴", "鸡子黄", "苦酒", "清酒", "白蜜", "粳米",
        "蜀漆", "蜀椒", "花椒", "乌头", "川乌", "草乌", "升麻", "葳蕤",
        "蒲黄", "茅根", "苇根", "芦根", "麦门冬", "天门冬", "桑白皮", "桑根白皮",
        "甘草炙", "人参芦", "白茯苓", "赤茯苓", "茯神", "白芍药", "生甘草", "炙甘草",
    })
    return names


def _extract_dosage(annot: str) -> str:
    """从注释中提取剂量字符串（基数+单位），无剂量返回空。"""
    annot = annot.replace(" ", "").replace("，", "")
    m = re.search(rf"各{_NUM}(?:{_UNITS})", annot)
    if m:
        return m.group(0).removeprefix("各")
    m = _DOSAGE_RE.search(annot)
    return m.group(0) if m else ""


def parse_composition(segment: str, lexicon: set[str]) -> ParsedComposition:
    """
    解析组成文本段 → 药材+剂量列表。

    Args:
        segment: 组成文本（药材串，含括号注释），允许跨行
        lexicon: 药材词表（正名+别名+异名）
    """
    segment = clean_ocr(segment)
    # 换行直接连接（定宽排版断行），空格保留为分隔符
    text = segment.replace("\r", "").replace("\n", "")

    components: list[FormulaComponent] = []
    pos = 0
    coverage_hits, coverage_total = 0, 0

    for m in _HERB_ANNOT_RE.finditer(text):
        herb, annot = m.group(1), m.group(2)
        # 注释通道同样过滤注释/附方/主治模式（医方集解的「名异功散（…）」等）
        if herb in _STOP_TOKENS or _STOP_TOKEN_RE.match(herb) or herb.startswith("治"):
            pos = m.end()
            continue
        # 两个带注释药材之间的无注释药材串
        components.extend(_parse_gap(text[pos : m.start()], lexicon))
        coverage_total += 1
        if herb in lexicon:
            coverage_hits += 1
        dosage = _extract_dosage(annot)
        if re.search(rf"各{_NUM}(?:{_UNITS})", annot):
            # 「各X」组剂量：回填此前无剂量的药材
            for c in components:
                if not c.dosage:
                    c.dosage = dosage
        components.append(FormulaComponent(herb, dosage))
        pos = m.end()

    # 尾部无注释药材串
    components.extend(_parse_gap(text[pos:], lexicon))

    # 过滤 + 去重（保序）
    seen: set[str] = set()
    deduped: list[FormulaComponent] = []
    for c in components:
        if not c.herb or c.herb in _STOP_TOKENS or c.herb in seen:
            continue
        seen.add(c.herb)
        deduped.append(c)

    coverage = coverage_hits / coverage_total if coverage_total else 0.0
    return ParsedComposition(deduped, coverage)


def _parse_gap(gap: str, lexicon: set[str]) -> list[FormulaComponent]:
    """解析无括号注释的药材串（空格分隔），词表匹配的才收。"""
    out: list[FormulaComponent] = []
    for token in gap.split(" "):
        token = token.strip()
        if not token or not _CJK_RE.match(token) or token in _STOP_TOKENS:
            continue
        if _STOP_TOKEN_RE.match(token):
            continue
        if token in lexicon:
            out.append(FormulaComponent(token, ""))
    return out


def find_prep_boundary(body: str) -> int | None:
    """在正文中定位制法句（组成段结束处），返回字符索引；无则 None。"""
    m = _PREP_COUNT_RE.search(body)
    if m:
        return m.start()
    # 医方集解式经义分析「此X经药也」也是组成结束标记
    m2 = re.search(r"此[一-龥]{0,12}药也", body)
    if m2:
        return m2.start()
    for marker in _PREP_MARKERS:
        idx = body.find(marker)
        if idx >= 0:
            return idx
    return None
