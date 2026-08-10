import shutil
from datetime import datetime, timezone

from app.core import storage
from app.core.config import settings
from app.models.project import Project


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ProjectManager:
    """Projects persisted as folders under the upload directory."""

    def create_project(self, name: str | None = None) -> Project:
        project = Project(
            name=(name.strip() if name and name.strip() else "Untitled Project"),
            created_at=_now(),
            updated_at=_now(),
        )

        # Create the standard project folder layout.
        storage.images_dir(project.id).mkdir(parents=True, exist_ok=True)
        storage.annotations_dir(project.id).mkdir(parents=True, exist_ok=True)
        storage.thumbnails_dir(project.id).mkdir(parents=True, exist_ok=True)
        storage.export_dir(project.id).mkdir(parents=True, exist_ok=True)

        # Initialize index files so the filesystem is always the source of truth.
        storage.write_json(storage.images_index_path(project.id), [])
        storage.write_json(storage.labels_path(project.id), [])
        storage.write_json(storage.annotations_path(project.id), [])

        self.save_project(project)
        return project

    def save_project(self, project: Project) -> None:
        storage.write_json(
            storage.metadata_path(project.id),
            project.model_dump(mode="json"),
        )

    def _load(self, project_id: str) -> Project | None:
        data = storage.read_json(storage.metadata_path(project_id), None)
        if data is None:
            return None
        try:
            return Project(**data)
        except Exception:
            return None

    def _refresh_counts(self, project: Project) -> Project:
        """Recompute image/annotation counts from disk so metadata is accurate.

        Counts must match what the API actually serves: the upload and
        annotation managers skip invalid/legacy entries (e.g. old image-level
        labels without bounding-box coordinates) when loading, so counting the
        raw JSON length here would overstate legacy projects. Import locally to
        avoid a circular import at module load.
        """
        from app.services.annotation.manager import manager as annotation_manager
        from app.services.upload.manager import manager as upload_manager

        new_images = len(upload_manager.list_images(project.id))
        new_annotations = len(annotation_manager.list_all(project.id))

        if project.images != new_images or project.annotations != new_annotations:
            project.images = new_images
            project.annotations = new_annotations
            self.save_project(project)

        return project

    def list_projects(self) -> list[Project]:
        projects: list[Project] = []

        if not settings.UPLOAD_DIR.exists():
            return projects

        for folder in settings.UPLOAD_DIR.iterdir():
            if not folder.is_dir():
                continue
            project = self._load(folder.name)
            if project is not None:
                projects.append(self._refresh_counts(project))

        projects.sort(key=lambda p: p.created_at, reverse=True)
        return projects

    def get_project(self, project_id: str) -> Project | None:
        project = self._load(project_id)
        if project is None:
            return None
        return self._refresh_counts(project)

    def update_project(
        self,
        project_id: str,
        name: str | None = None,
        status: str | None = None,
    ) -> Project | None:
        project = self._load(project_id)
        if project is None:
            return None

        if name is not None and name.strip():
            project.name = name.strip()
        if status is not None and status.strip():
            project.status = status.strip()

        project.updated_at = _now()
        self.save_project(project)
        return self._refresh_counts(project)

    def touch_opened(self, project_id: str) -> Project | None:
        project = self._load(project_id)
        if project is None:
            return None
        project.last_opened = _now()
        self.save_project(project)
        return self._refresh_counts(project)

    def delete_project(self, project_id: str) -> bool:
        project_path = storage.project_dir(project_id)
        if not project_path.exists():
            return False
        shutil.rmtree(project_path)
        return True


manager = ProjectManager()
