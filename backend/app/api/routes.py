from fastapi import APIRouter, File, UploadFile

from app.core.config import settings
from app.models.annotation import Annotation
from app.services.annotation.manager import manager as annotation_manager
from app.services.project.manager import manager
from app.services.upload.manager import manager as upload_manager
from app.utils.responses import error, success
from fastapi.responses import FileResponse

from app.services.export.manager import manager as export_manager

router = APIRouter()


@router.get("/")
async def root():
    return success("ForgoteLabeling API is running.")


@router.get("/health")
async def health():
    return success(
        "Backend is healthy.",
        {
            "status": "healthy",
        },
    )


@router.get("/version")
async def version():
    return success(
        "Application version.",
        {
            "version": settings.VERSION,
        },
    )


# -----------------------
# Projects
# -----------------------

@router.post("/projects")
def create_project():
    project = manager.create_project()

    return success(
        "Project created.",
        project.model_dump(mode="json"),
    )


@router.get("/projects")
def list_projects():
    return success(
        "Projects fetched.",
        [
            project.model_dump(mode="json")
            for project in manager.list_projects()
        ],
    )


@router.get("/projects/{project_id}")
def get_project(project_id: str):
    project = manager.get_project(project_id)

    if project is None:
        return error(
            "Project not found.",
            status_code=404,
        )

    return success(
        "Project fetched.",
        project.model_dump(mode="json"),
    )


@router.delete("/projects/{project_id}")
def delete_project(project_id: str):
    deleted = manager.delete_project(project_id)

    if not deleted:
        return error(
            "Project not found.",
            status_code=404,
        )

    return success("Project deleted.")


# -----------------------
# Images
# -----------------------

@router.post("/projects/{project_id}/images")
def upload_image(
    project_id: str,
    file: UploadFile = File(...),
):
    image = upload_manager.upload_image(
        project_id,
        file,
    )

    if image is None:
        return error(
            "Project not found.",
            status_code=404,
        )

    return success(
        "Image uploaded.",
        image.model_dump(mode="json"),
    )


@router.get("/projects/{project_id}/images")
def list_images(project_id: str):
    images = upload_manager.list_images(project_id)

    return success(
        "Images fetched.",
        [
            image.model_dump(mode="json")
            for image in images
        ],
    )


@router.delete("/projects/{project_id}/images/{image_id}")
def delete_image(
    project_id: str,
    image_id: str,
):
    deleted = upload_manager.delete_image(
        project_id,
        image_id,
    )

    if not deleted:
        return error(
            "Image not found.",
            status_code=404,
        )

    return success("Image deleted.")


# -----------------------
# Annotations
# -----------------------

@router.post("/projects/{project_id}/annotations")
def save_annotation(
    project_id: str,
    annotation: Annotation,
):
    annotation_manager.save_label(
        project_id,
        annotation.image_id,
        annotation.label,
    )

    return success(
        "Annotation saved.",
        annotation.model_dump(mode="json"),
    )


@router.get("/projects/{project_id}/annotations")
def list_annotations(project_id: str):
    annotations = annotation_manager.list_annotations(project_id)

    return success(
        "Annotations fetched.",
        [
            item.model_dump(mode="json")
            for item in annotations
        ],
    )


@router.delete("/projects/{project_id}/annotations/{image_id}")
def delete_annotation(
    project_id: str,
    image_id: str,
):
    deleted = annotation_manager.delete_annotation(
        project_id,
        image_id,
    )

    if not deleted:
        return error(
            "Annotation not found.",
            status_code=404,
        )

    return success("Annotation deleted.") 

@router.get("/projects/{project_id}/export")
def export_project(project_id: str):

    project = manager.get_project(project_id)

    if project is None:
        return error(
            "Project not found.",
            status_code=404,
        )

    images = upload_manager.list_images(project_id)

    annotations = annotation_manager.list_annotations(
        project_id
    )

    csv_file = export_manager.export_csv(
        project_id,
        annotations,
        images,
    )

    return FileResponse(
        path=csv_file,
        filename="labels.csv",
        media_type="text/csv",
    )