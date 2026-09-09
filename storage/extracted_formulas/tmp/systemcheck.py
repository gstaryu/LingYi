# -*- coding: utf-8 -*-
"""Systematic checks across all 416: name verbatim presence, 上X味 vs composition count."""
import json, re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = r'D:\PycharmProjects\LingYi\storage\extracted_formulas'
data = json.load(open(BASE + r'\waitai.json', encoding='utf-8'))
t = open(r'D:\PycharmProjects\LingYi\storage\classics_src\F-011-外台秘要.txt', encoding='utf-8').read()
t2 = ''.join(t.split())

NUM = {'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10,'十一':11,'十二':12,'十三':13,'十四':14,'十五':15,'十六':16,'十七':17,'十八':18,'十九':19,'二十':20,'廿':20,'卅':30,'三十':30,'四十':40}

def cnum(s):
    if s in NUM: return NUM[s]
    if s.isdigit(): return int(s)
    # simple composite like 二十一 handled by dict entries; fallback
    if len(s) == 3 and s[0]=='二' and s[2]=='十': return 20+NUM.get(s[1],0)
    if len(s) == 3 and s[0]=='三' and s[2]=='十': return 30+NUM.get(s[1],0)
    return None

name_found = 0
name_missing = []
shangwei_mismatch = []
shangwei_nofind = 0
for i, r in enumerate(data):
    name = (r.get('name') or '').replace(' ','')
    ex = ''.join((r.get('source_excerpt') or '').split())
    pos = t2.find(ex)
    # name check: does name (or name minus leading verbs) appear within 500 chars before excerpt start, or anywhere
    if pos >= 0:
        pre = t2[max(0,pos-500):pos]
        nm = name
        found = nm in pre
        if not found:
            # strip common leading verbs
            stripped = re.sub(r'^(又|次|乃|即|决计|得患|并宜|常服|别法|或是)', '', nm)
            stripped = re.sub(r'^(疗|服|主|为)', '', stripped)
            # try the trailing formula-word portion, e.g. 鳖甲汤 from 决计服此鳖甲汤
            m = re.search(r'([\u4e00-\u9fff]{1,7}(?:汤|丸|散|膏|酒|煎|圆))$', nm)
            if m: stripped = m.group(1)
            found = stripped in pre
        if found: name_found += 1
        else: name_missing.append((i, name, pre[-80:]))
    else:
        if name in t2: name_found += 1
        else: name_missing.append((i, name, '(excerpt not located)'))
    # 上X味 check
    herbs_n = len(r.get('composition') or [])
    window = ex[-200:] if ex else ''
    m = re.search(r'上(.{1,4}?)味', window)
    if m:
        n = cnum(m.group(1))
        if n is None:
            shangwei_nofind += 1
        elif n != herbs_n:
            shangwei_mismatch.append((i, name, 'source上%s味' % m.group(1), 'extracted %d herbs' % herbs_n))

print('name verbatim/nearby found:', name_found, '/', len(data))
print('name missing count:', len(name_missing))
for x in name_missing[:40]: print('  MISS', x[0], x[1])
print('上X味 present-but-mismatched:', len(shangwei_mismatch))
for x in shangwei_mismatch[:50]: print('  SW', x[0], x[1], '|', x[2], '|', x[3])
json.dump({'name_missing':[x[:2] for x in name_missing],
           'shangwei_mismatch':shangwei_mismatch},
          open(BASE + r'\tmp\systemcheck.json','w',encoding='utf-8'), ensure_ascii=False, indent=1)
