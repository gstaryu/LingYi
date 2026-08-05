"""
Chroma RAG 冒烟测试 - 用真实 Qwen3-Embedding-0.6B 验证向量检索全链路。

不依赖全量 ingest（2616 chunk 在 CPU 上过慢），仅用少量典型条文验证：
嵌入 -> 入库（显式传 embeddings）-> 查询（同模型嵌入）-> 召回相关条文。
模型从本地缓存加载（需先下载过一次）。
"""

import asyncio
import os
import shutil

# 直连 HF（hf-mirror 在本环境不可达）；模型已缓存时仅校验不下载
os.environ["HF_ENDPOINT"] = "https://huggingface.co"


async def main():
    from lingyi.config import Settings
    from lingyi.models.factory import create_embeddings
    from lingyi.rag.chroma import ChromaRAGClient

    settings = Settings(_env_file=None, embedding_device="cpu")
    embedder = create_embeddings(settings)

    smoke_dir = "storage/chroma_smoke"
    if os.path.exists(smoke_dir):
        shutil.rmtree(smoke_dir, ignore_errors=True)

    client = ChromaRAGClient(chroma_db_dir=smoke_dir, embedding_model=embedder)

    docs = [
        {"content": "太阳之为病，脉浮，头项强痛而恶寒。", "metadata": {"book": "伤寒论"}},
        {"content": "太阴之为病，腹满而吐，食不下，自利益甚。", "metadata": {"book": "伤寒论"}},
        {"content": "少阳之为病，口苦，咽干，目眩也。", "metadata": {"book": "伤寒论"}},
        {"content": "阳明之为病，胃家实是也。", "metadata": {"book": "伤寒论"}},
        {"content": "少阴之为病，脉微细，但欲寐也。", "metadata": {"book": "伤寒论"}},
    ]
    n = await client.add_documents(docs)
    print(f"[1] 入库 {n} 条文档（Qwen3-Embedding-0.6B 嵌入）")

    results = await client.search("发热恶寒头项强痛", top_k=3)
    print(f"[2] 查询 '发热恶寒头项强痛' 召回 {len(results)} 条：")
    for r in results:
        print(f"    [{r.source}] score={r.score:.3f} | {r.content[:40]}")

    assert len(results) > 0, "FAIL: 无召回结果"
    assert any("太阳" in r.content for r in results), "FAIL: 太阳病条文未召回"
    print("[3] SMOKE TEST PASSED: chroma RAG 全链路（Qwen3 嵌入->入库->检索）正常")


if __name__ == "__main__":
    asyncio.run(main())
