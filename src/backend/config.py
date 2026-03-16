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

    # Storage
    upload_dir: str = "./uploads"
    output_dir: str = "./outputs"
    max_upload_size: int = 10 * 1024 * 1024  # 10MB

    # Security
    data_retention_hours: int = 24

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


settings = Settings()
