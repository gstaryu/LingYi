"""
温病条辨 Chunker — 按中文数字编号条目切分。

文本结构:
  - 中文数字编号的条目：`一、`、`二、`、...、`二十、`、`二十一、` 等
  - 条目之间有解释性文字（按语）
  - 文件含散落的页码数字（如 10、11、12）和来源标注

切分策略:
  1. 通用清洗（去页码、去来源标注、去分隔线、去重复章节）
  2. 额外清理残留的页码数字行
  3. 按中文数字编号（`一、` 等）切分为条目
  4. 每个条目包含其后的解释性文字，直到下一个编号
"""

import re

from data_pipeline.base import BaseChunker, Chunk


class WenbingChunker(BaseChunker):
    """温病条辨切分器。"""

    book_name = "温病条辨"

    # 中文数字编号模式：行首的 "一、" ~ "九十九、" 等
    # 匹配 十/二十/三十/四十/五十/六十/七十/八十/九十 + 一~九，或单独的 一~九/十~九十
    _CLAUSE_PATTERN = re.compile(
        r"^(#{0,3})"  # 可选的 markdown 标记
        r"("
        r"[一二三四五六七八九十]"  # 个位数
        r"|"
        r"[二三四五六七八九十]十[一二三四五六七八九]?"  # 十位数
        r")、",
        re.MULTILINE,
    )

    def clean(self, text: str) -> str:
        """
        清洗温病条辨文本。

        在通用清洗基础上:
          - 去除散落的页码数字行
          - 去除来源项目名称
        """
        text = super().clean(text)
        # 去除残留的来源项目名
        text = text.replace("中国哲学书电子化计划", "")
        # 去除独立的页码数字行（与 remove_page_numbers 互补）
        text = re.sub(r"^\s*\d{1,4}\s*$", "", text, flags=re.MULTILINE)
        # 合并多余空行
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def chunk(self, text: str) -> list[Chunk]:
        """
        切分温病条辨。

        步骤:
          1. 按中文数字编号切分为条目
          2. 为每个条文生成 ID 和元数据
        """
        # 按中文数字编号分割，保留分隔符
        parts = self._CLAUSE_PATTERN.split(text)

        chunks: list[Chunk] = []
        idx = 0

        # parts 结构: [前缀, 可选#, 编号, 内容, 可选#, 编号, 内容, ...]
        # 跳过前缀（第一个元素），每 3 个一组（可选#, 编号, 内容）
        i = 0
        # 跳过开头的非编号文本
        while i < len(parts) and not self._is_clause_number(parts[i]):
            i += 1

        while i < len(parts):
            # 找到编号
            if self._is_clause_number(parts[i]):
                clause_num = parts[i]
                # 下一个元素是内容
                content = parts[i + 1] if i + 1 < len(parts) else ""
                content = content.strip()

                if content:
                    idx += 1
                    chunk_id = f"WBD_{idx:04d}"
                    chunks.append(Chunk(
                        id=chunk_id,
                        content=f"{clause_num}、{content}",
                        metadata={
                            "book": self.book_name,
                            "clause_number": clause_num,
                        },
                    ))
                i += 2
            else:
                i += 1

        return chunks

    @staticmethod
    def _is_clause_number(s: str) -> bool:
        """判断字符串是否为中文数字编号（如 '一'、'二十'）。"""
        if not s:
            return False
        s = s.strip()
        return bool(re.match(r"^[一二三四五六七八九十]+$", s))
