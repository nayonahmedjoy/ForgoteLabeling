from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Project(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str = "Untitled Project"
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    status: str = "active"

    model: str | None = None
    export_format: str | None = None

    images: int = 0
    annotations: int = 0

    last_opened: datetime | None = None
