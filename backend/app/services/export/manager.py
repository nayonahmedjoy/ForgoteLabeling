import shutil
import zipfile
from pathlib import Path

from app.core import storage
from app.models.annotation import Annotation
from app.models.image import Image
from app.models.label import Label


class ExportManager:
    """Generates dataset exports from persisted annotations."""

    def _yolo_class_index(self, labels: list[Label]) -> dict[str, int]:
        """Map label id -> class index (order = labels.json order)."""
        return {label.id: idx for idx, label in enumerate(labels)}

    def export_yolo(
        self,
        project_id: str,
        images: list[Image],
        annotations: list[Annotation],
        labels: list[Label],
    ) -> Path:
        """Build a YOLO-format dataset and return the path to a zip archive.

        Archive layout:
            dataset/
                images/
                labels/
                classes.txt
        """
        export_root = storage.export_dir(project_id)
        build_dir = export_root / "dataset"

        # Start clean so stale files never leak into a new export.
        if build_dir.exists():
            shutil.rmtree(build_dir)
        images_out = build_dir / "images"
        labels_out = build_dir / "labels"
        images_out.mkdir(parents=True, exist_ok=True)
        labels_out.mkdir(parents=True, exist_ok=True)

        class_index = self._yolo_class_index(labels)

        # classes.txt (one class name per line, ordered by index).
        classes_file = build_dir / "classes.txt"
        classes_file.write_text(
            "\n".join(label.name for label in labels) + ("\n" if labels else ""),
            encoding="utf-8",
        )

        annotations_by_image: dict[str, list[Annotation]] = {}
        for ann in annotations:
            annotations_by_image.setdefault(ann.image_id, []).append(ann)

        for image in images:
            src = Path(image.filepath)
            if src.exists():
                shutil.copy2(src, images_out / image.filename)

            # One label file per image (empty file if no boxes).
            label_lines: list[str] = []
            for ann in annotations_by_image.get(image.id, []):
                cls = class_index.get(ann.label_id)
                if cls is None:
                    continue  # skip boxes whose label was deleted
                # Convert top-left normalized box -> YOLO center format.
                cx = ann.x + ann.width / 2
                cy = ann.y + ann.height / 2
                label_lines.append(
                    f"{cls} {cx:.6f} {cy:.6f} {ann.width:.6f} {ann.height:.6f}"
                )

            label_name = Path(image.filename).stem + ".txt"
            (labels_out / label_name).write_text(
                "\n".join(label_lines) + ("\n" if label_lines else ""),
                encoding="utf-8",
            )

        zip_path = export_root / "dataset_yolo.zip"
        if zip_path.exists():
            zip_path.unlink()

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in build_dir.rglob("*"):
                if file.is_file():
                    zf.write(file, file.relative_to(export_root))

        return zip_path


manager = ExportManager()
