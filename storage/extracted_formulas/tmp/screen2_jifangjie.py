# -*- coding: utf-8 -*-
"""Refined screening: separate annotation-leak from real herbs."""
import json, re, sys, io, random
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE = r"D:\PycharmProjects\LingYi\storage\extracted_formulas"
data = json.load(open(BASE + r"\jifangjie.json", encoding="utf-8"))

# clear annotation-leak patterns: 加减法、方论、煎法 leaked as herbs
ANNOT = re.compile(r"^(加|去|并|为|此|用|不|或|若|减|宜|各|等|无|治|主|证|凡|其一|其二)")
REAL_HERB_WHITELIST = {"五味子","百合","三棱","百草霜","白术","五灵脂","巴戟天"}  # start with 加/去/为/不/用? none except; 三棱 fine
# herbs that legitimately start with those chars
LEGIT = {"五味子","三棱","百草霜","百合","巴戟天","五味","木通","五香","为末"}

def is_annotation(h):
    if ANNOT.match(h) and h not in REAL_HERB_WHITELIST:
        return True
    # herb names with verb phrases / sentence text
    if re.search(r"(煎|汤主之|药也|用之|宜增|润剂|通关|孕育|截之|姜煎|不同|一倍|汤$)", h) and h not in {"四物汤","二陈汤"}:
        return True
    return False

leaks = {}       # name -> leaked herbs
ind_issues = {}  # name -> indication problem
dup = {}
for it in data:
    n = it["name"]
    dup.setdefault(n, 0)
    dup[n] += 1
    bad = [c["herb"] for c in it.get("composition", []) if is_annotation(c["herb"])]
    if bad:
        leaks[n] = bad
    ind = (it.get("indication") or "").strip()
    if not ind:
        ind_issues[n] = "empty"
    elif len(ind) < 8:
        ind_issues[n] = f"short({len(ind)})"

print("== duplicate names ==")
print({k: v for k, v in dup.items() if v > 1})
print("\n== annotation leak in composition (%d formulas) ==" % len(leaks))
for k, v in leaks.items():
    print(" -", k, "->", v)
print("\n== indication issues (%d) ==" % len(ind_issues))
for k, v in ind_issues.items():
    print(" -", k, v)

# flags
flagged = [it for it in data if it.get("flags")]
clean = [it for it in data if not it.get("flags")]
print("\nflagged:", len(flagged), " clean:", len(clean))

# comp size distribution
import collections
sizes = collections.Counter(len(it.get("composition", [])) for it in data)
print("comp size dist:", dict(sorted(sizes.items())))
dos_empty = [it["name"] for it in data if it["composition"] and all(not c.get("dosage","").strip() for c in it["composition"])]
print("dosage_all_empty count:", len(dos_empty))
print("dosage_all_empty sample:", dos_empty[:15])

# coverage distribution
covs = [it.get("coverage", 0) for it in data]
print("coverage min/median/max:", min(covs), sorted(covs)[len(covs)//2], max(covs))

random.seed(42)
sample_clean = random.sample([it["name"] for it in clean], 20)
sample_flag = [it["name"] for it in flagged][:20] if len(flagged) >= 20 else [it["name"] for it in flagged]
print("\nSAMPLE_FLAG (first 20 of 37):", sample_flag)
print("\nSAMPLE_CLEAN (random 20):", sample_clean)
