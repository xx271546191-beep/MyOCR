"""结构化抽取 Schema 模块

定义结构化抽取相关的请求、响应和数据模型
支持 cable_route_v1 schema 的输入输出
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

from app.schemas.file import FilePrecheckResponse
from app.schemas.review import ReviewSummaryResponse
from app.schemas.topology import TopologySummaryResponse


class CableRouteNode(BaseModel):
    """光缆路由节点 Schema (cable_route_v1)
    
    表示光缆路由图中的一个节点
    包含节点属性、连接关系、距离等信息
    
    Attributes:
        node_id: 节点编号
        node_type: 节点类型 (joint, terminal, splice_box, etc.)
        prev_node: 上一端节点编号
        next_node: 下一端节点编号
        distance: 距离值
        distance_unit: 距离单位 (m, km)
        splice_box_id: 接头盒编号
        slack_length: 盘留长度
        cable_type: 光缆类型
        fiber_count: 光纤芯数
        remarks: 备注信息
        confidence: 置信度 (0-1)
        review_required: 是否需要人工复核
        uncertain_fields: 不确定字段列表
    """
    node_id: Optional[str] = Field(None, description="节点编号")
    node_type: Optional[str] = Field(None, description="节点类型")
    prev_node: Optional[str] = Field(None, description="上一端节点编号")
    next_node: Optional[str] = Field(None, description="下一端节点编号")
    distance: Optional[float] = Field(None, description="距离值")
    distance_unit: Optional[str] = Field(None, description="距离单位")
    splice_box_id: Optional[str] = Field(None, description="接头盒编号")
    slack_length: Optional[float] = Field(None, description="盘留长度")
    cable_type: Optional[str] = Field(None, description="光缆类型")
    fiber_count: Optional[int] = Field(None, description="光纤芯数")
    remarks: Optional[str] = Field(None, description="备注信息")
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="置信度")
    review_required: bool = Field(False, description="是否需要人工复核")
    uncertain_fields: List[str] = Field(default_factory=list, description="不确定字段列表")
    
    class Config:
        json_schema_extra = {
            "example": {
                "node_id": "J001",
                "node_type": "joint",
                "prev_node": "J000",
                "next_node": "J002",
                "distance": 150.5,
                "distance_unit": "m",
                "splice_box_id": "SB001",
                "slack_length": 10.0,
                "cable_type": "GYTA53",
                "fiber_count": 24,
                "remarks": "过路管",
                "confidence": 0.85,
                "review_required": False,
                "uncertain_fields": []
            }
        }


class ExtractionRequest(BaseModel):
    """结构化抽取请求
    
    Attributes:
        file_id: 文件 ID
        page_nos: 指定页码列表 (可选，默认全部)
        node_types: 指定节点类型列表 (可选，默认全部)
        include_image: 是否包含节点图片路径
    """
    file_id: int = Field(..., description="文件 ID")
    page_nos: Optional[List[int]] = Field(None, description="指定页码列表")
    node_types: Optional[List[str]] = Field(None, description="指定节点类型列表")
    include_image: bool = Field(False, description="是否包含节点图片路径")
    
    class Config:
        json_schema_extra = {
            "example": {
                "file_id": 1,
                "page_nos": [1, 2],
                "node_types": ["joint", "splice_box"],
                "include_image": False
            }
        }


class ExtractionResponse(BaseModel):
    """结构化抽取响应
    
    Attributes:
        success: 是否成功
        file_id: 文件 ID
        schema_version: schema 版本
        nodes: 抽取的节点列表
        total_nodes: 节点总数
        review_count: 需要复核的节点数
        low_confidence_count: 低置信度节点数
        processing_time_ms: 处理时间 (毫秒)
        error_message: 错误信息 (如果失败)
        risk_notice: 文件级风险提示
    """
    success: bool
    file_id: int
    schema_version: str = "cable_route_v1"
    nodes: List[CableRouteNode] = Field(default_factory=list)
    total_nodes: int = 0
    review_count: int = 0
    low_confidence_count: int = 0
    processing_time_ms: float = 0.0
    error_message: Optional[str] = None
    risk_notice: Optional[FilePrecheckResponse] = None
    topology_summary: TopologySummaryResponse = Field(default_factory=TopologySummaryResponse)
    review_summary: ReviewSummaryResponse = Field(default_factory=ReviewSummaryResponse)
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "file_id": 1,
                "schema_version": "cable_route_v1",
                "nodes": [
                    {
                        "node_id": "J001",
                        "node_type": "joint",
                        "prev_node": "J000",
                        "next_node": "J002",
                        "distance": 150.5,
                        "distance_unit": "m",
                        "confidence": 0.85,
                        "review_required": False,
                        "uncertain_fields": []
                    }
                ],
                "total_nodes": 1,
                "review_count": 0,
                "low_confidence_count": 0,
                "processing_time_ms": 1250.5
            }
        }


class BlockClassification(BaseModel):
    """块分类结果
    
    Attributes:
        block_type: 块类型 (title, paragraph, table, figure, etc.)
        confidence: 分类置信度
        bbox: 边界框坐标
        text_content: 文本内容
        metadata: 额外元数据
    """
    block_type: str = Field(..., description="块类型")
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="分类置信度")
    bbox: Optional[Dict[str, float]] = Field(None, description="边界框坐标")
    text_content: str = Field("", description="文本内容")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="额外元数据")


class LayoutAnalysisResult(BaseModel):
    """版面分析结果
    
    Attributes:
        file_id: 文件 ID
        page_no: 页码
        blocks: 块列表
        total_blocks: 块总数
        processing_time_ms: 处理时间
    """
    file_id: int
    page_no: int
    blocks: List[BlockClassification] = Field(default_factory=list)
    total_blocks: int = 0
    processing_time_ms: float = 0.0


class SemanticChunk(BaseModel):
    """语义切块结果
    
    基于语义而非固定长度的切块
    保留完整的上下文信息
    
    Attributes:
        chunk_id: 块 ID
        file_id: 文件 ID
        page_no: 页码
        block_type: 块类型
        text_content: 文本内容
        context: 上下文信息
        metadata: 元数据
        bbox: 边界框
    """
    chunk_id: str
    file_id: int
    page_no: int
    block_type: str
    text_content: str
    context: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    bbox: Optional[Dict[str, float]] = None
