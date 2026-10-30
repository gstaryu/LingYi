"""
过敏原安全校验 —— 患者过敏史 vs 处方药材 / 食疗建议。

设计原则:
- 纯 Python 规则表，不依赖 LLM 或外部服务；与 SafetyEngine（十八反十九畏）并列
- 只拦「映射表里明确写了」的组合；表外过敏原一律放行并记日志，不假装覆盖
- 过敏匹配按「整词/别名」比对药材名，绝不拿过敏原词去做子串匹配
  （否则「花粉」会命中「天花粉」，「虾」会命中无关药名）
- 食物类过敏原额外扫描回答中的食疗建议，命中则追加确定性提示，不阻断回答

维护约定:
- 表内只收公认的交叉反应（水产/蜂/昆虫/坚果/乳制品/小麦/酒精）与常见药名别名
- 未收录的过敏原不必强行补全：未知词会退化为「整词比对药材名」，仍能拦住同名药材
"""

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# 视为「无过敏」的占位值（大小写/空白已归一）
_EMPTY_ALLERGY_VALUES = {"", "无", "未知", "暂无", "none"}

# 过敏原字符串分隔符：中英文顿号、逗号、分号、斜杠、竖线
_SPLIT_PATTERN = re.compile(r"[、,，;；/|]+")

# 口语连接词（"对海鲜和青霉素过敏"），仅在剥离前缀后拆分
_CONJ_PATTERN = re.compile(r"[和与]")

# 口语前缀（"对白芷过敏" -> "白芷"）
_PREFIX_PATTERN = re.compile(r"^(?:对于|对)")

# LLM / 用户常附加的冗余后缀
_SUFFIX_PATTERN = re.compile(r"(及相关制品|及制品|相关制品|类药物|过敏)+$")

# 食疗扫描的否定语境（"不要用蜂蜜送服""避免虾蟹"不应判为推荐）
_NEGATION_PATTERN = re.compile(
    r"(不含|不包含|不用|不要用|不可用|不使用|不宜|避免|避开|忌|禁|勿|别|"
    r"已剔除|已去|去掉|删除|无需)[^。！？；\n]{0,10}$"
)


@dataclass(frozen=True)
class AllergenRule:
    """单条过敏原规则。

    type:  drug（药物）/ food（食物）/ other（环境等无关物）
    mode:  exact（同名）/ alias（俗名→正名）/ class（同类同源）/ none（已收录但无对应药材）
    targets: 处方中需要拦截的药材名（按「target in 药材名」匹配，可覆盖炮制品）
    diet_words: 食疗建议中需要提示的食物词（仅 food 类使用）
    """

    type: str
    mode: str
    targets: tuple[str, ...] = ()
    diet_words: tuple[str, ...] = ()
    note: str = ""


# 海洋来源药材：甲壳类/贝类/藻类过敏都可能涉及
_MARINE_HERBS = (
    "海藻", "昆布", "牡蛎", "海螵蛸", "石决明", "珍珠母",
    "瓦楞子", "蛤壳", "海马", "海龙",
)
_SHELL_HERBS = ("牡蛎", "海螵蛸", "石决明", "珍珠母", "瓦楞子", "蛤壳")
_HONEY_HERBS = ("蜂蜜", "蜂王浆", "蜂胶", "蜂房", "露蜂房")

