"""Regression test: YOLO export golden output.

This is the most valuable safety net in the suite: it pins the exact bytes of
the exported YOLO dataset so any change to the export math or archive layout is
caught immediately.

Golden math (top-left normalized box -> YOLO center format):
    box   = {x: 0.1, y: 0.2, width: 0.4, height: 0.3}
    cx    = x + width/2  = 0.1 + 0.20 = 0.30
    cy    = y + height/2 = 0.2 + 0.15 = 0.35
    line  = "0 0.300000 0.350000 0.400000 0.300000"   (class 0 = "car")
    classes.txt = "car\n"

Archive layout (arcnames relative to the export root):
    dataset/classes.txt
    dataset/images/<stored image filename>
    dataset/labels/<image stem>.txt
"""

import io
import zipfile

from conftest import make_annotation, make_label, make_project, upload_png

BOX = {"x": 0.1, "y": 0.2, "width": 0.4, "height": 0.3}


def _open_export_zip(client, project_id):
    resp = client.get(f"/projects/{project_id}/export/yolo")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/zip"
    return zipfile.ZipFile(io.BytesIO(resp.content))


def _read_text(zf, name):
    """Read a text member and normalize newlines to LF.

    The export writes files with Python text-mode ``write_text``, so on Windows
    each ``\\n`` becomes ``\\r\\n``. Normalizing CRLF -> LF here makes the golden
    assertions newline-independent while still verifying exact class ordering
    and content byte-for-byte otherwise.
    """
    return zf.read(name).decode("utf-8").replace("\r\n", "\n")


def test_yolo_export_golden_output(client, png_bytes):
    project = make_project(client, "Golden")
    image = upload_png(client, project["id"], "car.png", png_bytes)
    car = make_label(client, project["id"], "car")
    make_annotation(client, project["id"], image["id"], BOX, label=car)

    stem = image["filename"].rsplit(".", 1)[0]  # stored filename stem

    with _open_export_zip(client, project["id"]) as zf:
        names = set(zf.namelist())
        assert "dataset/classes.txt" in names
        assert f"dataset/images/{image['filename']}" in names
        assert f"dataset/labels/{stem}.txt" in names

        # classes.txt: one class name per line, newline-terminated.
        classes = _read_text(zf, "dataset/classes.txt")
        assert classes == "car\n"

        # The label file holds the exact center-format line for class 0.
        label_txt = _read_text(zf, f"dataset/labels/{stem}.txt")
        assert label_txt == "0 0.300000 0.350000 0.400000 0.300000\n"


def test_yolo_export_multiple_labels_indexed_by_order(client, png_bytes):
    project = make_project(client, "MultiLabel")
    image = upload_png(client, project["id"], "scene.png", png_bytes)
    # Label order defines the class index: car=0, person=1.
    car = make_label(client, project["id"], "car")
    person = make_label(client, project["id"], "person")

    make_annotation(
        client, project["id"], image["id"],
        {"x": 0.0, "y": 0.0, "width": 0.5, "height": 0.5}, label=car,
    )
    make_annotation(
        client, project["id"], image["id"],
        {"x": 0.5, "y": 0.5, "width": 0.4, "height": 0.4}, label=person,
    )

    stem = image["filename"].rsplit(".", 1)[0]

    with _open_export_zip(client, project["id"]) as zf:
        classes = _read_text(zf, "dataset/classes.txt")
        assert classes == "car\nperson\n"

        lines = _read_text(zf, f"dataset/labels/{stem}.txt").splitlines()
        # car box: cx=0.25, cy=0.25, w=0.5, h=0.5  -> class 0
        # person box: cx=0.70, cy=0.70, w=0.4, h=0.4 -> class 1
        assert lines[0] == "0 0.250000 0.250000 0.500000 0.500000"
        assert lines[1] == "1 0.700000 0.700000 0.400000 0.400000"


def test_yolo_export_skips_box_with_deleted_label(client, png_bytes):
    """Current behavior: a box whose label_id is not in labels.json is skipped.

    This documents the *existing* orphan-handling in export (M1 will revisit
    whether label deletion should be blocked). Here we simulate an orphan by
    giving the annotation a label_id that no label owns.
    """
    project = make_project(client, "Orphan")
    image = upload_png(client, project["id"], "car.png", png_bytes)
    make_label(client, project["id"], "car")

    # Annotation references a non-existent label id -> not in class_index.
    client.post(
        f"/projects/{project['id']}/images/{image['id']}/annotations",
        json={**BOX, "label_id": "ghost-label", "label": "ghost"},
    )

    stem = image["filename"].rsplit(".", 1)[0]
    with _open_export_zip(client, project["id"]) as zf:
        label_txt = _read_text(zf, f"dataset/labels/{stem}.txt")
        # The orphan box is skipped -> empty label file.
        assert label_txt == ""


def test_yolo_export_unknown_project_returns_404(client):
    assert client.get("/projects/nope/export/yolo").status_code == 404
