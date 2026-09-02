r"""
古籍方剂 OCR 清洗工具。

处理 jobkoko/tcm-database 文本（中医世家格式）的常见 OCR 伪迹:
- \x...\x 转义包裹字符串
- "KT KT"/"KT" 罕见字占位符
- "香港"（"脚气"的错码）、"浓朴"（"厚朴"）等系统性错字
"""

import re

# 系统性错字替换（中医世家文本库已知 OCR 习惯）
_REPLACEMENTS: list[tuple[str, str]] = [
    ("香港脚", "脚气"),
    ("香港", "脚气"),
    ("浓朴", "厚朴"),
    ("黄蓍", "黄芪"),
]

_ESCAPED_RE = re.compile(r"\\x[^\\\n]{0,60}\\x")
_KT_RE = re.compile(r"\bKT\b(?:\s*KT\b)?")


def clean_ocr(text: str) -> str:
    """清洗单段古籍文本的 OCR 伪迹。"""
    for old, new in _REPLACEMENTS:
        text = text.replace(old, new)
    text = _ESCAPED_RE.sub("", text)
    text = _KT_RE.sub("", text)
    return text


def strip_markup(text: str) -> str:
    """去掉 <目录>/<篇名>/内容：/属性： 等结构标记。"""
    return re.sub(r"<[^>]{1,20}>", "", text).replace("内容：", "").replace("属性：", "")
