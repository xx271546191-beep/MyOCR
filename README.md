# RouteRAG Backend

RouteRAG backend is a FastAPI service for a fiber-route drawing RAG demo. It covers file upload, parsing, chunking, embedding, retrieval QA, structured extraction, topology summarization, and review-oriented overview aggregation.

## Current Scope

This repository is the backend codebase for the demo. The current implementation already includes:

- file upload and manual re-ingest
- text / PDF parsing
- chunking and embedding storage
- retrieval QA with citations
- structured extraction with `cable_route_v1`
- file-level `precheck` and `risk_notice`
- `topology_summary` for relation recovery
- structured relation-first QA for `prev_node` / `next_node` questions
- `cross_page_hint` for multi-page relation review
- `review_summary` for complex sample review focus
- file-level `overview` and query history interfaces

The backend is in a demo/MVP stage. It is designed to be explainable and review-friendly, not to pretend full automation on all complex engineering drawings.

## Tech Stack

- Python
- FastAPI
- SQLAlchemy
- PostgreSQL + pgvector
- SQLite fallback for local tests
- OpenAI-compatible / Hugging Face / Google model providers
- LangGraph

## Repository Layout

```text
backend/
|-- app/
|   |-- api/           # FastAPI routes
|   |-- core/          # settings and config
|   |-- db/            # models and session
|   |-- prompts/       # extraction prompts
|   |-- rag/           # QA graph
|   |-- schemas/       # response/request schemas
|   `-- services/      # parser, ingest, retrieval, extraction, review logic
|-- scripts/           # verification and utility scripts
|-- storage/           # uploaded files and local artifacts
|-- .env.example
|-- requirements.txt
`-- README.md
```

## Quick Start

### 1. Create and activate a virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```powershell
pip install -r requirements.txt
```

### 3. Configure environment variables

Copy `.env.example` to `.env` and update values as needed.

Minimal local development options:

- PostgreSQL + pgvector:
  - use `DATABASE_URL=postgresql://...`
- SQLite fallback:
  - use `DATABASE_URL=sqlite:///./optic_rag.db`

For tests and local deterministic validation, the embedding layer supports:

```env
EMBEDDING_PROVIDER=mock
```

### 4. Start the service

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

Available endpoints after startup:

- `GET /`
- `GET /health`
- `GET /docs`

## Main API Endpoints

### Files

- `POST /api/v1/files/upload`
- `POST /api/v1/upload`
- `POST /api/v1/files/{file_id}/ingest`
- `GET /api/v1/files`
- `GET /api/v1/files/{file_id}`
- `GET /api/v1/files/{file_id}/queries`
- `GET /api/v1/files/{file_id}/overview`

### Search

- `POST /api/v1/search`

Highlights:

- citations
- `risk_notice`
- `question_analysis`
- relation-first answering for `previous_end / next_end / prev_node / next_node`

### Extraction

- `POST /api/v1/extract`
- `GET /api/v1/extract/schema`
- `POST /api/v1/extract/{file_id}`
- `GET /api/v1/extract/{file_id}`

Highlights:

- structured nodes
- `topology_summary`
- `cross_page_hint`
- `review_summary`

## Verification

Recommended verification commands:

```powershell
.\.venv\Scripts\python.exe -c "import app.main; print('app.main import ok')"
.\.venv\Scripts\python.exe scripts\test_precheck_service.py
.\.venv\Scripts\python.exe scripts\test_mock_embedding_provider.py
.\.venv\Scripts\python.exe scripts\test_topology_service.py
.\.venv\Scripts\python.exe scripts\test_cross_page_hinting.py
.\.venv\Scripts\python.exe scripts\test_relation_qa_enhancement.py
.\.venv\Scripts\python.exe scripts\test_review_summary_service.py
.\.venv\Scripts\python.exe scripts\test_review_view_enhancement.py
.\.venv\Scripts\python.exe scripts\test_api_integration.py
.\.venv\Scripts\python.exe scripts\test_stage3_acceptance.py
```

## Environment Notes

Key variables from `.env.example`:

- `DATABASE_URL`
- `LLM_PROVIDER`
- `LLM_API_BASE`
- `LLM_API_KEY`
- `LLM_MODEL_NAME`
- `EMBEDDING_PROVIDER`
- `EMBEDDING_API_BASE`
- `EMBEDDING_API_KEY`
- `EMBEDDING_MODEL_NAME`
- `GOOGLE_GENAI_API_KEY`

Current provider support:

- `hf`
- `openai`
- `google`
- `mock` for embeddings

## Practical Notes

- `storage/` is used for local uploaded files and test artifacts.
- SQLite is acceptable for local development and tests, but vector retrieval in production is intended for PostgreSQL + pgvector.
- The backend favors explicit risk and review signals over pretending uncertain results are final.
