import mimetypes

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import FileResponse

from app.core.config import settings
from app.models.annotation import AnnotationIn
from app.models.requests import (
    LabelCreate,
    LabelUpdate,
    ProjectCreate,
    ProjectUpdate,
)
from app.services.ai.manager import manager as ai_manager
from app.services.annotation.manager import manager as annotation_manager
from app.services.export.manager import manager as export_manager
from app.services.label.manager import LabelError, manager as label_manager
from app.services.project.manager import manager as project_manager
from app.services.upload.manager import UploadError, manager as upload_manager
from app.utils.responses import error, success

router = APIRouter()


# -----------------------
# Meta
# -----------------------

@router.get("/")
def root():
    return success("ForgoteLabeling API is running.")


@router.get("/health")
def health():
    return success("Backend is healthy.", {"status": "healthy"})


@router.get("/version")
def version():
    return success("Application version.", {"version": settings.VERSION})


# -----------------------
# Projects
# -----------------------

@router.post("/projects")
def create_project(payload: ProjectCreate | None = None):
    name = payload.name if payload else None
    project = project_manager.create_project(name)
    return success("Project created.", project.model_dump(mode="json"), 201)


@router.get("/projects")
def list_projects():
    return success(
        "Projects fetched.",
        [p.model_dump(mode="json") for p in project_manager.list_projects()],
    )


@router.get("/projects/{project_id}")
def get_project(project_id: str):
    project = project_manager.touch_opened(project_id)
    if project is None:
        return error("Project not found.", 404)
    return success("Project fetched.", project.model_dump(mode="json"))


@router.put("/projects/{project_id}")
def update_project(project_id: str, payload: ProjectUpdate):
    project = project_manager.update_project(
        project_id, name=payload.name, status=payload.status
    )
    if project is None:
        return error("Project not found.", 404)
    return success("Project updated.", project.model_dump(mode="json"))


@router.delete("/projects/{project_id}")
def delete_project(project_id: str):
    if not project_manager.delete_project(project_id):
        return error("Project not found.", 404)
    return success("Project deleted.")


# -----------------------
# Images
# -----------------------

@router.post("/projects/{project_id}/images")
def upload_images(
    project_id: str,
    files: list[UploadFile] = File(...),
):
    if project_manager.get_project(project_id) is None:
        return error("Project not found.", 404)

    uploaded = []
    skipped = []

    for file in files:
        try:
            image = upload_manager.upload_image(project_id, file)
            if image is None:
                skipped.append({"filename": file.filename, "reason": "Project not found."})
            else:
                uploaded.append(image.model_dump(mode="json"))
        except UploadError as exc:
            skipped.append({"filename": file.filename, "reason": str(exc)})

    if not uploaded and skipped:
        return error("No images were uploaded.", 400, {"skipped": skipped})

    return success(
        f"Uploaded {len(uploaded)} image(s).",
        {"uploaded": uploaded, "skipped": skipped},
        201,
    )


@router.get("/projects/{project_id}/images")
def list_images(project_id: str):
    if project_manager.get_project(project_id) is None:
        return error("Project not found.", 404)
    images = upload_manager.list_images(project_id)
    return success(
        "Images fetched.",
        [img.model_dump(mode="json") for img in images],
    )


@router.get("/projects/{project_id}/images/{image_id}")
def get_image(project_id: str, image_id: str):
    image = upload_manager.get_image(project_id, image_id)
    if image is None:
        return error("Image not found.", 404)
    return success("Image fetched.", image.model_dump(mode="json"))


@router.get("/projects/{project_id}/images/{image_id}/file")
def get_image_file(project_id: str, image_id: str):
    image = upload_manager.get_image(project_id, image_id)
    if image is None:
        return error("Image not found.", 404)

    media_type, _ = mimetypes.guess_type(image.filename)
    return FileResponse(
        path=image.filepath,
        media_type=media_type or "application/octet-stream",
        filename=image.original_filename or image.filename,
    )


@router.delete("/projects/{project_id}/images/{image_id}")
def delete_image(project_id: str, image_id: str):
    if not upload_manager.delete_image(project_id, image_id):
        return error("Image not found.", 404)
    return success("Image deleted.")


# -----------------------
# Labels
# -----------------------

@router.get("/projects/{project_id}/labels")
def list_labels(project_id: str):
    if project_manager.get_project(project_id) is None:
        return error("Project not found.", 404)
    labels = label_manager.list_labels(project_id)
    return success(
        "Labels fetched.",
        [label.model_dump(mode="json") for label in labels],
    )


@router.post("/projects/{project_id}/labels")
def create_label(project_id: str, payload: LabelCreate):
    if project_manager.get_project(project_id) is None:
        return error("Project not found.", 404)
    try:
        label = label_manager.create_label(project_id, payload.name, payload.color)
    except LabelError as exc:
        return error(str(exc), 409)
    return success("Label created.", label.model_dump(mode="json"), 201)


