from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---- Enums ----

class MakeupStyle(str, Enum):
    natural = "natural"
    refined = "refined"
    sculpt = "sculpt"


class Gender(str, Enum):
    male = "male"
    female = "female"


class TaskStatusEnum(str, Enum):
    pending = "pending"
    processing = "processing"
    quality_check = "quality_check"
    completed = "completed"
    failed = "failed"


class PackageCategory(str, Enum):
    chinese = "chinese"
    western = "western"
    artistic = "artistic"
    travel = "travel"


# ---- Upload ----

class FileInfo(BaseModel):
    id: str = Field(..., description="文件唯一标识")
    filename: str = Field(..., description="原始文件名")
    url: str = Field(..., description="访问地址")


class UploadResponse(BaseModel):
    user_id: str
    files: list[FileInfo]


# ---- Makeup ----

class MakeupRequest(BaseModel):
    user_id: str = Field(..., description="用户ID")
    gender: Gender = Field(..., description="性别")
    style: MakeupStyle = Field(MakeupStyle.natural, description="妆造风格")


class MakeupResponse(BaseModel):
    user_id: str
    images: list[str] = Field(..., description="三种妆造效果图URL")


# ---- Generate ----

class GenerateRequest(BaseModel):
    user_id: str = Field(..., description="用户ID")
    package_id: str = Field(..., description="套餐ID")
    groom_style: Optional[str] = Field(None, description="新郎风格描述")
    bride_style: Optional[str] = Field(None, description="新娘风格描述")


class GenerateResponse(BaseModel):
    task_id: str
    status: TaskStatusEnum = TaskStatusEnum.pending


class TaskStatus(BaseModel):
    task_id: str
    status: TaskStatusEnum
    progress: int = Field(0, ge=0, le=100, description="进度百分比")
    message: str = ""
    result_urls: list[str] = Field(default_factory=list)


# ---- Package ----

class PackageInfo(BaseModel):
    id: str
    name: str
    tag: str = Field("", description="标签，如 '热门'、'新品'")
    category: PackageCategory
    preview_url: str = ""


# ---- Common ----

class ErrorResponse(BaseModel):
    detail: str
