# -*- coding: utf-8 -*-
"""Dump context for specific indices for manual inspection."""
import json, re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
BASE = r'D:\PycharmProjects\LingYi\storage\extracted_formulas'
data = json.load(open(BASE + r'\waitai.json', encoding='utf-8'))
t = open(r'D:\PycharmProjects\LingYi\storage\classics_src\F-011-外台秘要.txt', encoding='utf-8').read()
t2 = ''.join(t.split())

for i in [int(x) for x in sys.argv[1:]]:
    r = data[i]
    print('='*80)
    print('IDX', i, 'NAME:', r['name'], '| sec:', r['section'], '| flags:', r['flags'], '| cov:', r.get('coverage'))
    print('IND:', r['indication'])
    print('COMP (%d):' % len(r['composition']), '; '.join('%s(%s)' % (c['herb'], c.get('dosage','')) for c in r['composition']))
    ex = ''.join((r['source_excerpt'] or '').split())
    pos = t2.find(ex)
    if pos < 0: pos = t2.find(ex[:30])
    if pos < 0:
        print('POS: NOT FOUND'); continue
    print('POS:', pos)
    print('PRE :', t2[max(0,pos-150):pos])
    print('EXC :', ex)
    print('POST:', t2[pos+len(ex):pos+len(ex)+120])
