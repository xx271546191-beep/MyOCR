"""Chunk 服务模块

负责将解析结果转换为数据库模型对象
支持固定长度切块和语义切块
保留 bbox、page_no、block_type 等关键信息
为后续的 embedding 生成做准备
"""

from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from app.db import models
from app.services.parser_service import ParseResult
from app.services.extraction_service import ExtractionService


class ChunkService:
    """Chunk 服务类
    
    负责将解析结果转换为数据库模型
    创建 Page 和 Chunk 记录并保存到数据库
    
    设计原则:
        1. 解析结果到数据库模型的转换
        2. 保留所有元数据 (bbox, page_no, block_type)
        3. 支持批量创建，提高效率
    
    Attributes:
        db: 数据库会话
    """
    
    def __init__(self, db: Session):
        """初始化 Chunk 服务
        
        Args:
            db: SQLAlchemy 数据库会话
        """
        self.db = db
    
    def create_page_objects(
        self,
        file_id: int,
        parse_result: ParseResult
    ) -> List[models.Page]:
        """创建页面级对象
        
        将解析结果中的页面信息转换为 Page 模型
        保存到数据库并返回
        
        Args:
            file_id: 所属文件 ID
            parse_result: 解析结果
            
        Returns:
            List[models.Page]: 创建的页面对象列表
            
        处理逻辑:
            1. 遍历解析结果中的每个页面
            2. 提取页面文本、图片路径、页码
            3. 创建 Page 模型并保存到数据库
            4. 返回所有创建的页面对象
        """
        page_objects = []
        
        # 遍历解析结果中的所有页面
        for page_result in parse_result.pages:
            # 创建页面对象
            page = models.Page(
                file_id=file_id,
                page_no=page_result.page_no,
                page_image_path=page_result.page_image_path,
                page_text=page_result.page_text,
                page_summary=None,  # 可后续通过 LLM 生成摘要
                page_metadata={
                    "parser": parse_result.file_name,
                    "total_pages": parse_result.total_pages
                }
            )
            
            self.db.add(page)
            page_objects.append(page)
        
        # 批量提交到数据库
        self.db.commit()
        
        # 刷新获取数据库生成的 ID
        for page in page_objects:
            self.db.refresh(page)
        
        return page_objects
    
    def create_chunk_objects(
        self,
        file_id: int,
        parse_result: ParseResult,
        page_objects: List[models.Page] = None
    ) -> List[models.Chunk]:
        """创建块级对象
        
        将解析结果中的块信息转换为 Chunk 模型
        保存到数据库并返回
        
        Args:
            file_id: 所属文件 ID
            parse_result: 解析结果
            page_objects: 页面对象列表 (可选，用于建立关联)
            
        Returns:
            List[models.Chunk]: 创建的 chunk 对象列表
            
        处理逻辑:
            1. 遍历解析结果中的每个页面的每个块
            2. 提取块文本、块类型、bbox 等信息
            3. 如果提供了 page_objects，建立与页面的关联
            4. 创建 Chunk 模型并保存到数据库
            5. 返回所有创建的 chunk 对象
            
        Note:
            - page_objects 为空时，只创建 chunk 不建立 page 关联
            - 这样设计是为了支持灵活的调用方式
        """
        chunk_objects = []
        
        # 建立 page_no 到 Page 对象的映射
        page_map = {}
        if page_objects:
            page_map = {page.page_no: page for page in page_objects}
        
        # 遍历解析结果中的所有页面和块
        for page_result in parse_result.pages:
            page_no = page_result.page_no
            page_obj = page_map.get(page_no)
            
            for block_result in page_result.blocks:
                # 创建 chunk 对象
                chunk = models.Chunk(
                    file_id=file_id,
                    page_id=page_obj.id if page_obj else None,  # 页面关联
                    page_no=page_no,  # 页码冗余存储，便于查询
                    block_type=block_result.block_type,  # 块类型：text, table, figure
                    text_content=block_result.text_content,  # 块文本内容
                    image_path=block_result.image_path,  # 块图片路径
                    bbox=block_result.bbox,  # 边界框坐标
                    metadata_json={
                        "parser": parse_result.file_name,
                        "source": "parser_service"
                    }
                )
                
                self.db.add(chunk)
                chunk_objects.append(chunk)
        
        # 批量提交到数据库
        self.db.commit()
        
        # 刷新获取数据库生成的 ID
        for chunk in chunk_objects:
            self.db.refresh(chunk)
        
        return chunk_objects
    
    def create_all_objects(
        self,
        file_id: int,
        parse_result: ParseResult
    ) -> tuple[List[models.Page], List[models.Chunk]]:
        """创建页面和块对象 (一站式方法)
        
        便捷方法，一次调用完成页面和块的创建
        
        Args:
            file_id: 所属文件 ID
            parse_result: 解析结果
            
        Returns:
            Tuple[List[models.Page], List[models.Chunk]]: (页面列表, chunk 列表)
            
        处理流程:
            1. 先创建页面对象
            2. 使用页面对象创建 chunk 对象
            3. 返回两者
        """
        # 第一步：创建页面对象
        page_objects = self.create_page_objects(file_id, parse_result)
        
        # 第二步：创建 chunk 对象 (带页面关联)
        chunk_objects = self.create_chunk_objects(
            file_id, 
            parse_result, 
            page_objects
        )
        
        return page_objects, chunk_objects
    
    def create_chunks_with_semantic_splitting(
        self,
        file_id: int,
        parse_result: ParseResult,
        use_semantic: bool = True
    ) -> Tuple[List[models.Page], List[models.Chunk]]:
        """使用语义切块创建页面和 chunk 对象
        
        增强的切块方法，支持语义切块和固定长度切块
        
        Args:
            file_id: 所属文件 ID
            parse_result: 解析结果
            use_semantic: 是否使用语义切块，默认 True
            
        Returns:
            Tuple[List[models.Page], List[models.Chunk]]: (页面列表，chunk 列表)
            
        处理流程:
            1. 创建页面对象
            2. 对每页进行语义切块 (或固定长度切块)
            3. 创建 chunk 对象并关联到页面
            4. 返回页面和 chunk 列表
        """
        # 第一步：创建页面对象
        page_objects = self.create_page_objects(file_id, parse_result)
        
        chunk_objects = []
        
        # 第二步：语义切块
        if use_semantic:
            extraction_service = ExtractionService()
            
            for page_result in parse_result.pages:
                page_no = page_result.page_no
                page_obj = next((p for p in page_objects if p.page_no == page_no), None)
                
                # 使用语义切块
                semantic_chunks = extraction_service.semantic_chunking(
                    page_result.page_text,
                    file_id,
                    page_no
                )
                
                # 将语义块转换为数据库模型
                for sem_chunk in semantic_chunks:
                    chunk = models.Chunk(
                        file_id=file_id,
                        page_id=page_obj.id if page_obj else None,
                        page_no=page_no,
                        block_type=sem_chunk.block_type,
                        text_content=sem_chunk.text_content,
                        image_path=None,
                        bbox=sem_chunk.bbox,
                        metadata_json={
                            "parser": parse_result.file_name,
                            "chunking_method": "semantic",
                            "context": sem_chunk.context
                        }
                    )
                    self.db.add(chunk)
                    chunk_objects.append(chunk)
        else:
            # 使用固定长度切块 (原有逻辑)
            chunk_objects = self.create_chunk_objects(
                file_id,
                parse_result,
                page_objects
            )
        
        # 提交到数据库
        self.db.commit()
        
        # 刷新获取数据库生成的 ID
        for chunk in chunk_objects:
            self.db.refresh(chunk)
        
        return page_objects, chunk_objects


