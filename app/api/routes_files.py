"""文件管理相关 API 路由。

负责处理文件上传、文件列表查询、文件详情查询和手动重跑 ingest。
当前实现重点是把上传入口与后端 ingest 主链打通，并对外暴露稳定响应结构。
"""

from pathlib import Path
from typing import Tuple
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db import models
from app.db.session import get_db
from app.schemas.file import (
    FileDetailResponse,
    FileDemoReadinessResponse,
    FileExtractionSummaryResponse,
    FileExtractionPreviewItemResponse,
    FileIngestResponse,
    FileListResponse,
    FileOverviewResponse,
    FilePrecheckResponse,
    FileQueryHistoryResponse,
    FileQueryLogItemResponse,
    FileQuerySummaryResponse,
    FileSummaryResponse,
    FileUploadResponse,
)
from app.schemas.task import TaskStatusResponse
from app.services.ingest_service import IngestService
from app.services.precheck_service import (
    build_precheck_from_stored_file,
    build_precheck_summary,
)
from app.services.review_summary_service import build_review_summary_from_records
from app.services.topology_service import build_topology_summary_from_records


router = APIRouter()

SUPPORTED_TEXT_TYPES = {".txt", ".md", ".json", ".csv"}
SUPPORTED_PDF_TYPE = ".pdf"
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".gif"}


def _backend_root() -> Path:
    """返回 backend 根目录。"""
    return Path(__file__).resolve().parents[2]


def _extract_text_from_pdf(file_content: bytes) -> str:
    """从 PDF 二进制内容中提取文本。

    这里的目的不是把 PDF 转成最终存储内容，而是做“是否可解析”的预检查。
    真正落盘时仍保留原始 PDF 字节，避免后续 parser_service 把文本文件误当 PDF。
    """
    try:
        import io
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(file_content))
        text_parts = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)
        return "\n".join(text_parts)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"PDF parsing failed: {exc}")


async def _read_text_from_upload(file: UploadFile) -> Tuple[bytes, str, str]:
    """读取上传文件并返回可落盘字节与内部文件类型。

    返回值约定：
    1. 第一个元素始终是最终写入磁盘的字节内容
    2. 第二个元素是系统内部识别用的文件类型
    3. 第三个元素是预检使用的可抽取文本
    """
    filename = file.filename or "uploaded"
    suffix = Path(filename).suffix.lower()
    raw = await file.read()

    if suffix in SUPPORTED_TEXT_TYPES or (file.content_type or "").startswith("text/"):
        text = raw.decode("utf-8", errors="ignore")
        return text.encode("utf-8", errors="ignore"), "text", text

    if suffix == SUPPORTED_PDF_TYPE or file.content_type == "application/pdf":
        text = _extract_text_from_pdf(raw)
        if not text or not text.strip():
            raise HTTPException(status_code=400, detail="PDF contains no extractable text")
        return raw, "pdf", text

    if suffix in IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Image OCR is not supported yet. Please upload text or PDF files.",
        )

    raise HTTPException(
        status_code=400,
        detail="Unsupported file type. Please upload .txt, .md, .json, .csv, or .pdf files.",
    )


def _parse_task_status(parse_status: str | None) -> TaskStatusResponse:
    """把数据库里的 `parse_status` 规整成统一 task 视图。"""
    raw = (parse_status or "pending").strip()
    if ":" in raw:
        status, detail = raw.split(":", 1)
        return TaskStatusResponse(status=status.strip(), detail=detail.strip() or None)
    return TaskStatusResponse(status=raw, detail=None)


def _build_upload_response(
    file: models.File,
    result,
    message: str,
    precheck: FilePrecheckResponse,
) -> FileUploadResponse:
    """构造上传接口响应。"""
    task = _parse_task_status(result.status if getattr(result, "status", None) else file.parse_status)
    return FileUploadResponse(
        file_id=file.id,
        filename=file.file_name,
        pages=getattr(result, "pages_count", 0),
        chunks=getattr(result, "chunks_count", 0),
        status=getattr(result, "status", file.parse_status),
        message=message,
        task=task,
        precheck=precheck,
    )


