# Markhub Frontend

React/Vite annotation workspace for Markhub. The page keeps the imported dashboard visual style while using the Python backend API for PDF layout analysis.

## Development

Start the Python backend first:

```bash
cd ../backend
/Users/lishixin/miniconda3/bin/python server.py --port 8787
```

Then start the frontend:

```bash
npm install
npm run dev
```

The frontend server runs on `http://localhost:3000` and proxies `/api/*` and `/jobs/*` to `http://127.0.0.1:8787` by default. Override this with `MARKHUB_BACKEND_URL` when needed.

## Backend-aligned Features

- PDF upload through backend `POST /api/analyze` multipart form data.
- Model endpoint, API key, timeout, render DPI, max pages, Qwen resize, and prompt template controls.
- Backend job polling through `GET /api/jobs/{job_id}/result`.
- History loading and deletion through `GET /api/jobs` and `DELETE /api/jobs/{job_id}`.
- Real backend block types: `doc_title`, `paragraph_title`, `text`, `table_of_contents`, `table`, `figure_title`, `image`, and `vision_footnote`.