ALLERGEN_MAP: dict[str, AllergenRule] = {
    # ==================== 药物类：明确无对应中药成分 ====================
    "青霉素": AllergenRule("drug", "none", note="抗生素，方剂中无对应成分"),
    "盘尼西林": AllergenRule("drug", "none", note="青霉素别名"),
    "头孢": AllergenRule("drug", "none", note="头孢类抗生素，方剂中无对应成分"),
    "头孢菌素": AllergenRule("drug", "none", note="头孢别名"),
    "先锋霉素": AllergenRule("drug", "none", note="头孢别名"),
    "磺胺": AllergenRule("drug", "none", note="磺胺类抗菌药，方剂中无对应成分"),
    "阿司匹林": AllergenRule("drug", "none", note="解热镇痛药，方剂中无对应成分"),
    "布洛芬": AllergenRule("drug", "none", note="解热镇痛药，方剂中无对应成分"),
    "碘": AllergenRule("drug", "none", note="含碘造影剂过敏不等同于海藻类过敏"),
    "造影剂": AllergenRule("drug", "none"),
    # ==================== 药物类：俗名 → 正名（别名映射） ====================
    "元参": AllergenRule("drug", "alias", ("玄参", "元参")),
    "元胡": AllergenRule("drug", "alias", ("延胡索", "元胡")),
    "延胡": AllergenRule("drug", "alias", ("延胡索", "元胡")),
    "淮山": AllergenRule("drug", "alias", ("山药", "淮山")),
    "怀山药": AllergenRule("drug", "alias", ("山药", "淮山")),
    "薏米": AllergenRule("drug", "alias", ("薏苡仁", "薏米")),
    "苡仁": AllergenRule("drug", "alias", ("薏苡仁", "薏米")),
    "银花": AllergenRule("drug", "alias", ("金银花", "银花", "双花")),
    "双花": AllergenRule("drug", "alias", ("金银花", "银花", "双花")),
    "二花": AllergenRule("drug", "alias", ("金银花", "银花", "双花")),
    "生地": AllergenRule("drug", "alias", ("生地黄", "地黄", "生地")),
    "熟地": AllergenRule("drug", "alias", ("熟地黄", "地黄", "熟地")),
    "川军": AllergenRule("drug", "alias", ("大黄", "川军")),
    "国老": AllergenRule("drug", "alias", ("甘草", "国老")),
    "山萸肉": AllergenRule("drug", "alias", ("山茱萸", "山萸肉")),
    # ==================== 食物类：同类同源拦截 ====================
    "海鲜": AllergenRule(
        "food", "class", _MARINE_HERBS,
        ("虾", "蟹", "贝", "蛤", "蚝", "牡蛎", "扇贝", "鱿鱼", "章鱼",
         "海参", "海胆", "鲍鱼", "海带", "紫菜", "鱼汤", "鱼类"),
        note="水产类交叉反应",
    ),
    "海产品": AllergenRule(
        "food", "class", _MARINE_HERBS,
        ("虾", "蟹", "贝", "蛤", "蚝", "牡蛎", "扇贝", "鱿鱼", "章鱼",
         "海参", "海胆", "鲍鱼", "海带", "紫菜", "鱼汤", "鱼类"),
    ),
    "水产": AllergenRule(
        "food", "class", _MARINE_HERBS,
        ("虾", "蟹", "贝", "蛤", "蚝", "牡蛎", "扇贝", "鱿鱼", "章鱼",
         "海参", "海胆", "鲍鱼", "海带", "紫菜", "鱼汤", "鱼类"),
    ),
    "虾": AllergenRule("food", "class", _MARINE_HERBS, ("虾",)),
    "蟹": AllergenRule("food", "class", _MARINE_HERBS, ("蟹",)),
    "贝类": AllergenRule("food", "class", _SHELL_HERBS, ("贝", "蛤", "蚝", "扇贝", "牡蛎")),
    "贝壳类": AllergenRule("food", "class", _SHELL_HERBS, ("贝", "蛤", "蚝", "扇贝", "牡蛎")),
    "蜂产品": AllergenRule(
        "food", "class", _HONEY_HERBS, ("蜂蜜", "蜂王浆", "蜂胶"), note="蜂产品交叉反应"
    ),
    "蜂蜜": AllergenRule("food", "class", _HONEY_HERBS, ("蜂蜜", "蜂王浆", "蜂胶")),
    "昆虫": AllergenRule(
        "food", "class",
        ("蝉蜕", "僵蚕", "全蝎", "蜈蚣", "土鳖虫", "斑蝥", "九香虫"),
        note="虫类药交叉反应",
    ),
    "虫类": AllergenRule(
        "food", "class",
        ("蝉蜕", "僵蚕", "全蝎", "蜈蚣", "土鳖虫", "斑蝥", "九香虫"),
        note="虫类药交叉反应",
    ),
    "坚果": AllergenRule(
        "food", "class", ("杏仁",),
        ("花生", "核桃", "腰果", "杏仁", "开心果", "榛子", "松子"),
    ),
    "花生": AllergenRule("food", "none", diet_words=("花生",), note="方剂中无对应药材"),
    "牛奶": AllergenRule(
        "food", "none", diet_words=("牛奶", "酸奶", "奶酪", "奶油", "黄油"),
        note="阿胶为驴皮制品，不属乳制品",
    ),
    "乳制品": AllergenRule(
        "food", "none", diet_words=("牛奶", "酸奶", "奶酪", "奶油", "黄油"),
    ),
    "鸡蛋": AllergenRule("food", "none", diet_words=("鸡蛋", "蛋清", "蛋黄")),
    "小麦": AllergenRule(
        "food", "class", ("浮小麦",),
        ("小麦", "面粉", "面条", "馒头", "面包", "饺子"),
    ),
    "麸质": AllergenRule(
        "food", "class", ("浮小麦",),
        ("小麦", "面粉", "面条", "馒头", "面包", "饺子"),
    ),
    "大豆": AllergenRule("food", "none", diet_words=("大豆", "黄豆", "豆浆", "豆腐")),
    "芒果": AllergenRule("food", "none", diet_words=("芒果",)),
    "酒精": AllergenRule(
        "food", "class", ("酒",),
        ("酒", "黄酒", "米酒", "啤酒", "红酒", "料酒"),
        note="酒制饮片",
    ),
    "乙醇": AllergenRule("food", "class", ("酒",), ("酒", "黄酒", "米酒", "啤酒", "红酒")),
    # ==================== 其他：不可能出现在方剂中 ====================
    "花粉": AllergenRule("other", "none", note="环境吸入性过敏原"),
    "尘螨": AllergenRule("other", "none"),
    "宠物毛": AllergenRule("other", "none"),
    "霉菌": AllergenRule("other", "none"),
}


