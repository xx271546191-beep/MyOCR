"""输入预检服务模块。

把阶段 D 的样本分级口径转成最小可执行实现。
当前版本采用轻量规则，不引入额外数据库字段或复杂模型。
"""

from __future__ import annotations

import io
from pathlib import Path

from pypdf import PdfReader

from app.schemas.file import FilePrecheckResponse


STANDARD_SAMPLE_NAMES = {
    "南方基地-钟落潭路由图.pdf",
    "西德胜-钟落潭96芯光缆路由图.pdf",
}

COMPLEX_SAMPLE_NAMES = {
    "惠州综合楼至三江收费站机房144芯光缆新建工程(20191217).pdf",
}


def _build_response(
    quality_grade: str,
    recommended_path: str,
    review_emphasis: bool,
    is_standard_demo_ready: bool,
    reasons: list[str],
) -> FilePrecheckResponse:
    """构造统一预检响应。"""
    return FilePrecheckResponse(
        quality_grade=quality_grade,
        recommended_path=recommended_path,
        result_nature="draft",
        review_emphasis=review_emphasis,
        is_standard_demo_ready=is_standard_demo_ready,
        reasons=reasons,
    )


def build_precheck_summary(
    file_name: str,
    file_type: str,
    extractable_text: str,
) -> FilePrecheckResponse:
    """基于文件名、文件类型和可抽取文本做最小预检。"""
    normalized_name = Path(file_name).name
    text = (extractable_text or "").strip()
    text_length = len(text)

    if normalized_name in STANDARD_SAMPLE_NAMES:
        return _build_response(
            quality_grade="Q1",
            recommended_path="full_pipeline",
            review_emphasis=False,
            is_standard_demo_ready=True,
            reasons=["matched_standard_sample_catalog"],
        )

    if normalized_name in COMPLEX_SAMPLE_NAMES:
        return _build_response(
            quality_grade="Q2",
            recommended_path="full_pipeline_with_review",
            review_emphasis=True,
            is_standard_demo_ready=False,
            reasons=["matched_complex_sample_catalog"],
        )

    if text_length < 80:
        return _build_response(
            quality_grade="Q3",
            recommended_path="search_only",
            review_emphasis=True,
            is_standard_demo_ready=False,
            reasons=["extractable_text_too_short"],
        )

    if file_type == "text" or text_length >= 200:
        return _build_response(
            quality_grade="Q1",
            recommended_path="full_pipeline",
            review_emphasis=False,
            is_standard_demo_ready=True,
            reasons=["extractable_text_sufficient"],
        )

    return _build_response(
        quality_grade="Q2",
        recommended_path="full_pipeline_with_review",
        review_emphasis=True,
        is_standard_demo_ready=False,
        reasons=["extractable_text_limited"],
    )


def _extract_text_from_pdf_bytes(file_content: bytes) -> str:
    """从 PDF 字节中提取文本，用于预检。"""
    reader = PdfReader(io.BytesIO(file_content))
    text_parts: list[str] = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            text_parts.append(text)
    return "\n".join(text_parts)


def build_precheck_from_stored_file(
    file_name: str,
    file_type: str,
    storage_path: str | None,
) -> FilePrecheckResponse:
    """从已落盘文件重新计算预检结果。"""
    if not storage_path:
        return _build_response(
            quality_grade="Q3",
            recommended_path="search_only",
            review_emphasis=True,
            is_standard_demo_ready=False,
            reasons=["storage_path_missing"],
        )

    path = Path(storage_path)
    if not path.exists():
        return _build_response(
            quality_grade="Q3",
            recommended_path="search_only",
            review_emphasis=True,
            is_standard_demo_ready=False,
            reasons=["stored_file_missing"],
        )

    if file_type == "text":
        extractable_text = path.read_text(encoding="utf-8", errors="ignore")
    elif file_type == "pdf":
        extractable_text = _extract_text_from_pdf_bytes(path.read_bytes())
    else:
        extractable_text = ""

    return build_precheck_summary(
        file_name=file_name,
        file_type=file_type,
        extractable_text=extractable_text,
    )
