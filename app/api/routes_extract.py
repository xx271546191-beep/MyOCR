"""结构化抽取相关 API 路由。

负责暴露抽取执行、抽取 schema 查询以及已持久化抽取结果回读接口。
这些接口共同组成 Stage 3 的抽取能力对外契约。
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.extraction import ExtractionRequest, ExtractionResponse
from app.services.extraction_service import ExtractionService


router = APIRouter()


@router.post("/extract", response_model=ExtractionResponse)
async def extract_structured_info(
    request: ExtractionRequest,
    db: Session = Depends(get_db),
):
    """按请求参数执行结构化抽取。"""
    result = ExtractionService().extract_from_file(db, request)
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error_message)
    return result


@router.get("/extract/schema")
async def get_schema_info():
    """返回当前支持的抽取 schema 定义。

    这个接口用于前端、测试脚本和阶段验收快速确认
    `cable_route_v1` 的字段范围及基本约束。
    """
    return {
        "schema_version": "cable_route_v1",
        "description": "光缆路由图结构化信息 schema",
        "fields": {
            "node_id": {"type": "string", "description": "节点编号", "example": "J001"},
            "node_type": {
                "type": "string",
                "description": "节点类型 (joint, terminal, splice_box, manhole, pole)",
                "example": "joint",
            },
            "prev_node": {"type": "string", "description": "上一节点编号", "example": "J000"},
            "next_node": {"type": "string", "description": "下一节点编号", "example": "J002"},
            "distance": {"type": "number", "description": "距离值", "example": 150.5},
            "distance_unit": {"type": "string", "description": "距离单位 (m, km)", "example": "m"},
            "splice_box_id": {"type": "string", "description": "接头盒编号", "example": "SB001"},
            "slack_length": {"type": "number", "description": "盘留长度", "example": 10.0},
            "cable_type": {"type": "string", "description": "光缆型号", "example": "GYTA53"},
            "fiber_count": {"type": "integer", "description": "光纤芯数", "example": 24},
            "remarks": {"type": "string", "description": "备注信息", "example": "过路管"},
            "confidence": {"type": "number", "description": "置信度 (0-1)", "example": 0.85},
            "review_required": {
                "type": "boolean",
                "description": "是否需要人工复核",
                "example": False,
            },
            "uncertain_fields": {
                "type": "array",
                "description": "不确定字段列表",
                "example": ["distance"],
            },
        },
        "constraints": [
            "不允许输出 schema 外核心字段",
            "缺失字段允许为 null",
            "不确定字段必须进入 uncertain_fields",
            "低置信度必须触发 review_required",
        ],
    }


@router.post("/extract/{file_id}", response_model=ExtractionResponse)
async def extract_structured_info_by_path(
    file_id: int,
    db: Session = Depends(get_db),
):
    """使用 RESTful 路径参数触发抽取。"""
    result = ExtractionService().extract_from_file(
        db,
        ExtractionRequest(file_id=file_id),
    )
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error_message)
    return result


@router.get("/extract/{file_id}", response_model=ExtractionResponse)
async def get_extraction_result(
    file_id: int,
    db: Session = Depends(get_db),
):
    """读取指定文件已持久化的抽取结果。"""
    result = ExtractionService().get_saved_extractions(db, file_id)
    if not result.success:
        raise HTTPException(status_code=404, detail=result.error_message)
    return result
