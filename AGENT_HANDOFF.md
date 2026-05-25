# Markhub Agent Handoff

Last updated: 2026-05-26

This document is for the next agent or engineer taking over Markhub. It summarizes the current project shape, important behavior, known decisions, and safe next steps.

## Project Overview

Markhub is a local document layout annotation and analysis tool. The current implementation is a React/Vite frontend backed by a Python HTTP server. The main supported workflow is PDF layout analysis using a Qwen/OpenAI-compatible vision model, then reviewing and editing detected layout blocks in the annotation workspace.

The product UI currently has three important areas:

- Main dashboard: shows real backend analysis jobs as datasets/projects.
- Dataset page: prototype-style light page, now driven by real `/api/jobs` data.
- Annotation workspace: uploads PDFs, runs backend layout analysis, shows pages, blocks, JSON, and prompt template selection.

## Directory Structure

```text
Markhub/
  start.sh                     # one-command launcher; supports ./start.sh restart
  AGENT_HANDOFF.md             # this handoff document
  README.md
  backend/
    server.py                  # Python backend, API routes, PDF rendering, LLM calls
    requirements.txt
    .env                       # local model/API/runtime config; do not commit secrets
    .env.example
    jobs/                      # generated analysis job results and page images
    prompt_templates.json      # created after saving prompt templates from Settings
    static/index.html          # legacy standalone backend UI
  frontend/
    server.ts                  # Express dev server, proxies /api and /jobs to backend
    src/App.tsx                # top-level routing/state, settings, prompt editor
    src/types.ts               # shared frontend types
    src/components/Dashboard.tsx
    src/components/DatasetsPage.tsx
    src/components/Workspace.tsx
    src/index.css              # Tailwind v4 theme tokens and global styling
```

## How To Run

From the project root:

```bash
./start.sh
```

Open:

```text
http://127.0.0.1:3000
```

When backend code changes, prefer:

```bash
./start.sh restart
```

The restart mode tries to stop existing listeners on ports `3000` and `8787`, then starts fresh services. This matters because `./start.sh` normally reuses already-running services when they respond successfully.

Useful environment variables:

```bash
BACKEND_PORT=8787
PORT=3000
PYTHON_BIN=/Users/lishixin/miniconda3/bin/python
MARKHUB_BACKEND_URL=http://127.0.0.1:8787
```

## Verification Commands

Frontend:

```bash
cd frontend
npm run lint
npm run build
```

Backend syntax check:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/markhub_pycache python3 -m py_compile backend/server.py
```

Backend health/config:

```bash
curl -s http://127.0.0.1:8787/api/config
curl -s http://127.0.0.1:8787/api/jobs
```

## Backend API Surface

Implemented in `backend/server.py`, mostly inside `LayoutAnalyzerHandler`.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/config` | Runtime config plus prompt templates. |
| `GET` | `/api/prompt-templates` | Prompt template list with category and prompt content. |
| `POST` | `/api/prompt-templates/{id}` | Save an existing prompt template. Persists to `backend/prompt_templates.json`. |
| `POST` | `/api/analyze` | Multipart PDF upload. Starts a layout analysis job. |
| `GET` | `/api/jobs` | Lists completed/running backend jobs for dashboard and datasets page. |
| `GET` | `/api/jobs/{job_id}/result` | Full job payload with pages and blocks. |
| `DELETE` | `/api/jobs/{job_id}` | Deletes an analysis job directory. |
| `GET` | `/jobs/...` | Serves generated page images and job assets. |

Backend job summaries include `first_page_url` in code. If the currently running backend process was started before this field was added, restart the backend.

## Frontend Routing Model

There is no React Router. `frontend/src/App.tsx` controls view state with:

- `activeScreen`: `dashboard` or `workspace`
- `activeHeaderTab`: `projects`, `datasets`, `analytics`, `team`, `settings`
- `selectedProject`: current project/job opened in the workspace

Important flow:

