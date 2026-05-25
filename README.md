# Markhub

[中文文档](README.zh-CN.md)

Markhub is a local data annotation platform for building and reviewing structured datasets for multimodal and computer-vision workflows. It is designed to support multiple annotation modes over time, including document layout analysis, bounding boxes, polygon segmentation, keypoints, and text transcription.

The current implementation has completed the document layout analysis annotation workflow. Users can upload a PDF, choose a prompt template and model endpoint, run analysis, then inspect pages, bounding boxes, block types, JSON payloads, and generated dataset records.

## What It Does

- Provides a dashboard and dataset view for annotation projects.
- Supports the completed PDF layout analysis annotation workflow.
- Analyzes PDF page layouts with a Qwen/OpenAI-compatible vision model.
- Renders PDF pages locally and maps model `0-1000` grounding coordinates back to preview-image pixels.
- Displays detected layout blocks such as document titles, paragraph titles, text, tables, figures, images, and footnotes.
- Lets users review, filter, delete, draw, and export annotation blocks.
- Stores local annotation jobs as reusable dataset records.
- Provides prompt-template editing for layout analysis and future annotation types.

## Product Areas

- **Dashboard**: shows real annotation jobs as projects.
- **Datasets**: summarizes completed and running annotation datasets.
- **Workspace**: currently supports PDF layout analysis, including upload, model configuration, analysis, and page-level review.
- **Settings**: manages Chinese UI preferences and prompt templates.

## Tech Stack

- **Frontend**: React 19, Vite, TypeScript, Tailwind CSS 4, Motion, Lucide icons.
- **Frontend server**: Express dev server with `/api` and `/jobs` proxying.
- **Backend**: Python HTTP server, PyMuPDF, Pillow, OpenAI Python SDK.
- **Runtime storage**: local files under `backend/jobs/` for generated page images and result JSON.

## Quick Start

From the project root:

```bash
./start.sh
```

Open:

```text
http://127.0.0.1:3000
```

The launcher starts both services:

- Frontend: `http://127.0.0.1:3000`
- Backend: `http://127.0.0.1:8787`

Use restart mode after backend changes:

```bash
./start.sh restart
```

## Configuration

Backend model and rendering settings can be provided through `backend/.env` or the workspace UI.

Useful variables:

```bash
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_API_KEY=
LLM_MODEL=
LLM_TIMEOUT=180
LAYOUT_RENDER_DPI=180
LAYOUT_MAX_PAGES=50
QWEN_RESIZE_PRESET=default
QWEN_RESIZED_WIDTH=1536
QWEN_RESIZED_HEIGHT=2176
```

Do not commit real `.env` files or API keys. Use `backend/.env.example` as the template.

## Common Commands

| Command | Description |
| --- | --- |
| `./start.sh` | Start backend and frontend together. |
| `./start.sh restart` | Stop existing Markhub listeners and start fresh services. |
| `cd frontend && npm run lint` | Run TypeScript checking. |
| `cd frontend && npm run build` | Build the frontend and server bundle. |
| `PYTHONPYCACHEPREFIX=/private/tmp/markhub_pycache python3 -m py_compile backend/server.py backend/features/layout_analysis/server.py` | Check backend Python syntax without writing cache files into the repo. |

## Architecture

```text
Markhub/
  backend/
    server.py              # backend entrypoint
    features/
      layout_analysis/     # completed PDF layout-analysis annotation service
    static/index.html      # legacy standalone preview UI
    jobs/                  # generated runtime results, ignored by Git
  frontend/
    server.ts              # Express/Vite server and backend proxy
    src/App.tsx            # app shell, dashboard routing, settings
    src/components/        # dashboard, datasets page, workspace UI
    src/types.ts           # shared frontend types
  start.sh                 # one-command local launcher
```

The frontend does not use React Router yet. Top-level view state is managed in `frontend/src/App.tsx`, and the completed layout-analysis annotation workflow lives mainly in `frontend/src/components/Workspace.tsx`.

Backend feature modules follow the standard in `docs/BACKEND_FEATURE_STANDARD.md`: each annotation capability should live in its own folder under `backend/features/`.

## API Overview

The Python backend exposes a small local API:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/config` | Runtime config and prompt templates. |
| `GET` | `/api/prompt-templates` | Prompt template list. |
| `POST` | `/api/prompt-templates/{id}` | Update an existing prompt template. |
| `POST` | `/api/analyze` | Upload a PDF and start analysis. |
| `GET` | `/api/jobs` | List analysis jobs. |
| `GET` | `/api/jobs/{job_id}/result` | Read a full job result. |
| `DELETE` | `/api/jobs/{job_id}` | Delete a local job. |
| `GET` | `/jobs/...` | Serve generated page images and assets. |

## Current Status

Markhub is intended to be a broader data annotation platform. At this stage, the completed workflow is PDF document layout analysis annotation. Bounding box, polygon, keypoints, and text transcription entry points are present as future annotation categories, but they are not implemented as full workflows yet.

For handoff notes and known caveats, see `AGENT_HANDOFF.md`.
