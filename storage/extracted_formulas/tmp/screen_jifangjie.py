# -*- coding: utf-8 -*-
"""Rule-based screening of jifangjie.json extraction results."""
import json, re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE = r"D:\PycharmProjects\LingYi\storage\extracted_formulas"
data = json.load(open(BASE + r"\jifangjie.json", encoding="utf-8"))

# suspicious non-herb tokens (comment/annotation words that shouldn't be herb names)
NON_HERB_HINTS = re.compile(
    r"^(此|以上|共|等|为|用|加|减|各|或|并|右|原注|按|又方|一方|凡|其|若|后|先|去|不|无|有|见|俱|更|入|二|三|四|五|六|七|八|九|十|百|千|万)"
)

report = []
flag_counter = {}

def check(i, item):
    problems = []
    name = (item.get("name") or "").strip()
    comp = item.get("composition") or []
    ind = (item.get("indication") or "").strip()
    dosages = [c.get("dosage", "") for c in comp]

    # name
    if len(name) < 2:
        problems.append(f"name_too_short(name={name!r})")
    if re.search(r"论|序|凡例|目录|跋|引$", name):
        problems.append(f"name_not_formula(name={name!r})")

    # composition size
    if len(comp) < 2:
        problems.append(f"comp_lt2(n={len(comp)})")
    if len(comp) > 40:
        problems.append(f"comp_gt40(n={len(comp)})")

    # dosage all empty
    if comp and all(not d.strip() for d in dosages):
        problems.append("dosage_all_empty")

    # indication
    if not ind:
        problems.append("indication_empty")
    elif len(ind) < 8:
        problems.append(f"indication_too_short(len={len(ind)})")

    # herb sanity: too long, contains punctuation/verbs, starts with non-herb hint
    for c in comp:
        h = (c.get("herb") or "").strip()
        if not h:
            problems.append("herb_empty")
            continue
        if len(h) > 12:
            problems.append(f"herb_too_long({h!r})")
        if NON_HERB_HINTS.match(h):
            problems.append(f"herb_suspect({h!r})")
        if re.search(r"[，。；：？！、（）()]", h):
            problems.append(f"herb_has_punct({h!r})")

    # flags tally
    for f in item.get("flags", []):
        flag_counter[f] = flag_counter.get(f, 0) + 1

    return problems

issues = {}
for i, item in enumerate(data):
    p = check(i, item)
    if p:
        issues.setdefault(item.get("name", f"#idx{i}"), []).append(p)

print("TOTAL:", len(data))
print("FLAGS COUNTS:", json.dumps(flag_counter, ensure_ascii=False))
print("ITEMS WITH RULE PROBLEMS:", len(issues))
for name, ps in issues.items():
    flat = sorted({x for group in ps for x in group})
    print(" -", name, "->", "; ".join(flat))
