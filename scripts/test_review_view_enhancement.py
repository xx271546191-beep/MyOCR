"""Review view enhancement integration test."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

backend_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend_root))

os.environ["EMBEDDING_PROVIDER"] = "mock"

from app.api import routes_extract, routes_files, routes_search
from app.db import models
from app.db.base import Base
from app.db.session import get_db
from app.rag import graph_nodes
from app.services import extraction_service as extraction_service_module


def build_test_app(SessionLocal):
    app = FastAPI()
    app.include_router(routes_search.router, prefix="/api/v1")
    app.include_router(routes_files.router, prefix="/api/v1")
    app.include_router(routes_extract.router, prefix="/api/v1")

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return app


def main() -> int:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    test_app = build_test_app(SessionLocal)

    original_generate_answer = graph_nodes.generate_answer
    original_call_llm = extraction_service_module.call_llm

    def fake_generate_answer(prompt: str) -> str:
        return "mock answer"

    def fake_call_llm(system_prompt: str, user_prompt: str, model=None, images=None) -> str:
        if "=== Page 1 ===" in user_prompt:
            payload = {
                "nodes": [
                    {
                        "node_id": "J001",
                        "node_type": "joint",
                        "next_node": "J010",
                        "distance": 88.0,
                        "distance_unit": None,
                        "confidence": 0.62,
                        "review_required": False,
                        "uncertain_fields": [],
                    }
                ]
            }
        else:
            payload = {
                "nodes": [
                    {
                        "node_id": "J010",
                        "node_type": "joint",
                        "prev_node": "J999",
                        "confidence": 0.91,
                        "review_required": False,
                        "uncertain_fields": [],
                    },
                    {
                        "node_id": "J020",
                        "node_type": "joint",
                        "confidence": 0.95,
                        "review_required": False,
                        "uncertain_fields": [],
                    },
                ]
            }
        return json.dumps(payload, ensure_ascii=False)

    graph_nodes.generate_answer = fake_generate_answer
    extraction_service_module.call_llm = fake_call_llm

    client = TestClient(test_app)
    try:
        upload_response = client.post(
            "/api/v1/files/upload",
            files={
                "file": (
                    "review_view.txt",
                    "\n".join(
                        [
                            "Page 1 route text.",
                            "Page 2 route text.",
                            "Complex review sample.",
                        ]
                        * 50
                    ).encode("utf-8"),
                    "text/plain",
                )
            },
        )
        assert upload_response.status_code == 200, upload_response.text
        file_id = upload_response.json()["file_id"]

        session = SessionLocal()
        try:
            page = models.Page(
                file_id=file_id,
                page_no=2,
                page_text="Page 2 relation text.",
                page_summary="Review focus continuation.",
            )
            session.add(page)
            session.flush()
            session.add(
                models.Chunk(
                    file_id=file_id,
                    page_id=page.id,
                    page_no=2,
                    block_type="text",
                    text_content="J010 and J020 are on page 2.",
                    metadata_json={"source": "review_view"},
                )
            )
            session.commit()
        finally:
            session.close()

        extract_response = client.post(f"/api/v1/extract/{file_id}")
        assert extract_response.status_code == 200, extract_response.text
        extract_payload = extract_response.json()
        assert extract_payload["review_summary"]["review_required_node_count"] == 2
        assert extract_payload["review_summary"]["review_required_node_ids"] == ["J001", "J010"]
        assert extract_payload["review_summary"]["issue_counts"]["low_confidence"] == 1
        assert extract_payload["review_summary"]["issue_counts"]["uncertain_fields"] == 1
        assert extract_payload["review_summary"]["issue_counts"]["relation_mismatch"] == 1
        assert extract_payload["review_summary"]["issue_counts"]["missing_target"] == 1
        assert extract_payload["review_summary"]["issue_counts"]["orphan_node"] == 1
        assert extract_payload["review_summary"]["issue_counts"]["cross_page_link"] == 1
        assert "topology_relations" in extract_payload["review_summary"]["recommended_sections"]
        assert "cross_page_links" in extract_payload["review_summary"]["recommended_sections"]
        assert "node_confidence" in extract_payload["review_summary"]["recommended_sections"]
        assert any(item["issue_type"] == "orphan_node" and item["node_id"] == "J020" for item in extract_payload["review_summary"]["focus_items"])

        overview_response = client.get(f"/api/v1/files/{file_id}/overview")
        assert overview_response.status_code == 200, overview_response.text
        overview_payload = overview_response.json()
        assert overview_payload["review_summary"]["review_required_node_count"] == 2
        assert overview_payload["review_summary"]["issue_counts"]["cross_page_link"] == 1
        assert "复核" in (overview_payload["review_summary"]["summary_message"] or "")

        print("review view enhancement ok")
        return 0
    finally:
        graph_nodes.generate_answer = original_generate_answer
        extraction_service_module.call_llm = original_call_llm


if __name__ == "__main__":
    raise SystemExit(main())
