"""Storage backend abstraction.

v1.0.0 persisted everything as JSON + image files on the local filesystem via
the flat helpers in :mod:`app.core.storage`. For the public web deployment the
host (Render free tier) has only an *ephemeral* disk, so persistent data must
live in external object storage (Supabase Storage).

To support both without duplicating the manager/M2 logic, all persistence now
goes through a small ``StorageBackend`` interface with two concerns:

  * **JSON documents** — the four per-project files (``metadata``/``images``/
    ``labels``/``annotations``) that the managers already read and write.
  * **image blobs** — the raw uploaded image bytes.

``LocalStorageBackend`` simply delegates to the existing
:mod:`app.core.storage` functions, so local/self-hosted behavior is byte-for
-byte identical to v1.0.0 (and the whole test suite, which never sets
``STORAGE_BACKEND=cloud``, exercises exactly this path).

``SupabaseStorageBackend`` maps the same logical keys onto Supabase Storage
objects over its REST API. The service-role key is used server-side only and is
never exposed to the browser.

Keep this abstraction deliberately small: it is a persistence seam, not a
general-purpose VFS.
"""

from __future__ import annotations

import json
import mimetypes
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from fastapi.responses import FileResponse, Response, StreamingResponse

from app.core import storage
from app.core.config import settings

# Logical JSON document names -> local path helper in app.core.storage.
_DOC_PATHS = {
    "metadata": storage.metadata_path,
    "images": storage.images_index_path,
    "labels": storage.labels_path,
    "annotations": storage.annotations_path,
}
# Object-storage suffix for each document (cloud keys: <pid>/<suffix>).
_DOC_KEYS = {
    "metadata": "metadata.json",
    "images": "images.json",
    "labels": "labels.json",
    "annotations": "annotations.json",
}


def _guess_media_type(filename: str) -> str:
    media_type, _ = mimetypes.guess_type(filename)
    return media_type or "application/octet-stream"


class StorageBackend(ABC):
    """Persistence seam shared by both the local and cloud backends."""

    # --- project lifecycle ---------------------------------------------------
    @abstractmethod
    def init_project(self, project_id: str) -> None:
        """Create the container for a new project (dirs locally; no-op cloud)."""

    @abstractmethod
    def list_project_ids(self) -> list[str]:
        """Return the ids of all persisted projects."""

    @abstractmethod
    def delete_project(self, project_id: str) -> bool:
        """Delete a project and everything under it. False if it was absent."""

    # --- JSON documents ------------------------------------------------------
    @abstractmethod
    def read_doc(self, project_id: str, doc: str, default: Any) -> Any:
        """Read one JSON document, returning ``default`` when missing/corrupt."""

    @abstractmethod
    def write_doc(self, project_id: str, doc: str, data: Any) -> None:
        """Write one JSON document (atomically where the medium allows)."""

    # --- image blobs ---------------------------------------------------------
    @abstractmethod
    def image_exists(self, project_id: str, stored_name: str) -> bool:
        ...

    @abstractmethod
    def write_image(self, project_id: str, stored_name: str, data: bytes) -> str:
        """Persist image bytes; return the reference stored on ``Image.filepath``."""

    @abstractmethod
    def read_image_bytes(self, project_id: str, stored_name: str) -> bytes | None:
        ...

    @abstractmethod
    def delete_image(self, project_id: str, stored_name: str) -> None:
        ...

    @abstractmethod
    def image_response(self, project_id: str, image) -> Response:
        """Build the HTTP response that streams an image to the browser."""


