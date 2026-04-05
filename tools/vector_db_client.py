import chromadb
import os
import hashlib
from typing import List, Dict, Any
# 导入模型工厂，确保检索和入库使用同一个模型实例
from model_provider import model_manager


class VectorDBClient:
    """
    中医药知识库向量检索客户端。
    已修复：显式使用 BGE-M3 进行查询向量化，确保检索准确性。
    """

    def __init__(self, db_path: str = "./storage/chroma_db"):
        if not os.path.exists(db_path):
            os.makedirs(db_path)

        self.client = chromadb.PersistentClient(path=db_path)
        self.collection_name = "tcm_classics"

        self._embedding_model = None

        # 2. 获取集合
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}
        )

    @property
    def embedding_model(self):
        if self._embedding_model is None:
            self._embedding_model = model_manager.get_embeddings()
        return self._embedding_model

    def search(self, query: str, top_k: int = 3) -> List[str]:
        """
        原有接口：根据查询词检索相关中医文献。
        已修复：通过显式 embed_query 统一向量空间。
        """
        # 3. 手动将文本转化为向量，避免 Chroma 使用默认的 MiniLM 模型
        query_embedding = self.embedding_model.embed_query(query)

        results = self.collection.query(
            query_embeddings=[query_embedding],  # 使用 embeddings 字段检索
            n_results=top_k,
            include=["documents"]
        )

        if results['documents'] and len(results['documents']) > 0:
            return results['documents'][0]
        return []

    def hybrid_search(self, query_text: str, n_results: int = 10) -> List[Dict]:
        """
        进阶接口：执行混合检索逻辑。
        """
        query_embedding = self.embedding_model.embed_query(query_text)

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            include=["documents", "metadatas", "distances"]
        )

        formatted_results = []
        if results['ids']:
            for i in range(len(results['ids'][0])):
                formatted_results.append({
                    "id": results['ids'][0][i],
                    "content": results['documents'][0][i],
                    "metadata": results['metadatas'][0][i],
                    "score": 1 - results['distances'][0][i]
                })
        return formatted_results

    def add_documents(self, ids: List[str], documents: List[str], metadatas: List[Dict],
                      embeddings: List[List[float]] = None):
        self.collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings
        )

    def get_collection_stats(self):
        return self.collection.count()


# 统一导出名为 vector_client 的实例
vector_client = VectorDBClient()