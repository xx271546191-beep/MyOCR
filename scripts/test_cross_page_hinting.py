"""Cross-page hinting integration test."""

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
                        "confidence": 0.93,
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
                        "prev_node": "J001",
                        "confidence": 0.91,
                        "review_required": False,
                        "uncertain_fields": [],
                    }
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
                    "cross_page_hinting.txt",
                    "\n".join(
                        [
                            "Page 1 relation text.",
                            "J001 continues on next page.",
                            "Cross-page demo content.",
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
                page_summary="Cross-page continuation.",
            )
            session.add(page)
            session.flush()
            session.add(
                models.Chunk(
                    file_id=file_id,
                    page_id=page.id,
                    page_no=2,
                    block_type="text",
                    text_content="J010 continues from previous page.",
                    metadata_json={"source": "cross_page_hinting"},
                )
            )
            session.commit()
        finally:
            session.close()

        extract_response = client.post(f"/api/v1/extract/{file_id}")
        assert extract_response.status_code == 200, extract_response.text
        extract_payload = extract_response.json()
        assert extract_payload["topology_summary"]["cross_page_relation_count"] == 2
        assert extract_payload["topology_summary"]["cross_page_hint"]["has_cross_page_links"] is True
        assert extract_payload["topology_summary"]["cross_page_hint"]["review_required"] is True
        assert extract_payload["topology_summary"]["cross_page_hint"]["focus_pages"] == [1, 2]
        assert (
            extract_payload["topology_summary"]["cross_page_hint"]["recommended_action"]
            == "review_cross_page_sequence"
        )
        assert len(extract_payload["topology_summary"]["cross_page_hint"]["cross_page_links"]) == 2

        overview_response = client.get(f"/api/v1/files/{file_id}/overview")
        assert overview_response.status_code == 200, overview_response.text
        overview_payload = overview_response.json()
        assert overview_payload["topology_summary"]["cross_page_hint"]["has_cross_page_links"] is True
        assert overview_payload["topology_summary"]["cross_page_hint"]["focus_pages"] == [1, 2]
        assert "跨页" in overview_payload["topology_summary"]["cross_page_hint"]["review_message"]

        print("cross-page hinting ok")
        return 0
    finally:
        graph_nodes.generate_answer = original_generate_answer
        extraction_service_module.call_llm = original_call_llm


if __name__ == "__main__":
    raise SystemExit(main())
