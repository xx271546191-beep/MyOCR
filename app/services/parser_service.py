"""文档解析服务模块

负责封装 PDF 和图片的解析能力
支持多种解析器后端 (pypdf 首期，olmOCR 后续)
输出统一的解析结果结构 (ParseResult)
"""

from typing import List, Optional
from pydantic import BaseModel
from pathlib import Path
import io


class BlockResult(BaseModel):
    """块级解析结果
    
    表示 PDF 页面中的单个内容块
    可以是文本、表格、图片等类型
    
    Attributes:
        block_type: 块类型 (text, table, figure)
        text_content: 块文本内容
        bbox: 边界框坐标 {x, y, width, height}
        image_path: 块对应的图片路径 (可选)
    """
    block_type: str  # 块类型：text, table, figure
    text_content: str  # 块文本内容
    bbox: Optional[dict] = None  # 边界框坐标
    image_path: Optional[str] = None  # 图片路径 (可选)


class PageResult(BaseModel):
    """页面级解析结果
    
    表示 PDF 文档的单个页面
    包含页面文本和页面内的所有块
    
    Attributes:
        page_no: 页码 (从 1 开始)
        page_text: 页面完整文本
        page_image_path: 页面图片路径 (可选)
        blocks: 页面内的块列表
    """
    page_no: int  # 页码
    page_text: str  # 页面完整文本
    page_image_path: Optional[str] = None  # 页面图片路径
    blocks: List[BlockResult] = []  # 块列表


class ParseResult(BaseModel):
    """文档解析结果
    
    表示整个文档的解析结果
    包含所有页面的解析数据
    
    Attributes:
        pages: 页面列表
        total_pages: 总页数
        file_name: 文件名
    """
    pages: List[PageResult]  # 页面列表
    total_pages: int  # 总页数
    file_name: str  # 文件名


