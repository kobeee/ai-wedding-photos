from fastapi import APIRouter

from config import settings

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health_check():
    """健康检查端点。"""
    api_configured = bool(settings.chat_api_key or settings.nano_banana_api_key)
    return {
        "status": "ok",
        "service": "lumiere-studio",
        "api_configured": api_configured,
    }


@router.get("/api/health/detail")
async def health_detail():
    """详细健康状态。"""
    return {
        "status": "ok",
        "service": settings.app_name,
        "debug": settings.debug,
        "api_configured": bool(settings.chat_api_key or settings.nano_banana_api_key),
        "chat_api_configured": bool(settings.chat_api_key),
        "nano_api_configured": bool(settings.nano_banana_api_key),
        "dedicated_nano_api_configured": bool(settings.laozhang_nano_api_key),
        "nano_banana_model": settings.nano_banana_model,
        "gpt_image_model": settings.gpt_image_model,
        "gpt_image_repairs_enabled": settings.enable_gpt_image_repairs,
        "vlm_timeout_seconds": settings.vlm_timeout_seconds,
        "vlm_max_tokens": settings.vlm_max_tokens,
        "vlm_max_image_dimension": settings.vlm_max_image_dimension,
        "allow_degraded_delivery_on_vlm_unavailable": settings.allow_degraded_delivery_on_vlm_unavailable,
        "upload_dir": settings.upload_dir,
        "output_dir": settings.output_dir,
        "data_retention_hours": settings.data_retention_hours,
    }
