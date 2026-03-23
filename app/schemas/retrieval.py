"""搜索问答相关 Schema。"""

from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.file import FilePrecheckResponse


class SearchRequest(BaseModel):
    """搜索问答请求。"""

    file_id: Optional[str] = None
    query: str
    top_k: int = 5


class CitationItem(BaseModel):
    """单条检索引用。"""

    chunk_id: str
    page_no: Optional[int] = None
    score: Optional[float] = None
    text_preview: Optional[str] = None
    image_path: Optional[str] = None


class SearchQuestionAnalysisResponse(BaseModel):
    """搜索问答的题型识别和回答来源分析。"""

    matched: bool
    question_type: Optional[str] = None
    answer_mode: str = "rag"
    matched_node_id: Optional[str] = None
    relation_field: Optional[str] = None
    related_node_id: Optional[str] = None
    relation_status: Optional[str] = None
    review_required: bool = False
    reason: Optional[str] = None


class SearchResponse(BaseModel):
    """搜索问答响应。"""

    answer: str
    citations: List[CitationItem]
    risk_notice: Optional[FilePrecheckResponse] = None
    question_analysis: SearchQuestionAnalysisResponse = Field(
        default_factory=lambda: SearchQuestionAnalysisResponse(
            matched=False,
            answer_mode="rag",
        )
    )
