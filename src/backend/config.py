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

    # GPT Image
    gpt_image_model: str = "gpt-image-1.5"
    enable_gpt_image_repairs: bool = False

    # Director / VLM (顶级语言与多模态模型)
    director_model: str = "gemini-3.1-pro-preview"
    vlm_model: str = "gemini-3.1-pro-preview"
    vlm_timeout_seconds: int = 120
    vlm_max_tokens: int = 2048
    vlm_max_image_dimension: int = 1536
    vlm_jpeg_quality: int = 85

    # Storage
    upload_dir: str = "./uploads"
    output_dir: str = "./outputs"
    db_path: str = "./data/lumiere.db"
    max_upload_size: int = 10 * 1024 * 1024  # 10MB

    # Security
    data_retention_hours: int = 24

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
