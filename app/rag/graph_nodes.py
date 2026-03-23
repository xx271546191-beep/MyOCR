"""QA Graph 核心节点实现。

每个函数对应图中的一个处理阶段，节点之间通过 `RagGraphState`
传递中间结果，保持职责边界清晰。
"""

from app.rag.graph_state import RagGraphState
from app.rag.prompts import build_qa_prompt
from app.services.llm_service import generate_answer
from app.services.retrieval_service import RetrievalService


def retrieve_chunks(state: RagGraphState) -> RagGraphState:
    """根据查询条件检索相关 chunk。"""
    query = state.get("query", "")
    file_id = state.get("file_id")
    top_k = state.get("top_k", 5)
    db = state.get("db")

    if not query:
        return {"error": "缺少 query 参数"}
    if not db:
        return {"error": "缺少数据库会话"}

    retrieval_service = RetrievalService(db)
    file_id_int = int(file_id) if file_id else None
    retrieved_chunks = retrieval_service.search_similar_chunks(
        query=query,
        file_id=file_id_int,
        top_k=top_k,
    )
    return {"retrieved_chunks": retrieved_chunks}


def build_context(state: RagGraphState) -> RagGraphState:
    """把检索结果转换为 LLM 可直接消费的上下文和引用列表。"""
    retrieved_chunks = state.get("retrieved_chunks", [])
    if not retrieved_chunks:
        return {"context_text": "", "citations": []}

    context_parts = []
    citations = []
    for chunk in retrieved_chunks:
        text_content = chunk.get("text_content", "")

        # 上下文文本给 LLM 使用，引用列表给前端和调用方展示证据来源。
        if text_content:
            context_parts.append(f"[Chunk {chunk.get('chunk_id')}]: {text_content}")

        citations.append(
            {
                "chunk_id": chunk.get("chunk_id"),
                "page_no": chunk.get("page_no"),
                "score": chunk.get("score"),
                "text_preview": text_content[:200] if text_content else None,
                "image_path": chunk.get("image_path"),
            }
        )

    return {
        "context_text": "\n\n".join(context_parts),
        "citations": citations,
    }


def generate_answer_node(state: RagGraphState) -> RagGraphState:
    """基于检索上下文生成最终答案。"""
    query = state.get("query", "")
    context_text = state.get("context_text", "")

    # 如果没有检索命中，就不要强行让模型编造答案。
    if not context_text:
        return {"answer": "根据当前检索结果，未找到相关信息"}

    prompt = build_qa_prompt(query, context_text)
    try:
        answer = generate_answer(prompt)
    except Exception as exc:
        # 生成阶段失败时保留错误信息，便于上层快速定位问题来源。
        answer = f"生成答案时出错：{exc}"

    return {"answer": answer}


def format_response(state: RagGraphState) -> RagGraphState:
    """整理 graph 最终输出结构。"""
    return {
        "answer": state.get("answer", ""),
        "citations": state.get("citations", []),
    }
