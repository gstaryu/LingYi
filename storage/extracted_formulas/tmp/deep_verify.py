# -*- coding: utf-8 -*-
"""深度核对：抽样 flags 非空 25 条 + flags 空 25 条，与原文比对"""
import json, re, random, sys

SRC = r"D:\PycharmProjects\LingYi\storage\extracted_formulas\jufang.json"
TXT = r"D:\PycharmProjects\LingYi\storage\classics_src\F-025-太平惠民和剂局方.txt"

data = json.load(open(SRC, encoding="utf-8"))
raw = open(TXT, encoding="utf-8").read()

# 解析原文为 篇名 -> 内容
sections = {}
for m in re.finditer(r"<篇名>(.*?)\n内容：(.*?)(?=<目录>|<篇名>|\Z)", raw, re.S):
    title = m.group(1).strip()
    body = m.group(2)
    body = re.sub(r"\s+", "", body)  # 去 OCR 断行/空白
    sections.setdefault(title, body)
print("sections parsed:", len(sections), file=sys.stderr)

def find_section(name):
    if name in sections:
        return name, sections[name]
    # 模糊：包含
    cands = [t for t in sections if name and (name in t or t in name)]
    if len(cands) == 1:
        t = cands[0]
        return t, sections[t]
    return None, None

random.seed(42)
flagged = [i for i, r in enumerate(data) if r.get("flags")]
unflagged = [i for i, r in enumerate(data) if not r.get("flags")]
sample_f = random.sample(flagged, min(25, len(flagged)))
sample_u = random.sample(unflagged, min(25, len(unflagged)))
sample = sample_f + sample_u
print("flagged sampled:", sample_f, file=sys.stderr)
print("unflagged sampled:", sample_u, file=sys.stderr)

results = []
ok = 0
for i in sample:
    r = data[i]
    name = r["name"]
    t, body = find_section(name)
    rec = {"index": i, "name": name, "flags": r.get("flags"), "found_section": t}
    if body is None:
        rec["status"] = "NOT_FOUND"
        # 尝试全局搜名字
        idxs = [m.start() for m in re.finditer(re.escape(name), raw)]
        rec["raw_hits"] = len(idxs)
        results.append(rec)
        continue
    herbs = [c.get("herb") or "" for c in r["composition"]]
    dos = [c.get("dosage") or "" for c in r["composition"]]
    herb_hits = [(h, h in body) for h in herbs if h]
    hit_rate = sum(1 for _, h in herb_hits if h) / max(1, len(herb_hits))
    # 剂量核对：原文中 出现 药名+（...剂量） 的模式
    dosage_checked = []
    for c in r["composition"]:
        h, dg = (c.get("herb") or "").strip(), (c.get("dosage") or "").strip()
        if not h or not dg:
            dosage_checked.append((h, dg, None))
            continue
        # 在该药名后面 30 字符窗口内找剂量
        pos = body.find(h)
        window = body[pos:pos + 40] if pos >= 0 else ""
        dosage_checked.append((h, dg, dg[:4] in window or window[:40]))
    rec["status"] = "FOUND"
    rec["herb_hit_rate"] = round(hit_rate, 3)
    rec["herb_miss"] = [h for h, b in herb_hits if not b]
    rec["herb_n"] = len(herbs)
    rec["dosage_examples"] = dosage_checked[:6]
    rec["body_head"] = body[:200]
    if hit_rate >= 0.8:
        ok += 1
        rec["verdict"] = "OK"
    elif hit_rate >= 0.5:
        rec["verdict"] = "PARTIAL"
    else:
        rec["verdict"] = "BAD"
    results.append(rec)

print(f"\nOK(>=80% herb hit): {ok}/{len(sample)}", file=sys.stderr)
json.dump(results, open("deep_verify.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("written deep_verify.json", file=sys.stderr)
