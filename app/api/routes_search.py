from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.retrieval import SearchRequest, SearchResponse, CitationItem
from app.rag.graph_builder import run_qa_graph
from typing import List

router = APIRouter()


@router.post("/search", response_model=SearchResponse)
def search(request: SearchRequest, db: Session = Depends(get_db)):
    result = run_qa_graph(
        query=request.query,
        file_id=request.file_id,
        db=db
    )
    
    citations = [
        CitationItem(
            chunk_id=cit["chunk_id"],
            page_no=cit.get("page_no"),
            score=cit.get("score"),
            text_preview=cit.get("text_preview"),
            image_path=cit.get("image_path")
        )
        for cit in result["citations"]
    ]
    
    return SearchResponse(
        answer=result["answer"],
        citations=citations
    )