def _build_ingest_response(
    file: models.File,
    result,
    message: str,
) -> FileIngestResponse:
    """构造手动 ingest 接口响应。"""
    task = _parse_task_status(result.status if getattr(result, "status", None) else file.parse_status)
    precheck = build_precheck_from_stored_file(
        file_name=file.file_name,
        file_type=file.file_type,
        storage_path=file.storage_path,
    )
    return FileIngestResponse(
        file_id=file.id,
        filename=file.file_name,
        pages=getattr(result, "pages_count", 0),
        chunks=getattr(result, "chunks_count", 0),
        status=getattr(result, "status", file.parse_status),
        message=message,
        task=task,
        precheck=precheck,
    )


def _reset_file_artifacts(db: Session, file_id: int) -> None:
    """清理派生结果，确保手动 ingest 可以幂等重跑。

    这里不会删除原始文件记录，只删除由 ingest 产生的页面、块、向量和抽取结果。
    """
    chunk_ids = [
        row[0]
        for row in db.query(models.Chunk.id).filter(models.Chunk.file_id == file_id).all()
    ]
    if chunk_ids:
        db.query(models.Embedding).filter(models.Embedding.chunk_id.in_(chunk_ids)).delete(
            synchronize_session=False
        )
    db.query(models.StructuredExtraction).filter(
        models.StructuredExtraction.file_id == file_id
    ).delete(synchronize_session=False)
    db.query(models.Chunk).filter(models.Chunk.file_id == file_id).delete(
        synchronize_session=False
    )
    db.query(models.Page).filter(models.Page.file_id == file_id).delete(
        synchronize_session=False
    )
    db.commit()


def _build_extraction_summary(db: Session, file_id: int) -> FileExtractionSummaryResponse:
    """构造文件级抽取摘要，供列表和详情展示使用。"""
    rows = (
        db.query(models.StructuredExtraction)
        .filter(models.StructuredExtraction.file_id == file_id)
        .all()
    )
    if not rows:
        return FileExtractionSummaryResponse(has_saved_extraction=False)

    review_count = sum(
        1
        for row in rows
        if str(row.review_required).strip().lower() in {"1", "true", "yes", "on"}
    )
    low_confidence_count = sum(1 for row in rows if (row.confidence or 0.0) < 0.7)
    schema_version = rows[0].schema_version if rows else None
    return FileExtractionSummaryResponse(
        has_saved_extraction=True,
        schema_version=schema_version,
        total_nodes=len(rows),
        review_count=review_count,
        low_confidence_count=low_confidence_count,
    )


def _build_query_summary(db: Session, file_id: int) -> FileQuerySummaryResponse:
    """构造文件级查询摘要。"""
    rows = (
        db.query(models.QueryLog)
        .filter(models.QueryLog.file_id == file_id)
        .order_by(models.QueryLog.created_at.desc(), models.QueryLog.id.desc())
        .all()
    )
    if not rows:
        return FileQuerySummaryResponse(total_queries=0)

    latest = rows[0]
    answer_preview = (latest.answer_text or "")[:120] or None
    return FileQuerySummaryResponse(
        total_queries=len(rows),
        latest_query_text=latest.query_text,
        latest_answer_preview=answer_preview,
    )


def _build_recent_queries(
    db: Session,
    file_id: int,
    limit: int = 5,
) -> list[FileQueryLogItemResponse]:
    """构造文件最近查询列表。"""
    rows = (
        db.query(models.QueryLog)
        .filter(models.QueryLog.file_id == file_id)
        .order_by(models.QueryLog.created_at.desc(), models.QueryLog.id.desc())
        .limit(limit)
        .all()
    )
    return [
        FileQueryLogItemResponse(
            query_id=row.id,
            query_text=row.query_text,
            answer_text=row.answer_text,
            retrieved_chunk_ids=row.retrieved_chunk_ids or [],
            latency_ms=row.latency_ms,
            created_at=row.created_at.isoformat() if row.created_at else None,
        )
        for row in rows
    ]


def _build_recent_extractions(
    db: Session,
    file_id: int,
    limit: int = 5,
) -> list[FileExtractionPreviewItemResponse]:
    """构造最近结构化抽取节点预览。"""
    rows = (
        db.query(models.StructuredExtraction)
        .filter(models.StructuredExtraction.file_id == file_id)
        .order_by(models.StructuredExtraction.created_at.desc(), models.StructuredExtraction.id.desc())
        .limit(limit)
        .all()
    )
    return [
        FileExtractionPreviewItemResponse(
            node_id=row.node_id,
            node_type=row.node_type,
            prev_node=row.prev_node,
            next_node=row.next_node,
            distance=row.distance,
            distance_unit=row.distance_unit,
            confidence=row.confidence,
            review_required=str(row.review_required).strip().lower() in {"1", "true", "yes", "on"},
        )
        for row in rows
    ]


