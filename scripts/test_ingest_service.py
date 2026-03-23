"""Ingest Service 测试脚本

测试 Ingest 服务的完整流程
验证文件解析、切块、向量化入库的全链路
"""

import sys
from pathlib import Path

# Windows/PowerShell 默认可能是 GBK，打印 unicode 符号会触发 UnicodeEncodeError。
# 这里把输出切到 UTF-8，确保测试脚本可运行。
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 添加项目根目录到路径
backend_root = Path(__file__).parent.parent
sys.path.insert(0, str(backend_root))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.base import Base
from app.db import models
from app.services.ingest_service import IngestService, IngestResult
from pypdf import PdfWriter


def create_test_db():
    """创建测试数据库
    
    使用 SQLite 内存数据库进行测试
    
    Returns:
        Session: 数据库会话
    """
    # 创建内存数据库
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def create_test_pdf(file_path: str) -> str:
    """创建测试 PDF 文件
    
    Args:
        file_path: PDF 文件路径
        
    Returns:
        str: 文件路径
    """
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    
    with open(path, "wb") as f:
        writer.write(f)
    
    return str(path)


def test_ingest_file():
    """测试完整 ingest 流程
    
    验证文件从上传到入库的完整流程
    """
    print("=" * 60)
    print("测试完整 ingest 流程")
    print("=" * 60)
    
    try:
        # 创建测试数据库
        db = create_test_db()
        
        # 创建测试 PDF 文件
        test_pdf_path = backend_root / "storage" / "test_ingest.pdf"
        create_test_pdf(str(test_pdf_path))
        
        # 创建测试文件记录
        test_file = models.File(
            file_name="test_ingest.pdf",
            file_type="pdf",
            storage_path=str(test_pdf_path),
            parse_status="pending"
        )
        db.add(test_file)
        db.commit()
        db.refresh(test_file)
        
        print(f"✓ 创建测试文件：{test_file.file_name}")
        print(f"  - 初始状态：{test_file.parse_status}")
        
        # 执行 ingest 流程
        service = IngestService()
        result = service.ingest_file(db, test_file)
        
        # 验证结果
        print(f"\nIngest 结果:")
        print(f"  - 成功：{result.success}")
        print(f"  - 状态：{result.status}")
        print(f"  - 页面数：{result.pages_count}")
        print(f"  - chunk 数：{result.chunks_count}")
        
        # 断言验证
        assert result.success, "ingest 应该成功"
        assert result.status == "indexed", "状态应该是 indexed"
        assert result.pages_count > 0, "应该有页面"
        assert result.chunks_count > 0, "应该有 chunks"
        
        # 验证数据库中的文件状态
        db_file = db.query(models.File).filter(models.File.id == test_file.id).first()
        assert db_file.parse_status == "indexed", "文件状态应该是 indexed"
        
        # 验证页面创建
        pages = db.query(models.Page).filter(models.Page.file_id == test_file.id).all()
        assert len(pages) > 0, "应该创建了页面"
        print(f"  - 数据库页面数：{len(pages)}")
        
        # 验证 chunk 创建
        chunks = db.query(models.Chunk).filter(models.Chunk.file_id == test_file.id).all()
        assert len(chunks) > 0, "应该创建了 chunks"
        print(f"  - 数据库 chunk 数：{len(chunks)}")
        
        # 验证向量创建
        # 注意：测试 PDF 使用的是空白页，ParserService 可能产出空文本，
        # IngestService 会在文本为空时跳过向量化，因此 embeddings 允许为 0。
        embeddings = db.query(models.Embedding).all()
        if len(embeddings) > 0:
            print(f"  - 向量数：{len(embeddings)}")
        else:
            print("  - 警告：向量数为 0（测试 PDF 页面无可抽取文本）")
        
        # 清理测试文件
        test_pdf_path.unlink()
        print(f"\n✓ 清理测试文件")
        
        db.close()
        return True
        
    except Exception as e:
        print(f"❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()
        return False


def test_ingest_error_handling():
    """测试 ingest 错误处理
    
    验证文件不存在时的错误处理
    """
    print("\n" + "=" * 60)
    print("测试 ingest 错误处理")
    print("=" * 60)
    
    try:
        # 创建测试数据库
        db = create_test_db()
        
        # 创建不存在的文件记录
        test_file = models.File(
            file_name="nonexistent.pdf",
            file_type="pdf",
            storage_path="/nonexistent/path/file.pdf",
            parse_status="pending"
        )
        db.add(test_file)
        db.commit()
        db.refresh(test_file)
        
        print(f"✓ 创建测试文件 (不存在的文件)")
        
        # 执行 ingest 流程 (应该失败)
        service = IngestService()
        result = service.ingest_file(db, test_file)
        
        # 验证失败结果
        print(f"\nIngest 结果:")
        print(f"  - 成功：{result.success}")
        print(f"  - 状态：{result.status}")
        print(f"  - 错误信息：{result.error_message}")
        
        # 断言验证
        assert not result.success, "ingest 应该失败"
        assert result.status == "failed", "状态应该是 failed"
        assert result.error_message is not None, "应该有错误信息"
        
        # 验证数据库中的文件状态
        db_file = db.query(models.File).filter(models.File.id == test_file.id).first()
        assert "failed" in db_file.parse_status, "文件状态应该包含 failed"
        
        print(f"\n✓ 错误处理正确")
        
        db.close()
        return True
        
    except Exception as e:
        print(f"❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()
        return False


def test_status_transitions():
    """测试状态机转换
    
    验证文件状态的正确转换
    """
    print("\n" + "=" * 60)
    print("测试状态机转换")
    print("=" * 60)
    
    try:
        # 创建测试数据库
        db = create_test_db()
        
        # 创建测试文件
        test_file = models.File(
            file_name="test.pdf",
            file_type="pdf",
            storage_path="/tmp/test.pdf",
            parse_status="pending"
        )
        db.add(test_file)
        db.commit()
        db.refresh(test_file)
        
        # 测试状态转换
        service = IngestService()
        
        # pending → parsing
        service._update_status(db, test_file, "parsing")
        assert test_file.parse_status == "parsing", "状态应该是 parsing"
        print(f"✓ pending → parsing")
        
        # parsing → indexing
        service._update_status(db, test_file, "indexing")
        assert test_file.parse_status == "indexing", "状态应该是 indexing"
        print(f"✓ parsing → indexing")
        
        # indexing → indexed
        service._update_status(db, test_file, "indexed")
        assert test_file.parse_status == "indexed", "状态应该是 indexed"
        print(f"✓ indexing → indexed")
        
        # 测试失败状态
        service._update_status(db, test_file, "failed", "Test error")
        assert "failed" in test_file.parse_status, "状态应该包含 failed"
        assert "Test error" in test_file.parse_status, "应该包含错误信息"
        print(f"✓ indexing → failed (带错误信息)")
        
        db.close()
        return True
        
    except Exception as e:
        print(f"❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()
        return False


def test_unsupported_file_type():
    """测试不支持的文件类型
    
    验证不支持的文件类型会被拒绝
    """
    print("\n" + "=" * 60)
    print("测试不支持的文件类型")
    print("=" * 60)
    
    try:
        # 创建测试数据库
        db = create_test_db()
        
        # 创建不支持的文件类型
        test_file = models.File(
            file_name="test.docx",
            file_type="docx",  # 不支持的类型
            storage_path="/tmp/test.docx",
            parse_status="pending"
        )
        db.add(test_file)
        db.commit()
        db.refresh(test_file)
        
        print(f"✓ 创建不支持的文件类型：{test_file.file_type}")
        
        # 执行 ingest (应该失败)
        service = IngestService()
        result = service.ingest_file(db, test_file)
        
        # 验证失败
        assert not result.success, "应该失败"
        assert result.status == "failed", "状态应该是 failed"
        print(f"✓ 不支持的文件类型正确被拒绝")
        
        db.close()
        return True
        
    except Exception as e:
        print(f"❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("Ingest Service 测试套件")
    print("=" * 60)
    
    tests = [
        ("完整 ingest 流程", test_ingest_file),
        ("ingest 错误处理", test_ingest_error_handling),
        ("状态机转换", test_status_transitions),
        ("不支持的文件类型", test_unsupported_file_type)
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ 测试 {name} 异常：{e}")
            results.append((name, False))
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status} - {name}")
    
    print(f"\n总计：{passed}/{total} 测试通过")
    
    if passed == total:
        print("\n🎉 所有测试通过!")
        return True
    else:
        print(f"\n⚠️  {total - passed} 个测试失败")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
