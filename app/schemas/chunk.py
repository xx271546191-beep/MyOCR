"""Chunk 相关 Schema 定义。"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ChunkItem(BaseModel):
    """用于 API 响应的单个 Chunk 结构。"""

    id: int
    file_id: int
    page_no: Optional[int] = None
    chunk_type: Optional[str] = None
    text_content: Optional[str] = None
    image_path: Optional[str] = None
    bbox: Optional[dict] = None
    metadata_json: Optional[dict] = None
    created_at: datetime

    class Config:
        # 允许直接从 ORM 模型对象转换为 Pydantic 响应对象。
        from_attributes = True


class ChunkCreate(BaseModel):
    """用于创建 Chunk 的请求结构。"""

    file_id: int
    page_no: Optional[int] = None
    chunk_type: Optional[str] = None
    text_content: Optional[str] = None
    image_path: Optional[str] = None
    bbox: Optional[dict] = None
    metadata_json: Optional[dict] = None
