from __future__ import annotations

from enum import Enum
from typing import Any, Optional

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


class PaymentStatus(str, Enum):
    unpaid = "unpaid"
    pending = "pending"
    paid = "paid"
    free_granted = "free_granted"
    failed = "failed"
    refunded = "refunded"
    expired = "expired"


class FulfillmentStatus(str, Enum):
    not_started = "not_started"
    queued = "queued"
    processing = "processing"
    delivered = "delivered"
    partially_delivered = "partially_delivered"
    failed = "failed"


class ServiceStatus(str, Enum):
    normal = "normal"
    aftersale = "aftersale"
    closed = "closed"


class BatchStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class BatchType(str, Enum):
    preview = "preview"
    initial = "initial"
    rerun = "rerun"
    manual_retouch = "manual_retouch"


class InitiatedBy(str, Enum):
    system = "system"
    user = "user"
    support = "support"


class PaymentProvider(str, Enum):
    mock = "mock"
    alipay = "alipay"


class DeliveryTier(str, Enum):
    preview = "preview"
    four_k = "4k"


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
    role: str = Field("", description="角色标签")
    slot: str = Field("", description="固定坑位标识")


class UploadValidationIssue(BaseModel):
    level: str = Field(..., description="error 或 warning")
    message: str = Field(..., description="面向用户的提示文案")
    slot: str = Field("", description="关联的坑位标识")


class UploadValidationSummary(BaseModel):
    ok: bool = True
    issues: list[UploadValidationIssue] = Field(default_factory=list)
    summary: str = ""


class UploadResponse(BaseModel):
    user_id: str
    session_token: str = ""
    files: list[FileInfo]
    validation: UploadValidationSummary | None = None


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


# ---- Commerce ----

class EntitlementSnapshot(BaseModel):
    promised_photos: int = Field(..., ge=1)
    scene_count: int = Field(..., ge=1)
    photo_mix: dict[str, int] = Field(default_factory=dict)
    rerun_quota: int = Field(0, ge=0)
    repaint_quota: int = Field(0, ge=0)
    retention_days: int = Field(1, ge=1)
    delivery_specs: list[str] = Field(default_factory=list)
    preview_policy: str = "trial"


class SkuInfo(BaseModel):
    sku_id: str
    name: str
    description: str = ""
    tag: str = ""
    price: int = Field(..., ge=0, description="价格，单位分")
    currency: str = "CNY"
    active: bool = True
    highlight: bool = False
    entitlements: EntitlementSnapshot


class OrderCreateRequest(BaseModel):
    package_id: str = Field(..., description="视觉主题")
    sku_id: str = Field(..., description="销售 SKU")


class GenerationBatchInfo(BaseModel):
    batch_id: str
    order_id: str
    batch_type: BatchType
    initiated_by: InitiatedBy
    status: BatchStatus
    requested_photos: int = 0
    delivered_photos: int = 0
    progress: int = 0
    message: str = ""
    quality_score: float = 0.0
    failure_reason: str = ""
    started_at: str | None = None
    completed_at: str | None = None
    created_at: str
    updated_at: str


class DeliverableInfo(BaseModel):
    deliverable_id: str
    order_id: str
    batch_id: str
    url: str
    photo_status: str = "delivered"
    quality_score: float = 0.0
    delivery_tier: DeliveryTier = DeliveryTier.four_k
    created_at: str


class OrderInfo(BaseModel):
    order_id: str
    identity_id: str
    sku_id: str
    package_id: str
    amount: int = 0
    currency: str = "CNY"
    payment_status: PaymentStatus
    fulfillment_status: FulfillmentStatus
    service_status: ServiceStatus
    entitlement_snapshot: EntitlementSnapshot
    rerun_used_count: int = 0
    created_at: str
    paid_at: str | None = None
    expired_at: str | None = None
    closed_at: str | None = None
    latest_batch: GenerationBatchInfo | None = None
    deliverable_count: int = 0
    remaining_reruns: int = 0
    package_name: str = ""
    sku_name: str = ""


class PaymentSessionResponse(BaseModel):
    payment_id: str
    order_id: str
    provider: PaymentProvider
    status: str
    amount: int
    currency: str = "CNY"
    checkout_url: str = ""


class PaymentConfirmResponse(BaseModel):
    payment_id: str
    order_id: str
    payment_status: PaymentStatus
    paid_at: str | None = None


class StartOrderResponse(BaseModel):
    order_id: str
    batch_id: str
    fulfillment_status: FulfillmentStatus


class StartOrderRequest(BaseModel):
    makeup_style: Optional[MakeupStyle] = None
    gender: Optional[Gender] = None
    groom_style: Optional[str] = None
    bride_style: Optional[str] = None


class BatchListResponse(BaseModel):
    items: list[GenerationBatchInfo]


class DeliverableListResponse(BaseModel):
    items: list[DeliverableInfo]


class OrderListResponse(BaseModel):
    items: list[OrderInfo]


class MockPayCreateRequest(BaseModel):
    order_id: str


class MockPayConfirmRequest(BaseModel):
    payment_id: str
    succeed: bool = True


# ---- Common ----

class ErrorResponse(BaseModel):
    detail: str


class JsonDictResponse(BaseModel):
    payload: dict[str, Any]
