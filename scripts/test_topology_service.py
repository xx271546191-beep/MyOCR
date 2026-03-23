"""Topology summary unit test."""

from __future__ import annotations

import sys
from pathlib import Path

backend_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend_root))

from app.schemas.extraction import CableRouteNode
from app.services.topology_service import build_topology_summary_from_nodes


def main() -> int:
    nodes = [
        CableRouteNode(node_id="J001", node_type="joint", next_node="J002"),
        CableRouteNode(node_id="J002", node_type="joint", prev_node="J001", next_node="J003"),
        CableRouteNode(node_id="J003", node_type="joint", prev_node="J002"),
        CableRouteNode(node_id="J099", node_type="joint"),
        CableRouteNode(node_id="J404", node_type="joint", next_node="J405"),
    ]
    topology_summary = build_topology_summary_from_nodes(
        nodes,
        page_nos=[1, 2, 2, 3, 4],
    )

    assert topology_summary.total_relations == 5
    assert topology_summary.confirmed_relations == 4
    assert topology_summary.broken_relation_count == 1
    assert topology_summary.cross_page_relation_count == 2
    assert topology_summary.orphan_node_ids == ["J099"]
    assert topology_summary.broken_relations[0].target_node_id == "J405"
    assert topology_summary.broken_relations[0].status == "missing_target"
    assert "review_cross_page_links" in topology_summary.review_focus
    assert "verify_missing_target_nodes" in topology_summary.review_focus
    assert "review_orphan_nodes" in topology_summary.review_focus
    assert topology_summary.cross_page_hint.has_cross_page_links is True
    assert topology_summary.cross_page_hint.review_required is True
    assert topology_summary.cross_page_hint.focus_pages == [1, 2]
    assert topology_summary.cross_page_hint.recommended_action == "review_cross_page_sequence"
    assert len(topology_summary.cross_page_hint.cross_page_links) == 2
    assert "跨页" in topology_summary.cross_page_hint.review_message

    print("topology summary ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