class ParserService:
    """文档解析服务类
    
    负责封装 PDF 解析能力，输出统一的解析结果结构
    支持多种解析器后端 (首期 pypdf，后续 olmOCR)
    
    设计原则:
        1. 统一的输入输出接口，隔离解析器差异
        2. 首期支持 pypdf，后续可扩展到 olmOCR
        3. 异常处理完善，解析失败时给出明确错误信息
    
    Attributes:
        parser_type: 当前使用的解析器类型 (pypdf/olmOCR)
    """
    
    def __init__(self, parser_type: str = "pypdf"):
        """初始化解析服务
        
        Args:
            parser_type: 解析器类型，默认 pypdf
        """
        self.parser_type = parser_type
    
    def parse_pdf(self, file_path: str) -> ParseResult:
        """解析 PDF 文件
        
        读取 PDF 文件，解析每页的文本内容
        将结果封装为 ParseResult 统一格式
        
        Args:
            file_path: PDF 文件的绝对路径或相对路径
            
        Returns:
            ParseResult: 包含所有页面解析结果的统一结构
            
        Raises:
            FileNotFoundError: 文件不存在
            ValueError: 文件不是有效的 PDF
            RuntimeError: PDF 解析失败
        """
        # 检查文件是否存在
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {file_path}")
        
        # 检查文件扩展名
        if path.suffix.lower() != ".pdf":
            raise ValueError(f"Expected PDF file, got: {path.suffix}")
        
        # 根据解析器类型选择解析方法
        if self.parser_type == "pypdf":
            return self._parse_with_pypdf(file_path)
        elif self.parser_type == "olmocr":
            return self._parse_with_olmocr(file_path)
        else:
            raise ValueError(f"Unknown parser type: {self.parser_type}")
    
    def _parse_with_pypdf(self, file_path: str) -> ParseResult:
        """使用 pypdf 解析 PDF
        
        使用 pypdf 库提取 PDF 中的文本内容
        将每页文本作为一个块处理
        
        Args:
            file_path: PDF 文件路径
            
        Returns:
            ParseResult: 解析结果
            
        Raises:
            RuntimeError: pypdf 解析失败
        """
        try:
            from pypdf import PdfReader
        except ImportError:
            raise RuntimeError(
                "pypdf is not installed. Install it with: pip install pypdf"
            )
        
        try:
            # 读取 PDF 文件
            path = Path(file_path)
            reader = PdfReader(file_path)
            
            pages_result = []
            
            # 遍历每页，提取文本
            for page_num, page in enumerate(reader.pages, start=1):
                # 提取页面文本
                page_text = page.extract_text()
                
                if not page_text:
                    # 空页面也保留，只是没有文本内容
                    page_text = ""
                
                # 创建块结果
                # pypdf 只能提取文本，块类型默认为 text
                block = BlockResult(
                    block_type="text",
                    text_content=page_text,
                    bbox=None,  # pypdf 不提供 bbox 信息
                    image_path=None
                )
                
                # 创建页面结果
                page_result = PageResult(
                    page_no=page_num,
                    page_text=page_text,
                    page_image_path=None,  # pypdf 不处理图片
                    blocks=[block]
                )
                
                pages_result.append(page_result)
            
            # 创建最终结果
            result = ParseResult(
                pages=pages_result,
                total_pages=len(pages_result),
                file_name=path.name
            )
            
            return result
            
        except Exception as e:
            raise RuntimeError(f"Failed to parse PDF with pypdf: {str(e)}")
    
    def _parse_with_olmocr(self, file_path: str) -> ParseResult:
        """使用 olmOCR 解析 PDF (后续实现)
        
        olmOCR 是更高级的 PDF 解析工具
        可以提取版面布局、表格、 bbox 等详细信息
        
        Args:
            file_path: PDF 文件路径
            
        Returns:
            ParseResult: 解析结果
            
        Raises:
            NotImplementedError: olmOCR 解析器尚未实现
        """
        raise NotImplementedError(
            "olmOCR parser is not implemented yet. "
            "Please use pypdf for now."
        )
    
    def parse_text_file(self, file_path: str) -> ParseResult:
        """解析纯文本文件
        
        直接读取文本文件内容，封装为 ParseResult 格式
        整个文件作为单个页面处理
        
        Args:
            file_path: 文本文件路径
            
        Returns:
            ParseResult: 解析结果
            
        Raises:
            FileNotFoundError: 文件不存在
            RuntimeError: 文件读取失败
        """
        # 检查文件是否存在
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Text file not found: {file_path}")
        
        try:
            # 读取文件内容 (UTF-8 编码)
            content = path.read_text(encoding="utf-8", errors="ignore")
            
            # 创建块结果
            block = BlockResult(
                block_type="text",
                text_content=content,
                bbox=None,
                image_path=None
            )
            
            # 创建页面结果 (整个文件作为一页)
            page_result = PageResult(
                page_no=1,
                page_text=content,
                page_image_path=None,
                blocks=[block]
            )
            
            # 创建最终结果
            result = ParseResult(
                pages=[page_result],
                total_pages=1,
                file_name=path.name
            )
            
            return result
            
        except Exception as e:
            raise RuntimeError(f"Failed to read text file: {str(e)}")
    
    def parse_image(self, file_path: str) -> ParseResult:
        """解析图片文件 (后续实现 OCR)
        
        读取图片文件，使用 OCR 技术提取文本
        当前版本暂不支持，返回明确错误
        
        Args:
            file_path: 图片文件路径
            
        Returns:
            ParseResult: 解析结果
            
        Raises:
            NotImplementedError: 图片 OCR 尚未实现
        """
        # 检查文件是否存在
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Image file not found: {file_path}")
        
        # 检查文件是否是图片
        image_extensions = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".gif"}
        if path.suffix.lower() not in image_extensions:
            raise ValueError(f"Expected image file, got: {path.suffix}")
        
        # 当前版本不支持图片 OCR
        raise NotImplementedError(
            "Image OCR is not implemented yet. "
            "Only PDF parsing is supported in this version."
        )
    
    @staticmethod
    def is_supported(file_path: str) -> bool:
        """检查文件是否支持解析
        
        Args:
            file_path: 文件路径
            
        Returns:
            bool: 是否支持解析
        """
        path = Path(file_path)
        supported_extensions = {".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".gif"}
        return path.suffix.lower() in supported_extensions


# 全局单例，供整个应用使用
parser_service = ParserService()


def parse_pdf(file_path: str) -> ParseResult:
    """便捷函数：解析 PDF 文件
    
    Args:
        file_path: PDF 文件路径
        
    Returns:
        ParseResult: 解析结果
    """
    return parser_service.parse_pdf(file_path)


def parse_image(file_path: str) -> ParseResult:
    """便捷函数：解析图片文件
    
    Args:
        file_path: 图片文件路径
        
    Returns:
        ParseResult: 解析结果
    """
    return parser_service.parse_image(file_path)


def is_supported(file_path: str) -> bool:
    """便捷函数：检查文件是否支持解析
    
    Args:
        file_path: 文件路径
        
    Returns:
        bool: 是否支持
    """
    return ParserService.is_supported(file_path)
