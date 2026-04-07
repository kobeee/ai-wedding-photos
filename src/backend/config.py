from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Lumiere Studio API"
    debug: bool = False

    # AI APIs (via laozhang.ai proxy)
    laozhang_api_key: str = ""
    laozhang_nano_api_key: str = ""
    laozhang_base_url: str = "https://api.laozhang.ai"

    # Nano Banana Pro
    nano_banana_model: str = "gemini-3-pro-image-preview"
    nano_timeout_seconds: int = 300
    nano_image_size: str = "1K"
    nano_reference_max_image_dimension: int = 1280
    nano_reference_jpeg_quality: int = 82
    nano_reference_min_jpeg_quality: int = 52
    nano_reference_max_bytes: int = 220 * 1024
    nano_reference_total_max_bytes: int = 880 * 1024
    nano_reference_max_images: int = 4

    # GPT Image
    gpt_image_model: str = "gpt-image-1.5"
    enable_gpt_image_repairs: bool = False

    # Director / VLM (顶级语言与多模态模型)
    director_model: str = "gemini-3.1-pro-preview"
    vlm_model: str = "gemini-3.1-pro-preview"
    vlm_timeout_seconds: int = 120
    vlm_max_tokens: int = 4096
    vlm_max_image_dimension: int = 1536
    vlm_jpeg_quality: int = 85
    upload_validation_timeout_seconds: int = 90
    upload_validation_max_tokens: int = 900
    upload_validation_max_image_dimension: int = 768
    upload_validation_jpeg_quality: int = 72
    upload_validation_min_jpeg_quality: int = 48
    upload_validation_max_bytes: int = 180 * 1024
    upload_validation_total_max_bytes: int = 720 * 1024
    upload_validation_max_images: int = 4

    # Storage
    upload_dir: str = "./uploads"
    output_dir: str = "./outputs"
    db_path: str = "./data/lumiere.db"
    max_upload_size: int = 10 * 1024 * 1024  # 10MB
    upload_store_max_image_dimension: int = 2200
    upload_store_jpeg_quality: int = 88
    upload_store_max_bytes: int = 3 * 1024 * 1024
    delivery_long_edge: int = 4096

    # Security
    data_retention_hours: int = 24
    session_cookie_name: str = "lumiere_session"
    session_cookie_secure: bool = False
    session_ttl_hours: int = 24 * 7

    # ACP Server
    acp_port: int = 8001

    # Quality thresholds
    quality_excellent: float = 0.95   # 直接交付
    quality_acceptable: float = 0.85  # 合格
    quality_fixable: float = 0.70     # 需修复
    # < 0.70 → 重新生成
    allow_degraded_delivery_on_vlm_unavailable: bool = True
    photos_per_package: int = 4
    max_fix_rounds: int = 3
    v14_max_attempts: int = 3

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }

    @property
    def chat_api_key(self) -> str:
        """Director / VLM / GPT Image 默认走按量 key。"""
        return self.laozhang_api_key

    @property
    def gpt_image_api_key(self) -> str:
        return self.laozhang_api_key

    @property
    def nano_banana_api_key(self) -> str:
        """
        Nano Banana 支持独立 key。
        若未显式提供，则回退到 LAOZHANG_API_KEY 以兼容旧配置。
        """
        return self.laozhang_nano_api_key or self.laozhang_api_key


settings = Settings()
