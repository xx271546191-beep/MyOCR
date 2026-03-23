"""任务状态相关 Schema。"""

from pydantic import BaseModel


class TaskStatusResponse(BaseModel):
    """把文件 ingest 状态规范化后的任务视图。"""

    task_type: str = "ingest"
    status: str
    detail: str | None = None
