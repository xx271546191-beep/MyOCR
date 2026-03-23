"""Parser Service 测试脚本

测试 PDF 解析服务的功能
验证解析结果的正确性
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

from app.services.parser_service import ParserService, ParseResult


def test_parse_pdf():
    """测试 PDF 解析功能
    
    创建一个简单的 PDF 文件并解析
    验证解析结果的结构和内容
    """
    print("=" * 60)
    print("测试 PDF 解析功能")
    print("=" * 60)
    
    # 创建测试 PDF 文件 (使用 pypdf 创建)
    try:
        from pypdf import PdfWriter
        
        # 创建临时测试 PDF
        test_pdf_path = backend_root / "storage" / "test_temp.pdf"
        test_pdf_path.parent.mkdir(parents=True, exist_ok=True)
        
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)  # Letter 尺寸
        
        # 保存 PDF
        with open(test_pdf_path, "wb") as f:
            writer.write(f)
        
        print(f"✓ 创建测试 PDF: {test_pdf_path}")
        
        # 测试解析
        parser = ParserService(parser_type="pypdf")
        result = parser.parse_pdf(str(test_pdf_path))
        
        # 验证结果
        print(f"\n解析结果:")
        print(f"  - 文件名：{result.file_name}")
        print(f"  - 总页数：{result.total_pages}")
        print(f"  - 页面数：{len(result.pages)}")
        
        # 验证结构
        assert result.file_name == "test_temp.pdf", "文件名错误"
        assert result.total_pages == 1, "总页数错误"
        assert len(result.pages) == 1, "页面数错误"
        
        # 验证第一页
        page = result.pages[0]
        assert page.page_no == 1, "页码错误"
        assert isinstance(page.page_text, str), "页面文本类型错误"
        assert len(page.blocks) == 1, "块数错误"
        
        # 验证块
        block = page.blocks[0]
        assert block.block_type == "text", "块类型错误"
        assert isinstance(block.text_content, str), "块文本类型错误"
        
        print(f"\n✓ 所有验证通过!")
        
        # 清理测试文件
        test_pdf_path.unlink()
        print(f"✓ 清理测试文件")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()
        return False


def test_parser_type():
    """测试解析器类型选择
    
    验证不同解析器类型的处理
    """
    print("\n" + "=" * 60)
    print("测试解析器类型选择")
    print("=" * 60)
    
    # 测试 pypdf (默认)
    try:
        parser = ParserService(parser_type="pypdf")
        assert parser.parser_type == "pypdf", "解析器类型设置错误"
        print("✓ pypdf 解析器创建成功")
    except Exception as e:
        print(f"❌ pypdf 解析器创建失败：{e}")
        return False
    
    # 测试 olmocr (未实现)
    try:
        parser = ParserService(parser_type="olmocr")
        print("✓ olmocr 解析器创建成功")
    except Exception as e:
        print(f"❌ olmocr 解析器创建失败：{e}")
        return False
    
    # 测试未知类型
    # ParserService 在 __init__ 阶段不做 parser_type 校验，校验发生在 parse_pdf 中
    test_pdf_path = backend_root / "storage" / "test_temp_unknown_parser.pdf"
    try:
        from pypdf import PdfWriter

        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        test_pdf_path.parent.mkdir(parents=True, exist_ok=True)
        with open(test_pdf_path, "wb") as f:
            writer.write(f)

        parser = ParserService(parser_type="unknown")
        try:
            parser.parse_pdf(str(test_pdf_path))
            print("❌ 未知解析器类型应该在 parse_pdf 阶段报错")
            return False
        except ValueError as e:
            print(f"✓ 未知解析器类型正确在 parse_pdf 阶段抛出异常：{e}")
    finally:
        if test_pdf_path.exists():
            test_pdf_path.unlink()
    
    return True


def test_is_supported():
    """测试文件支持检查
    
    验证 is_supported 方法的正确性
    """
    print("\n" + "=" * 60)
    print("测试文件支持检查")
    print("=" * 60)
    
    # 测试支持的文件
    supported_files = [
        "test.pdf",
        "test.PDF",
        "test.png",
        "test.jpg",
        "test.jpeg",
        "test.bmp",
        "test.tiff",
        "test.gif"
    ]
    
    for filename in supported_files:
        result = ParserService.is_supported(filename)
        if result:
            print(f"✓ {filename} 支持解析")
        else:
            print(f"❌ {filename} 应该支持解析")
            return False
    
    # 测试不支持的文件
    unsupported_files = [
        "test.txt",
        "test.md",
        "test.json",
        "test.csv",
        "test.docx"
    ]
    
    for filename in unsupported_files:
        result = ParserService.is_supported(filename)
        if not result:
            print(f"✓ {filename} 不支持解析 (正确)")
        else:
            print(f"❌ {filename} 不应该支持解析")
            return False
    
    return True


def test_error_handling():
    """测试错误处理
    
    验证文件不存在、格式错误等情况的处理
    """
    print("\n" + "=" * 60)
    print("测试错误处理")
    print("=" * 60)
    
    parser = ParserService()
    
    # 测试文件不存在
    try:
        parser.parse_pdf("/nonexistent/file.pdf")
        print("❌ 文件不存在应该抛出异常")
        return False
    except FileNotFoundError as e:
        print(f"✓ 文件不存在正确抛出异常：{e}")
    
    # 测试错误的文件类型
    # 需要先准备一个真实存在的非 PDF 文件，才能触发 parse_pdf 的“扩展名错误”ValueError
    bad_file_path = backend_root / "storage" / "test_temp_not_pdf.txt"
    try:
        bad_file_path.parent.mkdir(parents=True, exist_ok=True)
        bad_file_path.write_text("not a pdf", encoding="utf-8")

        parser.parse_pdf(str(bad_file_path))
        print("❌ 非 PDF 文件应该抛出异常")
        return False
    except ValueError as e:
        print(f"✓ 非 PDF 文件正确抛出异常：{e}")
    finally:
        if bad_file_path.exists():
            bad_file_path.unlink()
    
    return True


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("Parser Service 测试套件")
    print("=" * 60)
    
    tests = [
        ("PDF 解析功能", test_parse_pdf),
        ("解析器类型选择", test_parser_type),
        ("文件支持检查", test_is_supported),
        ("错误处理", test_error_handling)
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
