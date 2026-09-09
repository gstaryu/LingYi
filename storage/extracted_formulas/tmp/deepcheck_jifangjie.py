# -*- coding: utf-8 -*-
"""Deep verification: compare sampled extracted formulas against source txt."""
import json, re, sys, io, random
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE = r"D:\PycharmProjects\LingYi\storage\extracted_formulas"
SRC = r"D:\PycharmProjects\LingYi\storage\classics_src\F-091-医方集解.txt"
data = json.load(open(BASE + r"\jifangjie.json", encoding="utf-8"))
src = open(SRC, encoding="utf-8").read()
src_nows = re.sub(r"\s+", "", src)  # whitespace-stripped source

# split source into sections by <篇名>
sections = {}  # title -> section text (whitespace-normalized)
parts = re.split(r"<篇名>([^\n<]+)", src)
for i in range(1, len(parts) - 1, 2):
    title = parts[i].strip()
    body = re.sub(r"\s+", "", parts[i + 1])
    sections[title] = body

def find_section(name):
    name_clean = re.sub(r"（.*?）|\(.*?\)", "", name).strip()
    for t in (name, name_clean):
        if t in sections:
            return sections[t], t
    # substring search
    for t, body in sections.items():
        if name_clean and (name_clean in t or t in name_clean):
            return body, t
    return None, None

MARKER = re.compile(r"此[手足太少阴阳厥足二三]?[经阴阳]?[^，。；]{0,8}药也")

def comp_zone(body):
    """text from start of section up to 此X经药也 marker; fallback before first '此'"""
    m = MARKER.search(body)
    if m:
        return body[:m.start()]
    idx = body.find("此")
    return body[:idx] if idx > 0 else body

def find_all(sub, text):
    return [m.start() for m in re.finditer(re.escape(sub), text)]

random.seed(42)
flagged = [it for it in data if it.get("flags")]
clean = [it for it in data if not it.get("flags")]
samples = [it["name"] for it in flagged][:20] + random.sample([it["name"] for it in clean], 20)
sample_map = {it["name"]: it for it in data}

results = []
for name in samples:
    it = sample_map[name]
    body, stitle = find_section(name)
    rec = {"name": name, "section_found": bool(body), "herbs": [c["herb"] for c in it["composition"]],
           "flags": it.get("flags", [])}
    if not body:
        rec["status"] = "SECTION_NOT_FOUND"
        results.append(rec)
        continue
    zone = comp_zone(body)
    found_in_zone, found_in_comment, not_found = [], [], []
    for h in rec["herbs"]:
        hz = re.sub(r"（.*?）", "", h).strip()  # strip parenthetical
        inz = hz in zone
        inb = hz in body
        if inz:
            found_in_zone.append(h)
        elif inb:
            found_in_comment.append(h)  # appears only after marker = comment text
        else:
            not_found.append(h)
    rec.update(found_in_zone=len(found_in_zone), only_comment=found_in_comment,
               not_found=not_found, status="OK" if not not_found else "MISMATCH")

    # missing herbs: count herb-like entries in zone not covered
    # crude: count dosage annotations （…两|…钱|…枚|等分） in zone
    dos_annos = re.findall(r"（[^（）]{0,30}?[两钱枚分个只颗寸盏匙]）", zone)
    rec["dosage_annos_in_zone"] = len(dos_annos)
    rec["n_herbs_extracted"] = len(rec["herbs"])
    results.append(rec)

json.dump(results, open(BASE + r"\tmp\deepcheck_results.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

ok = sum(1 for r in results if r.get("status") == "OK")
print(f"sections found: {sum(1 for r in results if r.get('section_found'))}/{len(results)}")
print(f"status OK: {ok}/{len(results)}")
for r in results:
    print("\n###", r["name"], f"[{r.get('status')}] flags={r.get('flags')}")
    if r.get("section_found"):
        print(f"  extracted={r['n_herbs_extracted']} in_zone={r['found_in_zone']} "
              f"only_comment={r['only_comment']} not_found={r['not_found']} "
              f"dos_annos_in_zone={r['dosage_annos_in_zone']}")
