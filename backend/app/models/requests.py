from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    status: str | None = None


class LabelCreate(BaseModel):
    name: str
    color: str | None = None


class LabelUpdate(BaseModel):
    name: str | None = None
    color: str | None = None
