from pydantic import BaseModel
from typing import List, Optional


class SearchRequest(BaseModel):
    file_id: Optional[str] = None
    query: str
    top_k: int = 5


class CitationItem(BaseModel):
    chunk_id: str
    page_no: Optional[int] = None
    score: Optional[float] = None
    text_preview: Optional[str] = None
    image_path: Optional[str] = None


class SearchResponse(BaseModel):
    answer: str
    citations: List[CitationItem]
