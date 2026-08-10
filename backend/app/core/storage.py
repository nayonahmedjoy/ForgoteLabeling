"""Centralized filesystem layout and JSON helpers.

Every service derives its paths from here so storage is consistent and
independent of the current working directory. The layout for one project:

    uploads/<project_id>/
        metadata.json          project metadata
        images.json            persistent image index (source of truth)
        labels.json            project labels / classes
        images/                image files
        thumbnails/            reserved for future thumbnails
        export/                generated export artifacts
        annotations/
            annotations.json   bounding-box annotations for the project
"""

import json
import tempfile
from pathlib import Path
from typing import Any

from app.core.config import settings


def project_dir(project_id: str) -> Path:
    return settings.UPLOAD_DIR / project_id


def images_dir(project_id: str) -> Path:
    return project_dir(project_id) / "images"


def thumbnails_dir(project_id: str) -> Path:
    return project_dir(project_id) / "thumbnails"


def export_dir(project_id: str) -> Path:
    return project_dir(project_id) / "export"


def annotations_dir(project_id: str) -> Path:
    return project_dir(project_id) / "annotations"


def metadata_path(project_id: str) -> Path:
    return project_dir(project_id) / "metadata.json"


def images_index_path(project_id: str) -> Path:
    return project_dir(project_id) / "images.json"


def labels_path(project_id: str) -> Path:
    return project_dir(project_id) / "labels.json"


def annotations_path(project_id: str) -> Path:
    return annotations_dir(project_id) / "annotations.json"


def read_json(path: Path, default: Any) -> Any:
    """Read JSON, returning ``default`` when the file is missing or corrupt."""
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def write_json(path: Path, data: Any) -> None:
    """Atomically write JSON, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write to a temp file then replace, so a crash mid-write cannot
    # leave a half-written index behind.
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with open(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
