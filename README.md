# Meta-Data-Tag-Generator

**Document Meta-Tagging API v2.0** — a full-stack application that extracts text from **PDF** documents (digital or scanned), optionally enriches it with **LLM-based entity extraction**, and generates **metadata tags** via **OpenRouter**. Tags are intended to improve **search and discovery** (for example, indexing pipelines), with support for **exclusion lists** so repeated or generic terms can be suppressed.

The product has two main experiences:

- **Single document**: upload a PDF or supply a public **URL**, configure the model and extraction settings, and receive tags plus diagnostics (extraction method, timing, text preview).
- **Batch processing**: many documents (typically from **CSV** or the in-app grid), each resolved from **`url`**, **`s3`**, or **`local`** paths, with **background jobs**, **Redis-backed progress**, and a **WebSocket observer** (or REST polling) for the UI.

---

## Architecture (high level)

| Layer | Technology | Role |
|--------|------------|------|
| **Frontend** | Next.js (App Router), TypeScript, Tailwind-style UI | Pages: home (`/`), batch (`/batch`), auth (`/login`, `/register`), dashboard/history/documents. Uses **Zustand** for batch state and auth tokens (`frontend/lib/batchStore.ts`, auth store). |
| **Backend** | FastAPI (`backend/app/main.py`) | REST + WebSocket; orchestrates PDF I/O, OCR, tagging, persistence. |
| **Database** | PostgreSQL | Users, refresh tokens, **jobs**, **documents** (see `backend/app/database/schema.sql`). Initialized via Docker mount on first Postgres startup. |
| **Cache / jobs** | Redis | Per-job **hash state**, **result list**, **pub/sub** progress channel, **cancel/pause/resume** commands, **24h TTL** (`backend/app/services/redis_client.py`). |
| **Object storage** | MinIO (S3-compatible) | Optional uploads/exports via `StorageService` (`backend/app/services/storage_service.py`); compose wires MinIO for local stacks. |
| **Runtime** | Docker Compose | `docker-compose.yml`: `postgres`, `redis`, `minio`, `backend`, `frontend`; optional `nginx` profile for reverse proxy. |

**API surface** is mounted under `/api/*` (see router includes in `backend/app/main.py`). OpenAPI title/version match **v2.0.0**.

```text
Browser  →  Next.js  →  FastAPI
                ↓           ↓
            Bearer JWT   PostgreSQL (users, jobs, documents)
                           Redis (job state + pub/sub)
                           MinIO (optional files)
                           OpenRouter (tagging + entity LLM calls)
                           Tesseract / EasyOCR / PDF libraries (local)
```

---

## How processing works

1. **Acquire PDF bytes** — multipart upload, HTTP(S) URL download (`FileHandler`), or S3/local for batch rows.
2. **Text extraction** (`PDFExtractor` in `backend/app/services/pdf_extractor.py`) — embedded text first; then **Tesseract** for scans; **EasyOCR** when confidence or script complexity warrants it; **PyMuPDF** helps with awkward PDF image encodings. EasyOCR can run in a **subprocess** to reduce risk of OOM taking down the API.
3. **Entity extraction (optional, best-effort)** — `EntityExtractor` calls the same OpenRouter model family to pull structured entities from a longer text window before tagging; failures must not break the pipeline.
4. **Tag generation** — `AITagger` calls **OpenRouter** (`https://openrouter.ai/api/v1`) with the user’s **API key** and **model**, applies prompts, normalization, generic-term filtering, and **exclusion words**.
5. **Persistence** — batch jobs write **jobs** and **documents** rows when PostgreSQL is available; live progress and results are mirrored in **Redis** for observers and operators.

---

## Batch jobs: design (important)

Batch processing is **decoupled** from the WebSocket:

1. Client calls **`POST /api/batch/start`** with JSON body (documents + `TaggingConfig` + `column_mapping`, optional `job_id`). **Requires** a valid **access token**.
2. The server creates DB rows (if DB is up), seeds **Redis** job state, and starts a **background `asyncio` task** (`AsyncBatchProcessor` in `backend/app/services/async_batch_processor.py`).
3. Client opens **`WebSocket /api/batch/ws/{job_id}`** as a **read-only observer**: it receives a **`catchup`** payload (current state + prior results), then **live messages** from Redis pub/sub. **Disconnecting does not cancel the job.** Auth: `?token=<access_token>` or `Authorization: Bearer` header.
4. If WebSockets are unreliable, the UI can **poll** **`GET /api/batch/jobs/{job_id}/status`** (implemented in `frontend/lib/batchStore.ts`).

