import shutil
from pathlib import Path

from fastapi import APIRouter, File, Header, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.core.config import settings
from app.core.storage_backend import get_backend
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
# Shared helpers
# -----------------------

def _require_project(project_id: str):
    """Return a 404 response when a project is missing **or expired**.

    Expired public projects are treated as already gone, so every project-scoped
    endpoint refuses them the moment the deadline passes — without waiting for
    the cleanup sweep to physically remove the objects. Uses the cheap existence
    check, which does not recompute counts.
    """
    if project_manager.exists(project_id):
        return None
    return error("Project not found.", 404)


def _project_payload(project) -> dict:
    """Serialize a project, adding the server-authoritative countdown.

    ``seconds_remaining`` is computed from the stored ``expires_at`` against the
    server clock, so the UI can render a countdown without the browser's clock
    ever influencing the real deadline. It is ``None`` when the project has no
    expiry (local/self-hosted mode).
    """
    data = project.model_dump(mode="json")
    data["seconds_remaining"] = project_manager.seconds_remaining(project)
    return data


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


@router.get("/config")
def config():
    """Public runtime configuration the frontend needs to render correctly.

    The frontend must not hardcode deployment facts: the same build is served
    against a self-hosted backend (projects are permanent) and against the free
    public deployment (projects are temporary). Asking the server which mode it
    is in keeps the expiry warning honest instead of guessing from the URL.

    Deliberately exposes nothing sensitive — no keys, no paths, no tokens.
    """
    return success(
        "Configuration fetched.",
        {
            "temporary_projects": settings.project_ttl_enabled,
            "project_ttl_hours": (
                settings.PROJECT_TTL_HOURS if settings.project_ttl_enabled else None
            ),
            "max_upload_bytes": settings.MAX_UPLOAD_BYTES,
            "max_images_per_project": settings.MAX_IMAGES_PER_PROJECT,
        },
    )


@router.post("/maintenance/cleanup")
def maintenance_cleanup(x_maintenance_token: str | None = Header(default=None)):
    """Sweep expired anonymous projects (cloud deployment only).

    Guarded by a shared secret so it can be driven by an external free cron
    without exposing an open deletion endpoint. Disabled (404) when no token is
    configured or when running in local mode, so a self-hosted instance never
    exposes this and never auto-deletes data.
    """
    if not settings.is_cloud or not settings.MAINTENANCE_TOKEN:
        return error("Not found.", 404)
    if x_maintenance_token != settings.MAINTENANCE_TOKEN:
        return error("Unauthorized.", 401)
    result = project_manager.cleanup_expired_projects()
    return success("Cleanup complete.", result)


# -----------------------
# Projects
# -----------------------

@router.post("/projects")
def create_project(payload: ProjectCreate | None = None):
    name = payload.name if payload else None
    project = project_manager.create_project(name)
    return success("Project created.", _project_payload(project), 201)


@router.get("/projects")
def list_projects():
    return success(
        "Projects fetched.",
        [_project_payload(p) for p in project_manager.list_projects()],
    )


@router.get("/projects/{project_id}")
def get_project(project_id: str):
    project = project_manager.touch_opened(project_id)
    if project is None:
        return error("Project not found.", 404)
    return success("Project fetched.", _project_payload(project))


@router.put("/projects/{project_id}")
def update_project(project_id: str, payload: ProjectUpdate):
    project = project_manager.update_project(
        project_id, name=payload.name, status=payload.status
    )
    if project is None:
        return error("Project not found.", 404)
    return success("Project updated.", _project_payload(project))


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
    gone = _require_project(project_id)
    if gone is not None:
        return gone
    image = upload_manager.get_image(project_id, image_id)
    if image is None:
        return error("Image not found.", 404)
    return success("Image fetched.", image.model_dump(mode="json"))


