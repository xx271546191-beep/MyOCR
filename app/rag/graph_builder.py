"""QA Graph 构建与执行辅助函数。

负责把检索、上下文构建、答案生成和响应格式化几个节点
编排成一条可重复执行的 LangGraph 工作流。
"""

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from app.rag.graph_nodes import (
    build_context,
    format_response,
    generate_answer_node,
    retrieve_chunks,
)
from app.rag.graph_state import RagGraphState


def create_qa_graph():
    """创建 QA Graph。

    当前图结构是线性的：
    `retrieve -> build_context -> generate -> format -> END`
    这样设计是为了先把最小可验证主链跑通，后续再按需要扩展分支和错误恢复。
    """
    workflow = StateGraph(RagGraphState)
    workflow.add_node("retrieve", retrieve_chunks)
    workflow.add_node("build_context", build_context)
    workflow.add_node("generate", generate_answer_node)
    workflow.add_node("format", format_response)

    workflow.set_entry_point("retrieve")
    workflow.add_edge("retrieve", "build_context")
    workflow.add_edge("build_context", "generate")
    workflow.add_edge("generate", "format")
    workflow.add_edge("format", END)
    return workflow.compile()


def run_qa_graph(
    query: str,
    file_id: str | None,
    db: Session,
    top_k: int = 5,
):
    """执行 QA Graph 并返回最终问答结果。"""
    graph = create_qa_graph()
    initial_state: RagGraphState = {
        "query": query,
        "file_id": file_id,
        "top_k": top_k,
        "db": db,
        "retrieved_chunks": [],
        "context_text": "",
        "answer": "",
        "citations": [],
    }
    result = graph.invoke(initial_state)
    return {
        "answer": result.get("answer", ""),
        "citations": result.get("citations", []),
    }
