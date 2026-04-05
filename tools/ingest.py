import os
import re
import hashlib
from typing import List, Dict
from tqdm import tqdm

# 从模型工厂导入向量模型实例
from model_provider import model_manager
# 使用修复后的 vector_client 实例名
from tools.vector_db_client import vector_client


class TCMIngestor:
    def __init__(self, data_dir: str = "../TCM_data"):
        self.data_dir = data_dir
        self.embeddings_model = model_manager.get_embeddings()
        self.max_chunk_len = 1000

        self.parse_configs = {
            "神农本草经_完整清洗版.txt": {"func": self._parse_by_pattern, "pattern": r'\n(?=\d+\n)'},
            "脉经_完整清洗版.txt": {"func": self._parse_by_pattern, "pattern": r'\n(?=\d+\n)'},
            "黄帝内经-素问_完整清洗版.txt": {"func": self._parse_by_pattern, "pattern": r'\n(?=\d+\.\s)'},
            "温病条辨_完整清洗版.txt": {"func": self._parse_by_pattern, "pattern": r'\n(?=[一二三四五六七八九十]+、)'},
            "伤寒论_完整清洗版.txt": {"func": self._parse_by_paragraph, "min_len": 15},
            "金匮要略_完整清洗版.txt": {"func": self._parse_by_paragraph, "min_len": 15}
        }

    def _clean_text(self, text: str) -> str:
        text = re.sub(r'中国哲学书电子化计划.*?\n', '', text)
        text = re.sub(r'#.*?\n', '', text)
        text = re.sub(r'\n\s*\n', '\n', text)
        return text.strip()

    def _split_long_chunk(self, text: str) -> List[str]:
        if len(text) <= self.max_chunk_len:
            return [text]
        sub_chunks = re.split(r'([。；])', text)
        result = []
        current = ""
        for i in range(0, len(sub_chunks) - 1, 2):
            part = sub_chunks[i] + sub_chunks[i + 1]
            if len(current) + len(part) <= self.max_chunk_len:
                current += part
            else:
                if current: result.append(current)
                current = part
        if current: result.append(current)
        final_result = []
        for r in result:
            if len(r) > self.max_chunk_len:
                for j in range(0, len(r), self.max_chunk_len):
                    final_result.append(r[j:j + self.max_chunk_len])
            else:
                final_result.append(r)
        return final_result

    def _parse_by_pattern(self, content: str, pattern: str) -> List[str]:
        entries = re.split(pattern, content)
        all_sub_chunks = []
        for e in entries:
            cleaned = self._clean_text(e)
            if len(cleaned) > 5:
                all_sub_chunks.extend(self._split_long_chunk(cleaned))
        return all_sub_chunks

    def _parse_by_paragraph(self, content: str, min_len: int = 10) -> List[str]:
        paragraphs = content.split('\n\n')
        all_sub_chunks = []
        for p in paragraphs:
            cleaned = self._clean_text(p)
            if len(cleaned) >= min_len:
                all_sub_chunks.extend(self._split_long_chunk(cleaned))
        return all_sub_chunks

    def run_ingestion(self):
        print(f"🎋 灵医 RAG 数据入库引擎启动...")

        all_chunks = []
        for filename, config in self.parse_configs.items():
            file_path = os.path.join(self.data_dir, filename)
            if not os.path.exists(file_path): continue

            print(f"📖 正在解析: {filename}")
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            if config["func"] == self._parse_by_pattern:
                chunks = config["func"](content, config["pattern"])
            else:
                chunks = config["func"](content, config.get("min_len", 10))

            book_name = filename.replace("_完整清洗版.txt", "")
            for chunk in chunks:
                all_chunks.append({
                    "content": chunk,
                    "metadata": {"source": book_name}
                })

        print(f"✅ 解析完成，共计 {len(all_chunks)} 个知识块。")

        is_local = os.getenv("EMBEDDING_STRATEGY", "local") == "local"
        batch_size = 32 if is_local else 16

        for i in tqdm(range(0, len(all_chunks), batch_size)):
            batch = all_chunks[i:i + batch_size]
            ids, texts, metadatas = [], [], []

            for idx, item in enumerate(batch):
                content = item["content"]
                # 包含索引以确保 ID 绝对唯一，避免单批次重复报错
                raw_id = f"{content}_{item['metadata']['source']}_{i + idx}"
                doc_id = hashlib.md5(raw_id.encode()).hexdigest()
                ids.append(doc_id)
                texts.append(content)
                metadatas.append(item["metadata"])

            try:
                embeddings = self.embeddings_model.embed_documents(texts)
                # 使用 vector_client 实例
                vector_client.add_documents(ids=ids, documents=texts, metadatas=metadatas, embeddings=embeddings)
            except Exception as e:
                print(f"\n⚠️ 批次 {i // batch_size} 异常，重试单条入库: {e}")
                for j in range(len(ids)):
                    try:
                        emb = self.embeddings_model.embed_documents([texts[j]])
                        vector_client.add_documents([ids[j]], [texts[j]], [metadatas[j]], emb)
                    except Exception as single_e:
                        print(f"❌ 严重错误 (ID: {ids[j]}): {single_e}")

        print(f"🎉 任务完成！知识库当前总量: {vector_client.get_collection_stats()}")


if __name__ == "__main__":
    ingestor = TCMIngestor()
    ingestor.run_ingestion()