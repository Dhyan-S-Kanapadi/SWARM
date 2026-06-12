# SWARM.AI

SWARM.AI is a local-business app factory. A user enters a plain-language business problem, and SWARM coordinates a small agent workflow that analyzes requirements, designs an architecture, generates a runnable app, and packages a pitch for the result.

The generated app is a React + Vite frontend with an Express API and local JSON persistence. It is designed for small local businesses that need a quick workflow tool for orders, appointments, visits, memberships, enrollments, or other operational records.

## Project Overview

SWARM.AI has two main surfaces:

- `backend/`: FastAPI service, LangGraph workflow, agents, output utilities, preview management, validation, and quality scoring.
- `frontend/`: React control panel for starting runs, tracking agent status, reviewing artifacts, launching previews, validating generated apps, scoring quality, browsing generated files, and downloading app zips.

Each run creates a unique output directory under `outputs/<run_id>/` with JSON artifacts and a materialized generated app.

## Architecture

```text
User prompt
  |
  v
React frontend
  |
  v
FastAPI backend
  |
  v
LangGraph workflow
  |
  +-- Analyst   -> requirements.json
  +-- Architect -> architecture.json
  +-- Builder   -> generated-app/
  +-- Pitcher   -> pitch_deck.json
  |
  v
outputs/<run_id>/
```

Backend responsibilities:

- Accept app generation requests through `POST /run`.
- Store run state in memory for the current server process.
- Execute the LangGraph workflow in the background.
- Persist artifacts under `outputs/`.
- Materialize, zip, validate, score, and preview generated apps.

Frontend responsibilities:

- Submit prompts to the backend.
- Poll run status and display agent progress.
- Show requirements, architecture, pitch, artifacts, generated source files, validation results, and quality results.
- Trigger generated app preview actions.

## LangGraph Workflow

The workflow is defined in `backend/graph.py` and runs in this order:

1. `analyst`: turns the user prompt into structured requirements.
2. `architect`: turns requirements into app architecture, API routes, schema, screens, workflows, and validation notes.
3. `builder`: creates the complete generated app file map and writes it to disk.
4. `pitcher`: summarizes the generated app as a pitch deck.

Each node updates its agent status through the shared `ProjectState`. The compiled workflow marks the run complete and writes a final `summary.json`.

## Groq Setup

The Analyst, Architect, and Pitcher agents can call Groq for JSON completions through `backend/agents/llm.py`.

`.env.example` documents the expected backend environment variables:

```powershell
Copy-Item .env.example .env
```

Set at least `GROQ_API_KEY` in the shell that starts the backend, or load the `.env` values with your preferred environment manager:

```powershell
$env:GROQ_API_KEY="your_groq_key_here"
```

Optional Groq settings:

```text
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_MODELS=llama-3.3-70b-versatile,llama-3.1-8b-instant,gemma2-9b-it
GROQ_TEMPERATURE=0
GROQ_MAX_TOKENS=2048
GROQ_TIMEOUT_SECONDS=30
GROQ_RATE_LIMIT_RETRIES=2
GROQ_RATE_LIMIT_DELAY_SECONDS=2
```

If `GROQ_API_KEY` is missing or a Groq JSON request fails, the agents fall back to deterministic outputs so the workflow can still complete locally.

## Builder Behavior

The Builder agent is internal and deterministic. It does not ask an LLM to write code. It uses the user prompt, requirements, architecture, and domain detection to generate a complete React + Express app.

Generated app files include:

- `package.json`
- `index.html`
- `vite.config.js`
- `README.md`
- `server/index.js`
- `server/dataStore.js`
- `server/app.test.js`
- `server/seed-data.json`
- `src/main.jsx`
- `src/api.js`
- `src/i18n.js`
- `src/App.jsx`
- `src/styles.css`

The generated app includes:

- Dashboard metrics.
- CRUD record management.
- Search and status filtering.
- Local JSON data storage.
- Seed data.
- Express API health and metrics routes.
- Node test runner coverage for data store behavior.
- Vite production build support.

## Supported Domains

The builder currently detects these local-business domains from the prompt:

