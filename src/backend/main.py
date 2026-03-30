import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from routers import files, generate, health, makeup, orders, payments, upload
from models.database import get_db, close_db
from middleware.auth import SessionAuthMiddleware
from utils.storage import ensure_dirs, periodic_cleanup

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

_cleanup_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理。"""
    global _cleanup_task

    # ---- Startup ----
    logger.info("Starting %s ...", settings.app_name)
    ensure_dirs()
    logger.info("Upload dir: %s", Path(settings.upload_dir).resolve())
    logger.info("Output dir: %s", Path(settings.output_dir).resolve())

    # 初始化数据库
    await get_db()
    logger.info("Database initialized: %s", settings.db_path)

    if not settings.chat_api_key:
        logger.warning(
            "LAOZHANG_API_KEY is not set. Director/VLM and optional GPT Image repairs will be unavailable."
        )
    if not settings.nano_banana_api_key:
        logger.warning(
            "LAOZHANG_NANO_API_KEY is not set. Nano Banana image generation will be unavailable."
        )
    if not settings.enable_gpt_image_repairs:
        logger.info(
            "GPT Image repairs are disabled. Emotional fixes will stay on the Nano Banana pipeline."
        )
    if settings.allow_degraded_delivery_on_vlm_unavailable:
        logger.info(
            "VLM unavailable fallback is enabled. Generate tasks will degrade to deliverable output when inspection is down."
        )

    # 启动后台清理任务
    _cleanup_task = asyncio.create_task(periodic_cleanup(interval_seconds=3600))

    yield

    # ---- Shutdown ----
    if _cleanup_task and not _cleanup_task.done():
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass

    await close_db()
    logger.info("%s shut down.", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    description="AI 高定婚纱摄影后端服务",
    version="0.2.0",
    lifespan=lifespan,
)

# ---- CORS ----
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Session Auth ----
app.add_middleware(SessionAuthMiddleware)

# ---- Routers ----
app.include_router(health.router)
app.include_router(upload.router)
app.include_router(makeup.router)
app.include_router(generate.router)
app.include_router(orders.router)
app.include_router(payments.router)
app.include_router(files.router)
