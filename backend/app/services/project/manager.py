import json
import shutil
import uuid

from datetime import UTC, datetime
from pathlib import Path

from app.core.config import settings
from app.models.project import Project

UPLOAD_DIR = settings.UPLOAD_DIR


class ProjectManager:

    def create_project(self):

        project_id = str(uuid.uuid4())

        project_path = UPLOAD_DIR / project_id

        (project_path / "images").mkdir(parents=True)
        (project_path / "annotations").mkdir()
        (project_path / "thumbnails").mkdir()
        (project_path / "export").mkdir()

        project = Project(
            id=project_id,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        self.save_project(project)

        return project

    def save_project(self, project: Project):

        metadata = UPLOAD_DIR / project.id / "metadata.json"

        with open(metadata, "w") as f:
            json.dump(
                project.model_dump(mode="json"),
                f,
                indent=4,
            )

    def list_projects(self):

        projects = []

        if not UPLOAD_DIR.exists():
            return projects

        for folder in UPLOAD_DIR.iterdir():

            metadata = folder / "metadata.json"

            if metadata.exists():

                with open(metadata) as f:

                    project = Project.model_validate(
                        json.load(f)
                    )

                    projects.append(project)

        return projects

    def get_project(self, project_id: str):

        metadata = UPLOAD_DIR / project_id / "metadata.json"

        if not metadata.exists():
            return None

        with open(metadata) as f:

            return Project.model_validate(
                json.load(f)
            )

    def delete_project(self, project_id: str):

        project_path = UPLOAD_DIR / project_id

        if not project_path.exists():
            return False

        shutil.rmtree(project_path)

        return True


manager = ProjectManager()