"""文件相关 API Schema。"""

from pydantic import BaseModel, Field

from app.schemas.review import ReviewSummaryResponse
from app.schemas.task import TaskStatusResponse
from app.schemas.topology import TopologySummaryResponse


class FilePrecheckResponse(BaseModel):
    """文件预检结果。"""

    quality_grade: str
    recommended_path: str
    result_nature: str = "draft"
    review_emphasis: bool
    is_standard_demo_ready: bool
    reasons: list[str]


class FileExtractionSummaryResponse(BaseModel):
    """文件级结构化抽取摘要。"""

    has_saved_extraction: bool
    schema_version: str | None = None
    total_nodes: int = 0
    review_count: int = 0
    low_confidence_count: int = 0


class FileQuerySummaryResponse(BaseModel):
    """文件级查询摘要。"""

    total_queries: int = 0
    latest_query_text: str | None = None
    latest_answer_preview: str | None = None


class FileQueryLogItemResponse(BaseModel):
    """单条查询日志响应。"""

    query_id: int
    query_text: str
    answer_text: str | None = None
    retrieved_chunk_ids: list[int | str] = []
    latency_ms: float | None = None
    created_at: str | None = None


class FileQueryHistoryResponse(BaseModel):
    """文件级查询历史响应。"""

    file_id: int
    total_queries: int
    queries: list[FileQueryLogItemResponse]


class FileExtractionPreviewItemResponse(BaseModel):
    """最近结构化抽取节点预览。"""

    node_id: str | None = None
    node_type: str | None = None
    prev_node: str | None = None
    next_node: str | None = None
    distance: float | None = None
    distance_unit: str | None = None
    confidence: float | None = None
    review_required: bool = False


class FileDemoReadinessResponse(BaseModel):
    """文件级 Demo 就绪状态。"""

    is_ready: bool
    status_label: str
    blockers: list[str]
    primary_action: str | None = None
    recovery_suggestions: list[str] = []


class FileOverviewResponse(BaseModel):
    """文件聚合概览响应。"""

    file_id: int
    file_name: str
    file_type: str
    parse_status: str
    task: TaskStatusResponse
    precheck: FilePrecheckResponse
    extraction_summary: FileExtractionSummaryResponse | None = None
    query_summary: FileQuerySummaryResponse | None = None
    recent_queries: list[FileQueryLogItemResponse] = []
    recent_extractions: list[FileExtractionPreviewItemResponse] = []
    topology_summary: TopologySummaryResponse = Field(default_factory=TopologySummaryResponse)
    review_summary: ReviewSummaryResponse = Field(default_factory=ReviewSummaryResponse)
    demo_readiness: FileDemoReadinessResponse


class FileSummaryResponse(BaseModel):
    """文件列表中的简要信息。"""

    id: int
    name: str
    precheck: FilePrecheckResponse | None = None
    extraction_summary: FileExtractionSummaryResponse | None = None
    query_summary: FileQuerySummaryResponse | None = None


class FileListResponse(BaseModel):
    """文件列表响应。"""

    files: list[FileSummaryResponse]


class FileDetailResponse(BaseModel):
    """文件详情响应。"""

    id: int
    file_name: str
    file_type: str
    parse_status: str
    task: TaskStatusResponse
    precheck: FilePrecheckResponse
    extraction_summary: FileExtractionSummaryResponse | None = None
    query_summary: FileQuerySummaryResponse | None = None


class FileUploadResponse(BaseModel):
    """文件上传并完成 ingest 后的响应。"""

    file_id: int
    filename: str
    pages: int
    chunks: int
    status: str
    message: str
    task: TaskStatusResponse
    precheck: FilePrecheckResponse


class FileIngestResponse(BaseModel):
    """手动触发 ingest 后的响应。"""

    file_id: int
    filename: str
    pages: int
    chunks: int
    status: str
    message: str
    task: TaskStatusResponse
    precheck: FilePrecheckResponse
