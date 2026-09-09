# -*- coding: utf-8 -*-
"""规则筛查 jufang.json —— 古籍方剂提取质量校验"""
import json, re, sys
from collections import Counter

SRC = r"D:\PycharmProjects\LingYi\storage\extracted_formulas\jufang.json"
data = json.load(open(SRC, encoding="utf-8"))

# 疑似非药名的动词/残片特征
HERB_BAD_CHARS = re.compile(r"[0-9０-９一二三四五六七八九十百千两〇]+")
HERB_BAD_WORDS = [
    "主治", "疗之", "并治", "皆治", "服之", "每服", "空心", "食前", "温服", "为末",
    "煎汤", "水煎服", "右为", "右件", "修制", "用法", "同研", "上件", "不论",
    "冷热", "宣男", "汤使", "浸洗", "酒下", "汤下", "以下", "以上诸疾",
    "半升", "如皂", "绢袋", "一本作", "熬成膏", "不可", "主治", "若非",
]
# 名字可疑后缀：丸散膏丹汤饮/丹油锭露之外
NAME_BAD_SUFFIX = ("论", "序", "法", "说", "记", "注", "辨", "考", "卷", "目录", "附", "方论")

results = {}
drop = []
def flag(r, reason):
    drop.append({"name": r.get("name", "<空>"), "reason": reason})

stats = Counter()
for i, r in enumerate(data):
    name = (r.get("name") or "").strip()
    comp = r.get("composition") or []
    dosages = [c.get("dosage") or "" for c in comp]
    herbs = [c.get("herb") or "" for c in comp]
    ind = (r.get("indication") or "").strip()
    reasons = []

    if len(name) < 2:
        reasons.append("name少于2字")
        stats["name_short"] += 1
    else:
        core = name
        # 去掉常见剂型后缀后再查
        stripped = re.sub(r"[丸散膏丹汤饮油锭露丹砂圆丹]+$", "", core)
        if any(stripped.endswith(s) for s in NAME_BAD_SUFFIX) or core.endswith(NAME_BAD_SUFFIX):
            reasons.append(f"name可疑后缀: {name}")
            stats["name_suffix"] += 1
    if any(name.endswith(s) for s in ("论", "序", "法", "序")):
        pass  # already covered above

    if len(comp) < 2:
        reasons.append(f"composition仅{len(comp)}味")
        stats["comp_lt2"] += 1
    elif len(comp) > 40:
        reasons.append(f"composition多至{len(comp)}味")
        stats["comp_gt40"] += 1
    if dosages and all(d.strip() == "" for d in dosages):
        reasons.append("dosage全空")
        stats["dosage_empty"] += 1
    if not ind:
        reasons.append("indication为空")
        stats["ind_empty"] += 1
    elif len(ind) < 8:
        reasons.append(f"indication过短({len(ind)}字): {ind}")
        stats["ind_short"] += 1

    bad_herbs = []
    for h in herbs:
        hs = h.strip()
        if not hs:
            bad_herbs.append(hs); continue
        bad = False
        if HERB_BAD_CHARS.fullmatch(hs):  # 纯数字
            bad = True
        elif HERB_BAD_CHARS.search(hs) and len(hs) >= 4 and any(w in hs for w in ("(", "（", "、", "各")):
            bad = True
        for w in HERB_BAD_WORDS:
            if w in hs:
                bad = True
                break
        # 动词特征
        if re.search(r"(治|疗|主|服|下|煎|煮|入|用|为|和|研|细|切|炒|炙)(之|焉|也)$", hs):
            bad = True
        if bad:
            bad_herbs.append(hs)
    if bad_herbs:
        reasons.append("可疑药名: " + " | ".join(bad_herbs[:5]))
        stats["herb_suspicious"] += 1

    if reasons:
        r["_issues"] = reasons
        for _ in reasons:
            flag(r, None) if False else None

out = []
for i, r in enumerate(data):
    if "_issues" in r:
        out.append({"index": i, "name": r["name"], "section": r.get("section"), "issues": r["_issues"], "flags": r.get("flags"), "coverage": r.get("coverage")})

print("total:", len(data))
print("rule-hit records:", len(out))
print(stats)
json.dump(out, open(r"D:\PycharmProjects\LingYi\storage\extracted_formulas\tmp\rule_hits.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
