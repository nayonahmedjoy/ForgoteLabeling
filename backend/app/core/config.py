from pathlib import Path

from pydantic_settings import BaseSettings


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    APP_NAME: str = "ForgoteLabeling API"
    VERSION: str = "1.0.0"

    BASE_DIR: Path = BASE_DIR

    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    EXPORT_DIR: Path = BASE_DIR / "exports"
    PROJECT_DIR: Path = BASE_DIR / "projects"
    CHECKPOINT_DIR: Path = BASE_DIR / "checkpoints"


settings = Settings()