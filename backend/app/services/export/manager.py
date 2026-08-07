import csv
from pathlib import Path

from app.core.config import settings

UPLOAD_DIR = settings.UPLOAD_DIR
EXPORT_DIR = Path("exports")


class ExportManager:

    def export_csv(
        self,
        project_id: str,
        annotations: list,
        images: list,
    ):

        project_export = EXPORT_DIR / project_id
        project_export.mkdir(
            parents=True,
            exist_ok=True,
        )

        csv_file = project_export / "labels.csv"

        image_map = {
            image.id: image.filename
            for image in images
        }

        with open(
            csv_file,
            "w",
            newline="",
            encoding="utf-8",
        ) as file:

            writer = csv.writer(file)

            writer.writerow(
                [
                    "filename",
                    "label",
                ]
            )

            for item in annotations:

                writer.writerow(
                    [
                        image_map.get(
                            item.image_id,
                            "",
                        ),
                        item.label,
                    ]
                )

        return csv_file


manager = ExportManager()