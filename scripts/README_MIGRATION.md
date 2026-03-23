# 数据模型迁移与测试指南

## 任务 1.1: 完善数据模型层 - 完成情况

✅ **已完成内容**:

### 1. 更新 `app/db/models.py`

#### 新增模型:

**Page 模型** (页面级对象):
- `id`: 主键
- `file_id`: 外键关联 File
- `page_no`: 页码
- `page_image_path`: 页面图片路径
- `page_text`: 页面文本
- `page_summary`: 页面摘要
- `page_metadata`: 页面元数据 (JSON)
- `created_at`: 创建时间

**StructuredExtraction 模型** (结构化抽取结果):
- `id`: 主键
- `file_id`: 外键关联 File
- `page_no`: 页码
- `node_id`: 节点编号
- `node_type`: 节点类型 (井点、接头盒等)
- `prev_node`: 上一节点
- `next_node`: 下一节点
- `distance`: 距离
- `distance_unit`: 距离单位
- `splice_box_id`: 接头盒编号
- `slack_length`: 盘留长度
- `cable_type`: 光缆型号
- `fiber_count`: 芯数
- `remarks`: 备注
- `confidence`: 置信度
- `review_required`: 是否需要复核
- `uncertain_fields`: 不确定字段 (JSON)
- `schema_version`: schema 版本 (默认 cable_route_v1)

#### 更新现有模型:

**File 模型** 新增:
- `source_type`: 来源类型
- `pages` 关系 (cascade delete)
- `extractions` 关系 (cascade delete)

**Chunk 模型** 更新:
- `chunk_type` → `block_type` (字段重命名)
- 新增 `page_id` 外键关联 Page
- 新增 `page` 关系

### 2. 新增脚本

**scripts/migrate_db.py** - 数据库迁移脚本
- 自动检测现有表
- 创建新表
- 启用 pgvector 扩展 (如果使用 PostgreSQL)

**scripts/test_new_models.py** - 模型测试脚本
- 测试所有新模型
- 验证关系映射
- 验证新字段

### 3. 运行说明

#### 方式 1: 使用 scripts 目录中的脚本
```bash
# 进入 backend 目录
cd coding-workspace/backend

# 运行迁移
python scripts/migrate_db.py

# 运行测试
python scripts/test_new_models.py
```

#### 方式 2: 使用 backend 目录中的脚本
```bash
# 进入 backend 目录
cd coding-workspace/backend

# 运行迁移
python run_migrate.py

# 运行测试
python run_test_models.py
```

### 4. 验收标准

- [x] 数据库迁移脚本可执行
- [x] 新模型可正常 CRUD
- [x] 与现有模型关系正确
- [x] Page 模型包含所有必需字段
- [x] StructuredExtraction 模型符合 cable_route_v1 schema
- [x] review_required 机制字段完整
- [x] 所有关系映射正确

### 5. 数据库表结构

新增表:
- `pages`: 页面级对象表
- `structured_extractions`: 结构化抽取结果表

更新表:
- `files`: 新增 source_type 列
- `chunks`: 新增 page_id、block_type 列

### 6. 下一步

任务 1.1 已完成，可以继续执行:
- **任务 1.2**: 实现 parser_service

---

**文档创建时间**: 2026-03-19  
**任务状态**: ✅ 已完成
