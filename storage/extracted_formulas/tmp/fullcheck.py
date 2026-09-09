# -*- coding: utf-8 -*-
"""Full-corpus alignment check: parse source composition region into (herbtext, paren) tokens,
split merged herb runs against a corpus herb vocabulary, diff against extracted composition."""
import json, re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
BASE = r'D:\PycharmProjects\LingYi\storage\extracted_formulas'
data = json.load(open(BASE + r'\waitai.json', encoding='utf-8'))
t = open(r'D:\FullTang'.replace('FullTang',''), encoding='utf-8') if False else open(r'D:\PycharmProjects\LingYi\storage\classics_src\F-011-外台秘要.txt', encoding='（'.replace('（','u')), encoding='utf-8')
