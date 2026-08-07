from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field


class Annotation(BaseModel):

    id: str = Field(
        default_factory=lambda: str(uuid4())
    )

    image_id: str

    label: str

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC)
    )