"""
通用文本清洗函数 — 去页码、去来源标注、去重复章节、去分隔线。

所有古籍共享的清洗逻辑集中在此处，避免重复代码。
"""

import re


def remove_page_numbers(text: str) -> str:
    """
    去除独立页码行。

    匹配模式: 独占一行的纯数字（1-4 位），如 "217"、"1"。
    不匹配嵌入在正文中的数字。
    """
    # 匹配: 行首 + 可选空白 + 1-4 位数字 + 可选空白 + 行尾
    return re.sub(r"^\s*\d{1,4}\s*$", "", text, flags=re.MULTILINE)


def remove_source_markers(text: str) -> str:
    """
    去除来源标注行。

    匹配模式: "中国哲学书电子化计划" 等数字来源标记。
    """
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        # 跳过包含来源标记的行
        if "中国哲学书电子化计划" in line:
            continue
        if re.match(r"^\s*\d+\s*$", line.strip()) and len(line.strip()) <= 4:
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


def remove_separators(text: str) -> str:
    """
    去除分隔线（如 ----------）。
    """
    return re.sub(r"^-{3,}\s*$", "", text, flags=re.MULTILINE)


def deduplicate_sections(text: str) -> str:
    """
    去除重复章节。

    检测连续出现的相同章节标题，保留第一个。
    """
    lines = text.split("\n")
    seen_headers: set[str] = set()
    cleaned = []

    for line in lines:
        # 检测章节标题行（以 ### 或 数字. 开头）
        if re.match(r"^(###\s|第.+[章节卷])", line.strip()):
            header = line.strip()
            if header in seen_headers:
                continue
            seen_headers.add(header)
        cleaned.append(line)

    return "\n".join(cleaned)


def clean_text(text: str) -> str:
    """
    通用文本清洗流水线。

    按顺序执行:
    1. 去页码
    2. 去来源标注
    3. 去分隔线
    4. 去重复章节
    5. 合并多余空行
    """
    text = remove_page_numbers(text)
    text = remove_source_markers(text)
    text = remove_separators(text)
    text = deduplicate_sections(text)

    # 合并连续 3 个以上空行为 2 个
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()
