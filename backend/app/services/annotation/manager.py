import json
from pathlib import Path

from app.core.config import settings
from app.models.annotation import Annotation

UPLOAD_DIR = settings.UPLOAD_DIR


class AnnotationManager:

    def _annotation_file(self, project_id: str):
        return (
            UPLOAD_DIR
            / project_id
            / "annotations"
            / "annotations.json"
        )

    def list_annotations(self, project_id: str):

        file = self._annotation_file(project_id)

        if not file.exists():
            return []

        with open(file, "r") as f:
            data = json.load(f)

        return [
            Annotation(**item)
            for item in data
        ]

    def save_label(
        self,
        project_id: str,
        image_id: str,
        label: str,
    ):

        annotations = self.list_annotations(project_id)

        found = False

        for annotation in annotations:

            if annotation.image_id == image_id:

                annotation.label = label
                found = True
                break

        if not found:

            annotations.append(
                Annotation(
                    image_id=image_id,
                    label=label,
                )
            )

        file = self._annotation_file(project_id)

        file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with open(file, "w") as f:

            json.dump(
                [
                    item.model_dump(mode="json")
                    for item in annotations
                ],
                f,
                indent=4,
            )

        return True

    def delete_annotation(
        self,
        project_id: str,
        image_id: str,
    ):

        annotations = self.list_annotations(project_id)

        new_annotations = [
            item
            for item in annotations
            if item.image_id != image_id
        ]

        if len(new_annotations) == len(annotations):
            return False

        file = self._annotation_file(project_id)

        with open(file, "w") as f:

            json.dump(
                [
                    item.model_dump(mode="json")
                    for item in new_annotations
                ],
                f,
                indent=4,
            )

        return True


manager = AnnotationManager()