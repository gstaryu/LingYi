"""
四部古籍方剂条目提取器。

四本书同为中医世家 <目录>/<篇名> 标签格式，但正文排版各异，分书解析:

- 局方（太平惠民和剂局方）: 条目级，组成 = 病症文后的药材串（括号注炮制/剂量）
- 千金要方（备急千金要方）: 条目级，「治…方。」起首，组成后接「上X味 咀…」制法
- 外台秘要: 聚合条目（一篇含数十方），需按「…X方。药材（剂量）…上X味」内嵌模式切分
- 医方集解: 条目级，「属性：（出处）主治。药材（炮制。剂量）… 此X经药也。」

产出 RawFormula（含确定性 flags），供后续 Agent 校验与入库。
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from lingyi.knowledge.models import FormulaComponent

from data_pipeline.formula_extract.clean import clean_ocr, strip_markup
from data_pipeline.formula_extract.compose import (
    _HERB_ANNOT_RE,
    _PREP_COUNT_RE,
    find_prep_boundary,
    parse_composition,
)

logger = logging.getLogger(__name__)

# ============ 书目配置 ============

BOOKS: dict[str, dict[str, str]] = {
    "qianjin": {"file": "F-009-备急千金要方.txt", "source": "备急千金要方", "category": "千金方"},
    "waitai": {"file": "F-011-外台秘要.txt", "source": "外台秘要", "category": "外台秘要"},
    "jufang": {"file": "F-025-太平惠民和剂局方.txt", "source": "太平惠民和剂局方", "category": "局方"},
    "jifangjie": {"file": "F-091-医方集解.txt", "source": "医方集解", "category": "医方集解"},
}

_SRC_DIR = Path(__file__).resolve().parent.parent.parent / "storage" / "classics_src"

# 非方剂条目名（序/论/目录等）
_NON_FORMULA_NAME_RE = re.compile(
    r"(序|记|跋|凡例|目录|进表|论$|法$|考$|辨$|说$|答$|赋$|歌$)$"
)
# 医方集解「此X经药也」经义分析标记


# 治/疗/主之 起首的指示句（优先作为 indication）
_INDICATION_SENT_RE = re.compile(r"((?:治|疗|主)[^。；]{6,150}。)")
# 中文数字（「上X味」计数核对用）
_CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8,
           "九": 9, "十": 10, "廿": 20, "卅": 30}


def _cn_to_int(s: str) -> int:
    """中文数字 → int（支持 1-99 的常见写法）。"""
    s = s.strip()
    if s.isdigit():
        return int(s)
    if not s:
        return 0
    # 十X / X十 / X十Y / 十
    if "十" in s:
        parts = s.split("十")
        tens = _CN_NUM.get(parts[0], 1) if parts[0] else 1
        ones = _CN_NUM.get(parts[1], 0) if len(parts) > 1 and parts[1] else 0
        return tens * 10 + ones
    return _CN_NUM.get(s, 0)


def _stated_herb_count(body: str) -> int | None:
    """从正文提取「上X味」声明的药味数；无则 None。"""
    m = re.search(r"[上右]([一二三四五六七八九十廿卅\d]+)味", body)
    return _cn_to_int(m.group(1)) if m else None


def _clean_indication(text: str) -> str:
    """取指示句（治/疗/主之 起首优先），否则取最后一句；限 150 字。"""
    text = re.sub(r"\s+", "", text)
    m = _INDICATION_SENT_RE.search(text)
    if m:
        return m.group(1)
    sentences = [s for s in text.split("。") if len(s.strip()) >= 6]
    return (sentences[-1] + "。") if sentences else ""


@dataclass
class RawFormula:
    """解析产出的候选方剂。"""

    name: str
    source: str
    category: str
    section: str = ""
    indication: str = ""
    components: list[FormulaComponent] = field(default_factory=list)
    coverage: float = 0.0
    source_excerpt: str = ""  # 组成原文片段（供 Agent 校验）
    flags: list[str] = field(default_factory=list)


def _iter_entries(text: str):
    """按 <目录> 切分，产出 (section, name, body)。"""
    for chunk in re.split(r"<目录>", text)[1:]:
        m = re.search(r"<篇名>([^\n]+)\n?", chunk)
        if not m:
            continue
        name = m.group(1).strip()
        body = strip_markup(chunk[m.end() :])
        section_m = re.match(r"([^\n]+)", chunk)
        section = section_m.group(1).strip() if section_m else ""
        yield section, name, body


def _composition_bounds(body: str, lexicon: set[str]) -> tuple[int, int] | None:
    """
    定位条目级正文的组成段 [start, end)。

    start = 第一个「药材（注释）」匹配，再向前回溯词表药材（修复组成行首药味丢失）；
    end = 制法句边界。
    """
    annot_m = _HERB_ANNOT_RE.search(body)
    if not annot_m:
        return None
    start = annot_m.start()
    # 向前回溯：行首无注释的裸药名串（词表命中）也属于组成
    pos = start
    while pos > 0:
        prev_chunk = body[:pos]
        # 取前一段以空白结尾的 token
        tokens = re.findall(r"([一-龥·]{1,6})[\s]+$", prev_chunk)
        if not tokens:
            break
        token = tokens[0]
        if token in lexicon:
            start = prev_chunk.rfind(token)
            pos = start
        else:
            break
    end_rel = find_prep_boundary(body[annot_m.end() :])
    end = annot_m.end() + end_rel if end_rel is not None else len(body)
    return start, end


def _extract_entry_level(
    entries, book_key: str, lexicon: set[str]
) -> list[RawFormula]:
    """局方/千金/医方集解共用的条目级提取。"""
    cfg = BOOKS[book_key]
    out: list[RawFormula] = []
    for section, name, raw_body in entries:
        name = clean_ocr(name).strip()
        if not name or _NON_FORMULA_NAME_RE.search(name) or len(name) > 20:
            continue
        body = clean_ocr(raw_body)
        bounds = _composition_bounds(body, lexicon)
        if bounds is None:
            continue
        start, end = bounds
        comp_segment = body[start:end]
        indication = _clean_indication(body[:start])

        parsed = parse_composition(comp_segment, lexicon)
        if len(parsed.components) < 2:
            continue
        # 至少一个剂量，否则多半是医论/药材名录（局方常见「各X两」尾部集中，放行）
        if not any(c.dosage for c in parsed.components) and book_key != "jufang":
            continue
        # OCR 严重破损（词表覆盖率过低）的直接丢弃
        if parsed.coverage < 0.4 and len(parsed.components) < 5:
            continue

        rf = RawFormula(
            name=name,
            source=cfg["source"],
            category=cfg["category"],
            section=section,
            indication=indication,
            components=parsed.components,
            coverage=parsed.coverage,
            source_excerpt=re.sub(r"\s+", "", comp_segment)[:200],
        )
        if parsed.coverage < 0.5:
            rf.flags.append("low_coverage")
        if not any(c.dosage for c in parsed.components):
            rf.flags.append("no_dosage")
        if len(rf.indication) < 6:
            rf.flags.append("weak_indication")
        # 「上X味」计数核对：解析出的药味数明显少于原文计数 → 疑似漏药
        stated = _stated_herb_count(body)
        if stated and len(parsed.components) + 1 < stated:
            rf.flags.append(f"herb_count_mismatch:{len(parsed.components)}/{stated}")
        out.append(rf)
    return out


# 外台内嵌方名句: 「X方。」X 以剂型后缀结尾
_WAITAI_NAME_RE = re.compile(
    r"(?:。|^|又)((?:宜|与|服|用|可)?[一-龥]{1,12}?(?:汤|丸|散|膏|丹|饮|煎|圆|油|酒|粉|霜|蜜))方[。：:]"
)
# 外台指示文首部的引书前缀
_WAITAI_SRC_PREFIX_RE = re.compile(
    r"^\s*(?:又|深师|仲景|崔氏|肘后|千金|古今录验|救急|集验|范汪|删繁|小品|延年|必效|张文仲|陶氏|广济|许仁则|近效|备急)"
)


def _extract_waitai(text: str, lexicon: set[str]) -> list[RawFormula]:
    """
    外台秘要: 聚合条目内嵌方切分。

    对每个「上X味」标记回溯最近的「X方。」句取方名，其间为组成段。
    """
    cfg = BOOKS["waitai"]
    out: list[RawFormula] = []
    for section, _gname, body in _iter_entries(text):
        body = clean_ocr(body)
        for marker in _PREP_COUNT_RE.finditer(body):
            m_end = marker.start()
            window_start = max(0, m_end - 600)
            window = body[window_start:m_end]
            name_matches = list(_WAITAI_NAME_RE.finditer(window))
            if not name_matches:
                continue
            nm = name_matches[-1]
            name = re.sub(r"^(?:宜|与|服|用|可)", "", nm.group(1))
            comp_segment = window[nm.end() :]
            if len(comp_segment) > 300:
                comp_segment = comp_segment[-300:]
            parsed = parse_composition(comp_segment, lexicon)
            if len(parsed.components) < 2:
                continue
            if not any(c.dosage for c in parsed.components):
                continue
            # 指示文 = 方名句之前最近的 1-2 句
            pre = body[: window_start + nm.start()]
            sentences = [s for s in pre.split("。") if s.strip()]
            indication = "".join(sentences[-2:])[-150:] if sentences else ""
            indication = _WAITAI_SRC_PREFIX_RE.sub("", indication)
            indication = _clean_indication(indication) if indication else ""

            rf = RawFormula(
                name=name,
                source=cfg["source"],
                category=cfg["category"],
                section=section,
                indication=indication,
                components=parsed.components,
                coverage=parsed.coverage,
                source_excerpt=re.sub(r"\s+", "", comp_segment)[:200],
            )
            if parsed.coverage < 0.5:
                rf.flags.append("low_coverage")
            if len(rf.indication) < 6:
                rf.flags.append("weak_indication")
            out.append(rf)
    return out


def extract_book(book_key: str, lexicon: set[str], src_dir: Path = _SRC_DIR) -> list[RawFormula]:
    """
    提取指定书的候选方剂。

    Args:
        book_key: BOOKS 键（qianjin/waitai/jufang/jifangjie）
        lexicon: 药材词表
        src_dir: 古籍 txt 目录
    """
    if book_key not in BOOKS:
        raise ValueError(f"未知书目: {book_key}")
    path = src_dir / BOOKS[book_key]["file"]
    text = path.read_text(encoding="utf-8")

    if book_key == "waitai":
        formulas = _extract_waitai(text, lexicon)
    else:
        formulas = _extract_entry_level(_iter_entries(text), book_key, lexicon)

    # 书内去重（保首现；跨书去重在 run_extract 按朝代优先级合并）
    seen: set[str] = set()
    deduped: list[RawFormula] = []
    for f in formulas:
        if f.name in seen:
            continue
        seen.add(f.name)
        deduped.append(f)

    logger.info("%s: 提取 %d 首候选方剂", BOOKS[book_key]["source"], len(deduped))
    return deduped
