from pathlib import Path

from pydantic_settings import BaseSettings


# backend/app/core/config.py -> parents[2] == backend/
BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    APP_NAME: str = "ForgoteLabeling API"
    VERSION: str = "1.0.0"

    BASE_DIR: Path = BASE_DIR

    # All storage derives from BASE_DIR so the app behaves the same
    # regardless of the directory uvicorn is started from.
    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    EXPORT_DIR: Path = BASE_DIR / "exports"
    PROJECT_DIR: Path = BASE_DIR / "projects"
    CHECKPOINT_DIR: Path = BASE_DIR / "checkpoints"

    # Allowed image types for uploads.
    ALLOWED_IMAGE_EXTENSIONS: set[str] = {".jpg", ".jpeg", ".png", ".webp"}

    # CORS origins for the local Vite dev server.
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ]


settings = Settings()


def ensure_storage_dirs() -> None:
    """Create the top-level storage directories if they do not exist."""
    for directory in (
        settings.UPLOAD_DIR,
        settings.EXPORT_DIR,
        settings.PROJECT_DIR,
        settings.CHECKPOINT_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)