def _build_demo_readiness(
    task: TaskStatusResponse,
    precheck: FilePrecheckResponse,
    extraction_summary: FileExtractionSummaryResponse,
) -> FileDemoReadinessResponse:
    """构造文件级 Demo 就绪状态。"""
    blockers: list[str] = []
    recovery_suggestions: list[str] = []
    primary_action = None

    if task.status != "indexed":
        blockers.append("task_not_indexed")
        recovery_suggestions.append("rerun_ingest_until_indexed")
    if precheck.recommended_path == "search_only":
        blockers.append("precheck_limited_to_search")
        recovery_suggestions.append("use_search_only_flow")
    if not precheck.is_standard_demo_ready:
        blockers.append("not_standard_demo_sample")
        recovery_suggestions.append("switch_to_standard_q1_sample")
    if not extraction_summary.has_saved_extraction:
        blockers.append("no_saved_extraction")
        recovery_suggestions.append("run_extract_then_refresh_overview")

    if "task_not_indexed" in blockers:
        primary_action = "run_ingest"
    elif "no_saved_extraction" in blockers:
        primary_action = "run_extract"
    elif "precheck_limited_to_search" in blockers:
        primary_action = "use_search_only_flow"
    elif "not_standard_demo_sample" in blockers:
        primary_action = "switch_sample"

    status_label = "ready" if not blockers else "needs_attention"
    return FileDemoReadinessResponse(
        is_ready=not blockers,
        status_label=status_label,
        blockers=blockers,
        primary_action=primary_action,
        recovery_suggestions=recovery_suggestions,
    )


def _build_topology_summary(db: Session, file_id: int):
    """构造文件级关系恢复摘要。"""
    rows = (
        db.query(models.StructuredExtraction)
        .filter(models.StructuredExtraction.file_id == file_id)
        .order_by(models.StructuredExtraction.page_no, models.StructuredExtraction.id)
        .all()
    )
    return build_topology_summary_from_records(rows)


def _build_review_summary(db: Session, file_id: int):
    """构造文件级复核摘要。"""
    rows = (
        db.query(models.StructuredExtraction)
        .filter(models.StructuredExtraction.file_id == file_id)
        .order_by(models.StructuredExtraction.page_no, models.StructuredExtraction.id)
        .all()
    )
    return build_review_summary_from_records(rows)


@router.post("/files/upload", response_model=FileUploadResponse)
@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """上传文件并立即执行 ingest。

    处理流程：
    1. 校验文件类型并读取内容
    2. 落盘到本地上传目录
    3. 创建 `files` 记录
    4. 调用 ingest_service 跑完整主链
    5. 返回统一的文件上传响应
    """
    stored_bytes, file_type, extractable_text = await _read_text_from_upload(file)

    upload_dir = _backend_root() / "storage" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    safe_name = Path(file.filename or "uploaded.txt").name
    stored_name = f"{uuid4().hex}_{safe_name}"
    stored_path = upload_dir / stored_name
    stored_path.write_bytes(stored_bytes)
    precheck = build_precheck_summary(
        file_name=safe_name,
        file_type=file_type,
        extractable_text=extractable_text,
    )

    db_file = models.File(
        file_name=safe_name,
        file_type=file_type,
        storage_path=str(stored_path),
        parse_status="pending",
        source_type="upload",
    )
    db.add(db_file)
    db.commit()
    db.refresh(db_file)

    try:
        result = IngestService().ingest_file(db, db_file)
        if not result.success:
            raise HTTPException(status_code=500, detail=f"Ingest failed: {result.error_message}")
        db.refresh(db_file)
        return _build_upload_response(
            db_file,
            result,
            "File processed successfully",
            precheck=precheck,
        )
    except Exception as exc:
        db_file.parse_status = f"failed: {exc}"
        db.add(db_file)
        db.commit()
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=500, detail=f"Processing failed: {exc}")


