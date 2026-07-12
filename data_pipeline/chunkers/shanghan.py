"""
伤寒论 Chunker — 按章节 + 段落切分。

文本结构:
  - `### ` 开头的章节标题（如 `### 辨太阳病脉证并治法上`）
  - 每个章节内按段落（双换行）切分
  - 文件含繁体、英文、简体三份重复内容，需去重并过滤元数据段

切分策略:
  1. 通用清洗（去页码、去来源标注、去分隔线、去重复章节）
  2. 按 `### ` 分割为章节
  3. 过滤元数据段（第二行为 ---------- 或 Chinese Text Project 的段）
  4. 每个章节按双换行切分为段落
"""

import re

from data_pipeline.base import BaseChunker, Chunk


class ShanghanChunker(BaseChunker):
    """伤寒论切分器。"""

    book_name = "伤寒论"

    # 元数据标记：出现在非内容章节中的关键词
    _META_MARKERS = ("中国哲学书电子化计划", "电子图书馆", "底本：", "显示全部", "全文检索")

    def _filter_metadata_sections(self, sections: list[str]) -> list[str]:
        """
        过滤元数据段。

        元数据段包含 "中国哲学书电子化计划"、"电子图书馆" 等来源标记。
        内容段（如辨脉法、辨太阳病等）不包含这些标记。
        """
        result = []
        for sec in sections:
            if any(marker in sec for marker in self._META_MARKERS):
                continue
            result.append(sec)
        return result

    def chunk(self, text: str) -> list[Chunk]:
        """
        切分伤寒论。

        步骤:
          1. 按 `### ` 分割为章节段
          2. 过滤元数据段
          3. 每个章节按双换行切分为条文
          4. 为每个条文生成 ID 和元数据
        """
        # 按章节标题分割（保留标题行）
        raw_sections = re.split(r"(?=^### )", text, flags=re.MULTILINE)
        sections = self._filter_metadata_sections(raw_sections)

        chunks: list[Chunk] = []
        idx = 0

        for sec in sections:
            sec = sec.strip()
            if not sec:
                continue

            # 提取章节标题和正文
            lines = sec.split("\n")
            header = lines[0].replace("### ", "").strip()
            body = "\n".join(lines[1:]).strip()

            if not body:
                continue

            # 按段落（双换行）切分
            paragraphs = re.split(r"\n\s*\n", body)
            for para in paragraphs:
                para = para.strip()
                if not para:
                    continue
                idx += 1
                chunk_id = f"SHL_{idx:04d}"
                chunks.append(Chunk(
                    id=chunk_id,
                    content=para,
                    metadata={
                        "book": self.book_name,
                        "chapter": header,
                    },
                ))

        return chunks
