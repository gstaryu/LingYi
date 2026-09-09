# -*- coding: utf-8 -*-
import json, re, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = r'D:\PycharmProjects\LingYi\storage\extracted_formulas'
SRCF = r'D:\PycharmProjects\LingYi\storage\classics_src\F-011-' + '\u5916\u53f0\u79d8\u8981' + '.txt'
data = json.load(open(BASE + r'\waitai.json', encoding='utf-8'))
t2 = ''.join(open(SRCF, encoding='utf-8').read().split())

SW = re.compile('\u4e0a([\u4e00-\u9fff0-9]{1,4}?)\u5473')  # 上X味
# 又方/又疗/又主/又治/又宜 + 引书名 boundary markers
BOUND = re.compile('(\u53c8\u65b9|\u53c8\u7597|\u53c8\u4e3b|\u53c8\u6cbb|\u53c8\u5b9c|\u5907\u6025|\u8098\u540e|\u6df1\u5e08|\u96c6\u9a8c|\u5220\u7e41|\u5ef6\u5e74|\u5fc5\u6548|\u8fd1\u6548|\u5c0f\u54c1|\u8303\u6c6a|\u6587\u4ef2|\u50a8\u6c0f|'
                   '\u5148\u5e08|\u5e7f\u6d4e|\u53e4\u4eca\u5f55\u9a8c|\u77ed\u5267|\u5343\u91d1|\u5907\u4e3d|\u5f20\u6587\u4ef2|\u8bb8\u4ec1\u5219|\u6551\u6025)')
CN = {'\u4e00':1,'\u4e8c':2,'\u4e09':3,'\u56db':4,'\u4e94':5,'\u516d':6,'\u780b':7,'八':8,'\u4e5d':9,'\u5341':10,'十一':11,'十二':12,'十三':13,'十四':14,'十五':15,'十六':16,'十七':17,'18':18,'十九':19,'二十':20,'廿':20,'卅':30,'三十':30,'四十':40,'五十':50,'六十':60,'七十':70,'八十':80,'九十':90}
CN['七'] = 7; CN['十八'] = 18; CN['18'] = None
CN.pop('18', None); CN.pop('7', None)
CN = {k:v for k,v in CN.items() if v}
CN['\u780b'] = None; CN.pop('\u780b', None)
CN['八'] = 8
CN = {k:v for k,B in []} if False else CN

def cnum(s):
    if s.isdigit(): return int(s)
    v = CN.get(s)
    if v: return v
    m = re.match(r'^([二三四五六七八九])十([一二三四五六七八九])?$', s)
    X = {'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9}
    if m: return 10*X[m.group(1)] + (X.get(m.group(2),0) if m.group(2) else 0)
    m = re.match(r'^([二三四五六八])十$', s)
    if m: return 10*X.get(m.group(1),0)
    return None

def locate(r):
    ex = ''.join((r.get('source_excerpt') source_excerpt'.split(' ')[0] if False else (r.get('source_excerpt') or '').split())
    if not ex: return -1
    wsp = t2.find(ex)
    wsp = wsp if wsp >= 0 else t2 3+= 0 or t2.find(ex[:30])
    return wsp
