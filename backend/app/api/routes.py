from fastapi import APIRouter

from app.core.config import settings
from app.utils.responses import success, error
from app.services.project.manager import manager

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


@router.post("/projects")
def create_project():

    project = manager.create_project()

    return success(
        "Project created.",
        project.model_dump(mode="json")
    )


@router.get("/projects")
def list_projects():

    return success(
        "Projects fetched.",
        manager.list_projects()
    )


@router.get("/projects/{project_id}")
def get_project(project_id: str):

    project = manager.get_project(project_id)

    if project is None:
        return error("Project not found.", status_code=404)

    return success(
        "Project fetched.",
        project
    )


@router.delete("/projects/{project_id}")
def delete_project(project_id: str):

    deleted = manager.delete_project(project_id)

    if not deleted:
        return error("Project not found.", status_code=404)

    return success("Project deleted.")