"""QA Graph 共享状态定义。"""

from typing import Any, Dict, List, Optional, TypedDict

from sqlalchemy.orm import Session


class RagGraphState(TypedDict, total=False):
    """定义 QA Graph 各节点之间传递的状态字段。

    这里用 TypedDict 而不是普通 dict 说明约定，
    目的是让节点函数在共享状态上保持统一字段名和统一语义。
    """

    query: str
    file_id: Optional[str]
    top_k: int
    db: Session
    retrieved_chunks: List[Dict[str, Any]]
    context_text: str
    answer: str
    citations: List[Dict[str, Any]]
    error: Optional[str]
