from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db import models
from typing import List, Tuple
from pathlib import Path
from uuid import uuid4
from app.services import embedding_service
from app.core.config import settings

router = APIRouter()

SUPPORTED_TEXT_TYPES = {".txt", ".md", ".json", ".csv"}
SUPPORTED_PDF_TYPE = ".pdf"
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".gif"}


def _split_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be >= 0 and < chunk_size")
    t = (text or "").strip()
    if not t:
        return []
    chunks: List[str] = []
    start = 0
    while start < len(t):
        end = min(len(t), start + chunk_size)
        chunk = t[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(t):
            break
        start = end - overlap
    return chunks


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _extract_text_from_pdf(file_content: bytes) -> str:
    try:
        import io
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(file_content))
        text_parts = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)
        return "\n".join(text_parts)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"PDF parsing failed: {str(e)}"
        )


async def _read_text_from_upload(file: UploadFile) -> Tuple[str, str]:
    filename = file.filename or "uploaded"
    suffix = Path(filename).suffix.lower()
    raw = await file.read()

    if suffix in SUPPORTED_TEXT_TYPES or (file.content_type or "").startswith("text/"):
        return raw.decode("utf-8", errors="ignore"), "text"

    if suffix == SUPPORTED_PDF_TYPE or file.content_type == "application/pdf":
        text = _extract_text_from_pdf(raw)
        if not text or not text.strip():
            raise HTTPException(
                status_code=400,
                detail="PDF contains no extractable text"
            )
        return text, "pdf"

    if suffix in IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Image OCR is not supported yet. Please upload text or PDF files."
        )

    raise HTTPException(
        status_code=400,
        detail="Unsupported file type. Please upload .txt, .md, .json, .csv, or .pdf files."
    )


@router.post("/files/upload")
@router.post("/upload")
async def upload_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    text_content, file_type = await _read_text_from_upload(file)

    upload_dir = _backend_root() / "storage" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    safe_name = Path(file.filename or "uploaded.txt").name
    stored_name = f"{uuid4().hex}_{safe_name}"
    stored_path = upload_dir / stored_name
    stored_path.write_bytes(text_content.encode("utf-8", errors="ignore"))

    db_file = models.File(
        file_name=safe_name,
        file_type=file_type,
        storage_path=str(stored_path),
        parse_status="indexing",
    )
    db.add(db_file)
    db.flush()

    chunks = _split_text(text_content)
    if not chunks:
        db_file.parse_status = "failed"
        db.commit()
        raise HTTPException(status_code=400, detail="No text content extracted from file")

    vectors = embedding_service.embed_texts(chunks)

    chunk_models: List[models.Chunk] = []
    for chunk_text in chunks:
        c = models.Chunk(
            file_id=db_file.id,
            page_no=None,
            chunk_type="text",
            text_content=chunk_text,
            metadata_json={"source": "upload"},
        )
        db.add(c)
        chunk_models.append(c)
    db.flush()

    for c, vec in zip(chunk_models, vectors):
        emb = models.Embedding(
            chunk_id=c.id,
            embedding_model=settings.EMBEDDING_MODEL_NAME,
            embedding=vec,
        )
        db.add(emb)

    db_file.parse_status = "indexed"
    db.commit()

    return {
        "file_id": db_file.id,
        "filename": db_file.file_name,
        "chunks": len(chunk_models),
        "status": db_file.parse_status,
    }


@router.get("/files")
def list_files(db: Session = Depends(get_db)):
    files = db.query(models.File).all()
    return {"files": [{"id": f.id, "name": f.file_name} for f in files]}


@router.get("/files/{file_id}")
def get_file(file_id: int, db: Session = Depends(get_db)):
    file = db.query(models.File).filter(models.File.id == file_id).first()
    if not file:
        return {"error": "File not found"}
    return {
        "id": file.id,
        "file_name": file.file_name,
        "file_type": file.file_type,
        "parse_status": file.parse_status
    }
