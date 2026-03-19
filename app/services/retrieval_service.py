from sqlalchemy.orm import Session
from sqlalchemy import func, text
from typing import List, Optional, Dict, Any
from app.db import models
from app.services import embedding_service
from app.core.config import settings


class RetrievalService:
    def __init__(self, db: Session):
        self.db = db

    def _is_postgres(self) -> bool:
        return settings.DATABASE_URL.startswith("postgresql")

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
            embedding_model=settings.EMBEDDING_MODEL_NAME,
            embedding=embedding_vector
        )
        self.db.add(embedding)
        self.db.commit()
        self.db.refresh(chunk)
        return chunk

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        if not vec1 or not vec2:
            return 0.0
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(dot_product / (norm1 * norm2))

    def _coerce_vector(self, raw: Any) -> Optional[List[float]]:
        if raw is None:
            return None

        if isinstance(raw, list):
            if raw and all(isinstance(x, (int, float)) for x in raw):
                return [float(x) for x in raw]
            return None

        if isinstance(raw, str):
            import json
            import ast
            s = raw.strip()
            if not s:
                return None
            try:
                parsed = json.loads(s)
            except Exception:
                parsed = None
            if parsed is None:
                try:
                    parsed = ast.literal_eval(s)
                except Exception:
                    return None
            if isinstance(parsed, list) and parsed and all(isinstance(x, (int, float)) for x in parsed):
                return [float(x) for x in parsed]
            return None

        return None

    def search_similar_chunks(
        self,
        query: str,
        file_id: Optional[int] = None,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        query_vector = embedding_service.embed_text(query)

        if self._is_postgres():
            return self._search_pgvector(query_vector, file_id, top_k)
        else:
            return self._search_python_fallback(query_vector, file_id, top_k)

    def _search_pgvector(
        self,
        query_vector: List[float],
        file_id: Optional[int] = None,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        query_text = "[" + ",".join(str(x) for x in query_vector) + "]"

        sql = """
            SELECT c.id as chunk_id, c.file_id, c.page_no, c.text_content,
                   c.image_path, c.bbox, c.metadata_json,
                   1 - (e.embedding <=> :query_vec::vector) as score
            FROM chunks c
            JOIN embeddings e ON c.id = e.chunk_id
            WHERE e.embedding IS NOT NULL
        """

        if file_id:
            sql += f" AND c.file_id = {file_id}"

        sql += f" ORDER BY score DESC LIMIT {top_k}"

        result = self.db.execute(text(sql), {"query_vec": query_text})

        rows = result.fetchall()
        print(f"pgvector found {len(rows)} similar chunks")

        if not rows:
            all_chunks = self.db.query(models.Chunk).all()
            results = []
            for chunk in all_chunks[:top_k]:
                results.append({
                    "chunk_id": str(chunk.id),
                    "file_id": chunk.file_id,
                    "page_no": chunk.page_no,
                    "text_content": chunk.text_content,
                    "image_path": chunk.image_path,
                    "bbox": chunk.bbox,
                    "score": 0.0
                })
            return results

        results = []
        for row in rows:
            results.append({
                "chunk_id": str(row.chunk_id),
                "file_id": row.file_id,
                "page_no": row.page_no,
                "text_content": row.text_content,
                "image_path": row.image_path,
                "bbox": row.bbox,
                "score": float(row.score)
            })

        return results

    def _search_python_fallback(
        self,
        query_vector: List[float],
        file_id: Optional[int] = None,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        all_chunks = self.db.query(models.Chunk).all()
        print(f"Found {len(all_chunks)} chunks in database")

        stmt = self.db.query(models.Chunk, models.Embedding)
        stmt = stmt.join(models.Embedding, models.Chunk.id == models.Embedding.chunk_id)
        if file_id:
            stmt = stmt.filter(models.Chunk.file_id == file_id)

        chunk_embeddings = stmt.all()
        print(f"Found {len(chunk_embeddings)} chunk-embedding pairs")

        if not chunk_embeddings:
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
            chunk_vector = self._coerce_vector(embedding.embedding)
            score = self._cosine_similarity(query_vector, chunk_vector) if chunk_vector else 0.0

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
        if self._is_postgres():
            return self._search_pgvector(vector, file_id, top_k)
        else:
            return self._search_python_fallback(vector, file_id, top_k)
