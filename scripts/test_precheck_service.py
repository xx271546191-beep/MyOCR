"""输入预检服务测试脚本。

验证最小预检规则是否按预期输出 Q1 / Q2 / Q3 等级，
以及推荐处理路径和风险提示是否一致。
"""

from __future__ import annotations

import sys
from pathlib import Path

backend_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend_root))

from app.services.precheck_service import build_precheck_summary


def test_q1_standard_text() -> None:
    """长文本样本应被判定为 Q1，全链路可用。"""
    summary = build_precheck_summary(
        file_name="demo_stage_d.txt",
        file_type="text",
        extractable_text="A" * 300,
    )
    assert summary.quality_grade == "Q1"
    assert summary.recommended_path == "full_pipeline"
    assert summary.is_standard_demo_ready is True
    assert summary.review_emphasis is False


def test_q2_named_complex_sample() -> None:
    """已知复杂样本应优先进入 Q2。"""
    summary = build_precheck_summary(
        file_name="惠州综合楼至三江收费站机房144芯光缆新建工程(20191217).pdf",
        file_type="pdf",
        extractable_text="A" * 1200,
    )
    assert summary.quality_grade == "Q2"
    assert summary.recommended_path == "full_pipeline_with_review"
    assert summary.is_standard_demo_ready is False
    assert summary.review_emphasis is True


def test_q3_sparse_text() -> None:
    """可抽取文本过少时应降为 Q3。"""
    summary = build_precheck_summary(
        file_name="tiny.pdf",
        file_type="pdf",
        extractable_text="abc",
    )
    assert summary.quality_grade == "Q3"
    assert summary.recommended_path == "search_only"
    assert summary.review_emphasis is True


def main() -> int:
    test_q1_standard_text()
    test_q2_named_complex_sample()
    test_q3_sparse_text()
    print("precheck service tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
