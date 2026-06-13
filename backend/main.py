import os
import subprocess
from threading import Lock
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.graph import workflow
from backend.agents.llm import allow_llm_fallback, groq_configured
from backend.state import ProjectState, initial_agent_statuses
from backend.utils import (
    OUTPUTS_DIR,
    GENERATED_APPS_DIR,
    PROJECT_ROOT,
    build_artifact_summary,
    build_demo_summary,
    create_code_zip,
    evaluate_generated_app,
    list_run_summaries,
    load_run_from_disk,
    materialize_generated_app,
    validate_generated_app,
    utc_now,
    write_run_summary,
)

load_dotenv(PROJECT_ROOT / ".env")
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="SWARM.AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

runs: dict[str, ProjectState] = {}
runs_lock = Lock()
preview_processes: dict[str, dict] = {}


class RunRequest(BaseModel):
    idea: str = Field(..., min_length=1)


def execute_workflow(run_id: str) -> None:
    state = runs[run_id]
    try:
        final_state = workflow.invoke(state)
        builder_status = final_state.get("agent_statuses", {}).get("builder")
        if final_state.get("fatal_error"):
            final_state["done"] = True
        elif builder_status == "waiting_for_trae":
            final_state["current_agent"] = "builder"
            final_state["done"] = False
        else:
            final_state["current_agent"] = "done"
            final_state["done"] = True
        final_state["updated_at"] = utc_now()
        runs[run_id] = final_state
    except Exception as exc:
        state.setdefault("errors", []).append(f"Workflow failed: {exc}")
        state["done"] = True
        state["current_agent"] = "done"
        state["updated_at"] = utc_now()
    finally:
        write_run_summary(runs[run_id])


@app.post("/run")
def run_project(payload: RunRequest, background_tasks: BackgroundTasks) -> dict[str, str]:
    run_id = str(uuid4())
    now = utc_now()
    state: ProjectState = {
        "idea": payload.idea,
        "requirements": {},
        "architecture": {},
        "builder_prompt": "",
        "code_files": {},
        "pitch_deck": {},
        "llm_calls": [],
        "current_agent": "queued",
        "agent_statuses": initial_agent_statuses(),
        "errors": [],
        "run_id": run_id,
        "done": False,
        "created_at": now,
        "updated_at": now,
    }
    with runs_lock:
        runs[run_id] = state
    write_run_summary(state)
    background_tasks.add_task(execute_workflow, run_id)
    return {"run_id": run_id}


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "SWARM.AI backend",
        "groq_configured": groq_configured(),
        "llm_fallback_enabled": allow_llm_fallback(),
        "builder_mode": "internal",
        "outputs_dir": str(OUTPUTS_DIR),
    }


@app.get("/runs")
def list_runs() -> dict:
    memory_summaries = []
    with runs_lock:
        for state in runs.values():
            memory_summaries.append(
                {
                    "run_id": state.get("run_id"),
                    "idea": state.get("idea", ""),
                    "current_agent": state.get("current_agent", "unknown"),
                    "agent_statuses": state.get("agent_statuses", initial_agent_statuses()),
                    "errors": state.get("errors", []),
                    "done": state.get("done", False),
                    "created_at": state.get("created_at"),
                    "updated_at": state.get("updated_at"),
                }
            )
    summaries_by_id = {item["run_id"]: item for item in list_run_summaries()}
    for item in memory_summaries:
        summaries_by_id[item["run_id"]] = item
    return {"runs": list(summaries_by_id.values())}


@app.get("/status/{run_id}")
def get_status(run_id: str) -> dict:
    state = _get_run(run_id)
    return {
        "run_id": run_id,
        "current_agent": state.get("current_agent", "unknown"),
        "agent_statuses": state.get("agent_statuses", initial_agent_statuses()),
        "errors": state.get("errors", []),
        "llm_calls": state.get("llm_calls", []),
        "done": state.get("done", False),
        "created_at": state.get("created_at"),
        "updated_at": state.get("updated_at"),
    }


@app.get("/output/{run_id}")
def get_output(run_id: str) -> dict:
    state = _get_run(run_id)
    return {
        "run_id": run_id,
        "idea": state.get("idea", ""),
        "requirements": state.get("requirements", {}),
        "architecture": state.get("architecture", {}),
        "builder_prompt": state.get("builder_prompt", ""),
        "code_files": state.get("code_files", {}),
        "pitch_deck": state.get("pitch_deck", {}),
        "errors": state.get("errors", []),
        "llm_calls": state.get("llm_calls", []),
        "done": state.get("done", False),
    }


