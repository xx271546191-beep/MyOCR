from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ChunkItem(BaseModel):
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
        from_attributes = True


class ChunkCreate(BaseModel):
    file_id: int
    page_no: Optional[int] = None
    chunk_type: Optional[str] = None
    text_content: Optional[str] = None
    image_path: Optional[str] = None
    bbox: Optional[dict] = None
    metadata_json: Optional[dict] = None
