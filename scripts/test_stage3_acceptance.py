"""Stage 3 API acceptance test."""

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

# 测试环境优先走本地可复现的 embedding provider，避免依赖外部网络。
os.environ["EMBEDDING_PROVIDER"] = "mock"

from app.api import routes_extract, routes_files, routes_search
from app.db import models
from app.db.base import Base
from app.db.session import get_db
from app.rag import graph_nodes
from app.services import extraction_service as extraction_service_module
from app.services.embedding_service import embed_text


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
    print("=" * 60)
    print("Stage 3 Acceptance Test")
    print("=" * 60)

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
        return "mock grounded answer"

    def fake_call_llm(system_prompt: str, user_prompt: str, model=None, images=None) -> str:
        return json.dumps(
            {
                "nodes": [
                    {
                        "node_id": "J001",
                        "node_type": "joint",
                        "prev_node": "J000",
                        "next_node": "J002",
                        "distance": 150.5,
                        "distance_unit": "m",
                        "cable_type": "GYTA53",
                        "fiber_count": 24,
                        "remarks": "stage3 acceptance",
                        "confidence": 0.92,
                        "review_required": False,
                        "uncertain_fields": [],
                    }
                ]
            },
            ensure_ascii=False,
        )

    graph_nodes.generate_answer = fake_generate_answer
    extraction_service_module.call_llm = fake_call_llm

    client = TestClient(test_app)
    storage_path = None

    try:
        test_text = "\n".join(
            [
                "RouteRAG stage3 acceptance document.",
                "Joint J001 connects to J002 with 150.5 m distance.",
                "Cable type is GYTA53 and fiber count is 24.",
            ]
            * 80
        )

        print("\n1. Upload and ingest")
        upload_response = client.post(
            "/api/v1/files/upload",
            files={"file": ("stage3_acceptance.txt", test_text.encode("utf-8"), "text/plain")},
        )
        assert upload_response.status_code == 200, upload_response.text
        upload_payload = upload_response.json()
        file_id = upload_payload["file_id"]
        print(f"   file_id={file_id}, chunks={upload_payload['chunks']}")
        assert upload_payload["task"]["status"] == "indexed"
        assert upload_payload["precheck"]["quality_grade"] == "Q1"
        assert upload_payload["precheck"]["recommended_path"] == "full_pipeline"

        session = SessionLocal()
        try:
            db_file = session.query(models.File).filter(models.File.id == file_id).first()
            assert db_file is not None
            storage_path = db_file.storage_path

            page = session.query(models.Page).filter(models.Page.file_id == file_id).first()
            assert page is not None
            extra_texts = [
                "Backup chunk A about splice boxes and route distance.",
                "Backup chunk B about cable type GYTA53 and 24 fibers.",
            ]
            for text in extra_texts:
                chunk = models.Chunk(
                    file_id=file_id,
                    page_id=page.id,
                    page_no=page.page_no,
                    block_type="text",
                    text_content=text,
                    metadata_json={"source": "stage3_acceptance"},
                )
                session.add(chunk)
                session.flush()
                session.add(
                    models.Embedding(
                        chunk_id=chunk.id,
                        embedding_model="BAAI/bge-m3",
                        embedding=embed_text(text),
                    )
                )
            session.commit()
        finally:
            session.close()

        print("\n2. Search API")
        search_response = client.post(
            "/api/v1/search",
            json={"file_id": str(file_id), "query": "What is the cable type?", "top_k": 1},
        )
        assert search_response.status_code == 200, search_response.text
        search_payload = search_response.json()
        assert search_payload["answer"] == "mock grounded answer"
        assert len(search_payload["citations"]) == 1
        assert search_payload["risk_notice"]["quality_grade"] == "Q1"
        assert search_payload["risk_notice"]["recommended_path"] == "full_pipeline"
        assert search_payload["risk_notice"]["result_nature"] == "draft"
        total_chunks = upload_payload["chunks"] + len(extra_texts)
        assert total_chunks > 1
        session = SessionLocal()
        try:
            query_logs = session.query(models.QueryLog).filter(models.QueryLog.file_id == file_id).all()
            assert len(query_logs) == 1
            assert query_logs[0].query_text == "What is the cable type?"
        finally:
            session.close()

        query_history_response = client.get(f"/api/v1/files/{file_id}/queries")
        assert query_history_response.status_code == 200, query_history_response.text
        query_history_payload = query_history_response.json()
        assert query_history_payload["total_queries"] == 1
        assert query_history_payload["queries"][0]["query_text"] == "What is the cable type?"

        overview_before_extract = client.get(f"/api/v1/files/{file_id}/overview")
        assert overview_before_extract.status_code == 200, overview_before_extract.text
        overview_before_extract_payload = overview_before_extract.json()
        assert overview_before_extract_payload["demo_readiness"]["is_ready"] is False
        assert overview_before_extract_payload["demo_readiness"]["status_label"] == "needs_attention"
        assert "no_saved_extraction" in overview_before_extract_payload["demo_readiness"]["blockers"]
        assert overview_before_extract_payload["demo_readiness"]["primary_action"] == "run_extract"
        assert "run_extract_then_refresh_overview" in overview_before_extract_payload["demo_readiness"]["recovery_suggestions"]
        print("   search response ok, top_k applied")

        print("\n3. File detail + manual ingest")
        file_list_response = client.get("/api/v1/files")
        assert file_list_response.status_code == 200, file_list_response.text
        file_list_payload = file_list_response.json()
        assert len(file_list_payload["files"]) == 1
        assert file_list_payload["files"][0]["precheck"]["quality_grade"] == "Q1"

        file_detail_response = client.get(f"/api/v1/files/{file_id}")
        assert file_detail_response.status_code == 200, file_detail_response.text
        file_detail_payload = file_detail_response.json()
        assert file_detail_payload["task"]["status"] == "indexed"
        assert file_detail_payload["precheck"]["quality_grade"] == "Q1"

        manual_ingest_response = client.post(f"/api/v1/files/{file_id}/ingest")
        assert manual_ingest_response.status_code == 200, manual_ingest_response.text
        manual_ingest_payload = manual_ingest_response.json()
        assert manual_ingest_payload["task"]["status"] == "indexed"
        assert manual_ingest_payload["precheck"]["recommended_path"] == "full_pipeline"
        print("   file/task schema and manual ingest ok")

        print("\n4. Extraction schema")
        schema_response = client.get("/api/v1/extract/schema")
        assert schema_response.status_code == 200, schema_response.text
        assert schema_response.json()["schema_version"] == "cable_route_v1"
        print("   schema endpoint ok")

        print("\n5. Extraction and persistence")
        extract_response = client.post(f"/api/v1/extract/{file_id}")
        assert extract_response.status_code == 200, extract_response.text
        extract_payload = extract_response.json()
        assert extract_payload["success"] is True
        assert extract_payload["total_nodes"] == 1
        assert extract_payload["risk_notice"]["quality_grade"] == "Q1"
        assert extract_payload["topology_summary"]["total_relations"] == 2
        assert extract_payload["topology_summary"]["confirmed_relations"] == 0
        assert extract_payload["topology_summary"]["broken_relation_count"] == 2
        assert extract_payload["topology_summary"]["orphan_node_ids"] == []
        assert "verify_missing_target_nodes" in extract_payload["topology_summary"]["review_focus"]
        print("   extraction endpoint ok")

        session = SessionLocal()
        try:
            saved_rows = (
                session.query(models.StructuredExtraction)
                .filter(models.StructuredExtraction.file_id == file_id)
                .all()
            )
            assert len(saved_rows) == 1
        finally:
            session.close()
        print("   extraction persistence ok")

        print("\n6. Extraction retrieval")
        get_response = client.get(f"/api/v1/extract/{file_id}")
        assert get_response.status_code == 200, get_response.text
        get_payload = get_response.json()
        assert get_payload["total_nodes"] == 1
        assert get_payload["nodes"][0]["node_id"] == "J001"
        assert get_payload["risk_notice"]["recommended_path"] == "full_pipeline"
        assert get_payload["topology_summary"]["broken_relation_count"] == 2
        print("   persisted extraction query ok")

        print("\n7. File extraction summary views")
        file_detail_after_extract = client.get(f"/api/v1/files/{file_id}")
        assert file_detail_after_extract.status_code == 200, file_detail_after_extract.text
        file_detail_after_extract_payload = file_detail_after_extract.json()
        assert file_detail_after_extract_payload["extraction_summary"]["total_nodes"] == 1
        assert file_detail_after_extract_payload["extraction_summary"]["review_count"] == 0
        assert file_detail_after_extract_payload["query_summary"]["total_queries"] == 1

        file_list_after_extract = client.get("/api/v1/files")
        assert file_list_after_extract.status_code == 200, file_list_after_extract.text
        file_list_after_extract_payload = file_list_after_extract.json()
        assert file_list_after_extract_payload["files"][0]["extraction_summary"]["total_nodes"] == 1
        assert file_list_after_extract_payload["files"][0]["query_summary"]["total_queries"] == 1
        print("   file extraction summary views ok")

        print("\n8. File overview view")
        overview_response = client.get(f"/api/v1/files/{file_id}/overview")
        assert overview_response.status_code == 200, overview_response.text
        overview_payload = overview_response.json()
        assert overview_payload["file_id"] == file_id
        assert overview_payload["task"]["status"] == "indexed"
        assert overview_payload["precheck"]["quality_grade"] == "Q1"
        assert overview_payload["extraction_summary"]["total_nodes"] == 1
        assert overview_payload["query_summary"]["total_queries"] == 1
        assert overview_payload["demo_readiness"]["is_ready"] is True
        assert overview_payload["demo_readiness"]["status_label"] == "ready"
        assert overview_payload["demo_readiness"]["primary_action"] is None
        assert overview_payload["demo_readiness"]["recovery_suggestions"] == []
        assert len(overview_payload["recent_queries"]) == 1
        assert overview_payload["recent_queries"][0]["query_text"] == "What is the cable type?"
        assert len(overview_payload["recent_extractions"]) == 1
        assert overview_payload["recent_extractions"][0]["node_id"] == "J001"
        assert overview_payload["topology_summary"]["total_relations"] == 2
        assert overview_payload["topology_summary"]["broken_relation_count"] == 2
        assert "verify_missing_target_nodes" in overview_payload["topology_summary"]["review_focus"]
        print("   file overview view ok")

        print("\nAll stage 3 acceptance checks passed.")
        return 0
    finally:
        graph_nodes.generate_answer = original_generate_answer
        extraction_service_module.call_llm = original_call_llm
        if storage_path:
            try:
                Path(storage_path).unlink(missing_ok=True)
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
