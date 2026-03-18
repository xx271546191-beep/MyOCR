from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional, Dict, Any
from app.db import models
from app.services import embedding_service
import numpy as np


class RetrievalService:
    def __init__(self, db: Session):
        self.db = db

    def save_chunk_with_embedding(
        self,
        file_id: int,
        page_no: Optional[int],
        chunk_type: str,
        text_content: str,
        image_path: Optional[str] = None,
        bbox: Optional[dict] = None,
        metadata: Optional[dict] = None
    ) -> models.Chunk:
        chunk = models.Chunk(
            file_id=file_id,
            page_no=page_no,
            chunk_type=chunk_type,
            text_content=text_content,
            image_path=image_path,
            bbox=bbox,
            metadata_json=metadata
        )
        self.db.add(chunk)
        self.db.flush()

        embedding_vector = embedding_service.embed_text(text_content)

        embedding = models.Embedding(
            chunk_id=chunk.id,
            embedding_model="qwen3-vl-embedding",
            embedding=str(embedding_vector)
        )
        self.db.add(embedding)
        self.db.commit()
        self.db.refresh(chunk)
        return chunk

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        v1 = np.array(vec1)
        v2 = np.array(vec2)
        dot_product = np.dot(v1, v2)
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(dot_product / (norm1 * norm2))

    def search_similar_chunks(
        self,
        query: str,
        file_id: Optional[int] = None,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        # 为查询生成嵌入向量
        query_vector = embedding_service.embed_text(query)

        # 先查询所有chunks
        all_chunks = self.db.query(models.Chunk).all()
        print(f"Found {len(all_chunks)} chunks in database")

        # 查询chunks及其对应的embeddings
        stmt = self.db.query(models.Chunk, models.Embedding)
        stmt = stmt.join(models.Embedding, models.Chunk.id == models.Embedding.chunk_id)
        if file_id:
            stmt = stmt.filter(models.Chunk.file_id == file_id)

        chunk_embeddings = stmt.all()
        print(f"Found {len(chunk_embeddings)} chunk-embedding pairs")

        if not chunk_embeddings:
            # 如果没有embeddings，直接返回chunks
            results = []
            for chunk in all_chunks:
                results.append({
                    "chunk_id": str(chunk.id),
                    "file_id": chunk.file_id,
                    "page_no": chunk.page_no,
                    "text_content": chunk.text_content,
                    "image_path": chunk.image_path,
                    "bbox": chunk.bbox,
                    "score": 0.0
                })
            return results[:top_k]

        results = []
        for chunk, embedding in chunk_embeddings:
            # 解析嵌入向量
            try:
                chunk_vector = eval(embedding.embedding)
                # 计算余弦相似度
                score = self._cosine_similarity(query_vector, chunk_vector)
            except:
                score = 0.0
            
            results.append({
                "chunk_id": str(chunk.id),
                "file_id": chunk.file_id,
                "page_no": chunk.page_no,
                "text_content": chunk.text_content,
                "image_path": chunk.image_path,
                "bbox": chunk.bbox,
                "score": score
            })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def search_by_vector(
        self,
        vector: List[float],
        file_id: Optional[int] = None,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        # 查询chunks及其对应的embeddings
        stmt = self.db.query(models.Chunk, models.Embedding)
        stmt = stmt.join(models.Embedding, models.Chunk.id == models.Embedding.chunk_id)
        if file_id:
            stmt = stmt.filter(models.Chunk.file_id == file_id)

        chunk_embeddings = stmt.all()

        if not chunk_embeddings:
            return []

        results = []
        for chunk, embedding in chunk_embeddings:
            # 解析嵌入向量
            try:
                chunk_vector = eval(embedding.embedding)
                # 计算余弦相似度
                score = self._cosine_similarity(vector, chunk_vector)
            except:
                score = 0.0
            
            results.append({
                "chunk_id": str(chunk.id),
                "file_id": chunk.file_id,
                "page_no": chunk.page_no,
                "text_content": chunk.text_content,
                "image_path": chunk.image_path,
                "bbox": chunk.bbox,
                "score": score
            })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]
