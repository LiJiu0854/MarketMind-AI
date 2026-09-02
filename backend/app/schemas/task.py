"""后台任务 API 数据结构。"""

from typing import Literal

from pydantic import BaseModel, Field

TaskState = Literal["PENDING", "STARTED", "SUCCESS", "FAILURE"]


class TaskCreated(BaseModel):
    task_id: str = Field(min_length=1)


class TaskStatus(BaseModel):
    task_id: str = Field(min_length=1)
    state: TaskState
    result: dict[str, int | str] | None = None
    error: str | None = None
