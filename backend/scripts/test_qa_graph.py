import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import SessionLocal
from app.rag.graph_builder import run_qa_graph


def test_qa_graph():
    db = SessionLocal()
    try:
        print("=" * 50)
        print("Testing QA Graph")
        print("=" * 50)

        test_queries = [
            "井点B的下一端是谁？",
            "这段路由的距离是多少？",
            "光缆的型号和芯数是什么？",
            "有哪些接头盒？",
            "盘留信息是什么？"
        ]

        for query in test_queries:
            print(f"\nQuery: {query}")
            print("-" * 30)
            result = run_qa_graph(query=query, file_id=None, db=db)
            print(f"Answer: {result['answer']}")
            print(f"Citations count: {len(result['citations'])}")
            for cit in result['citations']:
                print(f"  - chunk_id: {cit['chunk_id']}, score: {cit.get('score', 'N/A')}")
            print()

    except Exception as e:
        print(f"Error testing QA graph: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    test_qa_graph()
