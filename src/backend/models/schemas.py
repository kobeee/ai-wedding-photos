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


class IssueCategory(str, Enum):
    """VLM 质检问题分类 — 决定修复路径。"""
    physical = "physical"    # 手指、穿模、五官、光影 → Nano 局部重绘
    emotional = "emotional"  # 表情、情绪、眼神 → GPT I2I 修复


# ---- Camera Schema (Director 输出) ----

class CameraSchema(BaseModel):
    """LLM 摄影导演输出的结构化拍摄方案。"""
    scene: str = Field(..., description="场景描述，如 '冰岛黑沙滩日落'")
    lighting: str = Field(..., description="光线方案，如 'golden hour 侧逆光'")
    composition: str = Field(..., description="构图方式，如 '中景，三分法构图'")
    lens: str = Field(..., description="镜头参数，如 '85mm f/1.4 浅景深'")
    mood: str = Field(..., description="情绪关键词，如 '浪漫、宁静'")
    wardrobe: str = Field(..., description="服装描述，如 '白色拖尾婚纱'")
    pose_direction: str = Field(..., description="姿势指导，如 '相视而笑，额头轻触'")


# ---- Quality Issue ----

class QualityIssue(BaseModel):
    """单个质检问题。"""
    description: str
    category: IssueCategory
    severity: float = Field(0.5, ge=0.0, le=1.0, description="严重程度 0-1")


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
    makeup_style: Optional[MakeupStyle] = Field(None, description="妆造风格（来自试妆步骤）")
    gender: Optional[Gender] = Field(None, description="性别")
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
    quality_score: float = Field(0.0, ge=0.0, le=1.0, description="综合质量评分")
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
