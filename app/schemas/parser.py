"""解析结果 Schema 定义模块

定义文档解析的请求和响应结构
与 parser_service.py 配合使用
"""

from pydantic import BaseModel
from typing import List, Optional


class BlockSchema(BaseModel):
    """块级解析结果 Schema
    
    Attributes:
        block_type: 块类型 (text, table, figure)
        text_content: 块文本内容
        bbox: 边界框坐标 (可选)
        image_path: 图片路径 (可选)
    """
    block_type: str  # 块类型
    text_content: str  # 文本内容
    bbox: Optional[dict] = None  # 边界框
    image_path: Optional[str] = None  # 图片路径


class PageSchema(BaseModel):
    """页面级解析结果 Schema
    
    Attributes:
        page_no: 页码
        page_text: 页面完整文本
        page_image_path: 页面图片路径 (可选)
        blocks: 块列表
    """
    page_no: int  # 页码
    page_text: str  # 页面文本
    page_image_path: Optional[str] = None  # 图片路径
    blocks: List[BlockSchema] = []  # 块列表


class ParseResultSchema(BaseModel):
    """文档解析结果 Schema
    
    Attributes:
        pages: 页面列表
        total_pages: 总页数
        file_name: 文件名
    """
    pages: List[PageSchema]  # 页面列表
    total_pages: int  # 总页数
    file_name: str  # 文件名


class ParseRequestSchema(BaseModel):
    """文档解析请求 Schema
    
    Attributes:
        file_path: 文件路径
        parser_type: 解析器类型 (可选，默认 pypdf)
    """
    file_path: str  # 文件路径
    parser_type: Optional[str] = "pypdf"  # 解析器类型