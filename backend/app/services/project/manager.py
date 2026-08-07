import json
import shutil
import uuid

from datetime import datetime
from pathlib import Path

from app.core.config import settings
from app.models.project import Project
from datetime import datetime, UTC


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

        with open(project_path / "metadata.json", "w") as f:
            json.dump(
                project.model_dump(mode="json"),
                f,
                indent=4,
            )

        return project

    def list_projects(self):

        projects = []

        if not UPLOAD_DIR.exists():
            return projects

        for folder in UPLOAD_DIR.iterdir():

            metadata = folder / "metadata.json"

            if metadata.exists():

                with open(metadata) as f:
                    projects.append(json.load(f))

        return projects

    def get_project(self, project_id: str):

        metadata = UPLOAD_DIR / project_id / "metadata.json"

        if not metadata.exists():
            return None

        with open(metadata) as f:
            return json.load(f)

    def delete_project(self, project_id: str):

        project_path = UPLOAD_DIR / project_id

        if not project_path.exists():
            return False

        shutil.rmtree(project_path)

        return True


manager = ProjectManager()