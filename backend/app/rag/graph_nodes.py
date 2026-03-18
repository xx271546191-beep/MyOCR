from typing import Dict, Any, List, Optional
from app.rag.graph_state import RagGraphState
from app.services.retrieval_service import RetrievalService
from app.services.llm_service import generate_answer
from app.rag.prompts import build_qa_prompt
from sqlalchemy.orm import Session


def retrieve_chunks(state: RagGraphState) -> RagGraphState:
    query = state.get("query", "")
    file_id = state.get("file_id")
    db = state.get("db")
    
    if not query:
        return {"error": "Query is required"}
    
    if not db:
        return {"error": "Database session is required"}
    
    retrieval_service = RetrievalService(db)
    
    file_id_int = int(file_id) if file_id else None
    
    retrieved_chunks = retrieval_service.search_similar_chunks(
        query=query,
        file_id=file_id_int,
        top_k=5
    )
    
    return {"retrieved_chunks": retrieved_chunks}


def build_context(state: RagGraphState) -> RagGraphState:
    retrieved_chunks = state.get("retrieved_chunks", [])
    
    if not retrieved_chunks:
        return {"context_text": "", "citations": []}
    
    context_parts = []
    citations = []
    
    for i, chunk in enumerate(retrieved_chunks):
        text_content = chunk.get("text_content", "")
        if text_content:
            context_parts.append(f"[Chunk {chunk.get('chunk_id')}]: {text_content}")
        
        citations.append({
            "chunk_id": chunk.get("chunk_id"),
            "page_no": chunk.get("page_no"),
            "score": chunk.get("score"),
            "text_preview": text_content[:200] if text_content else None,
            "image_path": chunk.get("image_path")
        })
    
    context_text = "\n\n".join(context_parts)
    
    return {"context_text": context_text, "citations": citations}


def generate_answer_node(state: RagGraphState) -> RagGraphState:
    query = state.get("query", "")
    context_text = state.get("context_text", "")
    
    if not context_text:
        return {"answer": "根据当前检索结果，未找到相关信息"}
    
    prompt = build_qa_prompt(query, context_text)
    
    try:
        answer = generate_answer(prompt)
    except Exception as e:
        answer = f"生成答案时出错: {str(e)}"
    
    return {"answer": answer}


def format_response(state: RagGraphState) -> RagGraphState:
    answer = state.get("answer", "")
    citations = state.get("citations", [])
    
    return {
        "answer": answer,
        "citations": citations
    }