**Control**: **`POST /api/batch/jobs/{job_id}/cancel`**, **`/pause`**, **`/resume`** set Redis commands consumed between documents in the worker loop.

---

## Authentication

- **JWT access tokens** (short-lived) and **refresh tokens** (stored hashed in PostgreSQL) are issued on login (`backend/app/routers/auth.py`, `AuthService`).
- Most **write/read business APIs** require: **`Authorization: Bearer <access_token>`**.
- **Public** (no app JWT): **`GET /`**, **`GET /api/health`**, **`GET /api/status`**, **`GET /api/single/preview`** (URL proxy only).

---

## External APIs and local engines

### OpenRouter API

- **Endpoint**: `https://openrouter.ai/api/v1/chat/completions`
- **Method**: POST
- **Purpose**: Tag generation and optional entity extraction from document text
- **Authentication**: User-provided OpenRouter API key in `TaggingConfig.api_key`
- **Model**: User-selected (for example `google/gemini-flash-1.5`, `openai/gpt-4o-mini`)

### Tesseract OCR

- **Type**: Local OCR (CLI) via `pytesseract`, `pdf2image`, `Pillow`
- **Purpose**: Fast OCR for scanned pages; Hindi (`hin`) and English (`eng`) among supported paths
- **Strengths**: Fast, lightweight, good for Hindi/English scans

### EasyOCR

- **Type**: Deep learning OCR (PyTorch)
- **Purpose**: Higher-accuracy text for complex scripts and low-quality scans
- **Languages**: Broad set including Indian languages
- **Usage**: Fallback when Tesseract confidence is low (for example below 60%) or script detection suggests it

### AWS S3 (optional)

- **Library**: `boto3`
- **Purpose**: Download or validate objects when `file_source_type` is `s3` and credentials are configured on `FileHandler`

### HTTP(S)

- **Library**: `requests`
- **Purpose**: Download PDFs from URLs (single and batch), HEAD/GET for path validation

---

## Backend API (summary)

**Base URL (local)**: `http://localhost:8000`  
**Prefix**: almost all routes under **`/api`**.

### Root and health

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/` | No | API name and version JSON |
| GET | `/api/health` | No | Liveness / version (`HealthCheckResponse`) |
| GET | `/api/status` | No | Minimal OK payload |

### Authentication (`/api/auth`)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/auth/register` | Create user |
| POST | `/api/auth/login` | Access + refresh tokens |
| POST | `/api/auth/refresh` | New access token from refresh token |
| POST | `/api/auth/logout` | Revoke refresh token |
| GET | `/api/auth/me` | Current user profile |

### Single PDF (`/api/single`)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/single/process` | **Yes** | Multipart: `config` (JSON string `TaggingConfig`), optional `pdf_file` **or** `pdf_url`, optional `exclusion_file` |
| GET | `/api/single/preview` | No | Query `url` — proxies PDF bytes for iframe preview (CORS bypass) |

**`TaggingConfig`** (JSON string in form field `config`):

```json
{
  "api_key": "string",
  "model_name": "openai/gpt-4o-mini",
  "num_pages": 3,
  "num_tags": 8,
  "exclusion_words": ["optional", "terms"]
}
```

**`exclusion_file`**: `.txt` or `.pdf`; one term per line or comma-separated; `#` comments ignored (`ExclusionListParser`).

### Batch (`/api/batch`)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/batch/start` | **Yes** | Start background job; body `BatchStartRequest`: `documents`, `config`, `column_mapping`, optional `job_id` |
| WebSocket | `/api/batch/ws/{job_id}` | **Yes** (token query or header) | Observer: `catchup`, progress payloads, `keepalive`, terminal `completed` / `cancelled` / `error` |
| GET | `/api/batch/jobs/{job_id}/status` | **Yes** | Poll job status + counts from Redis |
| POST | `/api/batch/jobs/{job_id}/cancel` | **Yes** | Cancel command |
| POST | `/api/batch/jobs/{job_id}/pause` | **Yes** | Pause command |
| POST | `/api/batch/jobs/{job_id}/resume` | **Yes** | Resume command |
| GET | `/api/batch/active` | **Yes** | List active processing jobs (from Redis scan) |
| POST | `/api/batch/validate-paths` | **Yes** | Pre-flight URL / S3 / local checks |
| GET | `/api/batch/template` | **Yes** | Sample CSV + column descriptions (JSON) |
| POST | `/api/batch/process` | **Yes** | **Legacy** synchronous CSV upload (`multipart/form-data`) |

