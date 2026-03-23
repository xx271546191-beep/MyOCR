"""SQLAlchemy 基础模型类模块

定义所有 ORM 模型的基类
使用 declarative_base 创建 Base，用于所有数据模型的继承
"""

from sqlalchemy.ext.declarative import declarative_base

# 创建基础模型类
# 所有数据模型 (models.py 中的类) 都继承自这个 Base
# SQLAlchemy 使用它来创建数据库表
Base = declarative_base()
