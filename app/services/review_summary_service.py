"""复核摘要聚合服务。"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

from app.db import models
from app.schemas.extraction import CableRouteNode
from app.schemas.review import ReviewFocusItemResponse, ReviewSummaryResponse
from app.schemas.topology import TopologySummaryResponse
from app.services.topology_service import (
    build_topology_summary_from_nodes,
    build_topology_summary_from_records,
)


@dataclass
class _ReviewNode:
    """统一的复核分析输入。"""

    node_id: str | None
    confidence: float
    review_required: bool
    uncertain_fields: list[str]
    page_no: int | None = None


def build_review_summary_from_nodes(
    nodes: list[CableRouteNode],
    page_nos: list[int] | None = None,
    topology_summary: TopologySummaryResponse | None = None,
) -> ReviewSummaryResponse:
    """从内存节点列表构建复核摘要。"""
    entries = [
        _ReviewNode(
            node_id=node.node_id,
            confidence=node.confidence,
            review_required=node.review_required,
            uncertain_fields=node.uncertain_fields or [],
            page_no=page_nos[index] if page_nos and index < len(page_nos) else None,
        )
        for index, node in enumerate(nodes)
    ]
    topology_summary = topology_summary or build_topology_summary_from_nodes(nodes, page_nos=page_nos)
    return _build_review_summary(entries, topology_summary)


def build_review_summary_from_records(
    records: Iterable[models.StructuredExtraction],
) -> ReviewSummaryResponse:
    """从持久化抽取记录构建复核摘要。"""
    records = list(records)
    entries = [
        _ReviewNode(
            node_id=record.node_id,
            confidence=record.confidence or 0.0,
            review_required=_as_bool(record.review_required),
            uncertain_fields=record.uncertain_fields or [],
            page_no=record.page_no,
        )
        for record in records
    ]
    topology_summary = build_topology_summary_from_records(records)
    return _build_review_summary(entries, topology_summary)


def _build_review_summary(
    entries: list[_ReviewNode],
    topology_summary: TopologySummaryResponse,
) -> ReviewSummaryResponse:
    issue_counts: dict[str, int] = defaultdict(int)
    focus_items: list[ReviewFocusItemResponse] = []
    recommended_sections: list[str] = []

    review_required_node_ids: list[str] = []
    for entry in entries:
        node_id = _normalize_node_id(entry.node_id)
        if node_id is not None and entry.review_required and node_id not in review_required_node_ids:
            review_required_node_ids.append(node_id)
    page_by_node_id = {
        node_id: entry.page_no
        for entry in entries
        if (node_id := _normalize_node_id(entry.node_id)) is not None
    }

    for entry in entries:
        node_id = _normalize_node_id(entry.node_id)
        if node_id is None:
            continue

        if entry.confidence < 0.7:
            issue_counts["low_confidence"] += 1
            focus_items.append(
                ReviewFocusItemResponse(
                    issue_type="low_confidence",
                    node_id=node_id,
                    page_no=entry.page_no,
                    severity="medium",
                    message=f"{node_id} 的置信度较低，建议优先复核。",
                )
            )

        if entry.uncertain_fields:
            issue_counts["uncertain_fields"] += 1
            focus_items.append(
                ReviewFocusItemResponse(
                    issue_type="uncertain_fields",
                    node_id=node_id,
                    page_no=entry.page_no,
                    fields=entry.uncertain_fields,
                    severity="medium",
                    message=f"{node_id} 存在不确定字段，建议结合原图复核。",
                )
            )

    for relation in topology_summary.broken_relations:
        if relation.source_node_id not in review_required_node_ids:
            review_required_node_ids.append(relation.source_node_id)
        if relation.status == "missing_target":
            issue_counts["missing_target"] += 1
            focus_items.append(
                ReviewFocusItemResponse(
                    issue_type="missing_target",
                    node_id=relation.source_node_id,
                    page_no=relation.source_page_no,
                    related_node_id=relation.target_node_id,
                    severity="high",
                    message=(
                        f"{relation.source_node_id} 指向 {relation.target_node_id} 的关系未在当前结果中闭合，"
                        "建议补查目标节点。"
                    ),
                )
            )
        elif relation.status == "mismatch":
            issue_counts["relation_mismatch"] += 1
            focus_items.append(
                ReviewFocusItemResponse(
                    issue_type="relation_mismatch",
                    node_id=relation.source_node_id,
                    page_no=relation.source_page_no,
                    related_node_id=relation.target_node_id,
                    severity="high",
                    message=(
                        f"{relation.source_node_id} 与 {relation.target_node_id} 的前后关系存在不一致，"
                        "建议人工核对连接顺序。"
                    ),
                )
            )

    for node_id in topology_summary.orphan_node_ids:
        issue_counts["orphan_node"] += 1
        focus_items.append(
            ReviewFocusItemResponse(
                issue_type="orphan_node",
                node_id=node_id,
                page_no=page_by_node_id.get(node_id),
                severity="medium",
                message=f"{node_id} 当前没有前后连接关系，建议确认是否为孤立节点或缺失链路。",
            )
        )

    for relation in topology_summary.cross_page_hint.cross_page_links:
        issue_counts["cross_page_link"] += 1
        focus_items.append(
            ReviewFocusItemResponse(
                issue_type="cross_page_link",
                node_id=relation.source_node_id,
                page_no=relation.source_page_no,
                related_node_id=relation.target_node_id,
                severity="medium",
                message=(
                    f"{relation.source_node_id} 与 {relation.target_node_id} 存在跨页连接，"
                    "建议结合前后页顺序复核。"
                ),
            )
        )

    if issue_counts.get("low_confidence") or issue_counts.get("uncertain_fields"):
        recommended_sections.append("node_confidence")
    if (
        issue_counts.get("missing_target")
        or issue_counts.get("relation_mismatch")
        or issue_counts.get("orphan_node")
    ):
        recommended_sections.append("topology_relations")
    if issue_counts.get("cross_page_link"):
        recommended_sections.append("cross_page_links")

    summary_message = None
    if review_required_node_ids or focus_items:
        summary_message = (
            f"当前共有 {len(review_required_node_ids)} 个需重点复核的节点，"
            f"共识别 {len(focus_items)} 项复核重点。"
        )

    return ReviewSummaryResponse(
        review_required_node_count=len(review_required_node_ids),
        review_required_node_ids=review_required_node_ids,
        issue_counts=dict(issue_counts),
        focus_items=focus_items,
        recommended_sections=recommended_sections,
        summary_message=summary_message,
    )


def _normalize_node_id(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    return normalized or None


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
