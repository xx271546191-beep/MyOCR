"""数据库会话管理模块

负责创建和管理数据库连接池与会话
支持 PostgreSQL 和 SQLite 两种数据库
自动加载 pgvector 扩展（PostgreSQL）
"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# 创建数据库引擎
# echo=settings.DEBUG: 根据配置决定是否打印 SQL 日志
engine = create_engine(settings.DATABASE_URL, echo=settings.DEBUG)


def _load_pgvector_extension(dbapi_conn, connection_record):
    """加载 pgvector 扩展
    
    在 PostgreSQL 连接建立时自动创建 vector 扩展
    使用 event listen 机制，仅在首次连接时执行
    
    Args:
        dbapi_conn: 数据库 API 连接对象
        connection_record: SQLAlchemy 连接记录
        
    Note:
        - 仅在 PostgreSQL 环境下执行
        - 使用 CREATE EXTENSION IF NOT EXISTS 避免重复创建
        - 异常时静默失败，兼容无 pgvector 的环境
    """
    if settings.DATABASE_URL.startswith("postgresql"):
        try:
            cursor = dbapi_conn.cursor()
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cursor.close()
        except Exception:
            # 静默失败：兼容未安装 pgvector 的 PostgreSQL
            pass


# 如果是 PostgreSQL，注册连接事件监听器
# 在每次建立新连接时自动加载 pgvector 扩展
if engine.dialect.name == "postgresql":
    event.listen(engine, "connect", _load_pgvector_extension)

# 创建会话工厂
# autocommit=False: 不自动提交事务，需要手动 commit
# autoflush=False: 不自动刷新，需要手动 flush
# bind=engine: 绑定到上面创建的引擎
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """获取数据库会话的依赖注入函数
    
    FastAPI 依赖注入使用，为每个请求创建独立的数据库会话
    使用生成器模式，确保会话在请求结束后正确关闭
    
    Yields:
        Session: SQLAlchemy 数据库会话对象
        
    Usage:
        @router.get("/xxx")
        def xxx(db: Session = Depends(get_db)):
            # 使用 db 进行数据库操作
            pass
            
    Note:
        - 使用 try-finally 确保会话关闭
        - 每个请求独立的会话，避免并发问题
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
