from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from config import settings

router = APIRouter(tags=["files"])


def _base_dir(kind: str) -> Path:
    if kind == "uploads":
        return Path(settings.upload_dir)
    if kind == "outputs":
        return Path(settings.output_dir)
    raise HTTPException(status_code=404, detail="Unknown file collection")


@router.get("/api/files/{kind}/{user_id}/{filename}")
async def read_private_file(kind: str, user_id: str, filename: str, request: Request):
    if request.state.user_id != user_id:
        raise HTTPException(status_code=404, detail="File not found")
    if filename.endswith(".meta.json"):
        raise HTTPException(status_code=404, detail="File not found")

    base_dir = _base_dir(kind).resolve()
    file_path = (base_dir / user_id / filename).resolve()
    try:
        file_path.relative_to(base_dir)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="File not found") from exc

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(file_path)