- Dashboard project card click calls `handleSelectProject(project)` and opens `Workspace`.
- Dataset tab renders `DatasetsPage` and passes real `jobs` from `/api/jobs`.
- Settings tab renders `SettingsPage`, which contains `PromptTemplateManager`.

## Current Feature State

### Supported Annotation Type Entry Points

The right dashboard panel in `Dashboard.tsx` is now interactive:

- `Layout Analysis` is marked live and opens the annotation workspace.
- `Bounding Box`, `Polygon Segment`, `Keypoints Picker`, and `Text Transcription` alert `该标注功能未上线`.

The click behavior is wired through `onOpenAnnotationFeature` from `App.tsx`.

### Real Datasets

The app no longer uses static dataset cards for the dashboard or dataset page.

- `App.tsx` loads `/api/jobs` in `loadRealDatasets()`.
- `mapJobToProject()` converts backend jobs into dashboard projects.
- `DatasetsPage.tsx` maps backend jobs into dataset cards and KPIs.

The current KPI meanings are:

- Total Pages: sum of `page_count`
- Layout Blocks: sum of `block_count`
- Datasets: number of backend jobs

### Prompt Templates

Prompt templates are categorized by annotation feature. Current categories are:

- `layout`
- `bounding_box`
- `polygon`
- `keypoints`
- `text_transcription`

The existing `默认模板 1` belongs to `layout`. It is defined in `backend/server.py` and can be edited in Settings. Saving writes `backend/prompt_templates.json`, which is loaded at backend startup.

Frontend types live in `frontend/src/types.ts`:

- `AnnotationFeature`
- `PromptTemplateOption`

Settings editor lives in `frontend/src/App.tsx` as `PromptTemplateManager`.

Workspace template selection lives in `frontend/src/components/Workspace.tsx`. It still fetches templates from `/api/config`.

## Styling And UX Constraints

The app currently has two visual styles:

- Main dashboard/workspace/settings: dark industrial UI, square corners, serif italic headings, subdued borders.
- Dataset page: light Airy Industrial style imported from the provided prototype, using Tailwind v4 tokens in `frontend/src/index.css`.

When adding UI:

- Keep dashboard/workspace additions visually consistent with the dark UI.
- Keep dataset page additions on the tokenized light design system.
- Avoid introducing a third visual language.
- Use actual buttons for clickable UI; do not use bare clickable divs for new controls.

## Important Implementation Notes

- `frontend/server.ts` proxies `/api` and `/jobs` to `MARKHUB_BACKEND_URL`.
- Backend stores generated job data under `backend/jobs/{model_dir}/{job_id}`.
- Legacy jobs may be directly under `backend/jobs/{job_id}`; backend has compatibility lookup logic.
- `backend/.env` may contain API credentials. Do not print or commit secrets.
- `start.sh` reuses running services by default. Use `restart` when backend API changes are not reflected.
- This project may not be a Git repository in the local workspace. Do not rely on Git history being available.

## Common Next Tasks

If continuing development, likely next steps are:

1. Move `SettingsPage` and `PromptTemplateManager` out of `App.tsx` into separate components once they grow further.
2. Add create/delete prompt-template support, not just edit existing templates.
3. Add real implementations for `bounding_box`, `polygon`, `keypoints`, and `text_transcription`, or hide them behind a clearer beta/soon state.
4. Make the dataset cards link directly into the corresponding workspace job from the dataset page.
5. Add browser-level UI tests for the three core flows: open Layout workspace, edit prompt template, load real dataset job.

## Known Caveats

- Saving prompt templates requires a backend process that includes the `/api/prompt-templates/{id}` route. Restart backend after pulling these changes.
- `prompt_templates.json` is runtime-generated. If absent, the backend falls back to the built-in `默认模板 1` layout prompt.
- The prompt editor currently allows editing existing templates only. New template creation is intentionally not implemented yet.
- Some UI text remains English because the original prototype and dashboard used English copy. The app-level language is `zh-CN`, but not every label has been translated.

