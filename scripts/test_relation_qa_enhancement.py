"""Relationship QA enhancement integration test."""

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
        return "llm fallback answer"

    def fake_call_llm(system_prompt: str, user_prompt: str, model=None, images=None) -> str:
        return json.dumps(
            {
                "nodes": [
                    {
                        "node_id": "J001",
                        "node_type": "joint",
                        "prev_node": None,
                        "next_node": "J002",
                        "distance": 88.0,
                        "distance_unit": "m",
                        "confidence": 0.96,
                        "review_required": False,
                        "uncertain_fields": [],
                    },
                    {
                        "node_id": "J002",
                        "node_type": "joint",
                        "prev_node": "J001",
                        "next_node": None,
                        "distance": None,
                        "distance_unit": None,
                        "confidence": 0.91,
                        "review_required": False,
                        "uncertain_fields": [],
                    },
                ]
            },
            ensure_ascii=False,
        )

    graph_nodes.generate_answer = fake_generate_answer
    extraction_service_module.call_llm = fake_call_llm

    client = TestClient(test_app)
    try:
        upload_response = client.post(
            "/api/v1/files/upload",
            files={
                "file": (
                    "relation_qa.txt",
                    "\n".join(
                        [
                            "J001 connects to J002.",
                            "This route is 88m long.",
                            "Used for relation QA enhancement.",
                        ]
                        * 60
                    ).encode("utf-8"),
                    "text/plain",
                )
            },
        )
        assert upload_response.status_code == 200, upload_response.text
        file_id = upload_response.json()["file_id"]

        extract_response = client.post(f"/api/v1/extract/{file_id}")
        assert extract_response.status_code == 200, extract_response.text

        confirmed_response = client.post(
            "/api/v1/search",
            json={"file_id": str(file_id), "query": "J001 的下一端是什么？", "top_k": 2},
        )
        assert confirmed_response.status_code == 200, confirmed_response.text
        confirmed_payload = confirmed_response.json()
        assert "J002" in confirmed_payload["answer"]
        assert confirmed_payload["answer"] != "llm fallback answer"
        assert confirmed_payload["question_analysis"]["matched"] is True
        assert confirmed_payload["question_analysis"]["question_type"] == "node_connection"
        assert confirmed_payload["question_analysis"]["answer_mode"] == "structured_relation"
        assert confirmed_payload["question_analysis"]["matched_node_id"] == "J001"
        assert confirmed_payload["question_analysis"]["related_node_id"] == "J002"
        assert confirmed_payload["question_analysis"]["relation_field"] == "next_node"
        assert confirmed_payload["question_analysis"]["relation_status"] == "confirmed"
        assert len(confirmed_payload["citations"]) >= 1

        unavailable_response = client.post(
            "/api/v1/search",
            json={"file_id": str(file_id), "query": "J099 的下一端是什么？", "top_k": 2},
        )
        assert unavailable_response.status_code == 200, unavailable_response.text
        unavailable_payload = unavailable_response.json()
        assert "无法确认" in unavailable_payload["answer"]
        assert unavailable_payload["answer"] != "llm fallback answer"
        assert unavailable_payload["question_analysis"]["matched"] is True
        assert unavailable_payload["question_analysis"]["question_type"] == "node_connection"
        assert (
            unavailable_payload["question_analysis"]["answer_mode"]
            == "structured_relation_unavailable"
        )
        assert unavailable_payload["question_analysis"]["matched_node_id"] == "J099"
        assert unavailable_payload["question_analysis"]["relation_status"] == "node_not_found"

        print("relationship qa enhancement ok")
        return 0
    finally:
        graph_nodes.generate_answer = original_generate_answer
        extraction_service_module.call_llm = original_call_llm


if __name__ == "__main__":
    raise SystemExit(main())
