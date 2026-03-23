"""检索服务模块

负责从向量数据库中检索与查询相关的 chunks
支持 PostgreSQL + pgvector 原生检索和 Python fallback 检索
提供相似度计算、向量转换等底层能力
支持可选的 rerank 重排序
"""

from sqlalchemy.orm import Session
from sqlalchemy import func, text
from typing import List, Optional, Dict, Any, Tuple
from app.db import models
from app.services import embedding_service
from app.services.llm_service import call_llm
from app.core.config import settings


class RetrievalService:
    """检索服务类
    
    负责基于向量相似度检索相关 chunks
    支持两种检索模式:
    1. PostgreSQL + pgvector: 生产环境推荐，性能优
    2. Python fallback: 开发环境兼容，无需 pgvector
    
    Attributes:
        db: 数据库会话对象
    """
    
    def __init__(self, db: Session):
        """初始化检索服务
        
        Args:
            db: SQLAlchemy 数据库会话
        """
        self.db = db

    def _is_postgres(self) -> bool:
        """判断当前是否使用 PostgreSQL 数据库
        
        Returns:
            bool: True 表示使用 PostgreSQL，False 表示其他数据库
        """
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
        """保存 chunk 并生成对应的向量嵌入
        
        将 chunk 文本内容向量化后与 chunk 记录一起保存到数据库
        用于文件上传后的自动索引流程
        
        Args:
            file_id: 所属文件 ID
            page_no: 页码 (可选)
            chunk_type: chunk 类型 (如 text, table 等)
            text_content: chunk 文本内容
            image_path: chunk 对应图片路径 (可选)
            bbox: bounding box 坐标 (可选)
            metadata: 其他元数据 (可选)
            
        Returns:
            models.Chunk: 保存后的 chunk 对象
        """
        # 创建 chunk 记录
        chunk = models.Chunk(
            file_id=file_id,
            page_no=page_no,
            block_type=chunk_type,
            text_content=text_content,
            image_path=image_path,
            bbox=bbox,
            metadata_json=metadata
        )
        self.db.add(chunk)
        self.db.flush()

        # 生成向量嵌入并保存
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
        """计算两个向量之间的余弦相似度
        
        公式：cos(θ) = (A·B) / (||A|| * ||B||)
        值域：[-1, 1], 越接近 1 表示越相似
        
        Args:
            vec1: 向量 1
            vec2: 向量 2
            
        Returns:
            float: 余弦相似度分数
        """
        if not vec1 or not vec2:
            return 0.0
        # 计算点积
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        # 计算向量模长
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(dot_product / (norm1 * norm2))

    def _coerce_vector(self, raw: Any) -> Optional[List[float]]:
        """将原始数据转换为 float 向量列表
        
        支持多种输入格式：list, JSON 字符串，Python 字面量字符串
        用于兼容不同数据库驱动返回的向量格式
        
        Args:
            raw: 原始数据，可能是 list、JSON 字符串或其他格式
            
        Returns:
            List[float]: 转换后的 float 向量，失败返回 None
        """
        if raw is None:
            return None

        # 如果已经是 list 类型
        if isinstance(raw, list):
            if raw and all(isinstance(x, (int, float)) for x in raw):
                return [float(x) for x in raw]
            return None

        # 如果是字符串，尝试 JSON 解析或 ast.literal_eval
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
        """检索与查询文本最相似的 chunks
        
        主入口方法，自动选择 pgvector 或 fallback 检索模式
        返回按相似度降序排列的 chunk 列表
        
        Args:
            query: 查询文本
            file_id: 限定检索的文件 ID (可选，None 表示全局检索)
            top_k: 返回最相似的 K 个结果
            
        Returns:
            List[Dict[str, Any]]: chunk 列表，每个包含 chunk_id, text_content, score 等
        """
        # 生成查询向量
        query_vector = embedding_service.embed_text(query)

        # 根据数据库类型选择检索方式
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
        """使用 PostgreSQL pgvector 扩展进行向量检索
        
        利用 pgvector 的 <=> 余弦距离算子进行高效检索
        性能优，推荐生产环境使用
        
        Args:
            query_vector: 查询向量
            file_id: 限定检索的文件 ID (可选)
            top_k: 返回结果数量
            
        Returns:
            List[Dict[str, Any]]: chunk 列表，按相似度降序
        """
        # 将向量转换为 PostgreSQL 数组格式
        query_text = "[" + ",".join(str(x) for x in query_vector) + "]"

        # 构建 SQL 查询，使用 pgvector 的余弦距离算子
        # 1 - (embedding <=> query_vec) 将距离转换为相似度分数
        sql = """
            SELECT c.id as chunk_id, c.file_id, c.page_no, c.text_content,
                   c.image_path, c.bbox, c.metadata_json,
                   1 - (e.embedding <=> :query_vec::vector) as score
            FROM chunks c
            JOIN embeddings e ON c.id = e.chunk_id
            WHERE e.embedding IS NOT NULL
        """

        # 可选：限定文件范围
        if file_id:
            sql += f" AND c.file_id = {file_id}"

        # 按相似度降序，取 top_k
        sql += f" ORDER BY score DESC LIMIT {top_k}"

        result = self.db.execute(text(sql), {"query_vec": query_text})

        rows = result.fetchall()
        print(f"pgvector found {len(rows)} similar chunks")

        # 兼容模式：如果 pgvector 检索失败，返回一些默认结果
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

        # 构建结果列表
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
        """使用 Python 计算余弦相似度的 fallback 检索方案
        
        在不支持 pgvector 的环境中 (如 SQLite) 使用
        性能较差，但保证了开发环境的兼容性
        
        Args:
            query_vector: 查询向量
            file_id: 限定检索的文件 ID (可选)
            top_k: 返回结果数量
            
        Returns:
            List[Dict[str, Any]]: chunk 列表，按相似度降序
        """
        all_chunks = self.db.query(models.Chunk).all()
        print(f"Found {len(all_chunks)} chunks in database")

        # 查询所有 chunk 及其 embeddings
        stmt = self.db.query(models.Chunk, models.Embedding)
        stmt = stmt.join(models.Embedding, models.Chunk.id == models.Embedding.chunk_id)
        if file_id:
            stmt = stmt.filter(models.Chunk.file_id == file_id)

        chunk_embeddings = stmt.all()
        print(f"Found {len(chunk_embeddings)} chunk-embedding pairs")

        # 兼容模式：如果没有 embeddings，返回一些默认结果
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

        # 遍历所有 chunk-embedding 对，计算相似度
        results = []
        for chunk, embedding in chunk_embeddings:
            # 转换向量为标准格式
            chunk_vector = self._coerce_vector(embedding.embedding)
            # 计算余弦相似度
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

        # 按相似度降序排序
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def search_by_vector(
        self,
        vector: List[float],
        file_id: Optional[int] = None,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """直接使用向量进行检索 (不生成 query embedding)
        
        适用于已有查询向量的场景，避免重复计算
        
        Args:
            vector: 查询向量
            file_id: 限定检索的文件 ID (可选)
            top_k: 返回结果数量
            
        Returns:
            List[Dict[str, Any]]: chunk 列表，按相似度降序
        """
        if self._is_postgres():
            return self._search_pgvector(vector, file_id, top_k)
        else:
            return self._search_python_fallback(vector, file_id, top_k)
    
    def search_with_rerank(
        self,
        query: str,
        file_id: Optional[int] = None,
        top_k: int = 5,
        rerank_top_k: int = 3,
        use_rerank: bool = True
    ) -> List[Dict[str, Any]]:
        """检索并可选 rerank 重排序
        
        增强的检索方法，支持使用 LLM 进行重排序
        
        Args:
            query: 查询文本
            file_id: 限定检索的文件 ID (可选)
            top_k: 初始检索返回数量
            rerank_top_k: rerank 后返回数量
            use_rerank: 是否使用 rerank，默认 True
            
        Returns:
            List[Dict[str, Any]]: rerank 后的 chunk 列表
            
        处理流程:
            1. 向量检索获取 top_k 个候选
            2. 使用 LLM 评估每个 chunk 与 query 的相关性
            3. 按相关性分数重排序
            4. 返回 top rerank_top_k 个结果
        """
        # Step 1: 向量检索
        candidates = self.search_similar_chunks(query, file_id, top_k)
        
        if not candidates or not use_rerank:
            return candidates[:rerank_top_k]
        
        # Step 2: LLM rerank
        reranked = self._rerank_with_llm(query, candidates, rerank_top_k)
        
        return reranked
    
    def _rerank_with_llm(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """使用 LLM 进行 rerank 重排序
        
        Args:
            query: 查询文本
            candidates: 候选 chunk 列表
            top_k: 返回数量
            
        Returns:
            List[Dict[str, Any]]: rerank 后的 chunk 列表
        """
        # 构建 rerank prompt
        prompt = self._build_rerank_prompt(query, candidates)
        
        try:
            # 调用 LLM
            response = call_llm(
                system_prompt="你是一个专业的检索结果排序助手。请评估每个候选 chunk 与查询的相关性，并给出 0-1 的相关性分数。",
                user_prompt=prompt,
                model=None
            )
            
            # 解析 LLM 返回的分数
            scores = self._parse_rerank_response(response, len(candidates))
            
            # 更新候选结果的分数
            for i, candidate in enumerate(candidates):
                if i < len(scores):
                    candidate["rerank_score"] = scores[i]
            
            # 按 rerank 分数排序
            candidates.sort(key=lambda x: x.get("rerank_score", 0.0), reverse=True)
            
            return candidates[:top_k]
            
        except Exception as e:
            # LLM rerank 失败时，返回原始结果
            print(f"LLM rerank failed: {str(e)}, using original ranking")
            return candidates[:top_k]
    
    def _build_rerank_prompt(
        self,
        query: str,
        candidates: List[Dict[str, Any]]
    ) -> str:
        """构建 rerank prompt
        
        Args:
            query: 查询文本
            candidates: 候选 chunk 列表
            
        Returns:
            str: rerank prompt
        """
        prompt_parts = [
            f"查询：{query}\n",
            "请评估以下候选文本片段与查询的相关性，给出 0-1 的分数 (1 表示完全相关，0 表示完全不相关)：\n"
        ]
        
        for i, candidate in enumerate(candidates, 1):
            prompt_parts.append(f"\n候选 {i}:\n{candidate['text_content']}\n")
        
        prompt_parts.append("\n请以 JSON 格式输出，格式为：{\"scores\": [0.9, 0.7, 0.8, ...]}\n")
        
        return "".join(prompt_parts)
    
    def _parse_rerank_response(
        self,
        response: str,
        expected_count: int
    ) -> List[float]:
        """解析 LLM rerank 响应
        
        Args:
            response: LLM 返回的文本
            expected_count: 期望的分数数量
            
        Returns:
            List[float]: 分数列表
        """
        import json
        
        try:
            # 尝试提取 JSON
            json_str = response.strip()
            if json_str.startswith("```json"):
                json_str = json_str[7:]
            if json_str.endswith("```"):
                json_str = json_str[:-3]
            json_str = json_str.strip()
            
            data = json.loads(json_str)
            scores = data.get("scores", [])
            
            # 验证分数数量
            if len(scores) != expected_count:
                print(f"Expected {expected_count} scores, got {len(scores)}")
            
            # 验证分数范围
            scores = [max(0.0, min(1.0, float(s))) for s in scores]
            
            return scores
            
        except Exception as e:
            print(f"Failed to parse rerank response: {str(e)}")
            # 返回默认分数
            return [0.5] * expected_count
