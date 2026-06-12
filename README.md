# SWARM.AI

SWARM.AI is a local multi-agent MVP factory. A founder submits a raw startup idea, then a LangGraph workflow coordinates:

1. Analyst Agent: turns the idea into structured product requirements using Groq.
2. Architect Agent: turns requirements into a technical architecture using Groq.
3. Builder Agent: generates a complete local React + Express MVP directly inside SWARM.AI.
4. Pitcher Agent: turns all prior outputs into an investor-ready pitch deck using Groq after the generated app is created.

The main demo flow no longer depends on Trae. Trae/MCP integrations remain available as optional legacy tooling, but SWARM.AI can now generate the MVP by itself after the user types an idea in the UI.

## Project Structure

```text
backend/
  main.py
  graph.py
  state.py
  agents/
  mcp/
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
- Optional: Trae installed only if you want to test the legacy MCP handoff

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

Run the backend:

```bash
uvicorn backend.main:app --reload
```

The API runs at `http://localhost:8000`.

## One-Command Local Demo

After installing Python and frontend dependencies, use this launcher for the normal hackathon demo path:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_swarm_demo.ps1
```

It starts:

- SWARM backend at `http://127.0.0.1:8000`
- SWARM frontend at `http://127.0.0.1:5173`
- Optional Trae auto-worker only when `-WithTraeWorker` is present

Expected user flow:

1. Type an app idea in the SWARM UI.
2. Analyst and Architect run inside SWARM.
3. SWARM Builder generates a complete local app.
4. Pitcher creates the investor-ready output.
5. Preview, validation, and quality-gate workflows are available from the UI.

## Optional Legacy Trae MCP

Trae's MCP support is used in this project by letting Trae connect to SWARM.AI as an MCP server.

The project includes `.trae/mcp.json`, which tells Trae to start:

```text
D:\SWARM.AI\.venv\Scripts\python.exe D:\SWARM.AI\backend\mcp\swarm_server.py
```

That MCP server exposes these tools to Trae:

- `list_swarm_runs`
- `get_builder_prompt`
- `get_project_context`
- `get_quality_report`
- `get_submitted_code_files`
- `submit_code_files`
- `mark_builder_error`

Workflow:

1. Start the SWARM.AI backend.
2. Submit an idea with `POST /run`.
3. Wait until the Builder status is `waiting_for_trae`.
4. Keep Trae running on the demo/developer machine with `D:\SWARM.AI` open.
5. Ensure Trae loads `.trae/mcp.json`.
6. Ask Trae Builder to use the `swarm_ai` MCP server, call `get_builder_prompt`, build the project, then call `submit_code_files`.
7. SWARM.AI marks Builder done, runs Pitcher, and completes the run.

Example prompt to Trae Builder:

```text
Use the swarm_ai MCP server. Call get_builder_prompt for the latest SWARM.AI run, build the complete MVP described in that prompt, then call submit_code_files with every generated file.
```

No Trae API key is required for this flow. Trae authenticates through its own IDE/session. The only required key for SWARM.AI's backend agents is `GROQ_API_KEY`.

### Optional Trae Auto Worker

Trae does not currently expose a reliable CLI/API in this setup, so SWARM.AI cannot directly command Trae through a backend call. For a local hackathon demo, use the Windows automation worker in `scripts/trae_auto_worker.ps1`.

It watches the SWARM.AI backend for runs with:

```json
"builder": "waiting_for_trae"
```

Then it brings Trae to the foreground, pastes a run-specific instruction, and presses Enter. Trae still performs the build through the `swarm_ai` MCP server and submits files back with `submit_code_files`.

Setup:

1. Start the SWARM.AI backend.
2. Open `D:\SWARM.AI` in Trae.
3. Make sure Trae has loaded `.trae/mcp.json`.
4. Click the Trae chat input once so it can receive pasted text.
5. Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\trae_auto_worker.ps1
```

Leave that worker running during the demo.

This is full local demo automation after setup, but it is GUI automation. If Trae changes focus, changes its UI, or blocks pasted commands, the worker can fail. A production-grade version requires an official Trae CLI, API, or task-runner endpoint.

### Legacy Direct Trae MCP Client

`backend/mcp/trae_client.py` and `backend/mcp/mcp_config.json` are retained as a legacy direct-client adapter in case Trae later exposes a callable MCP server.

Edit `backend/mcp/mcp_config.json` only if you have a real Trae MCP server command or URL.

The default assumes a stdio server:

```json
{
  "server_name": "trae.ai",
  "transport": "stdio",
  "timeout_seconds": 900,
  "tool_name": "build_project",
  "argument_name": "prompt",
  "server": {
    "command": "trae",
    "args": ["mcp", "serve"],
    "env": {
      "TRAE_API_KEY": "${TRAE_API_KEY}"
    }
  }
}
```

This is not the active hackathon flow. Adjust `command`, `args`, `tool_name`, and `argument_name` only if your Trae install exposes a real MCP server. If your trae.ai server exposes streamable HTTP, use:

```json
{
  "server_name": "trae.ai",
  "transport": "streamable_http",
  "timeout_seconds": 900,
  "tool_name": "build_project",
  "argument_name": "prompt",
  "server": {
    "url": "http://localhost:9000/mcp"
  }
}
```

The MCP tool should return generated files as one of these shapes:

```json
{ "files": { "path/to/file.ext": "file content" } }
```

or:

```json
{ "files": [{ "path": "path/to/file.ext", "content": "file content" }] }
```

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

After Trae submits code files, SWARM.AI can prepare and run the generated app from the workspace UI.

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