class LocalStorageBackend(StorageBackend):
    """Filesystem persistence — identical behavior to v1.0.0.

    Every method delegates to :mod:`app.core.storage`, which derives paths from
    ``settings.UPLOAD_DIR`` *at call time*. That keeps the test suite's
    ``tmp_path`` monkeypatch working and means nothing here caches a root.
    """

    def init_project(self, project_id: str) -> None:
        storage.images_dir(project_id).mkdir(parents=True, exist_ok=True)
        storage.annotations_dir(project_id).mkdir(parents=True, exist_ok=True)
        storage.thumbnails_dir(project_id).mkdir(parents=True, exist_ok=True)
        storage.export_dir(project_id).mkdir(parents=True, exist_ok=True)

    def list_project_ids(self) -> list[str]:
        root = settings.UPLOAD_DIR
        if not root.exists():
            return []
        return [folder.name for folder in root.iterdir() if folder.is_dir()]

    def delete_project(self, project_id: str) -> bool:
        import shutil

        if not storage.is_safe_id(project_id):
            return False
        project_path = storage.project_dir(project_id)
        if not project_path.exists():
            return False
        shutil.rmtree(project_path)
        return True

    def read_doc(self, project_id: str, doc: str, default: Any) -> Any:
        return storage.read_json(_DOC_PATHS[doc](project_id), default)

    def write_doc(self, project_id: str, doc: str, data: Any) -> None:
        storage.write_json(_DOC_PATHS[doc](project_id), data)

    def image_exists(self, project_id: str, stored_name: str) -> bool:
        return (storage.images_dir(project_id) / stored_name).exists()

    def write_image(self, project_id: str, stored_name: str, data: bytes) -> str:
        images_dir = storage.images_dir(project_id)
        images_dir.mkdir(parents=True, exist_ok=True)
        file_path = images_dir / stored_name
        with open(file_path, "wb") as buffer:
            buffer.write(data)
        return str(file_path)

    def read_image_bytes(self, project_id: str, stored_name: str) -> bytes | None:
        path = storage.images_dir(project_id) / stored_name
        if not path.exists():
            return None
        return path.read_bytes()

    def delete_image(self, project_id: str, stored_name: str) -> None:
        path = storage.images_dir(project_id) / stored_name
        if path.exists():
            path.unlink()

    def image_response(self, project_id: str, image) -> Response:
        # Preserve v1.0.0 behavior exactly: stream straight from the file path
        # with a guessed media type and the original download filename.
        return FileResponse(
            path=image.filepath,
            media_type=_guess_media_type(image.filename),
            filename=image.original_filename or image.filename,
        )


