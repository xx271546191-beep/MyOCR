from fastapi import APIRouter, UploadFile, File, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db import models
from typing import List

router = APIRouter()


@router.post("/upload")
async def upload_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    return {"filename": file.filename, "status": "upload endpoint placeholder"}


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
