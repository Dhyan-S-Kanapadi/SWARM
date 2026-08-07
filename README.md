# SWARM.AI

SWARM.AI is a local multi-agent MVP factory. A founder submits a raw startup idea, then a LangGraph workflow coordinates:

1. Analyst Agent: turns the idea into structured product requirements using Groq.
2. Architect Agent: turns requirements into a technical architecture using Groq.
3. Builder Agent: generates a complete local React + Express MVP directly inside SWARM.AI.
4. Pitcher Agent: turns all prior outputs into an investor-ready pitch deck using Groq after the generated app is created.

SWARM.AI generates the MVP itself after the user types an idea in the UI.

## Project Structure

```text
backend/
  main.py
  graph.py
  state.py
  agents/
  prompts/
  outputs/
frontend/
  src/
  package.json
requirements.txt
```

## Prerequisites

- Python 3.11+
- Node.js 20+
- A Groq API key from the Groq Console: https://console.groq.com

## Backend Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env`:

```env
GROQ_API_KEY=your_groq_api_key_here
```

## Per-Agent LLM Routing

SWARM uses LiteLLM's Python SDK for Analyst, Architect, and Pitcher. Configure
each agent with a provider-prefixed model and, when needed, a separate key:

```env
LLM_ANALYST_MODEL=groq/openai/gpt-oss-120b
LLM_ANALYST_API_KEY=your_groq_key
LLM_ARCHITECT_MODEL=anthropic/claude-sonnet-4-5-20250929
LLM_ARCHITECT_API_KEY=your_anthropic_key
LLM_PITCHER_MODEL=openai/gpt-4o-mini
LLM_PITCHER_API_KEY=your_openai_key
```

Leaving an `LLM_<AGENT>_API_KEY` blank uses the provider's standard key such
as `GROQ_API_KEY`, `ANTHROPIC_API_KEY`, or `OPENAI_API_KEY`. Different models
on one provider key still share that provider account's rate limits.

Run the backend:

```bash
uvicorn backend.main:app --reload
```

The API runs at `http://localhost:8000`.

## One-Command Local Demo

After installing Python and frontend dependencies, use this launcher for the normal local demo path:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_swarm_demo.ps1
```

It starts:

- SWARM backend at `http://127.0.0.1:8000`
- SWARM frontend at `http://127.0.0.1:5173`

Expected user flow:

1. Type an app idea in the SWARM UI.
2. Analyst and Architect run inside SWARM.
3. SWARM Builder generates a complete local app.
4. Pitcher creates the investor-ready output.
5. Preview, validation, and quality-gate workflows are available from the UI.

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

If the backend is not on `http://localhost:8000`, create `frontend/.env`:

```env
VITE_API_BASE_URL=http://localhost:8000
```

## API

### `GET /health`

Returns backend liveness and basic configuration state.

```json
{
  "status": "ok",
  "service": "SWARM.AI backend",
  "groq_configured": true,
  "outputs_dir": "backend/outputs"
}
```

### `GET /runs`

Returns known in-memory and persisted run summaries.

### `POST /run`

Request:

```json
{ "idea": "A plain-English startup idea" }
```

Response:

```json
{ "run_id": "uuid" }
```

### `GET /status/{run_id}`

Returns:

```json
{
  "run_id": "uuid",
  "current_agent": "analyst",
  "agent_statuses": {
    "analyst": "running",
    "architect": "pending",
    "builder": "pending",
    "pitcher": "pending"
  },
  "errors": [],
  "done": false
}
```

### `GET /output/{run_id}`

Returns requirements, architecture, builder prompt, generated code files, pitch deck, errors, and run status.

### Generated App Preview

After the Builder generates code files, SWARM.AI can prepare and run the generated app from the workspace UI.

API flow:

```text
POST /preview/{run_id}/prepare
POST /preview/{run_id}/install
POST /preview/{run_id}/start
GET  /preview/{run_id}/status
POST /preview/{run_id}/stop
```

The preview launcher materializes generated source into:

```text
generated_apps/{run_id}/
```

It runs the generated API on:

```text
http://127.0.0.1:3001
```

It runs the generated frontend on:

```text
http://127.0.0.1:6200
```

Use the SWARM frontend's "Generated app preview" panel for the normal demo path.

## Output Files

Each run writes to `backend/outputs/{run_id}/`:

- `requirements.json`
- `architecture.json`
- `builder_prompt.txt`
- `code_files/`
- `pitch_deck.json`
- `run_summary.json`

## Notes

- Groq prompts are loaded from `backend/prompts/*.txt`.
- JSON responses are stripped of markdown fences before `json.loads()`.
- External calls are wrapped in `try/except`, and errors are stored in `state.errors`.
- The workflow keeps moving to the next agent after an error.
- CORS is enabled for browser-based local development.
