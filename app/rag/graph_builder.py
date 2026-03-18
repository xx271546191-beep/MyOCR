from langgraph.graph import StateGraph, END
from app.rag.graph_state import RagGraphState
from app.rag.graph_nodes import retrieve_chunks, build_context, generate_answer_node, format_response
from sqlalchemy.orm import Session

def create_qa_graph():
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
    
    compiled_workflow = workflow.compile()
    return compiled_workflow


def run_qa_graph(query: str, file_id: str | None, db: Session):  
    graph = create_qa_graph()
    
    initial_state: RagGraphState = {
        "query": query,
        "file_id": file_id,
        "db": db,
        "retrieved_chunks": [],
        "context_text": "",
        "answer": "",
        "citations": []
    }
    
    result = graph.invoke(initial_state)
    
    return {
        "answer": result.get("answer", ""),
        "citations": result.get("citations", [])
    }
