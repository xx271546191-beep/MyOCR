import sys
import os
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from fastapi import FastAPI
from app.core.config import settings
from app.api import routes_search, routes_files
from app.db.base import Base
from app.db.session import engine

app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG
)

app.include_router(routes_search.router, prefix="/api/v1", tags=["search"])
app.include_router(routes_files.router, prefix="/api/v1", tags=["files"])

@app.on_event("startup")
def _create_tables_on_startup():
    # Demo-friendly default: ensure tables exist.
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/")
def root():
    return {"message": "Optic RAG Demo API"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
