from fastapi import APIRouter

from app.core.config import settings
from app.utils.responses import success

router = APIRouter()


@router.get("/")
async def root():
    return success("ForgoteLabeling API is running.")


@router.get("/health")
async def health():
    return success(
        "Backend is healthy.",
        {
            "status": "healthy"
        }
    )


@router.get("/version")
async def version():
    return success(
        "Application version.",
        {
            "version": settings.VERSION
        }
    )