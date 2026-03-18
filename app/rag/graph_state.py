from typing import TypedDict, List, Dict, Any, Optional
from sqlalchemy.orm import Session


class RagGraphState(TypedDict, total=False):
    query: str
    file_id: Optional[str]
    db: Session
    retrieved_chunks: List[Dict[str, Any]]
    context_text: str
    answer: str
    citations: List[Dict[str, Any]]
    error: Optional[str]
