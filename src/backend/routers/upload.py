from __future__ import annotations

import logging

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request, Response

from config import settings
from models.schemas import (
    FileInfo,
    UploadResponse,
    UploadValidationIssue,
    UploadValidationSummary,
)
from models.database import create_user, get_user_by_token, increment_photos_count
from services.upload_validator import REQUIRED_SLOTS, UploadBundleItem, upload_validator_service
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
    slots: list[str] | None = Form(
        default=None,
        description="可选：与 files 一一对应的固定坑位，如 groom_portrait / bride_full",
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
    if slots is not None and len(slots) not in (0, len(files)):
        raise HTTPException(
            status_code=400,
            detail="slots length must match files length when provided",
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

    upload_items: list[tuple[UploadFile, bytes, str, str]] = []
    validation_candidates: list[UploadBundleItem] = []

    for index, file in enumerate(files):
        _validate_file(file)
        content = await file.read()

        if len(content) > settings.max_upload_size:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"单张照片不能超过 {settings.max_upload_size // (1024 * 1024)}MB，"
                    f"请换一张更小的图，或手动压缩后重试：{file.filename or 'upload.jpg'}"
                ),
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

        slot = ""
        if slots:
            slot = (slots[index] or "").strip().lower()

        stored_filename = file.filename or "upload.jpg"
        upload_items.append((file, content, stored_filename, role))

        if slot:
            mime_type = file.content_type or "image/jpeg"
            validation_candidates.append(
                UploadBundleItem(
                    slot=slot,
                    role=role,
                    filename=stored_filename,
                    content=content,
                    mime_type=mime_type,
                )
            )

    validation_report = None
    provided_slots = {item.slot for item in validation_candidates}
    should_validate_bundle = bool(validation_candidates) and REQUIRED_SLOTS.issubset(provided_slots)
    if should_validate_bundle:
        validation_report = await upload_validator_service.validate(validation_candidates)
        if validation_report.errors:
            raise HTTPException(
                status_code=400,
                detail=validation_report.summary_text() or "上传照片未通过校验，请调整后重试",
            )

    result_files: list[FileInfo] = []
    for index, (_file, stored_content, stored_filename, role) in enumerate(upload_items):
        slot = (slots[index] or "").strip().lower() if slots else ""
        file_id, path = await save_upload_file(
            user_id,
            stored_filename,
            stored_content,
            role=role or None,
            slot=slot or None,
            validation={
                "source": validation_report.source if validation_report else "",
                "accepted": validation_report.slot_ok(slot) if validation_report and slot else True,
                "message": (
                    validation_report.slot_messages.get(slot, "")
                    if validation_report and slot
                    else ""
                ),
            },
        )

        result_files.append(
            FileInfo(
                id=file_id,
                filename=stored_filename,
                url=f"/api/files/uploads/{user_id}/{path.name}",
                role=role,
                slot=slot,
            )
        )

    logger.info("User %s uploaded %d file(s)", user_id, len(result_files))

    await increment_photos_count(user_id, len(result_files))

    return {
        "user_id": user_id,
        "session_token": session_token,
        "files": [f.model_dump() for f in result_files],
        "validation": (
            UploadValidationSummary(
                ok=True,
                issues=[
                    UploadValidationIssue(
                        level=issue.level,
                        message=issue.message,
                        slot=issue.slot,
                    )
                    for issue in (validation_report.warnings if validation_report else [])
                ],
                summary="上传资料校验通过",
            ).model_dump()
            if validation_report
            else None
        ),
    }
