"""Review summary unit test."""

from __future__ import annotations

import sys
from pathlib import Path

backend_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend_root))

from app.schemas.extraction import CableRouteNode
from app.services.review_summary_service import build_review_summary_from_nodes
from app.services.topology_service import build_topology_summary_from_nodes


def main() -> int:
    nodes = [
        CableRouteNode(
            node_id="J001",
            node_type="joint",
            next_node="J002",
            distance=120.0,
            distance_unit=None,
            confidence=0.62,
            review_required=True,
            uncertain_fields=["distance_unit"],
        ),
        CableRouteNode(
            node_id="J002",
            node_type="joint",
            prev_node="J999",
            confidence=0.88,
            review_required=True,
            uncertain_fields=["prev_node"],
        ),
        CableRouteNode(
            node_id="J003",
            node_type="joint",
            next_node="J404",
            confidence=0.91,
            review_required=True,
            uncertain_fields=[],
        ),
        CableRouteNode(
            node_id="J004",
            node_type="joint",
            confidence=0.95,
            review_required=False,
            uncertain_fields=[],
        ),
    ]
    page_nos = [1, 2, 2, 3]
    topology_summary = build_topology_summary_from_nodes(nodes, page_nos=page_nos)
    review_summary = build_review_summary_from_nodes(
        nodes,
        page_nos=page_nos,
        topology_summary=topology_summary,
    )

    assert review_summary.review_required_node_count == 3
    assert review_summary.review_required_node_ids == ["J001", "J002", "J003"]
    assert review_summary.issue_counts["low_confidence"] == 1
    assert review_summary.issue_counts["uncertain_fields"] == 2
    assert review_summary.issue_counts["relation_mismatch"] == 1
    assert review_summary.issue_counts["missing_target"] == 2
    assert review_summary.issue_counts["orphan_node"] == 1
    assert review_summary.issue_counts["cross_page_link"] == 1
    assert "topology_relations" in review_summary.recommended_sections
    assert "cross_page_links" in review_summary.recommended_sections
    assert "node_confidence" in review_summary.recommended_sections
    assert any(item.issue_type == "missing_target" and item.node_id == "J003" for item in review_summary.focus_items)
    assert any(item.issue_type == "relation_mismatch" and item.node_id == "J001" for item in review_summary.focus_items)
    assert any(item.issue_type == "orphan_node" and item.node_id == "J004" for item in review_summary.focus_items)
    assert "复核" in (review_summary.summary_message or "")

    print("review summary ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
