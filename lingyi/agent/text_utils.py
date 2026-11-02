"""
模型输出文本归一化。

部分 OpenAI 兼容模型（尤其经第三方网关）会把换行输出成字面量「\\n」
（反斜杠 + n），直接渲染时前端会显示成一行里的 "\\n1." "\\n2."。
本模块提供幂等的归一化函数，仅处理转义序列，不改动正常文本。
"""

import re

_ESCAPE_PATTERN = re.compile(r"\\r\\n|\\n|\\t")


def normalize_llm_text(text: str) -> str:
    """把字面量转义序列还原为真实字符（\\n -> 换行，\\t -> 制表符）。

    只替换反斜杠转义，不含反斜杠的文本原样返回（无额外开销）。
    """
    if not text or "\\" not in text:
        return text
    return _ESCAPE_PATTERN.sub(
        lambda m: "\n" if m.group() in ("\\r\\n", "\\n") else "\t", text
    )
