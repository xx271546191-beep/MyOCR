"""数据模型层模块

定义 RouteRAG 系统的核心数据模型
使用 SQLAlchemy ORM 映射到数据库表
支持 PostgreSQL + pgvector 和 SQLite fallback 两种模式
"""

from sqlalchemy import Column, String, Integer, Float, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.base import Base

# pgvector 向量类型支持
# 如果安装了 pgvector 库，使用原生向量类型；否则使用 JSON fallback
try:
    from pgvector.sqlalchemy import Vector
    VECTOR_DIM = 1024  # 向量维度，与 embedding 模型匹配
    VECTOR_TYPE = Column(Vector(VECTOR_DIM), nullable=False)
except ImportError:
    # Fallback 方案：使用 JSON 存储向量
    VECTOR_TYPE = Column(JSON, nullable=False)


class File(Base):
    """文件模型
    
    表示上传的源文件（PDF、文本文件等）
    记录文件的基本信息、存储路径和处理状态
    
    关系:
        pages: 一对多，文件包含多个页面
        chunks: 一对多，文件包含多个 chunk
        extractions: 一对多，文件包含多个结构化抽取结果
    """
    __tablename__ = "files"

    id = Column(Integer, primary_key=True, index=True)
    file_name = Column(String(255), nullable=False)  # 原始文件名
    file_type = Column(String(50), nullable=False)  # 文件类型：text, pdf 等
    storage_path = Column(String(500))  # 文件存储路径
    source_type = Column(String(50), default="upload")  # 来源类型：upload, import 等
    parse_status = Column(String(50), default="pending")  # 处理状态：pending, indexing, indexed, failed
    created_at = Column(DateTime, default=datetime.utcnow)  # 创建时间

    # 关系定义
    pages = relationship("Page", back_populates="file", cascade="all, delete-orphan")
    chunks = relationship("Chunk", back_populates="file")
    extractions = relationship("StructuredExtraction", back_populates="file", cascade="all, delete-orphan")


class Page(Base):
    """页面模型
    
    表示文档的单个页面
    保留页面级中间结果，用于演示和复核
    
    关系:
        file: 多对一，页面属于某个文件
        chunks: 一对多，页面包含多个 chunk
    """
    __tablename__ = "pages"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("files.id"), nullable=False)  # 所属文件 ID
    page_no = Column(Integer, nullable=False)  # 页码
    page_image_path = Column(String(500))  # 页面图片路径
    page_text = Column(Text)  # 页面文本内容
    page_summary = Column(Text)  # 页面摘要
    page_metadata = Column(JSON)  # 页面元数据（尺寸、版面等）
    created_at = Column(DateTime, default=datetime.utcnow)  # 创建时间

    # 关系定义
    file = relationship("File", back_populates="pages")
    chunks = relationship("Chunk", back_populates="page", cascade="all, delete-orphan")


class Chunk(Base):
    """Chunk 模型
    
    表示文档切分后的文本块
    是向量检索的基本单位
    保留 bbox、block_type 等版面信息
    
    关系:
        file: 多对一，chunk 属于某个文件
        page: 多对一，chunk 属于某个页面（可选）
        embeddings: 一对多，chunk 包含多个向量（支持多模型）
    """
    __tablename__ = "chunks"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("files.id"), nullable=False)  # 所属文件 ID
    page_id = Column(Integer, ForeignKey("pages.id"))  # 所属页面 ID（可选）
    page_no = Column(Integer)  # 页码（冗余字段，便于查询）
    block_type = Column(String(50))  # 块类型：text, table, figure 等
    text_content = Column(Text)  # 文本内容
    image_path = Column(String(500))  # 块对应的图片路径
    bbox = Column(JSON)  # Bounding Box 坐标
    metadata_json = Column(JSON)  # 其他元数据
    created_at = Column(DateTime, default=datetime.utcnow)  # 创建时间

    # 关系定义
    file = relationship("File", back_populates="chunks")
    page = relationship("Page", back_populates="chunks")
    embeddings = relationship("Embedding", back_populates="chunk", cascade="all, delete-orphan")


class Embedding(Base):
    """向量嵌入模型
    
    存储 chunk 的向量表示
    支持 pgvector 原生向量类型或 JSON fallback
    
    关系:
        chunk: 多对一，向量属于某个 chunk
    """
    __tablename__ = "embeddings"

    id = Column(Integer, primary_key=True, index=True)
    chunk_id = Column(Integer, ForeignKey("chunks.id"), nullable=False, index=True)  # 所属 chunk ID
    embedding_model = Column(String(100))  # 使用的 embedding 模型名称
    embedding = VECTOR_TYPE  # 向量数据（pgvector 或 JSON）
    created_at = Column(DateTime, default=datetime.utcnow)  # 创建时间

    # 关系定义
    chunk = relationship("Chunk", back_populates="embeddings")

    def get_embedding_vector(self):
        """获取向量数据
        
        Returns:
            list: 向量列表，如果存储格式不支持则返回 None
        """
        if isinstance(self.embedding, list):
            return self.embedding
        return None


class QueryLog(Base):
    """查询日志模型
    
    记录用户的检索问答历史
    用于审计、分析和优化
    
    关系:
        file: 多对一，查询关联某个文件（可选）
    """
    __tablename__ = "query_logs"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("files.id"))  # 关联的文件 ID（可选）
    query_text = Column(Text, nullable=False)  # 用户查询文本
    answer_text = Column(Text)  # 生成的答案
    retrieved_chunk_ids = Column(JSON)  # 检索到的 chunk ID 列表
    latency_ms = Column(Float)  # 查询延迟（毫秒）
    created_at = Column(DateTime, default=datetime.utcnow)  # 创建时间


class StructuredExtraction(Base):
    """结构化抽取结果模型
    
    存储从文档中抽取的结构化信息
    符合 cable_route_v1 schema
    支持 review_required 机制
    
    关系:
        file: 多对一，抽取结果属于某个文件
    """
    __tablename__ = "structured_extractions"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("files.id"), nullable=False)  # 所属文件 ID
    page_no = Column(Integer)  # 页码
    node_id = Column(String(100))  # 节点编号（如 JD-001）
    node_type = Column(String(50))  # 节点类型：井点、接头盒、盘留等
    prev_node = Column(String(100))  # 上一节点编号
    next_node = Column(String(100))  # 下一节点编号
    distance = Column(Float)  # 距离值
    distance_unit = Column(String(20), default="米")  # 距离单位
    splice_box_id = Column(String(100))  # 接头盒编号
    slack_length = Column(Float)  # 盘留长度
    cable_type = Column(String(100))  # 光缆型号
    fiber_count = Column(Integer)  # 芯数
    remarks = Column(Text)  # 备注信息
    confidence = Column(Float, default=0.0)  # 置信度评分
    review_required = Column(String(50), default="false")  # 是否需要复核
    uncertain_fields = Column(JSON)  # 不确定字段列表
    schema_version = Column(String(50), default="cable_route_v1")  # schema 版本
    created_at = Column(DateTime, default=datetime.utcnow)  # 创建时间

    # 关系定义
    file = relationship("File", back_populates="extractions")
