"""复核视图相关 Schema。"""

from pydantic import BaseModel, Field


class ReviewFocusItemResponse(BaseModel):
    """单条复核重点项。"""

    issue_type: str
    node_id: str | None = None
    page_no: int | None = None
    related_node_id: str | None = None
    fields: list[str] = Field(default_factory=list)
    severity: str = "medium"
    message: str


class ReviewSummaryResponse(BaseModel):
    """结构化抽取结果的复核摘要。"""

    review_required_node_count: int = 0
    review_required_node_ids: list[str] = Field(default_factory=list)
    issue_counts: dict[str, int] = Field(default_factory=dict)
    focus_items: list[ReviewFocusItemResponse] = Field(default_factory=list)
    recommended_sections: list[str] = Field(default_factory=list)
    summary_message: str | None = None
