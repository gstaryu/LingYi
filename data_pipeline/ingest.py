"""
TCM 数据入库脚本 — 读取古籍文本，切分为 Chunk，输出 JSON 或写入 ChromaDB。

用法:
    # 输出 JSON 到 storage/chunks/
    python -m data_pipeline.ingest

    # 写入 ChromaDB（需 embedding 模型）
    python -m data_pipeline.ingest --mode chroma
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from pathlib import Path

# 添加项目根目录到 path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from data_pipeline.base import Chunk
from data_pipeline.chunkers.registry import get_chunker

logger = logging.getLogger(__name__)

# TCM 数据文件映射
TCM_FILES: dict[str, str] = {
    "伤寒论": "伤寒论_完整清洗版.txt",
    "金匮要略": "金匮要略_完整清洗版.txt",
    "温病条辨": "温病条辨_完整清洗版.txt",
    "神农本草经": "神农本草经_完整清洗版.txt",
    "脉经": "脉经_完整清洗版.txt",
    "黄帝内经-素问": "黄帝内经-素问_完整清洗版.txt",
}


def chunk_all_books(tcm_data_dir: str) -> dict[str, list[Chunk]]:
    """对所有古籍执行切分（各书 Chunker + 统一归一化后处理）。"""
    all_chunks: dict[str, list[Chunk]] = {}

    for book_name, filename in TCM_FILES.items():
        filepath = os.path.join(tcm_data_dir, filename)
        if not os.path.exists(filepath):
            logger.warning("文件不存在: %s", filepath)
            continue

        logger.info("切分 %s ...", book_name)
        with open(filepath, encoding="utf-8") as f:
            text = f.read()

        chunker = get_chunker(book_name)
        chunks = _normalize_chunks(chunker.chunk(text), book_name)
        all_chunks[book_name] = chunks
        logger.info("  %s: %d 个 chunk", book_name, len(chunks))

    # 全库内容去重（脉经底本存在整卷重复内容；重复 chunk 对检索无增益且浪费嵌入）
    import hashlib

    seen_md5: set[str] = set()
    for book_name, chunks in all_chunks.items():
        unique: list[Chunk] = []
        for c in chunks:
            fp = hashlib.md5(c.content.encode()).hexdigest()
            if fp in seen_md5:
                continue
            seen_md5.add(fp)
            unique.append(c)
        if len(unique) != len(chunks):
            logger.info("  %s: 内容去重 %d -> %d", book_name, len(chunks), len(unique))
        all_chunks[book_name] = unique

    return all_chunks


# ==================== 归一化后处理（处理各书格式差异的共性问题）====================

# 抓取源杂质行（Chinese Text Project / 中国哲学书电子化计划 的导航与版权页脚）
_BOILERPLATE_RE = re.compile(
    r"Chinese Text Project|Library Resources|Show all|Full-text search"
    r"|版权|严禁使用自动下载|违者自动封锁|在此提出|Chinese Medicine|Pre-Qin and Han"
    r"|Please confirm|请确认|人机验证|验证码|Cloudflare|challenge|captcha",
    re.IGNORECASE,
)
_MIN_CJK_RATIO = 0.3  # 中文占比低于此值的 chunk 视为垃圾
_MAX_CHUNK_LEN = 500  # 超长 chunk 再切到条文级粒度（古籍原文单条不过数百字）


def _split_long_chunk(c: Chunk, max_len: int) -> list[Chunk]:
    """超长 chunk 按句号边界再切（metadata 继承，id 加序号后缀）。

    单句超长时降级按 ；，、 二级切分，仍超长则硬切窗口。
    """
    # 二级切分：单句 > max_len 时按 ；，、 再切
    sentences: list[str] = []
    for s in c.content.split("。"):
        if not s.strip():
            continue
        if len(s) <= max_len:
            sentences.append(s)
            continue
        sub = re.split(r"([；，、])", s)  # 保留分隔符
        piece = ""
        for token in sub:
            piece += token
            if len(piece) >= max_len or (token in "；，、" and len(piece) > max_len // 3):
                sentences.append(piece)
                piece = ""
        if piece.strip():
            sentences.append(piece)

    out: list[Chunk] = []
    buf: list[str] = []
    part_no = 1
    for s in sentences:
        buf.append(s)
        # 阈值按 len+2 计（join 分隔符「。\n」占 2 字符），保证产出块不超 max_len
        if sum(len(x) + 2 for x in buf) > max_len:
            content = "。\n".join(buf[:-1]) + "。"
            if content.strip():
                out.append(Chunk(
                    id=f"{c.id}_{part_no}",
                    content=content,
                    metadata={**c.metadata, "split_from": c.id},
                ))
            part_no += 1
            buf = [buf[-1]]
    if buf:
        content = "。\n".join(buf)
        if not content.endswith("。"):
            content += "。"
        if content.strip():
            out.append(Chunk(
                id=f"{c.id}_{part_no}",
                content=content,
                metadata={**c.metadata, "split_from": c.id},
            ))
    return out or [c]


# 目录/导航块特征：编号目录行（"60. 骨空论"）或书名列表行
_TOC_LINE_RE = re.compile(r"^\s*\d{1,3}[\.、]\s*\S{1,20}\s*$|^\s*《[^》]{1,30}》\s*$")


def _is_toc_junk(content: str) -> bool:
    """
    目录/导航块判定（两类信号任一命中即判垃圾）:
    1. 非空行 ≥5 且 >50% 匹配目录行特征（编号行/书名行）
    2. 长块（>300 字）但句读标点（。！？；）密度 < 0.5% —— 古籍正文必带句读，
       无句读的长块只能是目录/列表/导航
    """
    lines = [l for l in content.splitlines() if l.strip()]
    if lines:
        toc_like = sum(1 for l in lines if _TOC_LINE_RE.match(l))
        if toc_like >= 5 and toc_like > 0.5 * len(lines):
            return True
    if len(content) > 300:
        punct = sum(content.count(p) for p in "。！？；")
        if punct < 0.005 * len(content):
            return True
    return False


def _normalize_chunks(chunks: list[Chunk], book_name: str) -> list[Chunk]:
    """
    各书 Chunker 之后的统一后处理:
    1. 剥离抓取源杂质行（CTP 导航/版权页脚）
    2. 丢弃中文占比过低的垃圾 chunk
    3. 超长 chunk 按句号边界再切（保留 metadata）
    """
    cleaned: list[Chunk] = []
    for c in chunks:
        content = _BOILERPLATE_RE.sub("", c.content)
        # 行级清洗：丢弃 ASCII 主导的行（CTP 导航行与中文正文交错时）
        lines = []
        for line in content.splitlines():
            letters = len(re.findall(r"[a-zA-Z]", line))
            cjk_line = len(re.findall(r"[一-鿿]", line))
            if letters > 3 and cjk_line < 0.15 * max(1, len(line)):
                continue
            lines.append(line)
        content = re.sub(r"\n{2,}", "\n", "\n".join(lines)).strip()
        cjk = len(re.findall(r"[一-鿿]", content))
        if len(content) < 10 or cjk < _MIN_CJK_RATIO * len(content):
            continue
        if _is_toc_junk(content):
            continue
        cleaned.append(Chunk(id=c.id, content=content, metadata=c.metadata))

    result: list[Chunk] = []
    for c in cleaned:
        if len(c.content) <= _MAX_CHUNK_LEN:
            result.append(c)
        else:
            result.extend(_split_long_chunk(c, _MAX_CHUNK_LEN))
    return result


def save_chunks_json(all_chunks: dict[str, list[Chunk]], output_dir: str) -> None:
    """将切分结果保存为 JSON 文件。"""
    os.makedirs(output_dir, exist_ok=True)

    for book_name, chunks in all_chunks.items():
        data = [
            {"id": c.id, "content": c.content, "metadata": c.metadata}
            for c in chunks
        ]
        safe_name = book_name.replace("/", "_").replace(" ", "_")
        filepath = os.path.join(output_dir, f"{safe_name}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("保存: %s (%d 条)", filepath, len(data))


def generate_mock_data(all_chunks: dict[str, list[Chunk]], output_path: str) -> None:
    """从切分结果中采样生成 mock RAG 测试数据。"""
    import random
    random.seed(42)

    mock_queries: dict = {"queries": [], "default_results": []}

    for book_name, chunks in all_chunks.items():
        sample_size = min(2, len(chunks))
        sampled = random.sample(chunks, sample_size)
        for c in sampled:
            mock_queries["default_results"].append({
                "content": c.content[:500],
                "source": book_name,
                "score": 0.6,
            })

    mock_queries["queries"] = [
        {
            "query_pattern": "脾胃虚寒|腹胀|怕冷|拉肚子",
            "results": [
                {"content": "太阴之为病，腹满而吐，食不下，自利益甚，时腹自痛。", "source": "伤寒论", "score": 0.92},
                {"content": "自利不渴者，属太阴，以其脏有寒故也。当温之，宜服四逆辈。", "source": "伤寒论", "score": 0.85},
            ],
        },
        {
            "query_pattern": "感冒|发热|恶寒|头痛",
            "results": [
                {"content": "太阳之为病，脉浮，头项强痛而恶寒。", "source": "伤寒论", "score": 0.90},
                {"content": "太阳病，发热汗出恶风，脉缓者，名为中风。", "source": "伤寒论", "score": 0.88},
            ],
        },
    ]

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(mock_queries, f, ensure_ascii=False, indent=2)
    logger.info("Mock 数据已生成: %s", output_path)


async def ingest_to_chroma(all_chunks: dict[str, list[Chunk]], settings) -> int:
    """
    将切分结果批量嵌入并写入 ChromaDB。

    使用 settings 中的 embedding 配置创建嵌入模型与 ChromaRAGClient，
    分批 add_documents（每批 BATCH_SIZE 条），确保入库与查询嵌入空间一致。
    """
    from lingyi.models.factory import create_embeddings
    from lingyi.rag.chroma import ChromaRAGClient
    from tqdm import tqdm

    BATCH_SIZE = 64
    embedder = create_embeddings(settings)
    client = ChromaRAGClient(
        chroma_db_dir=settings.chroma_db_dir,
        embedding_model=embedder,
    )

    total = 0
    skipped = 0
    # 断点续传：按内容指纹（md5）跳过已入库文档，中断后重跑只嵌入剩余部分
    existing = await client.existing_ids()
    logger.info("断点续传: 库中已有 %d 条，跳过重复", len(existing))

    for book_name, chunks in all_chunks.items():
        docs = [
            {"content": c.content, "metadata": {"book": book_name, **c.metadata}}
            for c in chunks
        ]
        # 分批入库，避免单批过大撑爆内存/embedding 请求
        for i in tqdm(
            range(0, len(docs), BATCH_SIZE),
            desc=book_name,
            unit="batch",
        ):
            batch = docs[i : i + BATCH_SIZE]
            # 跳过本批中按内容指纹已入库的文档
            import hashlib

            new_docs = [
                d for d in batch
                if hashlib.md5(d["content"].encode()).hexdigest() not in existing
            ]
            if not new_docs:
                skipped += len(batch)
                continue
            n = await client.add_documents(new_docs)
            total += n
        logger.info("%s: 入库 %d 条", book_name, len(docs))
    if skipped:
        logger.info("断点续传: 跳过已入库 %d 条", skipped)
    return total


def main():
    """主入口。"""
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description="TCM 数据入库脚本")
    parser.add_argument("--mode", choices=["json", "chroma", "mock"], default="json")
    parser.add_argument("--tcm-dir", default=str(_PROJECT_ROOT / "TCM_data"))
    parser.add_argument("--output-dir", default=str(_PROJECT_ROOT / "storage" / "chunks"))
    args = parser.parse_args()

    all_chunks = chunk_all_books(args.tcm_dir)
    total = sum(len(v) for v in all_chunks.values())
    print(f"\n总计: {len(all_chunks)} 本书, {total} 个 chunk\n")

    if args.mode == "json":
        save_chunks_json(all_chunks, args.output_dir)
        print(f"\nJSON 已保存到: {args.output_dir}")
    elif args.mode == "mock":
        mock_path = str(_PROJECT_ROOT / "storage" / "mock_rag_data.json")
        generate_mock_data(all_chunks, mock_path)
        print(f"\nMock 数据已保存到: {mock_path}")
    elif args.mode == "chroma":
        from lingyi.config import get_settings

        settings = get_settings()
        print(f"Embedding 模型: {settings.embedding_model_name} ({settings.embedding_mode})")
        total = asyncio.run(ingest_to_chroma(all_chunks, settings))
        print(f"\nChromaDB 入库完成: 共 {total} 条文档 -> {settings.chroma_db_dir}")


if __name__ == "__main__":
    main()
