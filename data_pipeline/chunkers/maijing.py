"""
脉经 Chunker — 按章节切分，长章节按「一曰」子变体细分。

文本结构:
  - 章节标题格式：`XXX第X》`（如 `平脉早晏法第二》`、`分别三关境界脉候所主第三》`）
  - 每个章节内包含脉象描述和注释
  - 部分条目有 `一曰` 子变体（同一脉象的不同描述）
  - 文件含繁体、英文、简体三份重复内容

切分策略:
  1. 通用清洗（去页码、去来源标注、去分隔线、去重复章节）
  2. 额外清理来源项目名和章节编号标记
  3. 按章节标题切分
  4. 长章节（超过阈值）按行首 `一曰` 进一步细分
"""

import re

from data_pipeline.base import BaseChunker, Chunk


class MaijingChunker(BaseChunker):
    """脉经切分器。"""

    book_name = "脉经"

    # 章节标题模式：以 `第` + 数字 + `》` 结尾
    # 如 `脉形状指下秘诀第一》`、`平脉早晏法第二》`
    _CHAPTER_PATTERN = re.compile(
        r"^(.+第[一二三四五六七八九十百千零\d]+)》?\s*$",
        re.MULTILINE,
    )

    # 长章节细分阈值（字符数）
    _LONG_CHAPTER_THRESHOLD = 2000

    # 一曰模式：行首的 `一曰`
    _YIYUE_PATTERN = re.compile(r"^一曰", re.MULTILINE)

    def clean(self, text: str) -> str:
        """
        清洗脉经文本。

        在通用清洗基础上:
          - 去除来源项目名
          - 去除 `### ` 元数据头（繁体/英文/简体重复的页眉）
        """
        text = super().clean(text)
        # 去除残留的来源项目名
        text = text.replace("Chinese Text Project", "")
        # 去除 ### 元数据头（如 ### 脈經卷第一）
        text = re.sub(r"^### .+$", "", text, flags=re.MULTILINE)
        # 去除分隔线
        text = re.sub(r"^-{3,}\s*$", "", text, flags=re.MULTILINE)
        # 合并多余空行
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def chunk(self, text: str) -> list[Chunk]:
        """
        切分脉经。

        步骤:
          1. 按章节标题切分
          2. 长章节按「一曰」进一步细分
          3. 为每个条文生成 ID 和元数据
        """
        chunks: list[Chunk] = []
        idx = 0

        # 按章节标题分段
        segments = self._split_by_chapters(text)

        for chapter_title, segment_text in segments:
            segment_text = segment_text.strip()
            if not segment_text:
                continue

            # 长章节按「一曰」细分
            if len(segment_text) > self._LONG_CHAPTER_THRESHOLD:
                sub_chunks = self._split_by_yiyue(segment_text)
                for sub_idx, sub_text in enumerate(sub_chunks, 1):
                    sub_text = sub_text.strip()
                    if not sub_text:
                        continue
                    idx += 1
                    chunk_id = f"MJ_{idx:05d}"
                    chunks.append(Chunk(
                        id=chunk_id,
                        content=sub_text,
                        metadata={
                            "book": self.book_name,
                            "chapter": chapter_title,
                            "sub_index": sub_idx,
                        },
                    ))
            else:
                idx += 1
                chunk_id = f"MJ_{idx:05d}"
                chunks.append(Chunk(
                    id=chunk_id,
                    content=segment_text,
                    metadata={
                        "book": self.book_name,
                        "chapter": chapter_title,
                    },
                ))

        return chunks

    def _split_by_chapters(self, text: str) -> list[tuple[str, str]]:
        """
        按章节标题分段。

        返回: [(章节标题, 该章节正文), ...]
        """
        matches = list(self._CHAPTER_PATTERN.finditer(text))
        if not matches:
            return [("", text)]

        segments = []
        for i, m in enumerate(matches):
            title = m.group(1).strip()
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            if body:
                segments.append((title, body))

        # 处理第一个章节之前的内容
        if matches and matches[0].start() > 0:
            preamble = text[:matches[0].start()].strip()
            if preamble:
                segments.insert(0, ("序言", preamble))

        return segments

    def _split_by_yiyue(self, text: str) -> list[str]:
        """
        按行首「一曰」细分长章节。

        「一曰」表示同一脉象的另一种描述，作为子变体保留。
        """
        # 按行首 "一曰" 分割，保留分隔符
        parts = re.split(r"(?=^一曰)", text, flags=re.MULTILINE)
        return [p for p in parts if p.strip()]
