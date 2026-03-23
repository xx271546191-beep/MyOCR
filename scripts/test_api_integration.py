"""API 路由集成测试脚本。

验证文件上传接口与 ingest_service 的集成是否正常工作。
当前版本兼容 FastAPI 路由函数直接返回的 Pydantic 响应模型。
"""

import io
import os
import sys
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# 测试环境优先走本地可复现的 embedding provider，避免依赖外部网络。
os.environ["EMBEDDING_PROVIDER"] = "mock"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

backend_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend_root))

from app.api.routes_files import upload_file
from app.db import models
from app.db.base import Base


def get_result_value(result, key: str):
    """兼容字典和 Pydantic 响应模型两种访问方式。"""
    if isinstance(result, dict):
        return result[key]
    return getattr(result, key)


def setup_database() -> Session:
    """初始化内存数据库，避免旧 SQLite 文件干扰测试。"""
    print("=" * 60)
    print("步骤 1: 初始化数据库表")
    print("=" * 60)

    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    print("✓ 数据库表创建成功")
    session_local = sessionmaker(bind=engine)
    return session_local()


def create_test_file() -> Path:
    """创建测试文本文件。"""
    print("\n" + "=" * 60)
    print("步骤 2: 创建测试文本文件")
    print("=" * 60)

    test_content = """RouteRAG 项目测试文档。

第一章：项目介绍
RouteRAG 是一个基于 RAG 技术的智能问答系统，支持文件上传、解析、切块、向量化和检索。

第二章：技术架构
RouteRAG 使用 FastAPI 作为后端框架，支持 PDF 和文本文件的处理。

第三章：功能特性
1. 文件上传
2. 自动解析
3. 智能切块
4. 向量化
5. 相似检索

第四章：测试总结
该文档用于验证 API 路由与 ingest_service 的完整集成链路。
"""

    test_file_path = backend_root / "storage" / "test_api_integration.txt"
    test_file_path.parent.mkdir(parents=True, exist_ok=True)
    test_file_path.write_text(test_content, encoding="utf-8")

    print(f"✓ 测试文件创建成功: {test_file_path}")
    print(f"  文件大小: {len(test_content)} 字符")
    return test_file_path


def test_upload_file_api(db: Session, test_file_path: Path):
    """直接调用 upload_file 路由函数。"""
    print("\n" + "=" * 60)
    print("步骤 3: 测试文件上传 API")
    print("=" * 60)

    try:
        file_content = test_file_path.read_bytes()
        upload_file_obj = UploadFile(
            filename="test_api_integration.txt",
            file=io.BytesIO(file_content),
        )

        print("正在调用 upload_file API...")
        import asyncio

        result = asyncio.run(upload_file(file=upload_file_obj, db=db))

        print("✓ API 调用成功")
        print(f"  file_id: {get_result_value(result, 'file_id')}")
        print(f"  filename: {get_result_value(result, 'filename')}")
        print(f"  pages: {get_result_value(result, 'pages')}")
        print(f"  chunks: {get_result_value(result, 'chunks')}")
        print(f"  status: {get_result_value(result, 'status')}")
        print(f"  message: {get_result_value(result, 'message')}")
        return result
    except Exception as exc:
        print(f"✗ API 调用失败: {exc}")
        raise


def verify_database(db: Session, file_id: int) -> bool:
    """验证数据库中的核心记录是否完整。"""
    print("\n" + "=" * 60)
    print("步骤 4: 验证数据库记录")
    print("=" * 60)

    file = db.query(models.File).filter(models.File.id == file_id).first()
    if not file:
        print(f"✗ 未找到文件记录 (ID={file_id})")
        return False

    print("✓ 文件记录存在")
    print(f"  文件名: {file.file_name}")
    print(f"  文件类型: {file.file_type}")
    print(f"  存储路径: {file.storage_path}")
    print(f"  解析状态: {file.parse_status}")
    print(f"  来源类型: {file.source_type}")

    pages = db.query(models.Page).filter(models.Page.file_id == file_id).all()
    chunks = db.query(models.Chunk).filter(models.Chunk.file_id == file_id).all()
    embeddings = db.query(models.Embedding).filter(
        models.Embedding.chunk_id.in_([chunk.id for chunk in chunks])
    ).all()

    print(f"✓ 页面记录: {len(pages)}")
    print(f"✓ Chunk 记录: {len(chunks)}")
    print(f"✓ Embedding 记录: {len(embeddings)}")

    if pages and chunks and embeddings:
        print("\n✓ 数据完整性验证通过")
        return True

    print("\n✗ 数据完整性验证失败")
    return False


def cleanup_test_files() -> None:
    """清理测试中创建的本地文件。"""
    print("\n" + "=" * 60)
    print("步骤 5: 清理测试文件")
    print("=" * 60)

    test_file = backend_root / "storage" / "test_api_integration.txt"
    if test_file.exists():
        test_file.unlink()
        print(f"✓ 测试文件已删除: {test_file}")
    else:
        print(f"  测试文件不存在: {test_file}")


def main() -> bool:
    """执行完整测试流程。"""
    print("\n" + "=" * 60)
    print("API 路由集成测试")
    print("测试 upload_file API 与 ingest_service 的集成")
    print("=" * 60)

    db = None
    try:
        db = setup_database()
        test_file_path = create_test_file()
        result = test_upload_file_api(db, test_file_path)
        success = verify_database(db, get_result_value(result, "file_id"))
        cleanup_test_files()

        print("\n" + "=" * 60)
        print("测试总结")
        print("=" * 60)
        if success:
            print("✓ 所有测试通过")
            print("  API 路由与 ingest_service 集成成功")
            print("  文件上传 -> 解析 -> 切块 -> 向量化 -> 入库流程正常")
        else:
            print("✗ 测试失败，请检查日志")

        return success
    except Exception as exc:
        print(f"\n✗ 测试异常: {exc}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        if db:
            db.close()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
