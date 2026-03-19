import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.db.base import Base
from app.db.session import engine
from app.db import models


def init_db():
    print("Creating database tables...")

    if settings.DATABASE_URL.startswith("postgresql"):
        try:
            with engine.connect() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.commit()
                print("pgvector extension enabled.")
        except Exception as e:
            print(f"Note: Could not create vector extension: {e}")
            print("Make sure PostgreSQL has pgvector installed: CREATE EXTENSION vector")

    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully!")


if __name__ == "__main__":
    from app.core.config import settings
    print(f"Using database: {settings.DATABASE_URL}")
    init_db()
