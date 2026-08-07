from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, Field


class Image(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    filename: str
    filepath: str
    size: int

    created_at: datetime = Field(default_factory=datetime.utcnow)