class SupabaseStorageBackend(StorageBackend):
    """Persistence on Supabase Storage via its REST API.

    Object key layout mirrors the local folder layout:

        <project_id>/metadata.json
        <project_id>/images.json
        <project_id>/labels.json
        <project_id>/annotations.json
        <project_id>/images/<stored_name>

    The service-role key authenticates every call and is kept server-side.
    """

    def __init__(self) -> None:
        if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
            raise RuntimeError(
                "STORAGE_BACKEND=cloud requires SUPABASE_URL and "
                "SUPABASE_SERVICE_KEY to be set."
            )
        self._base = settings.SUPABASE_URL.rstrip("/")
        self._bucket = settings.SUPABASE_BUCKET
        self._key = settings.SUPABASE_SERVICE_KEY

    # -- low-level REST helpers ----------------------------------------------
    def _client(self):
        # Imported lazily so the local backend never requires httpx installed.
        import httpx

        return httpx.Client(
            headers={
                "Authorization": f"Bearer {self._key}",
                "apikey": self._key,
            },
            timeout=30.0,
        )

    def _object_url(self, key: str) -> str:
        return f"{self._base}/storage/v1/object/{self._bucket}/{key}"

    def _get_bytes(self, key: str) -> bytes | None:
        with self._client() as client:
            resp = client.get(self._object_url(key))
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.content

    def _put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        # x-upsert lets writes overwrite an existing object (documents change).
        with self._client() as client:
            resp = client.post(
                self._object_url(key),
                content=data,
                headers={"Content-Type": content_type, "x-upsert": "true"},
            )
        resp.raise_for_status()

    def _delete_keys(self, keys: list[str]) -> int:
        """Permanently delete the given object keys. Returns the count removed."""
        if not keys:
            return 0
        with self._client() as client:
            resp = client.request(
                "DELETE",
                f"{self._base}/storage/v1/object/{self._bucket}",
                json={"prefixes": keys},
            )
        resp.raise_for_status()
        return len(keys)

    def _list_keys(self, prefix: str) -> list[str]:
        """Recursively list object keys under ``prefix`` (Supabase list API)."""
        found: list[str] = []
        stack = [prefix.rstrip("/")]
        with self._client() as client:
            while stack:
                folder = stack.pop()
                resp = client.post(
                    f"{self._base}/storage/v1/object/list/{self._bucket}",
                    json={
                        "prefix": folder,
                        "limit": 1000,
                        "offset": 0,
                    },
                )
                resp.raise_for_status()
                for entry in resp.json():
                    name = entry.get("name")
                    if not name:
                        continue
                    child = f"{folder}/{name}" if folder else name
                    # A null id marks a nested "folder" placeholder in Supabase.
                    if entry.get("id") is None:
                        stack.append(child)
                    else:
                        found.append(child)
        return found

    # -- StorageBackend -------------------------------------------------------
    def init_project(self, project_id: str) -> None:
        # Object storage has no directories to create; keys appear on write.
        return None

    def list_project_ids(self) -> list[str]:
        ids: list[str] = []
        with self._client() as client:
            resp = client.post(
                f"{self._base}/storage/v1/object/list/{self._bucket}",
                json={"prefix": "", "limit": 1000, "offset": 0},
            )
            resp.raise_for_status()
            for entry in resp.json():
                # Top-level folders (id is null) are project ids.
                if entry.get("id") is None and entry.get("name"):
                    ids.append(entry["name"])
        return ids

    def delete_project(self, project_id: str) -> bool:
        """Permanently delete every object belonging to one project.

        Two properties matter here, because this is what the TTL sweep calls:

        * **Scoped.** Only keys under ``<project_id>/`` are deleted. The listing
          is filtered against that exact prefix so a neighbouring project whose
          id merely starts with the same characters can never be caught.
        * **Ordered.** Image blobs and index documents go first, ``metadata.json``
          last. Metadata is what makes a project discoverable, so if a batch
          fails midway the project remains listed (and expired), and the next
          sweep retries it instead of leaving unreachable objects behind.
        """
        if not storage.is_safe_id(project_id):
            return False

        prefix = f"{project_id}/"
        keys = [key for key in self._list_keys(project_id) if key.startswith(prefix)]
        if not keys:
            return False

        metadata_key = f"{prefix}{_DOC_KEYS['metadata']}"
        payload_keys = [key for key in keys if key != metadata_key]

        self._delete_keys(payload_keys)
        if metadata_key in keys:
            self._delete_keys([metadata_key])
        return True

    def read_doc(self, project_id: str, doc: str, default: Any) -> Any:
        raw = self._get_bytes(f"{project_id}/{_DOC_KEYS[doc]}")
        if raw is None:
            return default
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return default

    def write_doc(self, project_id: str, doc: str, data: Any) -> None:
        payload = json.dumps(data, indent=4).encode("utf-8")
        self._put_bytes(
            f"{project_id}/{_DOC_KEYS[doc]}", payload, "application/json"
        )

    def image_exists(self, project_id: str, stored_name: str) -> bool:
        return self._get_bytes(f"{project_id}/images/{stored_name}") is not None

    def write_image(self, project_id: str, stored_name: str, data: bytes) -> str:
        key = f"{project_id}/images/{stored_name}"
        self._put_bytes(key, data, _guess_media_type(stored_name))
        return key

    def read_image_bytes(self, project_id: str, stored_name: str) -> bytes | None:
        return self._get_bytes(f"{project_id}/images/{stored_name}")

    def delete_image(self, project_id: str, stored_name: str) -> None:
        with self._client() as client:
            client.request(
                "DELETE",
                f"{self._base}/storage/v1/object/{self._bucket}",
                json={"prefixes": [f"{project_id}/images/{stored_name}"]},
            )

    def image_response(self, project_id: str, image) -> Response:
        data = self.read_image_bytes(project_id, image.filename)
        if data is None:
            data = b""
        filename = image.original_filename or image.filename
        return StreamingResponse(
            iter([data]),
            media_type=_guess_media_type(image.filename),
            headers={
                "Content-Disposition": f'inline; filename="{filename}"',
            },
        )


_backend: StorageBackend | None = None


def get_backend() -> StorageBackend:
    """Return the process-wide storage backend, selected by STORAGE_BACKEND.

    Cached after first use. Tests import managers without setting the env var,
    so this always resolves to :class:`LocalStorageBackend` there.
    """
    global _backend
    if _backend is None:
        _backend = SupabaseStorageBackend() if settings.is_cloud else LocalStorageBackend()
    return _backend
