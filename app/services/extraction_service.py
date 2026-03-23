"""Structured extraction service."""

from __future__ import annotations

import json
import time
from typing import Any, List, Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db import models
from app.prompts.extraction_prompts import (
    EXTRACTION_SYSTEM_PROMPT,
    EXTRACTION_USER_PROMPT,
    LAYOUT_ANALYSIS_PROMPT,
    SEMANTIC_CHUNKING_PROMPT,
)
from app.schemas.extraction import (
    BlockClassification,
    CableRouteNode,
    ExtractionRequest,
    ExtractionResponse,
    LayoutAnalysisResult,
    SemanticChunk,
)
from app.services.llm_service import call_llm
from app.services.precheck_service import build_precheck_from_stored_file
from app.services.review_summary_service import (
    build_review_summary_from_nodes,
    build_review_summary_from_records,
)
from app.services.rule_check_service import RuleCheckService
from app.services.topology_service import (
    build_topology_summary_from_nodes,
    build_topology_summary_from_records,
)


class ExtractionService:
    """Orchestrates structured extraction from parsed file content."""

    def __init__(
        self,
        schema_version: str = "cable_route_v1",
        llm_model: Optional[str] = None,
    ) -> None:
        self.schema_version = schema_version
        self.llm_model = llm_model

    def extract_from_file(
        self,
        db: Session,
        request: ExtractionRequest,
    ) -> ExtractionResponse:
        """Extract structured nodes from a file and persist them."""
        start_time = time.time()

        try:
            file = db.query(models.File).filter(models.File.id == request.file_id).first()
            if not file:
                return ExtractionResponse(
                    success=False,
                    file_id=request.file_id,
                    error_message=f"File {request.file_id} not found",
                )

            pages_query = db.query(models.Page).filter(
                models.Page.file_id == request.file_id
            )
            if request.page_nos:
                pages_query = pages_query.filter(models.Page.page_no.in_(request.page_nos))
            pages = pages_query.order_by(models.Page.page_no).all()
            if not pages:
                return ExtractionResponse(
                    success=False,
                    file_id=request.file_id,
                    error_message="No pages found for extraction",
                )

            page_nos_by_id = {page.id: page.page_no for page in pages}
            all_nodes: List[CableRouteNode] = []
            all_page_nos: List[int] = []

            for page in pages:
                chunks = (
                    db.query(models.Chunk)
                    .filter(models.Chunk.page_id == page.id)
                    .order_by(models.Chunk.id)
                    .all()
                )
                parsed_content = self._build_parsed_content(page, chunks)
                nodes = self._extract_from_page(
                    file_id=request.file_id,
                    file_name=file.file_name,
                    page_no=page.page_no,
                    parsed_content=parsed_content,
                )
                if request.node_types:
                    nodes = [node for node in nodes if node.node_type in request.node_types]

                all_nodes.extend(nodes)
                all_page_nos.extend([page.page_no] * len(nodes))

            checked_nodes = RuleCheckService().check_nodes(all_nodes)
            self._persist_extractions(
                db=db,
                request=request,
                nodes=checked_nodes,
                page_nos=all_page_nos,
                selected_pages=list(page_nos_by_id.values()),
            )

            review_count = sum(1 for node in checked_nodes if node.review_required)
            low_confidence_count = sum(1 for node in checked_nodes if node.confidence < 0.7)
            risk_notice = build_precheck_from_stored_file(
                file_name=file.file_name,
                file_type=file.file_type,
                storage_path=file.storage_path,
            )
            topology_summary = build_topology_summary_from_nodes(
                checked_nodes,
                page_nos=all_page_nos,
            )
            review_summary = build_review_summary_from_nodes(
                checked_nodes,
                page_nos=all_page_nos,
                topology_summary=topology_summary,
            )
            return ExtractionResponse(
                success=True,
                file_id=request.file_id,
                schema_version=self.schema_version,
                nodes=checked_nodes,
                total_nodes=len(checked_nodes),
                review_count=review_count,
                low_confidence_count=low_confidence_count,
                processing_time_ms=(time.time() - start_time) * 1000,
                risk_notice=risk_notice,
                topology_summary=topology_summary,
                review_summary=review_summary,
            )
        except Exception as exc:
            return ExtractionResponse(
                success=False,
                file_id=request.file_id,
                error_message=f"Extraction failed: {exc}",
            )

    def get_saved_extractions(self, db: Session, file_id: int) -> ExtractionResponse:
        """Return persisted extraction rows for a file."""
        file = db.query(models.File).filter(models.File.id == file_id).first()
        risk_notice = None
        if file:
            risk_notice = build_precheck_from_stored_file(
                file_name=file.file_name,
                file_type=file.file_type,
                storage_path=file.storage_path,
            )
        records = (
            db.query(models.StructuredExtraction)
            .filter(models.StructuredExtraction.file_id == file_id)
            .order_by(models.StructuredExtraction.page_no, models.StructuredExtraction.id)
            .all()
        )
        if not records:
            return ExtractionResponse(
                success=False,
                file_id=file_id,
                error_message=f"No extraction results found for file {file_id}",
            )

        nodes = [
            CableRouteNode(
                node_id=record.node_id,
                node_type=record.node_type,
                prev_node=record.prev_node,
                next_node=record.next_node,
                distance=record.distance,
                distance_unit=record.distance_unit,
                splice_box_id=record.splice_box_id,
                slack_length=record.slack_length,
                cable_type=record.cable_type,
                fiber_count=record.fiber_count,
                remarks=record.remarks,
                confidence=record.confidence or 0.0,
                review_required=self._as_bool(record.review_required),
                uncertain_fields=record.uncertain_fields or [],
            )
            for record in records
        ]
        review_count = sum(1 for node in nodes if node.review_required)
        low_confidence_count = sum(1 for node in nodes if node.confidence < 0.7)
        topology_summary = build_topology_summary_from_records(records)
        review_summary = build_review_summary_from_records(records)
        return ExtractionResponse(
            success=True,
            file_id=file_id,
            schema_version=self.schema_version,
            nodes=nodes,
            total_nodes=len(nodes),
            review_count=review_count,
            low_confidence_count=low_confidence_count,
            processing_time_ms=0.0,
            risk_notice=risk_notice,
            topology_summary=topology_summary,
            review_summary=review_summary,
        )

    def _build_parsed_content(
        self,
        page: models.Page,
        chunks: List[models.Chunk],
    ) -> str:
        parts = [
            f"=== Page {page.page_no} ===",
            f"Page text: {page.page_text or ''}",
            f"Page summary: {page.page_summary or ''}",
        ]
        for index, chunk in enumerate(chunks, start=1):
            parts.append(f"\n--- Chunk {index} ---")
            parts.append(f"Type: {chunk.block_type or 'text'}")
            parts.append(f"Content: {chunk.text_content or ''}")
            if chunk.bbox:
                parts.append(f"BBox: {chunk.bbox}")
        return "\n".join(parts)

    def _extract_from_page(
        self,
        file_id: int,
        file_name: str,
        page_no: int,
        parsed_content: str,
    ) -> List[CableRouteNode]:
        user_prompt = EXTRACTION_USER_PROMPT.format(
            file_id=file_id,
            file_name=file_name,
            page_no=page_no,
            parsed_content=parsed_content,
        )
        try:
            response_text = call_llm(
                system_prompt=EXTRACTION_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                model=self.llm_model,
            )
            return self._parse_llm_response(response_text)
        except Exception as exc:
            print(f"LLM extraction failed for page {page_no}: {exc}")
            return []

    def _parse_llm_response(self, response_text: str) -> List[CableRouteNode]:
        json_str = response_text.strip()
        if json_str.startswith("```json"):
            json_str = json_str[7:]
        if json_str.endswith("```"):
            json_str = json_str[:-3]
        data = json.loads(json_str.strip())
        return [CableRouteNode(**node_data) for node_data in data.get("nodes", [])]

    def analyze_layout(self, page_content: str) -> LayoutAnalysisResult:
        """Analyze page layout using the LLM."""
        try:
            response_text = call_llm(
                system_prompt="You are a professional document layout analysis assistant.",
                user_prompt=LAYOUT_ANALYSIS_PROMPT.format(page_content=page_content),
                model=self.llm_model,
            )
            blocks = [
                BlockClassification(**block_data)
                for block_data in self._load_json_payload(response_text).get("blocks", [])
            ]
            return LayoutAnalysisResult(
                file_id=0,
                page_no=0,
                blocks=blocks,
                total_blocks=len(blocks),
            )
        except Exception:
            return LayoutAnalysisResult(file_id=0, page_no=0, blocks=[], total_blocks=0)

    def semantic_chunking(
        self,
        page_content: str,
        file_id: int,
        page_no: int,
    ) -> List[SemanticChunk]:
        """Split content into semantic chunks using the LLM."""
        try:
            response_text = call_llm(
                system_prompt="You are a professional semantic chunking assistant.",
                user_prompt=SEMANTIC_CHUNKING_PROMPT.format(page_content=page_content),
                model=self.llm_model,
            )
            payload = self._load_json_payload(response_text)
            chunks = []
            for chunk_data in payload.get("chunks", []):
                chunks.append(
                    SemanticChunk(
                        chunk_id=f"chunk_{file_id}_{page_no}_{uuid4().hex[:8]}",
                        file_id=file_id,
                        page_no=page_no,
                        **chunk_data,
                    )
                )
            return chunks
        except Exception as exc:
            print(f"Semantic chunking failed: {exc}")
            return []

    def _persist_extractions(
        self,
        db: Session,
        request: ExtractionRequest,
        nodes: List[CableRouteNode],
        page_nos: List[int],
        selected_pages: List[int],
    ) -> None:
        """Persist extraction rows for later query by file."""
        if request.node_types:
            return

        delete_query = db.query(models.StructuredExtraction).filter(
            models.StructuredExtraction.file_id == request.file_id
        )
        if selected_pages:
            delete_query = delete_query.filter(
                models.StructuredExtraction.page_no.in_(selected_pages)
            )
        delete_query.delete(synchronize_session=False)

        for index, node in enumerate(nodes):
            db.add(
                models.StructuredExtraction(
                    file_id=request.file_id,
                    page_no=page_nos[index] if index < len(page_nos) else None,
                    node_id=node.node_id,
                    node_type=node.node_type,
                    prev_node=node.prev_node,
                    next_node=node.next_node,
                    distance=node.distance,
                    distance_unit=node.distance_unit or "m",
                    splice_box_id=node.splice_box_id,
                    slack_length=node.slack_length,
                    cable_type=node.cable_type,
                    fiber_count=node.fiber_count,
                    remarks=node.remarks,
                    confidence=node.confidence,
                    review_required="true" if node.review_required else "false",
                    uncertain_fields=node.uncertain_fields,
                    schema_version=self.schema_version,
                )
            )
        db.commit()

    def _load_json_payload(self, text: str) -> dict[str, Any]:
        json_str = text.strip()
        if json_str.startswith("```json"):
            json_str = json_str[7:]
        if json_str.endswith("```"):
            json_str = json_str[:-3]
        return json.loads(json_str.strip())

    def _as_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)


def extract_from_file(db: Session, request: ExtractionRequest) -> ExtractionResponse:
    return ExtractionService().extract_from_file(db, request)


def analyze_layout(page_content: str) -> LayoutAnalysisResult:
    return ExtractionService().analyze_layout(page_content)


def semantic_chunking(
    page_content: str,
    file_id: int,
    page_no: int,
) -> List[SemanticChunk]:
    return ExtractionService().semantic_chunking(page_content, file_id, page_no)
