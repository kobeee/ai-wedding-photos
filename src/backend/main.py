import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import settings
from routers import health, upload, makeup, generate
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

    if not settings.laozhang_api_key:
        logger.warning(
            "LAOZHANG_API_KEY is not set. AI features will be unavailable. "
            "Create a .env file or set the environment variable."
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

    logger.info("%s shut down.", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    description="AI 高定婚纱摄影后端服务",
    version="0.1.0",
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

# ---- Routers ----
app.include_router(health.router)
app.include_router(upload.router)
app.include_router(makeup.router)
app.include_router(generate.router)

# ---- Static file serving (uploads & outputs) ----
# 让前端能通过 /api/files/uploads/... 和 /api/files/outputs/... 访问文件
uploads_path = Path(settings.upload_dir)
outputs_path = Path(settings.output_dir)
uploads_path.mkdir(parents=True, exist_ok=True)
outputs_path.mkdir(parents=True, exist_ok=True)

app.mount(
    "/api/files/uploads",
    StaticFiles(directory=str(uploads_path)),
    name="uploads",
)
app.mount(
    "/api/files/outputs",
    StaticFiles(directory=str(outputs_path)),
    name="outputs",
)
