from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# backend/app/core/config.py -> parents[2] == backend/
BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # Read a local .env when present (handy for dev); ignore unknown vars so a
    # shared deployment environment can carry extra keys without crashing here.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "ForgoteLabeling API"
    VERSION: str = "1.0.0"

    BASE_DIR: Path = BASE_DIR

    # All local storage derives from BASE_DIR so the app behaves the same
    # regardless of the directory uvicorn is started from.
    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    EXPORT_DIR: Path = BASE_DIR / "exports"
    PROJECT_DIR: Path = BASE_DIR / "projects"
    CHECKPOINT_DIR: Path = BASE_DIR / "checkpoints"

    # Allowed image types for uploads.
    ALLOWED_IMAGE_EXTENSIONS: set[str] = {".jpg", ".jpeg", ".png", ".webp"}

    # -----------------------------------------------------------------
    # Storage backend selection
    # -----------------------------------------------------------------
    # "local"  -> JSON + image files on the local filesystem (v1.0.0 default,
    #             used for self-hosting and the whole test suite).
    # "cloud"  -> objects in Supabase Storage, for the ephemeral-disk public
    #             deployment. Selected only when STORAGE_BACKEND=cloud is set.
    STORAGE_BACKEND: str = "local"

    # Supabase Storage config (only required when STORAGE_BACKEND=cloud).
    # SUPABASE_SERVICE_KEY is a secret and must come from the environment; it is
    # used server-side only and never sent to the browser.
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_KEY: str = ""
    SUPABASE_BUCKET: str = "forgotelabeling"

    # Shared secret guarding the on-demand cleanup endpoint. When empty (the
    # default, and always in local mode) the endpoint is disabled entirely, so a
    # self-hosted instance never exposes it. Set from the environment in cloud.
    MAINTENANCE_TOKEN: str = ""

    # -----------------------------------------------------------------
    # CORS
    # -----------------------------------------------------------------
    # Local dev origins are always allowed. The deployed frontend origin is
    # added via FRONTEND_ORIGIN (e.g. https://your-project.pages.dev) so we
    # never need a wildcard origin alongside credentials.
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ]
    FRONTEND_ORIGIN: str = ""

    # -----------------------------------------------------------------
    # Abuse limits for anonymous public projects
    # -----------------------------------------------------------------
    MAX_UPLOAD_BYTES: int = 10 * 1024 * 1024          # 10 MB per image
    MAX_IMAGES_PER_PROJECT: int = 100                 # images per project
    MAX_PROJECT_BYTES: int = 200 * 1024 * 1024        # total bytes per project

    # -----------------------------------------------------------------
    # Temporary-project lifetime (cloud only)
    # -----------------------------------------------------------------
    # Public projects are anonymous and disposable: the free object-storage quota
    # is finite, so each project is stamped with an expiry at creation and hard
    # deleted once it passes. 0 or a negative value disables expiry entirely.
    # NEVER applied in local mode, so self-hosted data is never auto-deleted.
    PROJECT_TTL_HOURS: int = 30

    @property
    def project_ttl_enabled(self) -> bool:
        """True when projects should be stamped with (and checked against) a TTL.

        Cloud-only by design: expiry is a consequence of the free-tier public
        deployment, not of the product itself.
        """
        return self.is_cloud and self.PROJECT_TTL_HOURS > 0

    @property
    def all_cors_origins(self) -> list[str]:
        """Local dev origins plus the deployed frontend origin, if configured."""
        origins = list(self.CORS_ORIGINS)
        if self.FRONTEND_ORIGIN and self.FRONTEND_ORIGIN not in origins:
            origins.append(self.FRONTEND_ORIGIN)
        return origins

    @property
    def is_cloud(self) -> bool:
        return self.STORAGE_BACKEND.strip().lower() == "cloud"


settings = Settings()


def ensure_storage_dirs() -> None:
    """Create the local storage directories if they do not exist.

    A no-op for the cloud backend, which has no local persistent disk (object
    storage keys are created implicitly on first write).
    """
    if settings.is_cloud:
        return
    for directory in (
        settings.UPLOAD_DIR,
        settings.EXPORT_DIR,
        settings.PROJECT_DIR,
        settings.CHECKPOINT_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)
