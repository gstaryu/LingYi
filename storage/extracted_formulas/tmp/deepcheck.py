# -*- coding: utf-8 -*-
"""Deep verification: 30 flagged + 30 unflagged samples against source text."""
import json, re, sys, io, random
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = r'D:\PycharmProjects\LingYi\storage\extracted_formulas'
data = json.load(open(BASE + r'\waitai.json', encoding='utf-8'))
t = open(r'D:\PycharmProjects\LingYi\storage\classics_src\F-011-外台秘要.txt', encoding='utf-8').read()
t2 = ''.join(t.split())

NUMD = {'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10,
        '十一':11,'十二':12,'十三':13,'十四':14,'十五':15,'十六':16,'十七':17,'十八':18,
        '十九':19,'二十':20,'廿':20,'三十':30,'四十':40,'五十':50,'六十':60,'七十':70,'八十':80,'九十':90,'百':100}
def cnum(s):
    if s in NUMD: return NUMD[s]
    if s.isdigit(): return int(s)
    m = re.match(r'([二三四五六七八九十])十([一二三四五六七八九])?$', s)
    if m:
        base = NUMD[m.group(1)+'十'] if m.group(1)+'十' in NUMD else 10*NUMD[m.group(1)]
        return base + (NUMD.get(m.group(2),0) if m.group(2) else 0)
    if len(s)==2 and s[1]=='十': return 10*NUMD.get(s[0],0)
    return None

# pick samples: 30 from flagged (has flags OR rulescreen problems), 30 unflagged
rules = json.load(open(BASE + r'\tmp\rulescreen.json', encoding='utf-8'))
rule_flagged = {it['idx'] for it in rules['items']}
flagged = [i for i,r in enumerate(data) if r.get('flags') or i in rule_flagged]
unflagged = [i for i,r in enumerate(data) if not r.get('flags') and i not in rule_flagged]
random.seed(42)
samp_f = random.sample(flagged, min(30, len(flagged)))
samp_u = random.sample(unflagged, min(30, len(unflagged)))
print('samples: flagged-pool=%d take=%d ; unflagged-pool=%d take=%d' % (len(flagged),len(samp_f),len(unflagged),len(samp_u)))

results = []
for grp, idxs in (('flagged', samp_f), ('unflagged', samp_u)):
    for i in idxs:
        r = data[i]
        name = (r.get('name') or '').replace(' ','')
        ex = ''.join((r.get('source_excerpt') or '').split())
        rec = {'idx': i, 'grp': grp, 'name': name, 'issues': [], 'ok': []}
        pos = t2.find(ex)
        if pos < 0:
            p2 = t2.find(ex[:30])
            rec['issues'].append('EXCERPT_NOT_FOUND' if p2<0 else 'EXCERPT_PARTIAL')
            pos = p2 if p2 >= 0 else None
        if pos is not None:
            pre = t2[max(0,pos-400):pos]
            # --- name identity check ---
            m = re.search(r'([\u4e00-\u9fff]{1,12}?)方(?=[。：:]|$)', pre)
            # find the formula title: text ending with 方 closest to excerpt start
            titles = re.findall(r'([\u4e00-\u9fff]{2,20}方)', pre)
            rec['src_title'] = titles[-1] if titles else pre[-30:]
            # --- composition region: from first herb pair to first 上X味 after it ---
            comp = r['composition']
            pairs = [''.join((c['herb']+('（'+c['dosage']+'）' if c.get('dosage') else '')).split()) for c in comp]
            first_pos = None
            for p in pairs[:2]:
                pp = t2.find(p, pos)
                if pp >= 0: first_pos = pp if first_pos is None else min(first_pos, pp)
            if first_pos is None:
                # herb may appear with extra annotation inside parens; try herb only
                pp = t2.find(''.join(comp[0]['herb'].split()), pos) if comp else -1
                first_pos = pp
            if first_pos is not None:
                end_m = re.search(r'上[\u4e00-\u9fff0-9]{1,4}味', t2[first_pos:first_pos+1500])
                if end_m:
                    region = t2[first_pos:first_pos+end_m.end()]
                    nsw = cnum(end_m.group(0)[1:-1])
                    # boundary inside region?
                    bnd = re.search(r'(又方|又疗|又云|疗[^，。]{1,14}方。|。[^，。]{1,12}方。|备急|千金|肘后|深师|集验|删繁|延年|必效|近效|小品|范汪|文仲|崔氏|许仁则|救急|广济|古今录验)', region)
                    # locate comp items in region
                    missing = []
                    for c, p in zip(comp, pairs):
                        if p not in region:
                            # allow dosage annotation differences: herb must appear
                            if ''.join(c['herb'].split()) not in region:
                                missing.append(c['herb'])
                    rec['comp_region_head'] = region[:120]
                    rec['src_shangwei'] = end_m.group(0) + ('=' + str(nsw) if nsw else '')
                    if missing:
                        rec['issues'].append('HERBS_OUTSIDE_REGION:' + ','.join(missing[:6]))
                    if nsw and nsw != len(comp):
                        rec['issues'].append('SHANGWEI_MISMATCH:src=%s,ext=%d' % (nsw, len(comp)))
                    if bnd:
                        rec['issues'].append('BOUNDARY_IN_REGION:' + bnd.group(1))
                    # merged-herb check: herb token immediately followed by another herb char run then （
                    # (can't reliably detect; leave to manual)
                else:
                    rec['issues'].append('NO_SHANGWEI_FOUND')
            else:
                rec['issues'].append('COMP_NOT_LOCATED')
        # name-vs-title compare
        ttl = rec.get('src_title','')
        nm_stripped = re.sub(r'^(又|次|乃|即|决计|得患|并宜|常服|别法|或是|疗|服|主|为)','',name)
        if ttl and nm_stripped:
            tail = nm_stripped[-4:]
            if tail not in ttl and nm_stripped not in ttl and ttl not in nm_stripped:
                rec['issues'].append('NAME_TITLE_DIFF:title=%s' % ttl)
        results.append(rec)

json.dump(results, open(BASE + r'\tmp\deepcheck.json','w',encoding='utf-8'), ensure_ascii=False, indent=1)
ok = [r for r in results if not r['issues']]
print('sampled', len(results), 'clean', len(ok))
for r in results:
    if r['issues']:
        print('---', r['grp'], r['idx'], r['name'])
        for is_ in r['issues']: print('    ', is_)
