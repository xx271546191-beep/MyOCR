"""Chunk Service 测试脚本

测试 Chunk 服务的功能
验证页面和 chunk 对象的创建
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
from app.services.parser_service import ParserService, ParseResult, BlockResult, PageResult
from app.services.chunk_service import ChunkService


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


def test_create_page_objects():
    """测试页面对象创建
    
    验证页面对象能正确创建并保存到数据库
    """
    print("=" * 60)
    print("测试页面对象创建")
    print("=" * 60)
    
    try:
        # 创建测试数据库
        db = create_test_db()
        
        # 创建测试数据
        test_file = models.File(
            file_name="test.pdf",
            file_type="pdf",
            storage_path="/tmp/test.pdf"
        )
        db.add(test_file)
        db.commit()
        db.refresh(test_file)
        
        # 创建模拟解析结果
        parse_result = ParseResult(
            pages=[
                PageResult(
                    page_no=1,
                    page_text="第一页内容",
                    page_image_path="/images/page1.png",
                    blocks=[]
                ),
                PageResult(
                    page_no=2,
                    page_text="第二页内容",
                    page_image_path="/images/page2.png",
                    blocks=[]
                )
            ],
            total_pages=2,
            file_name="test.pdf"
        )
        
        # 测试创建页面对象
        service = ChunkService(db)
        pages = service.create_page_objects(test_file.id, parse_result)
        
        # 验证结果
        assert len(pages) == 2, f"应该创建 2 个页面，实际创建{len(pages)}个"
        assert pages[0].page_no == 1, "第一页页码错误"
        assert pages[0].page_text == "第一页内容", "第一页文本错误"
        assert pages[0].page_image_path == "/images/page1.png", "第一页图片路径错误"
        assert pages[1].page_no == 2, "第二页页码错误"
        assert pages[1].file_id == test_file.id, "文件 ID 错误"
        
        print(f"✓ 成功创建 {len(pages)} 个页面")
        print(f"  - 页面 1: {pages[0].page_text}")
        print(f"  - 页面 2: {pages[1].page_text}")
        
        db.close()
        return True
        
    except Exception as e:
        print(f"❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()
        return False


def test_create_chunk_objects():
    """测试 chunk 对象创建
    
    验证 chunk 对象能正确创建并保存到数据库
    """
    print("\n" + "=" * 60)
    print("测试 chunk 对象创建")
    print("=" * 60)
    
    try:
        # 创建测试数据库
        db = create_test_db()
        
        # 创建测试文件
        test_file = models.File(
            file_name="test.pdf",
            file_type="pdf",
            storage_path="/tmp/test.pdf"
        )
        db.add(test_file)
        db.commit()
        db.refresh(test_file)
        
        # 创建模拟解析结果 (带块)
        parse_result = ParseResult(
            pages=[
                PageResult(
                    page_no=1,
                    page_text="第一页内容",
                    page_image_path=None,
                    blocks=[
                        BlockResult(
                            block_type="text",
                            text_content="这是第一个文本块",
                            bbox={"x": 100, "y": 200, "width": 300, "height": 50},
                            image_path=None
                        ),
                        BlockResult(
                            block_type="table",
                            text_content="这是一个表格",
                            bbox={"x": 100, "y": 300, "width": 400, "height": 200},
                            image_path=None
                        )
                    ]
                ),
                PageResult(
                    page_no=2,
                    page_text="第二页内容",
                    page_image_path=None,
                    blocks=[
                        BlockResult(
                            block_type="text",
                            text_content="这是第二页的文本块",
                            bbox=None,
                            image_path=None
                        )
                    ]
                )
            ],
            total_pages=2,
            file_name="test.pdf"
        )
        
        # 先创建页面对象
        chunk_service = ChunkService(db)
        pages = chunk_service.create_page_objects(test_file.id, parse_result)
        
        # 测试创建 chunk 对象
        chunks = chunk_service.create_chunk_objects(
            test_file.id, 
            parse_result, 
            pages
        )
        
        # 验证结果
        assert len(chunks) == 3, f"应该创建 3 个 chunk，实际创建{len(chunks)}个"
        
        # 验证第一个 chunk
        chunk1 = chunks[0]
        assert chunk1.block_type == "text", "块类型错误"
        assert chunk1.text_content == "这是第一个文本块", "块文本错误"
        assert chunk1.bbox == {"x": 100, "y": 200, "width": 300, "height": 50}, "bbox 错误"
        assert chunk1.page_no == 1, "页码错误"
        assert chunk1.page_id == pages[0].id, "页面关联错误"
        
        # 验证第二个 chunk (表格)
        chunk2 = chunks[1]
        assert chunk2.block_type == "table", "表格块类型错误"
        assert chunk2.text_content == "这是一个表格", "表格文本错误"
        
        # 验证第三个 chunk (第二页)
        chunk3 = chunks[2]
        assert chunk3.page_no == 2, "第二页页码错误"
        assert chunk3.page_id == pages[1].id, "第二页页面关联错误"
        
        print(f"✓ 成功创建 {len(chunks)} 个 chunk")
        for i, chunk in enumerate(chunks, 1):
            print(f"  - Chunk {i}: 类型={chunk.block_type}, 页码={chunk.page_no}")
        
        db.close()
        return True
        
    except Exception as e:
        print(f"❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()
        return False


def test_create_all_objects():
    """测试一站式创建方法
    
    验证 create_all_objects 方法能同时创建页面和 chunk
    """
    print("\n" + "=" * 60)
    print("测试一站式创建方法")
    print("=" * 60)
    
    try:
        # 创建测试数据库
        db = create_test_db()
        
        # 创建测试文件
        test_file = models.File(
            file_name="test.pdf",
            file_type="pdf",
            storage_path="/tmp/test.pdf"
        )
        db.add(test_file)
        db.commit()
        db.refresh(test_file)
        
        # 创建模拟解析结果
        parse_result = ParseResult(
            pages=[
                PageResult(
                    page_no=1,
                    page_text="第一页",
                    blocks=[
                        BlockResult(block_type="text", text_content="块 1"),
                        BlockResult(block_type="text", text_content="块 2")
                    ]
                )
            ],
            total_pages=1,
            file_name="test.pdf"
        )
        
        # 测试一站式创建
        service = ChunkService(db)
        pages, chunks = service.create_all_objects(test_file.id, parse_result)
        
        # 验证结果
        assert len(pages) == 1, f"应该创建 1 个页面，实际创建{len(pages)}个"
        assert len(chunks) == 2, f"应该创建 2 个 chunk，实际创建{len(chunks)}个"
        
        # 验证页面和 chunk 的关联
        assert chunks[0].page_id == pages[0].id, "chunk 页面关联错误"
        assert chunks[1].page_id == pages[0].id, "chunk 页面关联错误"
        
        print(f"✓ 成功创建 {len(pages)} 个页面和 {len(chunks)} 个 chunk")
        print(f"  - 页面：{pages[0].page_text}")
        for i, chunk in enumerate(chunks, 1):
            print(f"  - Chunk {i}: {chunk.text_content}")
        
        db.close()
        return True
        
    except Exception as e:
        print(f"❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()
        return False


def test_metadata_preservation():
    """测试元数据保留
    
    验证 bbox、block_type 等元数据正确保留
    """
    print("\n" + "=" * 60)
    print("测试元数据保留")
    print("=" * 60)
    
    try:
        # 创建测试数据库
        db = create_test_db()
        
        # 创建测试文件
        test_file = models.File(
            file_name="test.pdf",
            file_type="pdf",
            storage_path="/tmp/test.pdf"
        )
        db.add(test_file)
        db.commit()
        db.refresh(test_file)
        
        # 创建带完整元数据的解析结果
        parse_result = ParseResult(
            pages=[
                PageResult(
                    page_no=1,
                    page_text="测试页面",
                    blocks=[
                        BlockResult(
                            block_type="figure",
                            text_content="这是一个图片",
                            bbox={"x": 50, "y": 100, "width": 500, "height": 300},
                            image_path="/images/fig1.png"
                        )
                    ]
                )
            ],
            total_pages=1,
            file_name="test.pdf"
        )
        
        # 创建对象
        service = ChunkService(db)
        pages, chunks = service.create_all_objects(test_file.id, parse_result)
        
        # 验证元数据
        chunk = chunks[0]
        assert chunk.block_type == "figure", "块类型错误"
        assert chunk.bbox == {"x": 50, "y": 100, "width": 500, "height": 300}, "bbox 错误"
        assert chunk.image_path == "/images/fig1.png", "图片路径错误"
        assert "parser" in chunk.metadata_json, "metadata 缺少 parser 字段"
        
        print(f"✓ 元数据正确保留")
        print(f"  - block_type: {chunk.block_type}")
        print(f"  - bbox: {chunk.bbox}")
        print(f"  - image_path: {chunk.image_path}")
        print(f"  - metadata: {chunk.metadata_json}")
        
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
    print("Chunk Service 测试套件")
    print("=" * 60)
    
    tests = [
        ("页面对象创建", test_create_page_objects),
        ("chunk 对象创建", test_create_chunk_objects),
        ("一站式创建", test_create_all_objects),
        ("元数据保留", test_metadata_preservation)
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
