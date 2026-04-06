from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from config import settings
from models.schemas import MakeupRequest, MakeupResponse
from services.makeup_reference import generate_makeup_previews

router = APIRouter(tags=["makeup"])


@router.post("/api/makeup/generate", response_model=MakeupResponse)
async def generate_makeup(req: MakeupRequest, request: Request):
    """
    AI 试妆 - 生成 3 种不同风格的妆造效果图。
    如果用户已上传照片，会基于上传照片进行图生图；
    否则直接文生图。
    """
    if request.state.user_id != req.user_id:
        raise HTTPException(status_code=403, detail="Session token does not match user_id")

    if not settings.nano_banana_api_key:
        raise HTTPException(
            status_code=503,
            detail="Nano Banana service not configured. Set LAOZHANG_NANO_API_KEY or LAOZHANG_API_KEY.",
        )
    try:
        images = await generate_makeup_previews(req.user_id, req.gender)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Makeup preview generation incomplete: {exc}") from exc

    return MakeupResponse(user_id=req.user_id, images=images)
