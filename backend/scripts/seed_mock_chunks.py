import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import SessionLocal
from app.db import models
from app.services.embedding_service import embed_text


MOCK_CHUNKS = [
    {
        "file_name": "光缆路由图示例1.pdf",
        "page_no": 1,
        "chunk_type": "text",
        "text_content": "井点A - 井点B，距离80米，光缆型号：GYTA-48B1.3，芯数：48芯"
    },
    {
        "file_name": "光缆路由图示例1.pdf",
        "page_no": 1,
        "chunk_type": "text",
        "text_content": "井点B - 井点C，距离120米，光缆型号：GYTA-48B1.3，芯数：48芯，接头盒编号：JTG-001"
    },
    {
        "file_name": "光缆路由图示例1.pdf",
        "page_no": 1,
        "chunk_type": "text",
        "text_content": "井点C - 井点D，距离95米，光缆型号：GYTA-48B1.3，芯数：48芯，盘留长度：5米"
    },
    {
        "file_name": "光缆路由图示例1.pdf",
        "page_no": 1,
        "chunk_type": "text",
        "text_content": "井点D - 井点E，距离150米，光缆型号：GYTA-96B1.3，芯数：96芯"
    },
    {
        "file_name": "光缆路由图示例1.pdf",
        "page_no": 1,
        "chunk_type": "text",
        "text_content": "井点E - 井点F，距离70米，光缆型号：GYTA-96B1.3，芯数：96芯，接头盒编号：JTG-002"
    },
    {
        "file_name": "光缆路由图示例1.pdf",
        "page_no": 2,
        "chunk_type": "text",
        "text_content": "井点F - 井点G，距离200米，光缆型号：GYTA-96B1.3，芯数：96芯，盘留长度：8米"
    },
    {
        "file_name": "光缆路由图示例1.pdf",
        "page_no": 2,
        "chunk_type": "text",
        "text_content": "井点G - 井点H，距离60米，光缆型号：GYTA-144B1.3，芯数：144芯"
    },
    {
        "file_name": "光缆路由图示例1.pdf",
        "page_no": 2,
        "chunk_type": "text",
        "text_content": "井点H - 井点I，距离110米，光缆型号：GYTA-144B1.3，芯数：144芯，接头盒编号：JTG-003"
    },
    {
        "file_name": "光缆路由图示例1.pdf",
        "page_no": 2,
        "chunk_type": "text",
        "text_content": "井点I - 井点J，距离85米，光缆型号：GYTA-144B1.3，芯数：144芯"
    },
    {
        "file_name": "光缆路由图示例1.pdf",
        "page_no": 3,
        "chunk_type": "text",
        "text_content": "备注：本路由图共10个井点，总长度约1050米，主干光缆为144芯G.652D光纤"
    }
]


def seed_mock_chunks():
    db = SessionLocal()
    try:
        existing_file = db.query(models.File).filter(
            models.File.file_name == "光缆路由图示例1.pdf"
        ).first()

        if existing_file:
            print("Mock data already exists, skipping...")
            return

        file = models.File(
            file_name="光缆路由图示例1.pdf",
            file_type="pdf",
            storage_path="/uploads/光缆路由图示例1.pdf",
            parse_status="completed"
        )
        db.add(file)
        db.flush()

        for chunk_data in MOCK_CHUNKS:
            chunk = models.Chunk(
                file_id=file.id,
                page_no=chunk_data["page_no"],
                chunk_type=chunk_data["chunk_type"],
                text_content=chunk_data["text_content"]
            )
            db.add(chunk)
            db.flush()

            # Skip embedding generation for now
            # embedding_vector = embed_text(chunk_data["text_content"])
            # 
            # embedding = models.Embedding(
            #     chunk_id=chunk.id,
            #     embedding_model="qwen3-vl-embedding",
            #     embedding=str(embedding_vector)
            # )
            # db.add(embedding)

        db.commit()
        print(f"Successfully seeded {len(MOCK_CHUNKS)} mock chunks!")

    except Exception as e:
        db.rollback()
        print(f"Error seeding mock chunks: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    seed_mock_chunks()
