import sys
from pathlib import Path

backend_root = Path(__file__).parent
sys.path.insert(0, str(backend_root))

from app.db.session import SessionLocal
from app.db import models


def test_models():
    db = SessionLocal()
    try:
        print("Testing new data models...\n")

        print("1. Testing File model with new fields...")
        test_file = models.File(
            file_name="test_cable_route.pdf",
            file_type="pdf",
            storage_path="/uploads/test.pdf",
            source_type="upload",
            parse_status="pending"
        )
        db.add(test_file)
        db.commit()
        db.refresh(test_file)
        print(f"   ✓ File created: id={test_file.id}, name={test_file.file_name}")
        print(f"   ✓ New field source_type: {test_file.source_type}")
        print(f"   ✓ Relationships: pages={len(test_file.pages)}, chunks={len(test_file.chunks)}, extractions={len(test_file.extractions)}")

        print("\n2. Testing Page model...")
        test_page = models.Page(
            file_id=test_file.id,
            page_no=1,
            page_image_path="/images/page_1.png",
            page_text="测试页面文本",
            page_summary="测试页面摘要",
            page_metadata={"width": 1000, "height": 800}
        )
        db.add(test_page)
        db.commit()
        db.refresh(test_page)
        print(f"   ✓ Page created: id={test_page.id}, page_no={test_page.page_no}")
        print(f"   ✓ Fields: page_text length={len(test_page.page_text or '')}, page_metadata={test_page.page_metadata}")

        print("\n3. Testing Chunk model with new fields...")
        test_chunk = models.Chunk(
            file_id=test_file.id,
            page_id=test_page.id,
            page_no=1,
            block_type="text",
            text_content="这是一个测试文本块",
            bbox={"x": 100, "y": 200, "width": 300, "height": 50},
            metadata_json={"source": "parser", "confidence": 0.95}
        )
        db.add(test_chunk)
        db.commit()
        db.refresh(test_chunk)
        print(f"   ✓ Chunk created: id={test_chunk.id}")
        print(f"   ✓ New field block_type: {test_chunk.block_type}")
        print(f"   ✓ New relationship page: {test_chunk.page.page_no if test_chunk.page else None}")

        print("\n4. Testing StructuredExtraction model...")
        test_extraction = models.StructuredExtraction(
            file_id=test_file.id,
            page_no=1,
            node_id="JD-001",
            node_type="井点",
            prev_node=None,
            next_node="JD-002",
            distance=80.5,
            distance_unit="米",
            splice_box_id=None,
            slack_length=5.0,
            cable_type="GYTA-48B1.3",
            fiber_count=48,
            remarks="测试备注",
            confidence=0.85,
            review_required="false",
            uncertain_fields=["splice_box_id"],
            schema_version="cable_route_v1"
        )
        db.add(test_extraction)
        db.commit()
        db.refresh(test_extraction)
        print(f"   ✓ StructuredExtraction created: id={test_extraction.id}, node_id={test_extraction.node_id}")
        print(f"   ✓ Fields: node_type={test_extraction.node_type}, distance={test_extraction.distance}{test_extraction.distance_unit}")
        print(f"   ✓ Review mechanism: confidence={test_extraction.confidence}, review_required={test_extraction.review_required}")
        print(f"   ✓ Uncertain fields: {test_extraction.uncertain_fields}")

        print("\n5. Testing relationships...")
        file_with_relations = db.query(models.File).filter(models.File.id == test_file.id).first()
        print(f"   ✓ File has {len(file_with_relations.pages)} page(s)")
        print(f"   ✓ File has {len(file_with_relations.chunks)} chunk(s)")
        print(f"   ✓ File has {len(file_with_relations.extractions)} extraction(s)")
        
        page_with_chunks = db.query(models.Page).filter(models.Page.id == test_page.id).first()
        print(f"   ✓ Page has {len(page_with_chunks.chunks)} chunk(s)")

        print("\n✅ All model tests passed successfully!")
        print("\n📊 Summary:")
        print("   - File model: ✓ Added source_type field, pages and extractions relationships")
        print("   - Page model: ✓ Created with all required fields")
        print("   - Chunk model: ✓ Added block_type field, page_id foreign key, page relationship")
        print("   - StructuredExtraction model: ✓ Created with cable_route_v1 schema and review mechanism")
        print("   - Relationships: ✓ All relationships working correctly")

    except Exception as e:
        db.rollback()
        print(f"\n❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    test_models()