# 便捷函数

def create_page_objects(
    db: Session,
    file_id: int,
    parse_result: ParseResult
) -> List[models.Page]:
    """便捷函数：创建页面对象
    
    Args:
        db: 数据库会话
        file_id: 文件 ID
        parse_result: 解析结果
        
    Returns:
        List[models.Page]: 页面列表
    """
    service = ChunkService(db)
    return service.create_page_objects(file_id, parse_result)


def create_chunk_objects(
    db: Session,
    file_id: int,
    parse_result: ParseResult,
    page_objects: List[models.Page] = None
) -> List[models.Chunk]:
    """便捷函数：创建 chunk 对象
    
    Args:
        db: 数据库会话
        file_id: 文件 ID
        parse_result: 解析结果
        page_objects: 页面对象列表
        
    Returns:
        List[models.Chunk]: chunk 列表
    """
    service = ChunkService(db)
    return service.create_chunk_objects(file_id, parse_result, page_objects)


def create_all_objects(
    db: Session,
    file_id: int,
    parse_result: ParseResult
) -> tuple[List[models.Page], List[models.Chunk]]:
    """便捷函数：创建页面和 chunk 对象
    
    Args:
        db: 数据库会话
        file_id: 文件 ID
        parse_result: 解析结果
        
    Returns:
        Tuple[List[models.Page], List[models.Chunk]]: (页面列表, chunk 列表)
    """
    service = ChunkService(db)
    return service.create_all_objects(file_id, parse_result)