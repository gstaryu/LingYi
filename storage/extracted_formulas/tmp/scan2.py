# -*- coding: utf-8 -*-
import json, re
from collections import Counter

BASE = r"D:\PycharmProjects\LingYi\storage\extracted_formulas"
data = json.load(open(BASE + r"\qianjin.json", encoding="utf-8"))
out = open(BASE + r"\tmp\scan2.txt", "w", encoding="utf-8")
def p(*a):
    print(*a, file=out)

# All names ending in 第X or containing 论/法/诀 as whole
susp_names = [(i, d["name"], d["section"], len(d["composition"])) for i, d in enumerate(data)
              if re.search(r"第[一二三四五六七八九十]+$", d["name"]) or re.search(r"(论|诀|法)$", d["name"])]
p("names ending 第X/论/诀/法:")
for r in susp_names:
    p("  ", r)

# specific suspicious
for i, d in enumerate(data):
    if d["name"] in ("治中结阳丸", "治丸方", "木药上部", "论合和第七", "五脏六腑变化旁通诀第四"):
        p("---", i, d["name"], d["section"])
        p("  indication:", d["indication"][:120])
        p("  comp:", [(c["herb"], c["dosage"]) for c in d["composition"]][:15])
        p("  excerpt:", d["source_excerpt"][:200])
        p("  flags:", d["flags"], "coverage", d["coverage"])

# records whose herbs contain prose fragments
prose = []
for i, d in enumerate(data):
    for c in d["composition"]:
        h = c["herb"].strip()
        if len(h) >= 4 and re.search(r"(其|而|宜|纳|敷|服|为使|之|以)", h):
            prose.append((i, d["name"], h, d["flags"]))
            break
p("\nprose-like herb fields:", len(prose))
for r in prose[:40]:
    p("  ", r)

# weak indication breakdown
wi = [(d["name"], d["indication"], d["section"]) for d in data if len(d["indication"].strip()) < 8]
empty = [x for x in wi if not x[1].strip()]
short = [x for x in wi if x[1].strip()]
p("\nweak indication: empty", len(empty), "short", len(short))
for r in short[:15]:
    p("  short:", r)

# names that end with 汤方/丸方/散方/膏方 (double suffix '方' after dosage form)
doub = [d["name"] for d in data if re.search(r"(汤|丸|散|膏)方$", d["name"])]
p("\n'X汤方' style names count:", len(doub), doub[:20])

# coverage distribution
cov = Counter(round(d["coverage"], 1) for d in data)
p("\ncoverage dist:", sorted(cov.items()))
lowcov = [d["name"] for d in data if d["coverage"] < 0.5]
p("coverage<0.5 count:", len(lowcov), lowcov[:15])

# name char check: names containing non-CJK punctuation
badnm = [d["name"] for d in data if re.search(r"[，。、；：（）0-9a-zA-Z]", d["name"])]
p("\nnames w/ punctuation:", badnm[:20])

# dosage text containing trailing junk
dj = []
for d in data:
    for c in d["composition"]:
        g = c["dosage"].strip()
        if len(g) > 10:
            dj.append((d["name"], c["herb"], g))
p("\nlong dosage:", len(dj), dj[:15])
out.close()
print("done")
