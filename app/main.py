"""FastAPI 应用入口模块

RouteRAG Demo 的主入口
负责初始化 FastAPI 应用、注册路由、创建数据库表
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径
# 确保可以从任何位置导入 app 模块
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from fastapi import FastAPI
from app.core.config import settings
from app.api import routes_search, routes_files, routes_extract
from app.db.base import Base
from app.db.session import engine

# 创建 FastAPI 应用实例
# title: API 文档标题，来自配置
# debug: 调试模式，来自配置
app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG
)

# 注册路由
# routes_search: 检索问答 API，挂载到 /api/v1
# routes_files: 文件管理 API，挂载到 /api/v1
# routes_extract: 结构化抽取 API，挂载到 /api/v1
app.include_router(routes_search.router, prefix="/api/v1", tags=["search"])
app.include_router(routes_files.router, prefix="/api/v1", tags=["files"])
app.include_router(routes_extract.router, prefix="/api/v1", tags=["extract"])


@app.on_event("startup")
def _create_tables_on_startup():
    """应用启动时自动创建数据库表
    
    在 FastAPI 应用启动时执行
    使用 SQLAlchemy 的 metadata.create_all 创建所有表
    如果表已存在则跳过
    
    Note:
        - 开发环境友好：无需手动运行迁移脚本
        - 生产环境建议使用 Alembic 等迁移工具
    """
    # Demo-friendly default: ensure tables exist.
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health_check():
    """健康检查接口
    
    用于 Kubernetes 或其他监控系统的健康探测
    
    Returns:
        dict: {"status": "ok"}
    """
    return {"status": "ok"}


@app.get("/")
def root():
    """根路径接口
    
    返回 API 欢迎信息
    
    Returns:
        dict: 包含欢迎消息
    """
    return {"message": "Optic RAG Demo API"}


if __name__ == "__main__":
    # 直接运行此文件时启动 Uvicorn 服务器
    # 监听 0.0.0.0:8001，允许外部访问
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
