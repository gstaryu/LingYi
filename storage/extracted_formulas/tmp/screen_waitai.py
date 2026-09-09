# -*- coding: utf-8 -*-
"""Rule screening for waitai.json extraction quality."""
import json, re, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = r'D:\PycharmProjects\LingYi\storage\extracted_formulas'
data = json.load(open(BASE + r'\waitai.json', encoding='utf-8'))

# dosage-like units that indicate a real dosage
UNIT_RE = re.compile(r'[两錢铢分升合斗枚个颗寸尺匙盏撮把束茎枚斤钱匕border]{1,2}$|^(一|二|三|四|五|六|七|八|九|十|半|各)')

# verbs / non-herb residue patterns in names
NAME_VERB = re.compile(r'(主|治|疗|服|加|减|去|若|者|以|用|为|之|其|并|及|又|先|后|再|即|然后|兼|千金|备急|肘后|深师|集验|删繁|延年|必效|近效|小品|范汪|张文仲|崔氏|许仁则|救急|广济|指迷)')
SRC_BOOKS = ['千金','备急','肘后','深师','集验','删繁','延年','必效','近效','小品','范汪','文仲','崔氏','许仁则','救急','广济','古今录验','肺藏','髓海']

# words that should never appear inside a composition herb name (context residue)
RESIDUE = ['汤成','去滓','温服','上件','右件','右一味','先煮','后下','绞汁','为散','为末','蜜和','枣膏','服之','主之','主疗','病源','日再','夜一','以水','以酒','以醋','煎取','分温','内药','着中','曝干','熬令','炙令','切之','捣筛','下筛','空心','食前','食后','平旦','临卧','渐加','瘥止','如梧子','如枣','如弹丸','绵裹','绢袋','水三升','酒四升']

def dosage_real(s):
    return bool(s and UNIT_RE.search(s.strip()))

def main():
    report = []
    for i, r in enumerate(data):
        name = (r.get('name') or '').strip()
        comp = r.get('composition') or []
        ind = (r.get('indication') or '').strip()
        dosages = [c.get('dosage','') for c in comp]
        herbs = [c.get('herb','') for c in comp]
        probs = []
        # name checks
        if len(name) < 2:
            probs.append(('name_short', name))
        if re.match(r'^[\u4e00-\u9fff]$', name):
            probs.append(('name_truncated', name))
        if NAME_VERB.search(name):
            probs.append(('name_verb_residue', name))
        # composition checks
        if len(comp) < 2:
            probs.append(('comp_lt2', str(comp)[:120]))
        if len(comp) > 40:
            probs.append(('comp_gt40', len(comp)))
        if comp and not any(dosage_real(d) for d in dosages):
            probs.append(('dosage_all_empty', str(dosages)[:120]))
        # indication
        if not ind:
            probs.append(('ind_empty', ''))
        elif len(ind) < 8:
            probs.append(('ind_short', ind))
        # residue in herbs / dosages
        resid = [h for h in herbs for w in RESIDUE if w in h]
        resid += [d for d in dosages for w in RESIDUE if w in d]
        if resid:
            probs.append(('residue_in_comp', ';'.join(resid)[:150]))
        # herb name anomalies: too long (>8 chars) or containing punctuation
        badherb = [h for h in herbs if len(h) > 8 or re.search(r'[，。；、：（）()]', h)]
        if badherb:
            probs.append(('herb_suspicious', ';'.join(badherb)[:150]))
        # duplicate herbs
        dup = [h for h,c in __import__('collections').Counter(herbs).items() if c>1 and h]
        if dup:
            probs.append(('dup_herbs', ';'.join(dup)[:100]))
        if probs:
            report.append({'idx': i, 'name': name, 'section': r.get('section',''), 'probs': probs})

    out = {'total': len(data), 'flagged_by_rules': len(report), 'items': report}
    json.dump(out, open(BASE + r'\tmp\rulescreen.json','w',encoding='utf-8'), ensure_ascii=False, indent=1)
    # summary counts by type
    from collections import Counter
    c = Counter(p[0] for it in report for p in it['probs'])
    for k,v in c.most_common(): print(k, v)
    print('total flagged:', len(report))

if __name__ == '__main__':
    main()
