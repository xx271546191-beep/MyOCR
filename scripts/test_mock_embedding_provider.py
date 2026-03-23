"""本地 mock embedding provider 测试。

验证 mock provider 不依赖外部网络，且返回稳定维度的向量。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["EMBEDDING_PROVIDER"] = "mock"

backend_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend_root))

from app.services.embedding_service import embed_text, get_embedding_dimension


def main() -> int:
    text = "RouteRAG mock embedding provider"
    vector_a = embed_text(text)
    vector_b = embed_text(text)

    assert vector_a == vector_b
    assert len(vector_a) == get_embedding_dimension()
    assert all(isinstance(x, float) for x in vector_a)

    print("mock embedding provider tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
