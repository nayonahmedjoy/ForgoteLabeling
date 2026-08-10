from pathlib import Path
from shutil import copyfileobj
from uuid import uuid4

from fastapi import UploadFile

from app.core import storage
from app.core.config import settings
from app.models.image import Image
from app.services.project.manager import manager as project_manager

try:
    from PIL import Image as PILImage  # optional: used to read dimensions
except Exception:  # pragma: no cover - pillow may not be installed
    PILImage = None


class UploadError(Exception):
    """Raised when an uploaded file is rejected."""


class UploadManager:
    """Image storage where the filesystem index (images.json) is the source
    of truth, so uploads survive a backend restart."""

    def _load(self, project_id: str) -> list[Image]:
        raw = storage.read_json(storage.images_index_path(project_id), [])
        images: list[Image] = []
        for item in raw:
            try:
                images.append(Image(**item))
            except Exception:
                continue
        return images

    def _save(self, project_id: str, images: list[Image]) -> None:
        storage.write_json(
            storage.images_index_path(project_id),
            [img.model_dump(mode="json") for img in images],
        )

    def _unique_filename(self, project_id: str, original: str) -> str:
        """Avoid collisions when two uploads share a name."""
        stem = Path(original).stem
        suffix = Path(original).suffix.lower()
        candidate = f"{stem}{suffix}"
        existing = {img.filename for img in self._load(project_id)}
        if candidate not in existing and not (
            storage.images_dir(project_id) / candidate
        ).exists():
            return candidate
        return f"{stem}_{uuid4().hex[:8]}{suffix}"

    def upload_image(self, project_id: str, file: UploadFile) -> Image | None:
        if project_manager.get_project(project_id) is None:
            return None

        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in settings.ALLOWED_IMAGE_EXTENSIONS:
            raise UploadError(
                f"Unsupported file type '{suffix or 'unknown'}'. "
                f"Allowed: {', '.join(sorted(settings.ALLOWED_IMAGE_EXTENSIONS))}."
            )

        images_dir = storage.images_dir(project_id)
        images_dir.mkdir(parents=True, exist_ok=True)

        stored_name = self._unique_filename(project_id, file.filename or "image")
        file_path = images_dir / stored_name

        with open(file_path, "wb") as buffer:
            copyfileobj(file.file, buffer)

        width = height = None
        if PILImage is not None:
            try:
                with PILImage.open(file_path) as im:
                    width, height = im.size
            except Exception:
                pass  # dimensions are best-effort

        image = Image(
            filename=stored_name,
            original_filename=file.filename or stored_name,
            filepath=str(file_path),
            size=file_path.stat().st_size,
            width=width,
            height=height,
        )

        images = self._load(project_id)
        images.append(image)
        self._save(project_id, images)

        # Keep project metadata counts in sync.
        project_manager.get_project(project_id)

        return image

    def list_images(self, project_id: str) -> list[Image]:
        return self._load(project_id)

    def get_image(self, project_id: str, image_id: str) -> Image | None:
        for image in self._load(project_id):
            if image.id == image_id:
                return image
        return None

    def delete_image(self, project_id: str, image_id: str) -> bool:
        images = self._load(project_id)
        target = next((img for img in images if img.id == image_id), None)
        if target is None:
            return False

        path = Path(target.filepath)
        if path.exists():
            path.unlink()

        self._save(project_id, [img for img in images if img.id != image_id])

        # Remove annotations tied to this image, then refresh counts.
        from app.services.annotation.manager import manager as annotation_manager

        annotation_manager.delete_for_image(project_id, image_id)
        project_manager.get_project(project_id)

        return True


manager = UploadManager()
