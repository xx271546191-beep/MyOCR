from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

engine = create_engine(settings.DATABASE_URL, echo=settings.DEBUG)


def _load_pgvector_extension(dbapi_conn, connection_record):
    if settings.DATABASE_URL.startswith("postgresql"):
        try:
            cursor = dbapi_conn.cursor()
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cursor.close()
        except Exception:
            pass


if engine.dialect.name == "postgresql":
    event.listen(engine, "connect", _load_pgvector_extension)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
