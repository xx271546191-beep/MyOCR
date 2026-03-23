"""检索问答 API 路由模块

负责处理用户的检索问答请求
接收用户查询，通过 RAG Graph 检索相关 chunks 并生成答案
返回答案、引用来源和风险提示
"""

import time

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db import models
from app.db.session import get_db
from app.schemas.retrieval import (
    SearchRequest,
    SearchResponse,
    CitationItem,
    SearchQuestionAnalysisResponse,
)
from app.rag.graph_builder import run_qa_graph
from app.services.precheck_service import build_precheck_from_stored_file
from app.services.qa_enhanced import answer_relation_question_from_structured_extraction

# 路由实例，挂载到 /api/v1 前缀
router = APIRouter()


@router.post("/search", response_model=SearchResponse)
def search(request: SearchRequest, db: Session = Depends(get_db)):
    """检索问答接口
    
    接收用户查询，通过 RAG Graph 工作流进行：
    1. 检索相关 chunks
    2. 构建上下文
    3. 生成答案
    4. 格式化响应
    
    Args:
        request: 检索请求，包含 query、file_id、top_k
        db: 依赖注入的数据库会话
        
    Returns:
        SearchResponse: 包含答案和引用来源
    """
    risk_notice = None
    file_id = None
    if request.file_id:
        try:
            file_id = int(request.file_id)
        except (TypeError, ValueError):
            file_id = None
        if file_id is not None:
            db_file = db.query(models.File).filter(models.File.id == file_id).first()
            if db_file:
                risk_notice = build_precheck_from_stored_file(
                    file_name=db_file.file_name,
                    file_type=db_file.file_type,
                    storage_path=db_file.storage_path,
                )

    start_time = time.time()

    # 调用 RAG Graph 工作流处理问答
    result = run_qa_graph(
        query=request.query,
        file_id=request.file_id,
        db=db,
        top_k=request.top_k,
    )

    answer_text = result["answer"]
    question_analysis = SearchQuestionAnalysisResponse(
        matched=False,
        answer_mode="rag",
    )
    if file_id is not None:
        structured_relation_result = answer_relation_question_from_structured_extraction(
            db=db,
            file_id=file_id,
            query=request.query,
        )
        if structured_relation_result is not None:
            answer_text = structured_relation_result["answer"]
            question_analysis = SearchQuestionAnalysisResponse(
                **structured_relation_result["question_analysis"]
            )
    
    # 将引用来源转换为 Schema 定义的格式
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

    file_id_for_log = None
    if request.file_id:
        try:
            file_id_for_log = int(request.file_id)
        except (TypeError, ValueError):
            file_id_for_log = None

    db.add(
        models.QueryLog(
            file_id=file_id_for_log,
            query_text=request.query,
            answer_text=answer_text,
            retrieved_chunk_ids=[cit["chunk_id"] for cit in result["citations"]],
            latency_ms=(time.time() - start_time) * 1000,
        )
    )
    db.commit()

    # 构建最终响应
    return SearchResponse(
        answer=answer_text,
        citations=citations,
        risk_notice=risk_notice,
        question_analysis=question_analysis,
    )
