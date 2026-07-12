"""
神农本草经 Chunker — 按药物条目切分，保留所属部类。

文本结构:
  - 部类标题：`玉石部上品`、`草部中品`、`木部下品` 等
  - 每个药物条目以药名 + 全角空格 + `味` 开头
    （如 `玉泉　味甘平。主治五脏百病。...`）
  - 文件开头有上/中/下卷序言（药性总论）

切分策略:
  1. 通用清洗（去页码、去来源标注、去分隔线、去重复章节）
  2. 额外清理来源项目名和卷标题
  3. 按部类标题分段，每段内按药物条目切分
  4. 每个药物条目归属其所属部类
"""

import re

from data_pipeline.base import BaseChunker, Chunk


class ShennongChunker(BaseChunker):
    """神农本草经切分器。"""

    book_name = "神农本草经"

    # 部类标题模式：如 `玉石部上品`、`草部中品`、`木部下品`、`兽部上品` 等
    _CATEGORY_PATTERN = re.compile(
        r"^(\S+部[上中下]品)\s*$", re.MULTILINE
    )

    # 药物条目模式：药名 + 全角空格 + `味`
    # 药名为连续非空白字符，后跟全角空格（　）和"味"
    _DRUG_PATTERN = re.compile(
        r"^(\S+?)　味", re.MULTILINE
    )

    def clean(self, text: str) -> str:
        """
        清洗神农本草经文本。

        在通用清洗基础上:
          - 去除来源项目名
          - 去除卷标题（上卷》、中卷》、下卷》）
        """
        text = super().clean(text)
        # 去除残留的来源项目名
        text = text.replace("中国哲学书电子化计划", "")
        # 去除卷标题行
        text = re.sub(r"^[上下中]卷》?\s*$", "", text, flags=re.MULTILINE)
        # 合并多余空行
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def chunk(self, text: str) -> list[Chunk]:
        """
        切分神农本草经。

        步骤:
          1. 识别部类标题，按部类分段
          2. 每段内按药物条目切分
          3. 保留部类作为元数据
        """
        chunks: list[Chunk] = []
        idx = 0

        # 按部类标题分段
        segments = self._split_by_categories(text)

        for category, segment_text in segments:
            # 按药物条目切分
            drug_entries = self._split_drug_entries(segment_text)
            for entry in drug_entries:
                entry = entry.strip()
                if not entry:
                    continue
                idx += 1
                chunk_id = f"SNBCJ_{idx:04d}"
                # 提取药名作为元数据
                drug_name = self._extract_drug_name(entry)
                chunks.append(Chunk(
                    id=chunk_id,
                    content=entry,
                    metadata={
                        "book": self.book_name,
                        "category": category,
                        "drug_name": drug_name,
                    },
                ))

        return chunks

    def _split_by_categories(self, text: str) -> list[tuple[str, str]]:
        """
        按部类标题分段。

        返回: [(部类名, 该部类下的文本), ...]
        """
        # 找到所有部类标题的位置
        matches = list(self._CATEGORY_PATTERN.finditer(text))
        if not matches:
            # 无部类标题，整体作为一个段
            return [("", text)]

        segments = []
        for i, m in enumerate(matches):
            category = m.group(1)
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            segment_text = text[start:end].strip()
            if segment_text:
                segments.append((category, segment_text))

        # 处理第一个部类之前的内容（序言等）
        if matches and matches[0].start() > 0:
            preamble = text[:matches[0].start()].strip()
            if preamble:
                segments.insert(0, ("序言", preamble))

        return segments

    @staticmethod
    def _split_drug_entries(text: str) -> list[str]:
        """
        按药物条目切分。

        药物条目以 `药名　味` 开头（全角空格分隔）。
        """
        # 按药物名 + 全角空格 + 味 分割，保留分隔符
        # 使用正向前瞻在药名前分割
        parts = re.split(r"(?=^\S+?　味)", text, flags=re.MULTILINE)
        return [p for p in parts if p.strip()]

    @staticmethod
    def _extract_drug_name(entry: str) -> str:
        """从药物条目中提取药名。"""
        m = re.match(r"^(\S+?)　味", entry)
        return m.group(1) if m else ""