@router.put("/projects/{project_id}/labels/{label_id}")
def update_label(project_id: str, label_id: str, payload: LabelUpdate):
    try:
        label = label_manager.update_label(
            project_id, label_id, name=payload.name, color=payload.color
        )
    except LabelError as exc:
        return error(str(exc), 409)
    if label is None:
        return error("Label not found.", 404)
    return success("Label updated.", label.model_dump(mode="json"))


@router.delete("/projects/{project_id}/labels/{label_id}")
def delete_label(project_id: str, label_id: str):
    if label_manager.get_label(project_id, label_id) is None:
        return error("Label not found.", 404)

    # Block deletion while annotations still reference this label, so boxes are
    # never silently orphaned. The caller must reassign or delete those
    # annotations first.
    references = annotation_manager.count_for_label(project_id, label_id)
    if references:
        return error(
            f"Label is used by {references} annotation(s) and cannot be deleted.",
            409,
            {"annotation_count": references},
        )

    label_manager.delete_label(project_id, label_id)
    return success("Label deleted.")


# -----------------------
# Annotations
# -----------------------

def _serialize_annotations(project_id: str, annotations):
    """Serialize annotations, resolving each ``label`` from its ``label_id``.

    The stored ``label`` string is a denormalized cache that goes stale when a
    label is renamed. ``label_id`` is the source of truth, so on read we
    overwrite ``label`` with the label's current name whenever the id resolves.
    Orphan/legacy annotations (no ``label_id`` or an id no label owns) keep
    their stored string, so no information is lost. The on-disk JSON is not
    modified.
    """
    names = {
        label.id: label.name
        for label in label_manager.list_labels(project_id)
    }
    result = []
    for annotation in annotations:
        data = annotation.model_dump(mode="json")
        if annotation.label_id in names:
            data["label"] = names[annotation.label_id]
        result.append(data)
    return result


@router.get("/projects/{project_id}/images/{image_id}/annotations")
def list_annotations(project_id: str, image_id: str):
    annotations = annotation_manager.list_for_image(project_id, image_id)
    return success(
        "Annotations fetched.",
        _serialize_annotations(project_id, annotations),
    )


@router.post("/projects/{project_id}/images/{image_id}/annotations")
def create_annotation(project_id: str, image_id: str, payload: AnnotationIn):
    if upload_manager.get_image(project_id, image_id) is None:
        return error("Image not found.", 404)
    try:
        annotation = annotation_manager.create(project_id, image_id, payload)
    except ValueError as exc:
        return error(str(exc), 400)
    # Refresh project counts.
    project_manager.get_project(project_id)
    data = _serialize_annotations(project_id, [annotation])[0]
    return success("Annotation created.", data, 201)


@router.put("/projects/{project_id}/images/{image_id}/annotations/{annotation_id}")
def update_annotation(
    project_id: str,
    image_id: str,
    annotation_id: str,
    payload: AnnotationIn,
):
    try:
        annotation = annotation_manager.update(project_id, annotation_id, payload)
    except ValueError as exc:
        return error(str(exc), 400)
    if annotation is None:
        return error("Annotation not found.", 404)
    data = _serialize_annotations(project_id, [annotation])[0]
    return success("Annotation updated.", data)


@router.delete(
    "/projects/{project_id}/images/{image_id}/annotations/{annotation_id}"
)
def delete_annotation(project_id: str, image_id: str, annotation_id: str):
    if not annotation_manager.delete(project_id, annotation_id):
        return error("Annotation not found.", 404)
    project_manager.get_project(project_id)
    return success("Annotation deleted.")


# -----------------------
# Export
# -----------------------

@router.get("/projects/{project_id}/export/yolo")
def export_yolo(project_id: str):
    project = project_manager.get_project(project_id)
    if project is None:
        return error("Project not found.", 404)

    images = upload_manager.list_images(project_id)
    annotations = annotation_manager.list_all(project_id)
    labels = label_manager.list_labels(project_id)

    zip_path = export_manager.export_yolo(project_id, images, annotations, labels)

    safe_name = (project.name or "dataset").strip().replace(" ", "_") or "dataset"
    return FileResponse(
        path=zip_path,
        filename=f"{safe_name}_yolo.zip",
        media_type="application/zip",
    )


# -----------------------
# AI auto-labeling (interface only; not implemented)
# -----------------------

@router.post("/projects/{project_id}/images/{image_id}/predict")
def predict(project_id: str, image_id: str):
    image = upload_manager.get_image(project_id, image_id)
    if image is None:
        return error("Image not found.", 404)

    if not ai_manager.is_available():
        return error(
            "AI auto-labeling is not implemented yet.",
            501,
            {"status": "not_implemented"},
        )

    predictions = ai_manager.predict(project_id, image)  # pragma: no cover
    created = [
        annotation_manager.create(project_id, image_id, p).model_dump(mode="json")
        for p in predictions
    ]
    return success("Predictions created.", created, 201)
