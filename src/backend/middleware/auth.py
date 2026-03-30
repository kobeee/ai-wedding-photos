"""Session Token 鉴权中间件。"""
from __future__ import annotations

import logging

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from config import settings
from models.database import get_user_by_token

logger = logging.getLogger(__name__)

# 不需要鉴权的路径前缀
_PUBLIC_PATHS = frozenset({
    "/api/health",
    "/api/upload",       # 上传时生成 token
    "/api/packages",     # 套餐列表公开
    "/api/skus",         # SKU 列表公开
    "/docs",
    "/openapi.json",
    "/redoc",
})


def _is_public(path: str) -> bool:
    """判断路径是否公开（不需要鉴权）。"""
    for prefix in _PUBLIC_PATHS:
        if path.startswith(prefix):
            return True
    return False


class SessionAuthMiddleware(BaseHTTPMiddleware):
    """
    简单 Bearer Token 鉴权。
    上传时生成 session_token，后续请求通过 Authorization header 携带。
    """

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS" or _is_public(request.url.path):
            return await call_next(request)

        token = request.cookies.get(settings.session_cookie_name, "")
        auth_header = request.headers.get("Authorization", "")
        if not token and auth_header.startswith("Bearer "):
            token = auth_header[7:]

        if not token:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid session"},
            )

        user = await get_user_by_token(token)
        if not user:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid session token"},
            )

        # 将 user 信息注入 request state
        request.state.user_id = user["user_id"]
        request.state.session_token = token

        return await call_next(request)
