# -*- coding: utf-8 -*-
import json, re, sys
from collections import Counter

BASE = r"D:\PycharmProjects\LingYi\storage\extracted_formulas"
data = json.load(open(BASE + r"\qianjin.json", encoding="utf-8"))
out = open(BASE + r"\tmp\scan1.txt", "w", encoding="utf-8")
def p(*a):
    print(*a, file=out)

p("total", len(data))
p("name<2:", [d["name"] for d in data if len(d["name"].strip()) < 2][:30])
p("name starts 治/疗/主:", [d["name"] for d in data if d["name"] and d["name"][0] in "治疗主"][:30])

sfx = Counter(d["name"][-2:] for d in data)
p("top name endings:", sfx.most_common(25))

sizes = Counter(len(d["composition"]) for d in data)
p("comp sizes:", sorted(sizes.items()))
big = [(d["name"], len(d["composition"]), d["section"]) for d in data if len(d["composition"]) > 40]
p("big comps count", len(big), big[:25])
small = [(d["name"], len(d["composition"]), d["section"]) for d in data if len(d["composition"]) < 2]
p("small comps count", len(small), small[:20])

de = [d["name"] for d in data if d["composition"] and all(not c["dosage"].strip() for c in d["composition"])]
p("dosage all empty:", len(de))

p("empty comp:", [(d["name"], d["indication"]) for d in data if not d["composition"]][:20])

wi = [(d["name"], d["indication"]) for d in data if len(d["indication"].strip()) < 8]
p("weak indication count", len(wi), wi[:10])

bad_herb = []
for d in data:
    for c in d["composition"]:
        h = c["herb"].strip()
        if re.search(r"[汤丸散膏丹酒煎饮]方?$", h) and len(h) >= 3:
            bad_herb.append((d["name"], h))
            break
p("herb looks like formula name:", len(bad_herb), bad_herb[:25])

odd = []
for d in data:
    for c in d["composition"]:
        h = c["herb"].strip()
        if re.search(r"[，。、（）();,()]", h) or re.search(r"\d", h) or len(h) > 8:
            odd.append((d["name"], h))
            break
p("odd herbs:", len(odd), odd[:25])

sec = Counter(d["section"].split("\\")[0] for d in data)
p("sections:", sec.most_common(40))

# name endings that look like section headers rather than formula names
hdr = [d["name"] for d in data if re.search(r"(上部|中部|下部|草部|木部|虫鱼|果部|菜部|米谷|兽部|禽部)$", d["name"])]
p("section-header-like names:", len(hdr), hdr[:30])

# dosage values that are not dosage-like
bad_dos = []
for d in data:
    for c in d["composition"]:
        g = c["dosage"].strip()
        if g and not re.search(r"[两分铢升合斗钱字枚颗挺寸尺斤握鸡子把束枚盏钱匕弹丸枣大小]", g):
            bad_dos.append((d["name"], c["herb"], g))
p("odd dosage values:", len(bad_dos), bad_dos[:30])

# duplicate names
nm = Counter(d["name"] for d in data)
p("duplicate names (top):", nm.most_common(15))
p("dup count:", sum(1 for k, v in nm.items() if v > 1))
out.close()
print("done")
