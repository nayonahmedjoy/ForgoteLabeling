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

    # Hard deletion deadline for temporary public projects, stamped by the
    # server at creation time. ``None`` means "never expires", which is always
    # the case in local/self-hosted mode. This is deliberately a stored field so
    # the deadline is deterministic and auditable rather than recomputed from a
    # setting that might change later. It is never accepted from a request body
    # (see app.models.requests), so a client cannot set or extend it.
    expires_at: datetime | None = None

    model: str | None = None
    export_format: str | None = None

    images: int = 0
    annotations: int = 0

    last_opened: datetime | None = None
