# SWARM.AI Context

## Purpose

SWARM.AI is a local-business app factory. It accepts a plain-language prompt and produces a runnable React + Express management app, supporting artifacts, validation results, and a pitch summary.

The project is built to demonstrate a multi-agent software generation workflow with a deterministic builder. Groq can improve planning and pitch artifacts, but the system still runs without a Groq key through local fallback logic.

## Current Architecture

```text
frontend/ React + Vite control panel
backend/  FastAPI API + LangGraph workflow + agents + utilities
outputs/  Per-run artifacts and generated apps
```

The backend API is created in `backend/main.py`. It keeps active run state in an in-memory `RUN_STORE`, starts workflows through FastAPI background tasks, and exposes endpoints for status, artifacts, download, validation, quality scoring, and generated app preview.

The workflow is defined in `backend/graph.py` with a linear LangGraph `StateGraph`.

## Agent Workflow

The current LangGraph order is:

1. Analyst
2. Architect
3. Builder
4. Pitcher

Agent responsibilities:

- Analyst: creates `requirements.json` from the user prompt.
- Architect: creates `architecture.json` from the prompt and requirements.
- Builder: creates and materializes `generated-app/`.
- Pitcher: creates `pitch_deck.json` from the prompt and generated artifacts.

Every agent updates shared `ProjectState` status metadata. The workflow writes `summary.json` when complete.

## Groq Behavior

`backend/agents/llm.py` provides JSON-only Groq completions.

Environment variables are read from the backend process environment:

- `GROQ_API_KEY`
- `GROQ_MODEL`
- `GROQ_MODELS`
- `GROQ_TEMPERATURE`
- `GROQ_MAX_TOKENS`
- `GROQ_TIMEOUT_SECONDS`
- `GROQ_RATE_LIMIT_RETRIES`
- `GROQ_RATE_LIMIT_DELAY_SECONDS`

The default model list is:

- `llama-3.3-70b-versatile`
- `llama-3.1-8b-instant`
- `gemma2-9b-it`

Analyst, Architect, and Pitcher use Groq when available. If the key is missing, authentication fails, rate limits exhaust, or JSON parsing fails, those agents produce deterministic fallback artifacts. The Builder is always deterministic and does not call Groq.

## Builder Behavior

The Builder is implemented in `backend/agents/builder.py`. It detects the business domain from the prompt, builds a domain context, creates seed records, and writes a complete generated app file map.

Generated app stack:

- React + Vite frontend
- Express backend
- Local JSON persistence
- Node test runner

Generated app capabilities:

- Dashboard metrics
- CRUD record workflows
- Search and status filtering
- Status advancement
- Seed data
- API health route
- Metrics route
- Local validation scripts

Supported domains:

- Bakery
- Salon, including "saloon"
- Clinic
- Fitness studio
- Tuition center
- Generic local business fallback

## Generated App Files

The generated app currently contains:

```text
package.json
index.html
vite.config.js
README.md
server/index.js
server/dataStore.js
server/app.test.js
server/seed-data.json
src/main.jsx
src/api.js
src/i18n.js
src/App.jsx
src/styles.css
```

The generated `package.json` includes:

```text
npm run dev
npm run server
npm run check
npm run test
npm run build
```

## Run Commands

Backend:

```powershell
pip install fastapi uvicorn langgraph groq pydantic
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Frontend:

```powershell
npm --prefix frontend install
npm --prefix frontend run dev
```

Default URLs:

- SWARM frontend: `http://127.0.0.1:5173`
- SWARM backend: `http://127.0.0.1:8000`
- Generated app API preview: `http://127.0.0.1:3001`
- Generated app frontend preview: `http://127.0.0.1:6200`

## Preview Flow

Preview endpoints:

- `POST /preview/{run_id}/prepare`
- `POST /preview/{run_id}/install`
- `POST /preview/{run_id}/start`
- `POST /preview/{run_id}/stop`
- `POST /preview/{run_id}/launch`
- `GET /preview/{run_id}/status`

`launch` runs prepare, install, and start in sequence. Preview status is persisted to `outputs/<run_id>/preview.json`.

## Validation And Quality

Validation endpoint:

```text
POST /validate/{run_id}
```

Validation runs inside the generated app:

```text
npm install
npm run check
npm run test
npm run build
```

Validation output is saved to `validation.json`.

Quality endpoint:

```text
POST /quality/{run_id}
```

Quality scoring checks:

- Project completeness
- Dynamic workflows
- Requirement coverage
- Localization readiness
- Runnable quality
- Demo polish

The current target score is `90`, and output is saved to `quality.json`.

## API Surface

Primary backend endpoints:

- `GET /health`
- `POST /run`
- `GET /status/{run_id}`
- `GET /output/{run_id}`
- `GET /runs`
- `GET /artifacts/{run_id}`
- `GET /download/{run_id}`
- `POST /validate/{run_id}`
- `POST /quality/{run_id}`
- Preview endpoints listed above

## Limitations

- Run state is process-local and not restored from disk into `RUN_STORE`.
- Generated apps use local JSON files rather than a production database.
- Preview ports are fixed in `backend/utils.py`.
- The generated app is template-driven and supports a bounded set of local-business workflows.
- Groq planning is useful but optional; deterministic fallbacks are the reliability path.
- No authentication, hosted deployment, background queue persistence, or multi-tenant storage is implemented yet.

## Pitch

SWARM.AI gives a small business owner a fast path from workflow problem to working demo. The project combines agent-based analysis and architecture with deterministic code generation, making the output repeatable enough to validate and practical enough to preview. The current product story is: describe a local workflow, watch the agents produce artifacts, inspect the generated code, launch the app, run checks, score quality, and download the result.
