# RouteRAG 后端服务

RouteRAG 后端是一个基于 FastAPI 的光缆路由图 RAG 演示服务，覆盖文件上传、解析、切块、向量化、检索问答、结构化抽取、关系恢复摘要，以及面向复核的聚合展示能力。

## 项目当前范围

本仓库是项目的后端代码仓库。当前已经落地的核心能力包括：

- 文件上传与手动重新入库
- 文本 / PDF 解析
- 文本切块与向量存储
- 带引用来源的检索问答
- 基于 `cable_route_v1` 的结构化抽取
- 文件级 `precheck` 预检结果与 `risk_notice` 风险提示
- 用于关系恢复的 `topology_summary`
- 面向 `prev_node` / `next_node` 等问题的关系优先问答
- 面向多页关系复核的 `cross_page_hint`
- 面向复杂样本复核的 `review_summary`
- 文件级 `overview` 聚合接口与查询历史接口

当前后端处于演示验证阶段，重点是让结果可解释、可复核，而不是对所有复杂工程图都假设为完全自动化处理。

## 技术栈

- Python
- FastAPI
- SQLAlchemy
- PostgreSQL + pgvector
- SQLite 本地回退
- OpenAI 兼容 / Hugging Face / Google 模型提供方
- LangGraph

## 仓库结构

```text
backend/
|-- app/
|   |-- api/           # FastAPI 路由
|   |-- core/          # 配置与设置
|   |-- db/            # 数据模型与会话
|   |-- prompts/       # 抽取提示词
|   |-- rag/           # 问答图编排
|   |-- schemas/       # 请求与响应模型
|   `-- services/      # 解析、入库、检索、抽取、复核等服务
|-- scripts/           # 验收与辅助脚本
|-- storage/           # 上传文件与本地运行产物
|-- .env.example
|-- requirements.txt
`-- README.md
```

## 快速开始

### 1. 创建并激活虚拟环境

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. 安装依赖

```powershell
pip install -r requirements.txt
```

### 3. 配置环境变量

将 `.env.example` 复制为 `.env`，再按本地环境修改参数。

本地开发可选两种最小配置：

- PostgreSQL + pgvector：
  - 使用 `DATABASE_URL=postgresql://...`
- SQLite 回退：
  - 使用 `DATABASE_URL=sqlite:///./optic_rag.db`

为了在本地测试和验收时获得稳定结果，向量层支持：

```env
EMBEDDING_PROVIDER=mock
```

### 4. 启动服务

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

启动后可访问：

- `GET /`
- `GET /health`
- `GET /docs`

## 主要接口

### 文件相关

- `POST /api/v1/files/upload`
- `POST /api/v1/upload`
- `POST /api/v1/files/{file_id}/ingest`
- `GET /api/v1/files`
- `GET /api/v1/files/{file_id}`
- `GET /api/v1/files/{file_id}/queries`
- `GET /api/v1/files/{file_id}/overview`

### 检索问答

- `POST /api/v1/search`

当前重点返回内容包括：

- `citations`
- `risk_notice`
- `question_analysis`
- 对 `上一端 / 下一端 / prev_node / next_node` 类问题的关系优先回答

### 结构化抽取

- `POST /api/v1/extract`
- `GET /api/v1/extract/schema`
- `POST /api/v1/extract/{file_id}`
- `GET /api/v1/extract/{file_id}`

当前重点返回内容包括：

- 结构化节点结果
- `topology_summary`
- `cross_page_hint`
- `review_summary`

## 验证命令

推荐按下面顺序做基础验证：

```powershell
.\.venv\Scripts\python.exe -c "import app.main; print('app.main import ok')"
.\.venv\Scripts\python.exe scripts\test_precheck_service.py
.\.venv\Scripts\python.exe scripts\test_mock_embedding_provider.py
.\.venv\Scripts\python.exe scripts\test_topology_service.py
.\.venv\Scripts\python.exe scripts\test_cross_page_hinting.py
.\.venv\Scripts\python.exe scripts\test_relation_qa_enhancement.py
.\.venv\Scripts\python.exe scripts\test_review_summary_service.py
.\.venv\Scripts\python.exe scripts\test_review_view_enhancement.py
.\.venv\Scripts\python.exe scripts\test_api_integration.py
.\.venv\Scripts\python.exe scripts\test_stage3_acceptance.py
```

## 环境变量说明

`.env.example` 中当前重点关注的变量包括：

- `DATABASE_URL`
- `LLM_PROVIDER`
- `LLM_API_BASE`
- `LLM_API_KEY`
- `LLM_MODEL_NAME`
- `EMBEDDING_PROVIDER`
- `EMBEDDING_API_BASE`
- `EMBEDDING_API_KEY`
- `EMBEDDING_MODEL_NAME`
- `GOOGLE_GENAI_API_KEY`

当前已接入或预留的提供方包括：

- `hf`
- `openai`
- `google`
- `mock`，用于本地向量能力验收

## 使用说明

- `storage/` 用于保存本地上传文件和运行过程中的临时产物。
- 本地开发和测试可以使用 SQLite，但生产向量检索目标仍然是 PostgreSQL + pgvector。
- 当前后端刻意强化风险提示与复核提示，而不是把不确定结果包装成最终结论。
