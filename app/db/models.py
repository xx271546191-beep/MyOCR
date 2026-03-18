from sqlalchemy import Column, String, Integer, Float, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.base import Base


class File(Base):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True, index=True)
    file_name = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=False)
    storage_path = Column(String(500))
    parse_status = Column(String(50), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)

    chunks = relationship("Chunk", back_populates="file")


class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("files.id"), nullable=False)
    page_no = Column(Integer)
    chunk_type = Column(String(50))
    text_content = Column(Text)
    image_path = Column(String(500))
    bbox = Column(JSON)
    metadata_json = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

    file = relationship("File", back_populates="chunks")
    embeddings = relationship("Embedding", back_populates="chunk")


class Embedding(Base):
    __tablename__ = "embeddings"

    id = Column(Integer, primary_key=True, index=True)
    chunk_id = Column(Integer, ForeignKey("chunks.id"), nullable=False)
    embedding_model = Column(String(100))
    # Store vector safely as JSON array (SQLite will persist as TEXT internally).
    embedding = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    chunk = relationship("Chunk", back_populates="embeddings")


class QueryLog(Base):
    __tablename__ = "query_logs"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("files.id"))
    query_text = Column(Text, nullable=False)
    answer_text = Column(Text)
    retrieved_chunk_ids = Column(JSON)
    latency_ms = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
