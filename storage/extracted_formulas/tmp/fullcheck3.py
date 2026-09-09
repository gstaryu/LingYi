# -*- coding: utf-8 -*-
# All non-ASCII as \uXXXX escapes to avoid encoding issues.
import json, re, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = r'D:\PycharmProjects\LingYi\storage\extracted_formulas'
SRC  = r'D:\Py constants placeholder'  # placeholder line, replaced below
SRC  = r'D:\PycharmProjects\LingYi\storage\classics_src\F-011-\u5916\u53f0\u79d8\u8981.txt'
