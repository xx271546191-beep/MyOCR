import sys
from pathlib import Path

backend_root = Path(__file__).parent
sys.path.insert(0, str(backend_root))

from sqlalchemy import text, inspect
from app.db.base import Base
from app.db.session import engine
from app.core.config import settings


def migrate_db():
    print("Starting database migration...")
    print(f"Using database: {settings.DATABASE_URL}")

    if settings.DATABASE_URL.startswith("postgresql"):
        try:
            with engine.connect() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.commit()
                print("✓ pgvector extension enabled.")
        except Exception as e:
            print(f"⚠ Could not create vector extension: {e}")
            print("  Make sure PostgreSQL has pgvector installed: CREATE EXTENSION vector")

    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    print(f"\nExisting tables: {existing_tables}")

    print("\nCreating new tables...")
    Base.metadata.create_all(bind=engine)
    
    new_tables = set(inspector.get_table_names()) - set(existing_tables)
    if new_tables:
        print(f"✓ Created new tables: {new_tables}")
    else:
        print("✓ All tables already exist (or updated successfully)")

    print("\n✓ Database migration completed successfully!")


if __name__ == "__main__":
    migrate_db()