@app.get("/artifacts/{run_id}")
def get_artifacts(run_id: str) -> dict:
    _get_run(run_id)
    summary = build_artifact_summary(run_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Artifacts not found")
    return summary


@app.get("/demo/{run_id}")
def get_demo_summary(run_id: str) -> dict:
    _get_run(run_id)
    summary = build_demo_summary(run_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Demo summary not found")
    return summary


@app.get("/download/{run_id}")
def download_generated_app(run_id: str) -> FileResponse:
    _get_run(run_id)
    try:
        zip_path = create_code_zip(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"swarm-ai-{run_id}-generated-app.zip",
    )


@app.post("/preview/{run_id}/prepare")
def prepare_preview(run_id: str) -> dict:
    _get_run(run_id)
    try:
        app_path = materialize_generated_app(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _preview_status_payload(run_id, app_path)


@app.post("/preview/{run_id}/install")
def install_preview_dependencies(run_id: str) -> dict:
    app_path = _ensure_preview_app(run_id)
    _install_preview_dependencies(run_id, app_path)
    return _preview_status_payload(run_id, app_path)


@app.post("/preview/{run_id}/launch")
def launch_preview(run_id: str) -> dict:
    app_path = _ensure_preview_app(run_id)
    if not (app_path / "node_modules").exists():
        _install_preview_dependencies(run_id, app_path)
    return _start_preview_processes(run_id, app_path)


def _install_preview_dependencies(run_id: str, app_path) -> None:
    package_json = app_path / "package.json"
    if not package_json.exists():
        raise HTTPException(status_code=400, detail="Generated app has no package.json")

    result = subprocess.run(
        ["npm.cmd", "install"],
        cwd=app_path,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    preview_processes.setdefault(run_id, {})["last_install"] = {
        "returncode": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
        "updated_at": utc_now(),
    }
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=preview_processes[run_id]["last_install"])


@app.post("/preview/{run_id}/start")
def start_preview(run_id: str) -> dict:
    app_path = _ensure_preview_app(run_id)
    package_json = app_path / "package.json"
    if not package_json.exists():
        raise HTTPException(status_code=400, detail="Generated app has no package.json")
    if not (app_path / "node_modules").exists():
        raise HTTPException(status_code=409, detail="Install dependencies before starting preview")
    return _start_preview_processes(run_id, app_path)


def _start_preview_processes(run_id: str, app_path) -> dict:
    record = preview_processes.setdefault(run_id, {})
    _stop_preview_processes(record)

    env = os.environ.copy()
    env["PORT"] = "3001"

    server_process = subprocess.Popen(
        ["npm.cmd", "run", "dev:server"],
        cwd=app_path,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    client_process = subprocess.Popen(
        ["npm.cmd", "run", "dev:client", "--", "--host", "127.0.0.1", "--port", "6200"],
        cwd=app_path,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    record.update(
        {
            "app_path": str(app_path),
            "frontend_url": "http://127.0.0.1:6200",
            "api_url": "http://127.0.0.1:3001",
            "server_pid": server_process.pid,
            "client_pid": client_process.pid,
            "server_process": server_process,
            "client_process": client_process,
            "started_at": utc_now(),
        }
    )
    return _preview_status_payload(run_id, app_path)


@app.post("/preview/{run_id}/stop")
def stop_preview(run_id: str) -> dict:
    record = preview_processes.setdefault(run_id, {})
    _stop_preview_processes(record)
    record["stopped_at"] = utc_now()
    app_path = GENERATED_APPS_DIR / run_id
    return _preview_status_payload(run_id, app_path)


@app.get("/preview/{run_id}/status")
def get_preview_status(run_id: str) -> dict:
    _get_run(run_id)
    return _preview_status_payload(run_id, GENERATED_APPS_DIR / run_id)


@app.post("/validate/{run_id}")
def validate_generated_app_endpoint(run_id: str) -> dict:
    _get_run(run_id)
    try:
        return validate_generated_app(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/quality/{run_id}")
def evaluate_generated_app_quality(run_id: str) -> dict:
    _get_run(run_id)
    try:
        return evaluate_generated_app(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _get_run(run_id: str) -> ProjectState:
    state = runs.get(run_id)
    disk_state = load_run_from_disk(run_id)
    if disk_state and (not state or _is_newer(disk_state, state)):
        state = disk_state
        with runs_lock:
            runs[run_id] = state
    if not state:
        raise HTTPException(status_code=404, detail="Run not found")
    return state


def _is_newer(candidate: ProjectState, current: ProjectState) -> bool:
    return str(candidate.get("updated_at", "")) > str(current.get("updated_at", ""))


def _ensure_preview_app(run_id: str):
    _get_run(run_id)
    app_path = GENERATED_APPS_DIR / run_id
    if not app_path.exists():
        try:
            app_path = materialize_generated_app(run_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return app_path


def _preview_status_payload(run_id: str, app_path) -> dict:
    record = preview_processes.get(run_id, {})
    server_running = _process_is_running(record.get("server_process"))
    client_running = _process_is_running(record.get("client_process"))
    return {
        "run_id": run_id,
        "app_path": str(app_path),
        "prepared": app_path.exists(),
        "dependencies_installed": (app_path / "node_modules").exists(),
        "frontend_url": record.get("frontend_url", "http://127.0.0.1:6200"),
        "api_url": record.get("api_url", "http://127.0.0.1:3001"),
        "server_running": server_running,
        "client_running": client_running,
        "running": server_running or client_running,
        "last_install": record.get("last_install"),
        "started_at": record.get("started_at"),
        "stopped_at": record.get("stopped_at"),
    }


def _process_is_running(process) -> bool:
    return bool(process and process.poll() is None)


def _stop_preview_processes(record: dict) -> None:
    for key in ("server_process", "client_process"):
        process = record.get(key)
        if process and process.poll() is None:
            process.terminate()
