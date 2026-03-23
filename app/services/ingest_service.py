"""Ingest 服务模块

负责文件接收后的完整处理流程总控
调度解析、切块、向量化入库的完整链路
管理文件处理状态机 (pending → parsing → indexing → indexed/failed)
"""

from typing import List, Optional
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db import models
from app.services.parser_service import ParserService, ParseResult
from app.services.chunk_service import ChunkService
from app.services.embedding_service import embedding_service


class IngestResult(BaseModel):
    """Ingest 处理结果
    
    表示文件 ingest 流程的最终结果
    
    Attributes:
        success: 是否成功
        file_id: 文件 ID
        pages_count: 页面数量
        chunks_count: chunk 数量
        status: 最终状态
        error_message: 错误信息 (如果失败)
    """
    success: bool  # 是否成功
    file_id: int  # 文件 ID
    pages_count: int = 0  # 页面数量
    chunks_count: int = 0  # chunk 数量
    status: str = "pending"  # 最终状态
    error_message: Optional[str] = None  # 错误信息


class IngestService:
    """Ingest 服务类
    
    负责编排文件处理的完整流程
    协调 parser_service、chunk_service、embedding_service 三个服务
    
    处理流程:
        1. 解析文件 (parser_service)
        2. 创建页面对象 (chunk_service)
        3. 创建 chunk 对象 (chunk_service)
        4. 生成向量嵌入 (embedding_service)
        5. 更新文件状态
    
    状态机:
        pending → parsing → indexing → indexed (成功)
        pending → parsing → failed (失败)
    
    Attributes:
        parser_service: 解析服务实例
    """
    
    def __init__(self):
        """初始化 Ingest 服务
        
        创建必要的服务实例
        """
        self.parser_service = ParserService()
    
    def ingest_file(
        self,
        db: Session,
        file: models.File
    ) -> IngestResult:
        """编排完整 ingest 流程
        
        文件上传后的主入口方法
        按顺序执行解析、切块、向量化入库
        
        Args:
            db: 数据库会话
            file: 待处理的文件对象
            
        Returns:
            IngestResult: ingest 处理结果
            
        处理流程:
            1. 更新状态为 parsing
            2. 调用 _parse_file 解析文件
            3. 更新状态为 indexing
            4. 调用 _create_chunks 创建 chunk
            5. 调用 _generate_embeddings 生成向量
            6. 更新状态为 indexed
            
        异常处理:
            - 任何步骤失败时，状态更新为 failed
            - 记录详细的错误信息
        """
        try:
            # Step 1: 更新状态为 parsing
            self._update_status(db, file, "parsing")
            
            # Step 2: 解析文件
            parse_result = self._parse_file(db, file)
            
            # Step 3: 更新状态为 indexing
            self._update_status(db, file, "indexing")
            
            # Step 4: 创建 chunk 对象
            chunks = self._create_chunks(db, file, parse_result)
            
            # Step 5: 生成向量嵌入
            self._generate_embeddings(db, chunks)
            
            # Step 6: 更新状态为 indexed
            self._update_status(db, file, "indexed")
            
            # 返回成功结果
            return IngestResult(
                success=True,
                file_id=file.id,
                pages_count=len(parse_result.pages),
                chunks_count=len(chunks),
                status="indexed"
            )
            
        except Exception as e:
            # 失败处理：更新状态为 failed
            error_message = f"Ingest failed: {str(e)}"
            self._update_status(db, file, "failed", error_message)
            
            return IngestResult(
                success=False,
                file_id=file.id,
                status="failed",
                error_message=error_message
            )
    
    def _update_status(
        self,
        db: Session,
        file: models.File,
        status: str,
        error_message: Optional[str] = None
    ):
        """更新文件处理状态
        
        将文件的状态变更持久化到数据库
        
        Args:
            db: 数据库会话
            file: 文件对象
            status: 新状态 (parsing, indexing, indexed, failed)
            error_message: 错误信息 (可选，仅在失败时提供)
            
        Note:
            - 每次状态变更都会 commit 到数据库
            - 错误信息记录在 parse_status 字段 (简单实现)
            - 生产环境建议使用专门的 error_message 字段
        """
        file.parse_status = status
        if error_message:
            # 简单实现：将错误信息附加到状态后
            # 生产环境建议使用专门的字段
            file.parse_status = f"{status}: {error_message[:100]}"
        
        db.add(file)
        db.commit()
        db.refresh(file)
    
    def _parse_file(
        self,
        db: Session,
        file: models.File
    ) -> ParseResult:
        """调用 parser_service 解析文件
        
        根据文件类型选择合适的解析器
        目前仅支持 PDF 文件
        
        Args:
            db: 数据库会话
            file: 文件对象
            
        Returns:
            ParseResult: 解析结果
            
        Raises:
            ValueError: 不支持的文件类型
            FileNotFoundError: 文件不存在
            RuntimeError: 解析失败
        """
        # 获取文件路径
        file_path = file.storage_path
        
        if not file_path:
            raise ValueError(f"File {file.id} has no storage_path")
        
        # 根据文件类型选择解析器
        if file.file_type == "pdf":
            # PDF 文件：使用 parser_service
            parse_result = self.parser_service.parse_pdf(file_path)
        elif file.file_type == "text":
            # 文本文件：直接读取文件内容
            parse_result = self.parser_service.parse_text_file(file_path)
        else:
            raise ValueError(f"Unsupported file type: {file.file_type}")
        
        return parse_result
    
    def _create_chunks(
        self,
        db: Session,
        file: models.File,
        parse_result: ParseResult
    ) -> List[models.Chunk]:
        """调用 chunk_service 创建 chunk 对象
        
        将解析结果转换为数据库模型
        包括页面对象和 chunk 对象
        
        Args:
            db: 数据库会话
            file: 文件对象
            parse_result: 解析结果
            
        Returns:
            List[models.Chunk]: 创建的 chunk 列表
            
        Note:
            - 使用 ChunkService 的 create_all_objects 一站式方法
            - 同时创建 Page 和 Chunk 对象
            - 保留所有元数据 (bbox, page_no, block_type)
        """
        # 创建 chunk 服务
        chunk_service = ChunkService(db)
        
        # 一站式创建页面和 chunk 对象
        pages, chunks = chunk_service.create_all_objects(
            file.id,
            parse_result
        )
        
        return chunks
    
    def _generate_embeddings(
        self,
        db: Session,
        chunks: List[models.Chunk]
    ):
        """调用 embedding_service 生成向量嵌入
        
        为每个 chunk 生成向量并保存到数据库
        
        Args:
            db: 数据库会话
            chunks: chunk 列表
            
        Raises:
            RuntimeError: 向量化失败
            
        Note:
            - 批量处理所有 chunks
            - 使用 embedding_service 的 embed_texts 方法
            - 向量保存到 Embedding 表
        """
        # 提取所有 chunk 的文本内容
        texts = [chunk.text_content for chunk in chunks if chunk.text_content]
        
        if not texts:
            # 没有文本内容，跳过向量化
            return
        
        try:
            # 批量生成向量
            vectors = embedding_service.embed_texts(texts)
            
            # 创建 Embedding 记录
            embeddings = []
            for chunk, vector in zip(chunks, vectors):
                embedding = models.Embedding(
                    chunk_id=chunk.id,
                    embedding_model=embedding_service.model_name,
                    embedding=vector
                )
                embeddings.append(embedding)
                db.add(embedding)
            
            # 批量提交
            db.commit()
            
        except Exception as e:
            db.rollback()
            raise RuntimeError(f"Failed to generate embeddings: {str(e)}")


# 便捷函数

def ingest_file(
    db: Session,
    file: models.File
) -> IngestResult:
    """便捷函数：执行 ingest 流程
    
    Args:
        db: 数据库会话
        file: 文件对象
        
    Returns:
        IngestResult: ingest 结果
    """
    service = IngestService()
    return service.ingest_file(db, file)


def update_file_status(
    db: Session,
    file: models.File,
    status: str,
    error_message: Optional[str] = None
):
    """便捷函数：更新文件状态
    
    Args:
        db: 数据库会话
        file: 文件对象
        status: 新状态
        error_message: 错误信息
    """
    service = IngestService()
    service._update_status(db, file, status, error_message)