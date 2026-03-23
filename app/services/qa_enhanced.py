"""QA 增强服务。"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.db import models
from app.services.topology_service import build_topology_summary_from_records


FIXED_QUESTION_TEMPLATES = {
    "node_connection": {
        "description": "查询节点的连接关系",
        "keywords": ["上一端", "下一端", "prev_node", "next_node", "连接"],
    },
    "distance": {
        "description": "查询距离信息",
        "keywords": ["距离", "distance", "多远", "间隔"],
    },
    "node_type": {
        "description": "查询节点类型",
        "keywords": ["类型", "node_type", "什么节点", "joint", "terminal"],
    },
    "cable_info": {
        "description": "查询光缆信息",
        "keywords": ["光缆", "型号", "fiber_count", "芯数"],
    },
    "splice_box": {
        "description": "查询接头盒信息",
        "keywords": ["接头盒", "splice_box", "接线盒"],
    },
}


class QAEnhancer:
    """提供题型识别、答案质量评估和结构化关系问答增强。"""

    def __init__(self, confidence_threshold: float = 0.6):
        self.confidence_threshold = confidence_threshold

    def classify_question(self, query: str) -> Optional[str]:
        """识别问题所属的固定题型。"""
        lowered = query.lower()
        for question_type, config in FIXED_QUESTION_TEMPLATES.items():
            if any(keyword.lower() in lowered for keyword in config["keywords"]):
                return question_type
        return None

    def extract_question_params(self, query: str, question_type: str) -> Dict[str, str]:
        """从问题中提取结构化参数。"""
        params: Dict[str, str] = {}

        node_matches = re.findall(r"\b(J\d+)\b", query, re.IGNORECASE)
        if node_matches:
            params["node_id"] = node_matches[0].upper()
            if question_type == "distance" and len(node_matches) > 1:
                params["next_node_id"] = node_matches[1].upper()

        splice_matches = re.findall(r"\b(SB\d+)\b", query, re.IGNORECASE)
        if splice_matches:
            params["splice_box_id"] = splice_matches[0].upper()

        return params

    def parse_answer(self, answer_text: str) -> Tuple[Optional[str], float, List[str]]:
        """解析 LLM 文本答案中的置信度和引用信息。"""
        confidence = 0.5
        confidence_match = re.search(r"置信度[：:]\s*([0-9.]+)", answer_text)
        if confidence_match:
            try:
                confidence = float(confidence_match.group(1))
            except ValueError:
                pass

        chunk_ids = re.findall(r"\[chunk_id:\s*([^\]]+)\]", answer_text, re.IGNORECASE)
        if not chunk_ids:
            chunk_ids = re.findall(r"\[([^\]]*chunk[^\]]*)\]", answer_text, re.IGNORECASE)

        return answer_text, confidence, chunk_ids

    def check_answer_quality(
        self,
        answer: str,
        confidence: float,
        chunk_ids: List[str],
    ) -> Dict[str, Any]:
        """评估答案质量，输出复核建议。"""
        issues = []

        if confidence < self.confidence_threshold:
            issues.append("low_confidence")
        if not chunk_ids:
            issues.append("no_citation")
        if any(phrase in answer for phrase in ("未找到相关信息", "无法确认", "不确定", "没有信息")):
            issues.append("cannot_confirm")

        quality = "good"
        if len(issues) >= 2:
            quality = "poor"
        elif issues:
            quality = "fair"

        return {
            "quality": quality,
            "issues": issues,
            "needs_review": quality in {"fair", "poor"},
            "confidence": confidence,
        }


def enhance_qa_answer(
    query: str,
    answer_text: str,
    retrieved_chunks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """对 LLM 文本答案做附加质量分析。"""
    enhancer = QAEnhancer()
    answer, confidence, chunk_ids = enhancer.parse_answer(answer_text)
    quality_info = enhancer.check_answer_quality(answer or "", confidence, chunk_ids)
    return {
        "query": query,
        "answer": answer,
        "confidence": confidence,
        "chunk_ids": chunk_ids,
        "quality": quality_info["quality"],
        "needs_review": quality_info["needs_review"],
        "issues": quality_info["issues"],
        "retrieved_chunks": retrieved_chunks[:3],
    }


def match_fixed_question(query: str) -> Optional[Dict[str, Any]]:
    """识别是否命中固定题型，并提取参数。"""
    enhancer = QAEnhancer()
    question_type = enhancer.classify_question(query)
    if not question_type:
        return None

    return {
        "question_type": question_type,
        "description": FIXED_QUESTION_TEMPLATES[question_type]["description"],
        "params": enhancer.extract_question_params(query, question_type),
        "matched": True,
    }


def answer_relation_question_from_structured_extraction(
    db: Session,
    file_id: int,
    query: str,
) -> Optional[Dict[str, Any]]:
    """优先用结构化抽取结果回答上一端/下一端问题。"""
    matched = match_fixed_question(query)
    if not matched or matched["question_type"] != "node_connection":
        return None

    relation_field = _detect_relation_field(query)
    node_id = _normalize_node_id(matched["params"].get("node_id"))
    if relation_field is None:
        return _build_unavailable_relation_result(
            node_id=node_id,
            relation_field=None,
            relation_status="missing_relation_direction",
            reason="query_missing_prev_or_next_hint",
        )
    if node_id is None:
        return _build_unavailable_relation_result(
            node_id=None,
            relation_field=relation_field,
            relation_status="missing_node_id",
            reason="query_missing_node_id",
        )

    records = (
        db.query(models.StructuredExtraction)
        .filter(models.StructuredExtraction.file_id == file_id)
        .order_by(models.StructuredExtraction.page_no, models.StructuredExtraction.id)
        .all()
    )
    if not records:
        return _build_unavailable_relation_result(
            node_id=node_id,
            relation_field=relation_field,
            relation_status="no_structured_extraction",
            reason="run_extract_first",
        )

    node_map = {
        normalized: record
        for record in records
        if (normalized := _normalize_node_id(record.node_id)) is not None
    }
    record = node_map.get(node_id)
    if record is None:
        return _build_unavailable_relation_result(
            node_id=node_id,
            relation_field=relation_field,
            relation_status="node_not_found",
            reason="node_not_found_in_extractions",
        )

    related_node_id = _normalize_node_id(getattr(record, relation_field))
    uncertain_fields = record.uncertain_fields or []
    if related_node_id is None:
        return _build_unavailable_relation_result(
            node_id=node_id,
            relation_field=relation_field,
            relation_status="missing_value",
            reason="relation_field_missing",
            review_required=_is_true(record.review_required) or relation_field in uncertain_fields,
        )

    topology_summary = build_topology_summary_from_records(records)
    relation_item = next(
        (
            item
            for item in topology_summary.relation_pairs
            if item.source_node_id == node_id
            and item.relation_field == relation_field
            and item.target_node_id == related_node_id
        ),
        None,
    )

    relation_status = relation_item.status if relation_item else "recorded"
    review_required = (
        _is_true(record.review_required)
        or relation_field in uncertain_fields
        or relation_status != "confirmed"
    )
    relation_label = "上一端" if relation_field == "prev_node" else "下一端"

    if relation_status == "confirmed":
        answer = f"根据当前结构化抽取结果，{node_id} 的{relation_label}是 {related_node_id}。"
    elif relation_status == "missing_target":
        answer = (
            f"根据当前结构化抽取结果，{node_id} 的{relation_label}标记为 {related_node_id}，"
            "但目标节点尚未在当前结果中闭合，建议人工复核。"
        )
    elif relation_status == "mismatch":
        answer = (
            f"根据当前结构化抽取结果，{node_id} 的{relation_label}标记为 {related_node_id}，"
            "但对应关系存在不一致，建议人工复核。"
        )
    else:
        answer = f"根据当前结构化抽取结果，{node_id} 的{relation_label}是 {related_node_id}。"

    if relation_item and relation_item.cross_page:
        answer += " 该关系涉及跨页连接，建议结合图纸上下文复核。"
        review_required = True

    answer_mode = "structured_relation" if relation_status == "confirmed" else "structured_relation_unavailable"
    return {
        "answer": answer,
        "question_analysis": {
            "matched": True,
            "question_type": "node_connection",
            "answer_mode": answer_mode,
            "matched_node_id": node_id,
            "relation_field": relation_field,
            "related_node_id": related_node_id,
            "relation_status": relation_status,
            "review_required": review_required,
            "reason": relation_item.reason if relation_item else None,
        },
    }


def _detect_relation_field(query: str) -> Optional[str]:
    lowered = query.lower()
    if any(keyword in lowered for keyword in ("上一端", "上一个", "prev_node")):
        return "prev_node"
    if any(keyword in lowered for keyword in ("下一端", "下一个", "next_node")):
        return "next_node"
    return None


def _build_unavailable_relation_result(
    node_id: Optional[str],
    relation_field: Optional[str],
    relation_status: str,
    reason: str,
    review_required: bool = True,
) -> Dict[str, Any]:
    relation_label = "连接关系"
    if relation_field == "prev_node":
        relation_label = "上一端"
    elif relation_field == "next_node":
        relation_label = "下一端"

    if node_id:
        answer = f"当前结构化结果中无法确认 {node_id} 的{relation_label}，建议人工复核。"
    else:
        answer = "当前无法从问题中识别目标节点或连接方向，建议改用明确的上一端/下一端问法。"

    return {
        "answer": answer,
        "question_analysis": {
            "matched": True,
            "question_type": "node_connection",
            "answer_mode": "structured_relation_unavailable",
            "matched_node_id": node_id,
            "relation_field": relation_field,
            "related_node_id": None,
            "relation_status": relation_status,
            "review_required": review_required,
            "reason": reason,
        },
    }


def _normalize_node_id(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip().upper()
    return normalized or None


def _is_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