@router.get("/projects/{project_id}/images/{image_id}/file")
def get_image_file(project_id: str, image_id: str):
    gone = _require_project(project_id)
    if gone is not None:
        return gone
    image = upload_manager.get_image(project_id, image_id)
    if image is None:
        return error("Image not found.", 404)

    # Serve through the storage backend so the same route streams a local file
    # (v1.0.0) or a cloud object without the route knowing which is active.
    return get_backend().image_response(project_id, image)


@router.delete("/projects/{project_id}/images/{image_id}")
def delete_image(project_id: str, image_id: str):
    gone = _require_project(project_id)
    if gone is not None:
        return gone
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
    gone = _require_project(project_id)
    if gone is not None:
        return gone
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
    gone = _require_project(project_id)
    if gone is not None:
        return gone
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
    gone = _require_project(project_id)
    if gone is not None:
        return gone
    annotations = annotation_manager.list_for_image(project_id, image_id)
    return success(
        "Annotations fetched.",
        _serialize_annotations(project_id, annotations),
    )


@router.post("/projects/{project_id}/images/{image_id}/annotations")
def create_annotation(project_id: str, image_id: str, payload: AnnotationIn):
    gone = _require_project(project_id)
    if gone is not None:
        return gone
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
    gone = _require_project(project_id)
    if gone is not None:
        return gone
    # The annotation must exist AND belong to the image named in the path.
    # Matching on annotation_id alone would let a request against the wrong
    # image URL mutate an unrelated annotation, so we reject a mismatch as
    # not-found rather than silently editing the wrong box.
    existing = annotation_manager.get(project_id, annotation_id)
    if existing is None or existing.image_id != image_id:
        return error("Annotation not found.", 404)
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
    gone = _require_project(project_id)
    if gone is not None:
        return gone
    # Same relationship guard as update: only delete the annotation when it
    # actually belongs to the image in the path.
    existing = annotation_manager.get(project_id, annotation_id)
    if existing is None or existing.image_id != image_id:
        return error("Annotation not found.", 404)
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

    # In the public (cloud) deployment the disk is ephemeral scratch space, so
    # the generated archive and its build dir are removed once the response has
    # been streamed. Self-hosted (local) mode leaves them in place, exactly as
    # v1.0.0 did.
    background = None
    if settings.is_cloud:
        background = BackgroundTask(_cleanup_export, zip_path)

    return FileResponse(
        path=zip_path,
        filename=f"{safe_name}_yolo.zip",
        media_type="application/zip",
        background=background,
    )


@router.get("/projects/{project_id}/export/coco")
def export_coco(project_id: str):
    """Export the project as a COCO dataset (images + annotations/instances.json).

    Deliberately the same shape as the YOLO endpoint above — same lookups, same
    archive delivery, same cloud-only scratch cleanup — so both formats behave
    identically from the frontend's point of view.
    """
    project = project_manager.get_project(project_id)
    if project is None:
        return error("Project not found.", 404)

    images = upload_manager.list_images(project_id)
    annotations = annotation_manager.list_all(project_id)
    labels = label_manager.list_labels(project_id)

    zip_path = export_manager.export_coco(project_id, images, annotations, labels)

    safe_name = (project.name or "dataset").strip().replace(" ", "_") or "dataset"

    background = None
    if settings.is_cloud:
        background = BackgroundTask(_cleanup_export, zip_path)

    return FileResponse(
        path=zip_path,
        filename=f"{safe_name}_coco.zip",
        media_type="application/zip",
        background=background,
    )


def _cleanup_export(zip_path: Path) -> None:
    """Remove a generated export archive and its build directory (cloud mode)."""
    zip_path = Path(zip_path)
    try:
        if zip_path.exists():
            zip_path.unlink()
        build_dir = zip_path.parent / "dataset"
        if build_dir.exists():
            shutil.rmtree(build_dir)
    except OSError:
        pass  # best-effort cleanup; never fail the request over scratch files


# -----------------------
# AI auto-labeling (interface only; not implemented)
# -----------------------

@router.post("/projects/{project_id}/images/{image_id}/predict")
def predict(project_id: str, image_id: str):
    gone = _require_project(project_id)
    if gone is not None:
        return gone
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