@router.post("/files/{file_id}/ingest", response_model=FileIngestResponse)
def ingest_file_manually(file_id: int, db: Session = Depends(get_db)):
    """手动触发指定文件重新 ingest。

    该接口主要用于开发验证和阶段性验收：
    1. 检查文件记录和原始落盘文件是否存在
    2. 清理旧的派生结果
    3. 把状态重置为 pending
    4. 再次执行 ingest 主链
    """
    db_file = db.query(models.File).filter(models.File.id == file_id).first()
    if not db_file:
        raise HTTPException(status_code=404, detail="File not found")
    if not db_file.storage_path or not Path(db_file.storage_path).exists():
        raise HTTPException(status_code=400, detail="Stored file is missing")

    _reset_file_artifacts(db, file_id)
    db_file.parse_status = "pending"
    db.add(db_file)
    db.commit()
    db.refresh(db_file)

    result = IngestService().ingest_file(db, db_file)
    db.refresh(db_file)
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error_message or "Ingest failed")
    return _build_ingest_response(db_file, result, "Ingest completed successfully")


@router.get("/files", response_model=FileListResponse)
def list_files(db: Session = Depends(get_db)):
    """查询已上传文件列表。"""
    files = db.query(models.File).order_by(models.File.id).all()
    return FileListResponse(
        files=[
            FileSummaryResponse(
                id=file.id,
                name=file.file_name,
                precheck=build_precheck_from_stored_file(
                    file_name=file.file_name,
                    file_type=file.file_type,
                    storage_path=file.storage_path,
                ),
                extraction_summary=_build_extraction_summary(db, file.id),
                query_summary=_build_query_summary(db, file.id),
            )
            for file in files
        ]
    )


@router.get("/files/{file_id}", response_model=FileDetailResponse)
def get_file(file_id: int, db: Session = Depends(get_db)):
    """查询单个文件详情及其规范化任务状态。"""
    db_file = db.query(models.File).filter(models.File.id == file_id).first()
    if not db_file:
        raise HTTPException(status_code=404, detail="File not found")
    precheck = build_precheck_from_stored_file(
        file_name=db_file.file_name,
        file_type=db_file.file_type,
        storage_path=db_file.storage_path,
    )
    return FileDetailResponse(
        id=db_file.id,
        file_name=db_file.file_name,
        file_type=db_file.file_type,
        parse_status=db_file.parse_status,
        task=_parse_task_status(db_file.parse_status),
        precheck=precheck,
        extraction_summary=_build_extraction_summary(db, db_file.id),
        query_summary=_build_query_summary(db, db_file.id),
    )


@router.get("/files/{file_id}/queries", response_model=FileQueryHistoryResponse)
def get_file_queries(file_id: int, db: Session = Depends(get_db)):
    """读取指定文件的查询历史。"""
    db_file = db.query(models.File).filter(models.File.id == file_id).first()
    if not db_file:
        raise HTTPException(status_code=404, detail="File not found")

    rows = (
        db.query(models.QueryLog)
        .filter(models.QueryLog.file_id == file_id)
        .order_by(models.QueryLog.created_at.desc(), models.QueryLog.id.desc())
        .all()
    )
    return FileQueryHistoryResponse(
        file_id=file_id,
        total_queries=len(rows),
        queries=_build_recent_queries(db, file_id, limit=max(len(rows), 1)),
    )


@router.get("/files/{file_id}/overview", response_model=FileOverviewResponse)
def get_file_overview(file_id: int, db: Session = Depends(get_db)):
    """返回单个文件的聚合概览视图。"""
    db_file = db.query(models.File).filter(models.File.id == file_id).first()
    if not db_file:
        raise HTTPException(status_code=404, detail="File not found")

    precheck = build_precheck_from_stored_file(
        file_name=db_file.file_name,
        file_type=db_file.file_type,
        storage_path=db_file.storage_path,
    )
    task = _parse_task_status(db_file.parse_status)
    extraction_summary = _build_extraction_summary(db, db_file.id)
    return FileOverviewResponse(
        file_id=db_file.id,
        file_name=db_file.file_name,
        file_type=db_file.file_type,
        parse_status=db_file.parse_status,
        task=task,
        precheck=precheck,
        extraction_summary=extraction_summary,
        query_summary=_build_query_summary(db, db_file.id),
        recent_queries=_build_recent_queries(db, db_file.id, limit=5),
        recent_extractions=_build_recent_extractions(db, db_file.id, limit=5),
        topology_summary=_build_topology_summary(db, db_file.id),
        review_summary=_build_review_summary(db, db_file.id),
        demo_readiness=_build_demo_readiness(task, precheck, extraction_summary),
    )
