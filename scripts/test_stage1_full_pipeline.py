"""阶段 1 完整链路验证脚本

验证从文件上传到入库的完整流程：
1. 创建测试 PDF 文件
2. 使用 parser_service 解析
3. 使用 chunk_service 创建页面和 chunk
4. 使用 embedding_service 生成向量
5. 使用 ingest_service 编排完整流程

验证点：
- 数据模型正确性
- 服务间集成
- 状态机转换
- 向量生成
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
backend_root = Path(__file__).parent.parent
sys.path.insert(0, str(backend_root))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.base import Base
from app.db import models
from pypdf import PdfWriter
from app.services.parser_service import ParserService, ParseResult
from app.services.chunk_service import ChunkService
from app.services.embedding_service import embedding_service
from app.services.ingest_service import IngestService, IngestResult


def create_test_db():
    """创建测试数据库
    
    使用 SQLite 内存数据库进行测试
    
    Returns:
        Session: 数据库会话
    """
    print("\n" + "=" * 60)
    print("步骤 1: 创建测试数据库")
    print("=" * 60)
    
    # 创建内存数据库
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    print("✓ 数据库创建成功 (SQLite 内存数据库)")
    print(f"  - 表：files, pages, chunks, embeddings, structured_extractions, query_logs")
    
    return db


def create_test_file(db):
    """创建测试 PDF 文件
    
    Returns:
        models.File: 文件对象
    """
    print("\n" + "=" * 60)
    print("步骤 2: 创建测试 PDF 文件")
    print("=" * 60)
    
    # 创建测试 PDF
    test_pdf_path = backend_root / "storage" / "test_pipeline.pdf"
    test_pdf_path.parent.mkdir(parents=True, exist_ok=True)
    
    writer = PdfWriter()
    # 创建 2 页
    writer.add_blank_page(width=612, height=792)
    writer.add_blank_page(width=612, height=792)
    
    with open(test_pdf_path, "wb") as f:
        writer.write(f)
    
    # 创建文件记录
    test_file = models.File(
        file_name="test_pipeline.pdf",
        file_type="pdf",
        storage_path=str(test_pdf_path),
        parse_status="pending",
        source_type="upload"
    )
    db.add(test_file)
    db.commit()
    db.refresh(test_file)
    
    print(f"✓ 测试文件创建成功")
    print(f"  - 文件名：{test_file.file_name}")
    print(f"  - 类型：{test_file.file_type}")
    print(f"  - 路径：{test_file.storage_path}")
    print(f"  - 初始状态：{test_file.parse_status}")
    
    return test_file


def test_parser_service(db, test_file):
    """测试 parser_service 解析
    
    Returns:
        ParseResult: 解析结果
    """
    print("\n" + "=" * 60)
    print("步骤 3: 测试 parser_service - 文件解析")
    print("=" * 60)
    
    parser = ParserService()
    parse_result = parser.parse_pdf(test_file.storage_path)
    
    # 验证解析结果
    print(f"✓ PDF 解析成功")
    print(f"  - 总页数：{parse_result.total_pages}")
    print(f"  - 文件名：{parse_result.file_name}")
    print(f"  - 页面数：{len(parse_result.pages)}")
    
    for page in parse_result.pages:
        print(f"    - 页面 {page.page_no}: 块数={len(page.blocks)}")
    
    # 断言验证
    assert parse_result.total_pages == 2, "应该有 2 页"
    assert len(parse_result.pages) == 2, "应该有 2 个页面对象"
    
    return parse_result


def test_chunk_service(db, test_file, parse_result):
    """测试 chunk_service - 创建页面和 chunk
    
    Returns:
        Tuple[List[Page], List[Chunk]]: 页面和 chunk 列表
    """
    print("\n" + "=" * 60)
    print("步骤 4: 测试 chunk_service - 创建页面和 chunk")
    print("=" * 60)
    
    chunk_service = ChunkService(db)
    pages, chunks = chunk_service.create_all_objects(test_file.id, parse_result)
    
    print(f"✓ 页面和 chunk 创建成功")
    print(f"  - 页面数：{len(pages)}")
    print(f"  - chunk 数：{len(chunks)}")
    
    # 验证页面
    for page in pages:
        print(f"    - 页面 {page.page_no}: ID={page.id}, file_id={page.file_id}")
        assert page.file_id == test_file.id, "页面 file_id 错误"
    
    # 验证 chunk
    for chunk in chunks:
        print(f"    - chunk {chunk.id}: 类型={chunk.block_type}, 页码={chunk.page_no}")
        assert chunk.file_id == test_file.id, "chunk file_id 错误"
        assert chunk.page_id is not None, "chunk 应该关联页面"
    
    # 断言验证
    assert len(pages) == 2, "应该有 2 个页面"
    assert len(chunks) == 2, "应该有 2 个 chunk"
    
    return pages, chunks


def test_embedding_service(db, chunks):
    """测试 embedding_service - 生成向量
    
    Returns:
        List[Embedding]: 向量列表
    """
    print("\n" + "=" * 60)
    print("步骤 5: 测试 embedding_service - 生成向量")
    print("=" * 60)
    
    # 提取文本
    texts = [chunk.text_content for chunk in chunks if chunk.text_content]
    print(f"  - 待向量化文本数：{len(texts)}")
    
    # 批量生成向量
    vectors = embedding_service.embed_texts(texts)
    print(f"  - 生成向量数：{len(vectors)}")
    print(f"  - 向量维度：{len(vectors[0]) if vectors else 0}")
    
    # 创建 Embedding 记录
    embeddings = []
    for chunk, vector in zip(chunks, vectors):
        embedding = models.Embedding(
            chunk_id=chunk.id,
            embedding_model=embedding_service.model_name,
            embedding=vector
        )
        db.add(embedding)
        embeddings.append(embedding)
    
    db.commit()
    
    print(f"✓ 向量创建成功")
    print(f"  - 向量模型：{embedding_service.model_name}")
    print(f"  - 保存的向量数：{len(embeddings)}")
    
    # 断言验证
    assert len(embeddings) == len(chunks), "每个 chunk 应该有向量"
    
    return embeddings


def test_ingest_service(db, test_file):
    """测试 ingest_service - 完整流程编排
    
    Returns:
        IngestResult: ingest 结果
    """
    print("\n" + "=" * 60)
    print("步骤 6: 测试 ingest_service - 完整流程编排")
    print("=" * 60)
    
    # 重新创建一个测试文件 (因为之前的已经处理过了)
    test_pdf_path = backend_root / "storage" / "test_ingest_full.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with open(test_pdf_path, "wb") as f:
        writer.write(f)
    
    ingest_file = models.File(
        file_name="test_ingest_full.pdf",
        file_type="pdf",
        storage_path=str(test_pdf_path),
        parse_status="pending"
    )
    db.add(ingest_file)
    db.commit()
    db.refresh(ingest_file)
    
    print(f"✓ 创建新的测试文件用于 ingest 测试")
    
    # 执行完整 ingest 流程
    service = IngestService()
    result = service.ingest_file(db, ingest_file)
    
    # 验证结果
    print(f"\nIngest 结果:")
    print(f"  - 成功：{result.success}")
    print(f"  - 状态：{result.status}")
    print(f"  - 页面数：{result.pages_count}")
    print(f"  - chunk 数：{result.chunks_count}")
    
    # 验证数据库状态
    db_file = db.query(models.File).filter(models.File.id == ingest_file.id).first()
    print(f"  - 数据库状态：{db_file.parse_status}")
    
    # 断言验证
    assert result.success, "ingest 应该成功"
    assert result.status == "indexed", "状态应该是 indexed"
    assert result.pages_count > 0, "应该有页面"
    assert result.chunks_count > 0, "应该有 chunks"
    assert db_file.parse_status == "indexed", "数据库状态应该是 indexed"
    
    print(f"✓ 完整 ingest 流程执行成功")
    
    return result


def verify_database(db, test_file):
    """验证数据库中的数据
    
    检查所有表的数据完整性
    """
    print("\n" + "=" * 60)
    print("步骤 7: 验证数据库完整性")
    print("=" * 60)
    
    # 查询 File
    files = db.query(models.File).all()
    print(f"✓ File 表：{len(files)} 条记录")
    
    # 查询 Page
    pages = db.query(models.Page).filter(models.Page.file_id == test_file.id).all()
    print(f"✓ Page 表：{len(pages)} 条记录 (file_id={test_file.id})")
    
    # 查询 Chunk
    chunks = db.query(models.Chunk).filter(models.Chunk.file_id == test_file.id).all()
    print(f"✓ Chunk 表：{len(chunks)} 条记录 (file_id={test_file.id})")
    
    # 查询 Embedding
    embeddings = db.query(models.Embedding).all()
    print(f"✓ Embedding 表：{len(embeddings)} 条记录")
    
    # 验证关系
    for page in pages:
        print(f"  - 页面 {page.page_no}: 关联 chunks={len(page.chunks)}")
    
    for chunk in chunks:
        print(f"  - chunk {chunk.id}: 类型={chunk.block_type}, 有向量={len(chunk.embeddings) > 0}")
    
    # 断言验证
    assert len(files) > 0, "File 表应该有数据"
    assert len(pages) > 0, "Page 表应该有数据"
    assert len(chunks) > 0, "Chunk 表应该有数据"
    assert len(embeddings) > 0, "Embedding 表应该有数据"
    
    print(f"\n✓ 数据库完整性验证通过")


def cleanup():
    """清理测试文件"""
    print("\n" + "=" * 60)
    print("步骤 8: 清理测试文件")
    print("=" * 60)
    
    test_files = [
        backend_root / "storage" / "test_pipeline.pdf",
        backend_root / "storage" / "test_ingest_full.pdf"
    ]
    
    for test_file in test_files:
        if test_file.exists():
            test_file.unlink()
            print(f"✓ 删除：{test_file.name}")
    
    print(f"✓ 测试文件清理完成")


def main():
    """运行完整链路验证"""
    print("\n" + "=" * 80)
    print(" " * 20 + "阶段 1 完整链路验证")
    print("=" * 80)
    print("\n验证目标:")
    print("  1. parser_service - PDF 解析")
    print("  2. chunk_service - 页面和 chunk 创建")
    print("  3. embedding_service - 向量生成")
    print("  4. ingest_service - 完整流程编排")
    print("  5. 数据模型 - 关系和完整性")
    print("=" * 80)
    
    try:
        # 步骤 1: 创建数据库
        db = create_test_db()
        
        # 步骤 2: 创建测试文件
        test_file = create_test_file(db)
        
        # 步骤 3: 测试解析服务
        parse_result = test_parser_service(db, test_file)
        
        # 步骤 4: 测试 chunk 服务
        pages, chunks = test_chunk_service(db, test_file, parse_result)
        
        # 步骤 5: 测试 embedding 服务
        embeddings = test_embedding_service(db, chunks)
        
        # 步骤 6: 测试 ingest 服务
        ingest_result = test_ingest_service(db, test_file)
        
        # 步骤 7: 验证数据库
        verify_database(db, test_file)
        
        # 步骤 8: 清理
        cleanup()
        
        # 最终汇总
        print("\n" + "=" * 80)
        print(" " * 25 + "验证结果汇总")
        print("=" * 80)
        print("\n✅ 所有验证通过!")
        print("\n阶段 1 链路验证成功:")
        print("  ✓ 数据模型层 (models.py)")
        print("  ✓ 解析服务 (parser_service.py)")
        print("  ✓ Chunk 服务 (chunk_service.py)")
        print("  ✓ 向量化服务 (embedding_service.py)")
        print("  ✓ Ingest 总控 (ingest_service.py)")
        print("\n完整链路:")
        print("  文件上传 → 解析 → 切块 → 向量化 → 入库 ✓")
        print("=" * 80)
        
        db.close()
        return True
        
    except Exception as e:
        print(f"\n❌ 验证失败：{e}")
        import traceback
        traceback.print_exc()
        cleanup()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
