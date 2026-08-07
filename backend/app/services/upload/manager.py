from pathlib import Path
from shutil import copyfileobj
from typing import Dict, List

from fastapi import UploadFile

from app.models.image import Image
from app.services.project.manager import manager as project_manager


UPLOAD_ROOT = Path("uploads")


class UploadManager:

    def __init__(self):
        self.images: Dict[str, List[Image]] = {}

    def upload_image(
        self,
        project_id: str,
        file: UploadFile,
    ) -> Image | None:

        project = project_manager.get_project(project_id)

        if project is None:
            return None

        project_dir = UPLOAD_ROOT / project_id
        project_dir.mkdir(parents=True, exist_ok=True)

        file_path = project_dir / file.filename

        with open(file_path, "wb") as buffer:
            copyfileobj(file.file, buffer)

        image = Image(
            filename=file.filename,
            filepath=str(file_path),
            size=file_path.stat().st_size,
        )

        self.images.setdefault(project_id, []).append(image)

        project.images += 1
        project.updated_at = image.created_at

        return image

    def list_images(
        self,
        project_id: str,
    ) -> List[Image]:

        return self.images.get(project_id, [])

    def delete_image(
        self,
        project_id: str,
        image_id: str,
    ) -> bool:

        images = self.images.get(project_id)

        if images is None:
            return False

        for image in images:

            if image.id == image_id:

                path = Path(image.filepath)

                if path.exists():
                    path.unlink()

                images.remove(image)

                project = project_manager.get_project(project_id)

                if project:
                    project.images -= 1
                    project.updated_at = image.created_at

                return True

        return False


manager = UploadManager()