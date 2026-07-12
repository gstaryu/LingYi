"""
黄帝内经-素问 Chunker — 去重后按章节 + 段落切分。

文本结构:
  - `### ` 开头的章节标题（如 `### 上古天真论`、`### 四气调神大论`）
  - 每个章节内按段落（双换行）切分，段落为黄帝与岐伯的对话
  - 文件含繁体、英文、简体三份重复内容，需去重并过滤元数据段

切分策略:
  1. 通用清洗（去页码、去来源标注、去分隔线、去重复章节）
  2. 按 `### ` 分割为章节
  3. 过滤元数据段（第二行为 ---------- 或 Chinese Text Project 的段）
  4. 每个章节按双换行切分为段落
"""

import re

from data_pipeline.base import BaseChunker, Chunk


class SuwenChunker(BaseChunker):
    """黄帝内经-素问切分器。"""

    book_name = "黄帝内经-素问"

    # 元数据标记：出现在非内容章节中的关键词
    _META_MARKERS = ("中国哲学书电子化计划", "电子图书馆", "底本：", "显示全部", "全文检索")

    def _filter_metadata_sections(self, sections: list[str]) -> list[str]:
        """
        过滤元数据段。

        元数据段包含 "中国哲学书电子化计划"、"电子图书馆" 等来源标记。
        """
        result = []
        for sec in sections:
            if any(marker in sec for marker in self._META_MARKERS):
                continue
            result.append(sec)
        return result

    def chunk(self, text: str) -> list[Chunk]:
        """
        切分素问。

        步骤:
          1. 按 `### ` 分割为章节段
          2. 过滤元数据段（繁体/英文/简体重复的元数据头）
          3. 每个章节按双换行切分为段落
          4. 为每个条文生成 ID 和元数据
        """
        raw_sections = re.split(r"(?=^### )", text, flags=re.MULTILINE)
        sections = self._filter_metadata_sections(raw_sections)

        chunks: list[Chunk] = []
        idx = 0

        for sec in sections:
            sec = sec.strip()
            if not sec:
                continue

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
                chunk_id = f"SW_{idx:04d}"
                chunks.append(Chunk(
                    id=chunk_id,
                    content=para,
                    metadata={
                        "book": self.book_name,
                        "chapter": header,
                    },
                ))

        return chunks
