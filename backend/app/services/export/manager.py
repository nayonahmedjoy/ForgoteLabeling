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

        # Boxes that cannot be represented as a YOLO class (no label, or a
        # label id that no label owns) are recorded here so they are surfaced
        # explicitly in the export instead of silently vanishing.
        skipped: list[str] = []

        # YOLO pairs each image with its label file by a shared stem. Uploads
        # keep full filenames unique, but two images can still share a stem
        # (e.g. cat.jpg and cat.png both map to cat.txt), which would overwrite
        # one label file and silently drop its annotations. Track used stems and
        # disambiguate on collision so the image copy and its label file always
        # stay paired and no annotations are lost. In the common (no-collision)
        # case the export names are byte-identical to before.
        used_stems: set[str] = set()

        for image in images:
            src = Path(image.filepath)
            suffix = Path(image.filename).suffix

            stem = Path(image.filename).stem
            unique_stem = stem
            counter = 1
            while unique_stem in used_stems:
                unique_stem = f"{stem}_{counter}"
                counter += 1
            used_stems.add(unique_stem)

            if src.exists():
                shutil.copy2(src, images_out / f"{unique_stem}{suffix}")

            # One label file per image (empty file if no boxes).
            label_lines: list[str] = []
            skipped_here = 0
            for ann in annotations_by_image.get(image.id, []):
                cls = class_index.get(ann.label_id)
                if cls is None:
                    # Orphan/unlabeled box: keep it out of the YOLO label file
                    # (it has no valid class) but count it for the report.
                    skipped_here += 1
                    continue
                # Convert top-left normalized box -> YOLO center format.
                cx = ann.x + ann.width / 2
                cy = ann.y + ann.height / 2
                label_lines.append(
                    f"{cls} {cx:.6f} {cy:.6f} {ann.width:.6f} {ann.height:.6f}"
                )

            if skipped_here:
                skipped.append(f"{image.filename}\t{skipped_here}")

            label_name = unique_stem + ".txt"
            (labels_out / label_name).write_text(
                "\n".join(label_lines) + ("\n" if label_lines else ""),
                encoding="utf-8",
            )

        # Only write the report when something was skipped, so a fully-labeled
        # dataset still exports a pristine, standard YOLO structure.
        if skipped:
            total = sum(int(line.split("\t")[1]) for line in skipped)
            (build_dir / "unlabeled.txt").write_text(
                "# Annotations omitted from this YOLO export because they have "
                "no label or reference a label that no longer exists.\n"
                "# These boxes were NOT dropped from the project; assign a "
                "valid label to include them.\n"
                "# Format: <image_filename><TAB><skipped_count>\n"
                + "\n".join(skipped)
                + f"\n# total_skipped\t{total}\n",
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
