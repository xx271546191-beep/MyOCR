"""拓扑关系摘要相关 Schema。"""

from pydantic import BaseModel, Field


class TopologyRelationItemResponse(BaseModel):
    """单条节点关系引用的摘要结果。"""

    relation_field: str
    source_node_id: str
    target_node_id: str
    source_page_no: int | None = None
    target_page_no: int | None = None
    status: str
    reason: str | None = None
    cross_page: bool = False


class TopologyCrossPageHintResponse(BaseModel):
    """跨页关系的聚合提示。"""

    has_cross_page_links: bool = False
    review_required: bool = False
    focus_pages: list[int] = Field(default_factory=list)
    cross_page_links: list[TopologyRelationItemResponse] = Field(default_factory=list)
    recommended_action: str | None = None
    review_message: str | None = None


class TopologySummaryResponse(BaseModel):
    """结构化抽取结果对应的关系恢复摘要。"""

    total_relations: int = 0
    confirmed_relations: int = 0
    broken_relation_count: int = 0
    cross_page_relation_count: int = 0
    orphan_node_ids: list[str] = Field(default_factory=list)
    relation_pairs: list[TopologyRelationItemResponse] = Field(default_factory=list)
    broken_relations: list[TopologyRelationItemResponse] = Field(default_factory=list)
    review_focus: list[str] = Field(default_factory=list)
    cross_page_hint: TopologyCrossPageHintResponse = Field(
        default_factory=TopologyCrossPageHintResponse
    )
