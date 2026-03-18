import sys
import os
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.db.base import Base
from app.db.session import engine, SessionLocal
from app.db import models
from app.services.embedding_service import embed_text
from app.core.config import settings

# 创建所有表
print("Creating tables...")
Base.metadata.create_all(bind=engine)
print("Tables created successfully!")

# 添加测试数据
db = SessionLocal()
try:
    # 检查是否已有数据
    existing_files = db.query(models.File).count()
    if existing_files > 0:
        print("Database already has data, skipping initialization.")
    else:
        # 创建测试文件
        test_file = models.File(
            file_name="test_cable_route.pdf",
            file_type="pdf",
            storage_path="/path/to/test_cable_route.pdf",
            parse_status="completed"
        )
        db.add(test_file)
        db.flush()
        
        # 创建测试chunk
        test_chunk = models.Chunk(
            file_id=test_file.id,
            page_no=1,
            chunk_type="text",
            text_content="光缆路由图显示井点A连接到井点B，距离80米，光缆型号为GYTA-48B1.3，芯数为48芯。",
            metadata_json={"source": "test"}
        )
        db.add(test_chunk)
        db.flush()
        
        # 创建测试embedding
        embedding_vector = embed_text(test_chunk.text_content)
        test_embedding = models.Embedding(
            chunk_id=test_chunk.id,
            embedding_model=settings.EMBEDDING_MODEL_NAME,
            embedding=embedding_vector
        )
        db.add(test_embedding)
        
        db.commit()
        print("Test data added successfully!")
finally:
    db.close()

print("Database initialization completed!")
