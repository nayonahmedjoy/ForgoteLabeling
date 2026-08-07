from datetime import datetime

from pydantic import BaseModel


class Project(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    status: str = "active"

    model: str | None = None
    export_format: str | None = None

    images: int = 0
    annotations: int = 0

    last_opened: datetime | None = None