<div align="center">

# ForgoteLabeling

**A lightweight image annotation tool for building computer-vision datasets.**

Create a project, upload images, define labels, draw bounding boxes, and export straight to YOLO format — with everything stored locally as plain files you own.

[![License: MIT](https://img.shields.io/badge/License-MIT-000000.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB.svg)](https://react.dev/)

</div>

---

## Why ForgoteLabeling

Most annotation tools ask you to stand up a database, sign into an account, or push your images to someone else's cloud before you can draw a single box. ForgoteLabeling does none of that.

It runs entirely on your machine. Every project is a plain folder on disk — images, labels, and annotations are readable JSON you can inspect, back up, diff, or delete with ordinary tools. There is no database to migrate and no account to create. Start the two processes, open the browser, and label.

## Features

- **Projects** — create, browse, and delete isolated annotation projects.
- **Image upload** — multi-file upload with per-file validation (`.jpg`, `.jpeg`, `.png`, `.webp`).
- **Labels** — named, color-coded classes with a deterministic order that defines the YOLO class index.
- **Bounding-box editor** — draw, move, resize, select, and delete boxes on a canvas overlay.
- **Keyboard-first workflow** — `←` / `→` to move between images, `Delete` to remove the selected box.
- **Durable persistence** — annotations are written atomically and survive reloads and restarts.
- **YOLO export** — a zipped dataset with `images/`, `labels/`, and `classes.txt`, ready for training.
- **Honest reporting** — boxes that can't be exported are listed in `unlabeled.txt` rather than silently dropped.

## Tech Stack

| Layer    | Choice                              |
| -------- | ----------------------------------- |
| Frontend | React 19, Vite, React Router, Axios |
| Backend  | FastAPI, Pydantic v2, Uvicorn       |
| Storage  | JSON files on disk (no database)    |
| Export   | YOLO (normalized center format)     |
| Testing  | pytest + Starlette `TestClient`     |

## Requirements

- **Python** 3.10 or newer
- **Node.js** 18 or newer
- No database, no external services

## Getting Started

Clone the repository:

```bash
git clone https://github.com/nayonahmedjoy/ForgoteLabeling.git
cd ForgoteLabeling
```

### 1. Backend

The backend has no `__init__.py` files and relies on namespace packages, so it **must** be started from the `backend/` directory.

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install fastapi uvicorn pydantic pydantic-settings python-multipart pillow
uvicorn app.main:app --reload --port 8000
```

The API is now at **http://localhost:8000** (interactive docs at `/docs`).

### 2. Frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**.

> CORS is restricted to the Vite dev origins (`5173` and `4173` on `localhost` and `127.0.0.1`). If you serve the frontend from somewhere else, add that origin in `backend/app/core/config.py`.

## Usage

1. **Create a project** from the dashboard.
2. **Upload images** using the panel on the left.
3. **Add labels** on the right — each gets a color, and their order fixes the YOLO class index.
4. **Select a label**, then drag on the image to draw a box. Drag inside a box to move it, or grab a corner to resize.
5. **Navigate** with `←` / `→`; press `Delete` to remove the selected box.
6. **Export YOLO** from the top bar to download the finished dataset.

Annotations save as you work — there is no save button.

## Export Format

`Export YOLO` downloads a zip laid out as:

```
dataset/
├── images/          # your images, copied as-is
├── labels/          # one .txt per image, matched by filename stem
├── classes.txt      # class names, one per line, in index order
└── unlabeled.txt    # only written when some boxes could not be exported
```

Each line in a label file is a normalized, center-anchored box:

```
<class_index> <x_center> <y_center> <width> <height>
```

All four coordinates are floats in `0..1` relative to the image dimensions, which is the standard YOLO convention.

A box is omitted only when it has no label or points at a label that no longer exists. Those cases are counted per image in `unlabeled.txt`, so an incomplete dataset is always visible rather than silent. Images with no boxes still get an empty label file, as YOLO expects.

## Project Structure

```
ForgoteLabeling/
├── backend/
│   ├── app/
│   │   ├── api/routes.py        # every HTTP endpoint
│   │   ├── core/                # config, storage helpers, logging
│   │   ├── models/              # Pydantic models
│   │   ├── services/            # project / upload / label / annotation / export
│   │   └── main.py              # app setup, CORS, error handlers
│   ├── tests/                   # pytest regression suite
│   └── uploads/                 # project data (created at runtime)
├── frontend/
│   └── src/
│       ├── api/                 # thin API client per resource
│       ├── components/          # Navbar, ImageViewer, LabelPanel, dialogs…
│       └── pages/               # Dashboard, Project workspace
└── docs/                        # architecture and API notes
```

### How Storage Works

Each project is a UUID-named folder under `backend/uploads/`:

```
uploads/<project_id>/
├── metadata.json                # project record
├── images.json                  # image index (source of truth)
├── labels.json                  # label definitions, in order
├── annotations/annotations.json # every bounding box
└── images/                      # the uploaded files
```

Writes go through an atomic temp-file-and-replace helper, so an interrupted save can't leave a half-written file behind.

## API Overview

All responses use a consistent envelope: `{ success, message, data }` on success and `{ success, message, error }` on failure.

| Method   | Endpoint                                         | Purpose                 |
| -------- | ------------------------------------------------ | ----------------------- |
| `GET`    | `/health`                                        | Health check            |
| `POST`   | `/projects`                                      | Create a project        |
| `GET`    | `/projects`                                      | List projects           |
| `GET`    | `/projects/{pid}`                                | Get one project         |
| `DELETE` | `/projects/{pid}`                                | Delete a project        |
| `POST`   | `/projects/{pid}/images`                         | Upload images           |
| `GET`    | `/projects/{pid}/images`                         | List images             |
| `GET`    | `/projects/{pid}/images/{iid}/file`              | Serve an image          |
| `DELETE` | `/projects/{pid}/images/{iid}`                   | Delete an image         |
| `GET`    | `/projects/{pid}/labels`                         | List labels             |
| `POST`   | `/projects/{pid}/labels`                         | Create a label          |
| `DELETE` | `/projects/{pid}/labels/{lid}`                   | Delete an unused label  |
| `GET`    | `/projects/{pid}/images/{iid}/annotations`       | List boxes for an image |
| `POST`   | `/projects/{pid}/images/{iid}/annotations`       | Create a box            |
| `PUT`    | `/projects/{pid}/images/{iid}/annotations/{aid}` | Update a box            |
| `DELETE` | `/projects/{pid}/images/{iid}/annotations/{aid}` | Delete a box            |
| `GET`    | `/projects/{pid}/export/yolo`                    | Download the dataset    |

Deleting a label that annotations still reference returns `409` with the reference count, so boxes are never silently orphaned.

## Testing

```bash
cd backend
pip install pytest httpx
pytest
```

The suite runs against a temporary directory, so it never touches your real `uploads/` data. It covers the project/image/label/annotation lifecycle, persistence across restarts, and byte-level assertions on the YOLO export.

## Roadmap

Built and working today: the full manual annotation loop described above.

Under consideration:

- COCO and Pascal VOC export
- Zoom and pan in the editor
- Undo / redo
- Optional AI-assisted pre-labeling (the `/predict` endpoint is currently an honest `501` stub)

## Contributing

Issues and pull requests are welcome. Please run the backend test suite before opening a PR, and keep changes focused — small, reviewable diffs get merged faster.

## License

Released under the [MIT License](LICENSE).

## Developer

Built by **Noyon Ahmed**.

[LinkedIn](https://bd.linkedin.com/in/noyonahmedml) · [Facebook](https://www.facebook.com/noyonahmedml) · [Repository](https://github.com/nayonahmedjoy/ForgoteLabeling)