**CSV / row semantics** (batch): required logical fields include **`title`**, **`file_source_type`** (`url` \| `s3` \| `local`), **`file_path`**; optional description, publishing date, file size. **`column_mapping`** maps UI/CSV column keys to those system fields when headers differ.

**WebSocket messages (after connect)**:

- **`catchup`**: `{ "type": "catchup", "job_id", "state", "results" }` — current Redis state and all results so far.
- **Per-document updates** (from pub/sub): JSON objects with fields such as `job_id`, `row_id`, `row_number`, `title`, `status` (`processing` \| `success` \| `failed`), `progress`, `tags`, `error`, `metadata`, `model_name` (shape varies by event).
- **Terminal**: `{ "type": "completed" | "cancelled" | "error", ... }`.
- **`keepalive`**: sent by the server on idle timeout while checking job status.

### History and dashboard (`/api/history`)

All require **Bearer** authentication.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/history/jobs` | Paginated job list (`limit`, `offset`, optional `status`) |
| GET | `/api/history/jobs/{job_id}` | Job detail + documents |
| DELETE | `/api/history/jobs/{job_id}` | Delete job and cascaded documents |
| GET | `/api/history/documents` | Recent documents for user |
| GET | `/api/history/documents/{doc_id}` | Document detail (includes `extracted_text` when stored) |
| GET | `/api/history/documents/search` | Search by title/tags (`query`, `limit`) |
| GET | `/api/history/stats` | Aggregated user stats for dashboard |

**Implementation references**: `backend/app/routers/single.py`, `batch.py`, `auth.py`, `history.py`, `status.py`.

---

## Frontend routes (App Router)

| Path | Role |
|------|------|
| `/` | Single PDF upload / URL + tagging |
| `/batch` | CSV/grid batch flow, validation, `POST /start`, WebSocket or polling |
| `/login`, `/register` | Auth |
| `/dashboard`, `/history`, `/documents` | Logged-in history and stats |

Key clients: `frontend/lib/api.ts`, `frontend/lib/batchStore.ts`, components under `frontend/components/`.

---

## Configuration and deployment

- **Environment**: See `backend/app/config.py` and `docker-compose.yml` for `DATABASE_URL`, `REDIS_URL`, `MINIO_*`, `JWT_*`, etc.
- **CORS**: Currently permissive for development (`allow_origins=["*"]` in `main.py`); tighten for production behind a known origin.
- **CI / cloud**: `.github/workflows/deploy.yml`, `deployment/` (for example `docker-compose.prod.yml`, AWS notes).

---

## Features (product)

### URL-based documents

Single and batch flows can fetch PDFs from public **HTTP(S)** URLs (timeout and size limits apply in `FileHandler`). Preview uses **`/api/single/preview`** when embedding in the browser.

### Exclusion lists

Upload **`.txt`** or **`.pdf`** exclusion lists so generic or repeated terms are discouraged in the prompt and stripped in post-processing where possible, improving tag specificity for search use cases.

---

## Technical stack

- **Backend**: FastAPI, Pydantic, async PostgreSQL driver layer (`app/database`), repositories pattern
- **Frontend**: Next.js, TypeScript, React
- **PDF / text**: PyPDF2 / PyMuPDF (as available), `pdf2image`, Pillow
- **OCR**: Tesseract (`pytesseract`), EasyOCR (PyTorch)
- **AI client**: `openai` Python SDK pointed at OpenRouter
- **Auth**: JWT (access) + hashed refresh tokens in PostgreSQL
- **Job runtime**: `asyncio`, Redis pub/sub, background tasks

### Hybrid extraction strategy

1. **Embedded text** (fastest): use when the PDF already contains selectable text.
2. **Tesseract**: default OCR path for scans (Hindi/English focus in configuration).
3. **EasyOCR**: fallback for low confidence or complex Indic scripts; subprocess isolation for heavy jobs.

This balances **latency**, **accuracy**, and **stability** across varied government and institutional PDFs.