- Bakery
- Salon, including common "saloon" spelling
- Clinic
- Fitness studio
- Tuition center
- Generic local business fallback

Domain detection changes labels, record names, queue names, follow-up labels, services, seed data, and generated app copy.

## Run Commands

Install backend dependencies in your Python environment:

```powershell
pip install fastapi uvicorn langgraph groq pydantic
```

Install frontend dependencies:

```powershell
npm --prefix frontend install
```

Start the backend:

```powershell
$env:GROQ_API_KEY="your_groq_key_here"
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Start the SWARM frontend:

```powershell
npm --prefix frontend run dev
```

Open:

```text
http://127.0.0.1:5173
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Start a run directly:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/run -Method Post -ContentType "application/json" -Body '{"prompt":"Build a salon appointment tracker"}'
```

## API Endpoints

- `GET /health`: backend health check.
- `POST /run`: start a new SWARM run.
- `GET /status/{run_id}`: inspect current run state.
- `GET /output/{run_id}`: fetch summary and workflow artifacts.
- `GET /runs`: list in-memory runs for the active server process.
- `GET /artifacts/{run_id}`: list persisted artifact files and generated app files.
- `GET /download/{run_id}`: download the generated app zip.
- `POST /validate/{run_id}`: run generated app checks.
- `POST /quality/{run_id}`: score generated app quality.
- `POST /preview/{run_id}/prepare`: materialize the generated app for preview.
- `POST /preview/{run_id}/install`: install generated app dependencies.
- `POST /preview/{run_id}/start`: start generated API and frontend preview processes.
- `POST /preview/{run_id}/stop`: stop generated app preview processes.
- `POST /preview/{run_id}/launch`: prepare, install, and start preview.
- `GET /preview/{run_id}/status`: inspect preview status and URLs.

## Preview Commands

The backend preview utilities use:

- Generated Express API: `http://127.0.0.1:3001`
- Generated Vite frontend: `http://127.0.0.1:6200`

From the SWARM frontend, use the preview controls for the selected run.

From the API:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/preview/<run_id>/prepare -Method Post
Invoke-RestMethod http://127.0.0.1:8000/preview/<run_id>/install -Method Post
Invoke-RestMethod http://127.0.0.1:8000/preview/<run_id>/start -Method Post
Invoke-RestMethod http://127.0.0.1:8000/preview/<run_id>/status
Invoke-RestMethod http://127.0.0.1:8000/preview/<run_id>/stop -Method Post
```

Shortcut:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/preview/<run_id>/launch -Method Post
```

## Validation Flow

Validation is implemented in `backend/utils.py` and runs inside `outputs/<run_id>/generated-app`.

Commands executed:

```text
npm install
npm run check
npm run test
npm run build
```

Results are persisted to:

```text
outputs/<run_id>/validation.json
```

Quality scoring reads the generated app, requirements, architecture, pitch deck, and validation result. It writes:

```text
outputs/<run_id>/quality.json
```

The current quality target is `90`.

## Output Artifacts

Typical run artifacts:

```text
outputs/<run_id>/
  requirements.json
  architecture.json
  generated_files.json
  pitch_deck.json
  summary.json
  validation.json
  quality.json
  preview.json
  generated-app/
  generated-app.zip
```

## Limitations

- Run state is stored in memory, so `/runs` and `/status/{run_id}` only include runs known to the active backend process.
- The generated app database is local JSON, not a production database.
- Preview ports are fixed at `3001` and `6200` unless changed in code.
- Generated apps are intentionally template-based and domain-aware, not fully arbitrary applications.
- Groq outputs are expected to be JSON. The helper includes parsing repair, retries, and model fallback, but deterministic fallbacks are still used when live completions fail.
- Authentication, deployment, multi-user collaboration, and hosted persistence are outside the current scope.

## Pitch

SWARM.AI turns a small-business workflow problem into a runnable software demo in one pass. It combines structured agent planning with deterministic app generation, so the output is inspectable, repeatable, and easy to validate. The current system is aimed at fast local demos for businesses like bakeries, salons, clinics, fitness studios, and tuition centers: enter the workflow problem, review the generated requirements and architecture, launch the app preview, validate the code, and download the result.
