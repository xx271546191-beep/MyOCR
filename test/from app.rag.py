from app.rag.graph_builder import run_qa_graph
from app.db.session import get_db

db = next(get_db())
result = run_qa_graph(query="光缆路由", file_id=None, db=db)
print(f"Answer: {result['answer']}")
print(f"Citations: {len(result['citations'])}")
for citation in result['citations']:
    print(f"  Chunk ID: {citation['chunk_id']}, Score: {citation['score']}")