def normalize_allergen_term(term: str) -> str:
    """规范化过敏原名称：去空白与 LLM 常附加的冗余后缀。

    例: "白芷过敏" -> "白芷", "党参及相关制品" -> "党参"。
    """
    s = (term or "").strip()
    previous = None
    while s and s != previous:
        previous = s
        s = _SUFFIX_PATTERN.sub("", s).strip()
    s = _PREFIX_PATTERN.sub("", s).strip()
    return s


def parse_allergy_terms(allergy_text: str) -> list[str]:
    """把过敏史字符串解析为规范化、去重的过敏原列表。"""
    raw = (allergy_text or "").strip()
    if not raw or raw.lower() in _EMPTY_ALLERGY_VALUES:
        return []

    terms: list[str] = []
    seen: set[str] = set()
    for part in _SPLIT_PATTERN.split(raw):
        for sub in _CONJ_PATTERN.split(part):
            term = normalize_allergen_term(sub)
            if not term or term.lower() in _EMPTY_ALLERGY_VALUES:
                continue
            if term in seen:
                continue
            seen.add(term)
            terms.append(term)
    return terms


def _match_rule_herbs(rule: AllergenRule, herbs: list[str]) -> str | None:
    """返回第一味与规则目标命中的药材名（target in 药材名，覆盖炮制品）。"""
    for herb in herbs:
        if any(target in herb for target in rule.targets):
            return herb
    return None


def _match_unknown_term(term: str, herbs: list[str]) -> str | None:
    """表外过敏原：仅做整词比对（长度≥2 且为中文），避免单字误伤。"""
    if len(term) < 2 or not re.fullmatch(r"[一-鿿]+", term):
        return None
    for herb in herbs:
        if term in herb:
            return herb
    return None


def check_allergies(herb_list: list[str], allergy_text: str) -> tuple[bool, str | None]:
    """
    校验处方是否包含患者过敏原（含别名/同类同源/同名药材）。

    Args:
        herb_list: 处方药材名列表
        allergy_text: 患者过敏史原文（如 "青霉素、海鲜"）

    Returns:
        (is_safe, error_msg)；表外过敏原不拦截，仅记日志。
    """
    terms = parse_allergy_terms(allergy_text)
    if not terms or not herb_list:
        return True, None

    conflicts: list[str] = []
    unmatched: list[str] = []

    for term in terms:
        rule = ALLERGEN_MAP.get(term)

        if rule is None:
            herb = _match_unknown_term(term, herb_list)
            if herb:
                conflicts.append(f"【过敏原】患者对「{term}」过敏，处方含「{herb}」")
            else:
                unmatched.append(term)
            continue

        if rule.mode == "none":
            continue

        herb = _match_rule_herbs(rule, herb_list)
        if herb:
            if rule.mode == "class":
                reason = rule.note or "同类同源"
                conflicts.append(
                    f"【过敏原】患者对「{term}」过敏（{reason}），处方含「{herb}」"
                )
            else:
                conflicts.append(f"【过敏原】患者对「{term}」过敏，处方含「{herb}」")

    if unmatched:
        logger.info(
            "过敏原未收录或未命中药材，已放行并依赖模型规避: %s", "、".join(unmatched)
        )

    if conflicts:
        error_msg = "；".join(conflicts)
        logger.warning("处方过敏原校验失败: %s", error_msg)
        return False, error_msg

    return True, None


def _diet_hit(answer: str, word: str) -> bool:
    """回答中是否「推荐」了某食物词。

    以下语境不算推荐：同句出现否定词（避免/不要用/不含），
    或紧邻位置出现"过敏"（如"因您对小麦过敏""含小麦淀粉的过敏原"）。
    """
    for match in re.finditer(re.escape(word), answer):
        window = answer[max(0, match.start() - 6) : match.end() + 8]
        if "过敏" in window:
            continue
        clause_start = max(answer.rfind(ch, 0, match.start()) for ch in "。！？；\n") + 1
        clause = answer[clause_start : match.start()]
        if _NEGATION_PATTERN.search(clause[-15:]):
            continue
        return True
    return False


def dietary_caution(answer: str, allergy_text: str) -> str | None:
    """
    扫描回答中的食疗建议是否提及患者食物过敏原。

    只对映射表中 type=food 的过敏原生效；命中返回追加提示（不含换行），否则 None。
    否定语境（"不要用蜂蜜送服""避免虾蟹"）不计为推荐。
    """
    if not answer:
        return None
    terms = parse_allergy_terms(allergy_text)
    if not terms:
        return None

    hits: list[tuple[str, str]] = []
    for term in terms:
        rule = ALLERGEN_MAP.get(term)
        if rule is None or rule.type != "food":
            continue
        word = next((w for w in rule.diet_words if _diet_hit(answer, w)), None)
        if word:
            hits.append((term, word))

    if not hits:
        return None

    parts = [f"「{term}」（提及{word}）" for term, word in hits]
    return (
        "> ⚠️ 过敏提示：您报告对"
        + "、".join(parts)
        + "过敏，以上回答中的食疗建议请避开相关食物；具体饮食请遵医嘱。"
    )
