from __future__ import annotations

import uuid
import logging

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request, Response

from config import settings
from models.schemas import FileInfo, UploadResponse
from models.database import create_user, get_user_by_token, increment_photos_count
from utils.storage import save_upload_file

logger = logging.getLogger(__name__)

router = APIRouter(tags=["upload"])

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def _validate_file(file: UploadFile) -> None:
    """校验单个上传文件。"""
    # 检查 content type
    ct = (file.content_type or "").lower()
    if ct not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ct}. Only JPEG and PNG are allowed.",
        )

    # 检查扩展名
    if file.filename:
        ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file extension: {ext}. Only .jpg, .jpeg, .png are allowed.",
            )


@router.post("/api/upload", response_model=UploadResponse)
async def upload_files(
    request: Request,
    response: Response,
    files: list[UploadFile] = File(..., description="上传的照片文件"),
    roles: list[str] | None = Form(
        default=None,
        description="可选：与 files 一一对应的角色标签，支持 couple/bride/groom/unknown",
    ),
):
    """
    接收多文件上传，保存到 uploads/{user_id}/。
    - 支持 JPEG / PNG
    - 单文件大小限制 10MB
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    if roles is not None and len(roles) not in (0, len(files)):
        raise HTTPException(
            status_code=400,
            detail="roles length must match files length when provided",
        )

    session_token = request.cookies.get(settings.session_cookie_name, "")
    user = await get_user_by_token(session_token) if session_token else None
    if user:
        user_id = str(user["user_id"])
    else:
        user_id, session_token = await create_user()

    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        max_age=settings.session_ttl_hours * 3600,
    )

    result_files: list[FileInfo] = []

    for index, file in enumerate(files):
        # 校验类型
        _validate_file(file)

        # 读取内容
        content = await file.read()

        # 校验大小
        if len(content) > settings.max_upload_size:
            raise HTTPException(
                status_code=400,
                detail=f"File {file.filename} exceeds {settings.max_upload_size // (1024*1024)}MB limit.",
            )

        role = ""
        if roles:
            role = (roles[index] or "").strip().lower()
            if role not in {"", "couple", "bride", "groom", "unknown"}:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Unsupported role: '{role}'. "
                        "Allowed: couple, bride, groom, unknown"
                    ),
                )

        # 保存文件
        file_id, path = await save_upload_file(
            user_id,
            file.filename or "upload.jpg",
            content,
            role=role or None,
        )

        result_files.append(
            FileInfo(
                id=file_id,
                filename=file.filename or "upload.jpg",
                url=f"/api/files/uploads/{user_id}/{path.name}",
            )
        )

    logger.info("User %s uploaded %d file(s)", user_id, len(result_files))

    await increment_photos_count(user_id, len(result_files))

    return {
        "user_id": user_id,
        "session_token": session_token,
        "files": [f.model_dump() for f in result_files],
    }
