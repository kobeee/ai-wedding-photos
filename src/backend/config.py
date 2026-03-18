from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Lumiere Studio API"
    debug: bool = False

    # AI APIs (via laozhang.ai proxy)
    laozhang_api_key: str = ""
    laozhang_base_url: str = "https://api.laozhang.ai"

    # Nano Banana Pro
    nano_banana_model: str = "gemini-3-pro-image-preview"

    # GPT Image
    gpt_image_model: str = "gpt-image-1"

    # Director LLM (摄影导演用的模型)
    director_model: str = "gpt-4o"

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

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


settings = Settings()
