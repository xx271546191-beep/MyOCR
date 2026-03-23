"""结构化抽取结果的关系恢复摘要服务。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.db import models
from app.schemas.extraction import CableRouteNode
from app.schemas.topology import (
    TopologyCrossPageHintResponse,
    TopologyRelationItemResponse,
    TopologySummaryResponse,
)


@dataclass
class _TopologyNode:
    """统一的节点关系分析输入。"""

    node_id: str | None
    prev_node: str | None
    next_node: str | None
    page_no: int | None = None


def build_topology_summary_from_nodes(
    nodes: list[CableRouteNode],
    page_nos: list[int] | None = None,
) -> TopologySummaryResponse:
    """从内存中的节点列表构建拓扑摘要。"""
    entries = [
        _TopologyNode(
            node_id=node.node_id,
            prev_node=node.prev_node,
            next_node=node.next_node,
            page_no=page_nos[index] if page_nos and index < len(page_nos) else None,
        )
        for index, node in enumerate(nodes)
    ]
    return _build_topology_summary(entries)


def build_topology_summary_from_records(
    records: Iterable[models.StructuredExtraction],
) -> TopologySummaryResponse:
    """从持久化抽取记录构建拓扑摘要。"""
    entries = [
        _TopologyNode(
            node_id=record.node_id,
            prev_node=record.prev_node,
            next_node=record.next_node,
            page_no=record.page_no,
        )
        for record in records
    ]
    return _build_topology_summary(entries)


def _build_topology_summary(entries: list[_TopologyNode]) -> TopologySummaryResponse:
    node_map = {
        node_id: entry
        for entry in entries
        if (node_id := _normalize_node_id(entry.node_id)) is not None
    }
    relation_pairs: list[TopologyRelationItemResponse] = []
    broken_relations: list[TopologyRelationItemResponse] = []
    orphan_node_ids: list[str] = []
    confirmed_relations = 0
    cross_page_relation_count = 0
    cross_page_links: list[TopologyRelationItemResponse] = []

    for entry in entries:
        source_node_id = _normalize_node_id(entry.node_id)
        if source_node_id is None:
            continue

        prev_node = _normalize_node_id(entry.prev_node)
        next_node = _normalize_node_id(entry.next_node)
        if prev_node is None and next_node is None:
            orphan_node_ids.append(source_node_id)

        for relation_field, target_node_id, reciprocal_field in (
            ("prev_node", prev_node, "next_node"),
            ("next_node", next_node, "prev_node"),
        ):
            if target_node_id is None:
                continue

            target_entry = node_map.get(target_node_id)
            target_page_no = target_entry.page_no if target_entry else None
            cross_page = (
                target_entry is not None
                and entry.page_no is not None
                and target_entry.page_no is not None
                and entry.page_no != target_entry.page_no
            )
            if cross_page:
                cross_page_relation_count += 1

            status = "confirmed"
            reason = None
            if target_entry is None:
                status = "missing_target"
                reason = "target_node_missing"
            else:
                reciprocal_value = _normalize_node_id(getattr(target_entry, reciprocal_field))
                if reciprocal_value != source_node_id:
                    status = "mismatch"
                    reason = f"target_{reciprocal_field}_mismatch"

            relation_item = TopologyRelationItemResponse(
                relation_field=relation_field,
                source_node_id=source_node_id,
                target_node_id=target_node_id,
                source_page_no=entry.page_no,
                target_page_no=target_page_no,
                status=status,
                reason=reason,
                cross_page=cross_page,
            )
            relation_pairs.append(relation_item)
            if cross_page:
                cross_page_links.append(relation_item)
            if status == "confirmed":
                confirmed_relations += 1
            else:
                broken_relations.append(relation_item)

    review_focus: list[str] = []
    if any(item.status == "missing_target" for item in broken_relations):
        review_focus.append("verify_missing_target_nodes")
    if any(item.status == "mismatch" for item in broken_relations):
        review_focus.append("check_reciprocal_node_links")
    if cross_page_relation_count > 0:
        review_focus.append("review_cross_page_links")
    if orphan_node_ids:
        review_focus.append("review_orphan_nodes")

    focus_pages = sorted(
        {
            page_no
            for item in cross_page_links
            for page_no in (item.source_page_no, item.target_page_no)
            if page_no is not None
        }
    )
    cross_page_hint = TopologyCrossPageHintResponse(
        has_cross_page_links=bool(cross_page_links),
        review_required=bool(cross_page_links),
        focus_pages=focus_pages,
        cross_page_links=cross_page_links,
        recommended_action=(
            "review_cross_page_sequence" if cross_page_links else None
        ),
        review_message=(
            "检测到跨页关系连接，建议结合前后页顺序和图纸上下文复核。"
            if cross_page_links
            else None
        ),
    )

    return TopologySummaryResponse(
        total_relations=len(relation_pairs),
        confirmed_relations=confirmed_relations,
        broken_relation_count=len(broken_relations),
        cross_page_relation_count=cross_page_relation_count,
        orphan_node_ids=orphan_node_ids,
        relation_pairs=relation_pairs,
        broken_relations=broken_relations,
        review_focus=review_focus,
        cross_page_hint=cross_page_hint,
    )


def _normalize_node_id(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
