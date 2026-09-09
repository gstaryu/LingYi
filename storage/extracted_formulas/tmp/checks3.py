# -*- coding: utf-8 -*-
import json, re
from collections import Counter

BASE = r"D:\PycharmProjects\LingYi\storage\extracted_formulas"
SRC = r"D:\PycharmProjects\LingYi\storage\classics_src\F-009-备急千金要方.txt"
data = json.load(open(BASE + r"\qianjin.json", encoding="utf-8"))
raw = open(SRC, encoding="utf-8").read()
rawn = re.sub(r"\s+", "", raw)
out = open(BASE + r"\tmp\qj_checks3.txt", "w", encoding="utf-8")
def p(*a): print(*a, file=out)

# 1. dosage pollution scan
pol = []
for i, d in enumerate(data):
    for c in d["composition"]:
        g = c["dosage"].strip()
        if re.search(r"(为使|恶|畏|反|一作|作|即|使)", g) and len(g) > 6:
            pol.append((i, d["name"], c["herb"], g))
p("dosage prose pollution:", len(pol), pol[:15])

# 2. check reverse cases: ext > src
for idx in (13, 28, 8):
    d = data[idx]
    ex = re.sub(r"\s+", "", d["source_excerpt"])
    pos = rawn.find(ex)
    p("\n###", idx, d["name"], "pos", pos)
    if pos >= 0:
        p("   src:", rawn[pos:pos+400])
    p("   ext:", [(c["herb"], c["dosage"]) for c in d["composition"]])

# 3. section-title records: check one more (妊娠诸病第四) done above; check 小儿杂病第九/消渴第一/疥癣第四
for key in ("小儿杂病第九", "疥癣第四", "解百药毒第二"):
    pos = rawn.find("<篇名>" + key)
    p("\n### TITLE", key, "pos", pos)
    if pos >= 0:
        p("   ", rawn[pos:pos+350])

# 4. not-found group characterization: check 大承气汤 & 朴硝荡胞汤
for key in ("大承气汤", "朴硝荡胞汤"):
    pos = rawn.find("<篇名>" + key)
    p("\n### NF", key, "pos", pos)
    if pos >= 0:
        p("   ", rawn[pos:pos+400])

# 5. name of record 892 治丸方 source title & whether 篇名 corrupted
pos = rawn.find("<篇名>治丸方")
p("\n### 治丸方 pos", pos, rawn[pos-60:pos+80] if pos>=0 else "")

# 6. count composition herbs that are pure prose fragments across all records
frag = Counter()
for i, d in enumerate(data):
    for c in d["composition"]:
        h = c["herb"].strip()
        if re.search(r"(宜|纳|敷|服|作|以其|其|而|之$)", h) and len(h) >= 4:
            frag[i] += 1
p("\nrecords with prose-fragment herbs:", len(frag))
for i, n in frag.items():
    p("   ", i, data[i]["name"], n, data[i]["flags"])

# 7. duplicated herb within one composition
dup = [(d["name"], [c["herb"] for c in d["composition"]]) for d in data
       if len(set(c["herb"] for c in d["composition"])) != len(d["composition"])]
p("\nduplicate herb in same comp:", len(dup), dup[:10])
out.close()
print("done")
