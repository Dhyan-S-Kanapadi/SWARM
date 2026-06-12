"""FastAPI application entry point."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.graph import run_workflow
from backend.state import ProjectState, create_project_state, utc_now_iso
from backend.utils import (
    collect_artifact_summary,
    get_generated_app_dir,
    get_run_output_dir,
    load_run_summary,
    materialize_generated_app,
    score_generated_app_quality,
    validate_generated_app,
    zip_generated_app,
)

RUN_STORE: dict[str, ProjectState] = {}


class RunRequest(BaseModel):
    """Request body for starting a SWARM run."""

    prompt: str = Field(..., min_length=1)


def create_app() -> FastAPI:
    """Create and configure the SWARM API."""
    api = FastAPI(title="SWARM.AI API", version="0.1.0")

    api.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @api.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @api.post("/run", status_code=202)
    def start_run(
        request: RunRequest,
        background_tasks: BackgroundTasks,
    ) -> dict[str, Any]:
        state = create_project_state(request.prompt.strip())
        run_id = state["run_id"]
        run_dir = get_run_output_dir(run_id)

        state["output_dir"] = str(run_dir)
        state["status"] = "queued"
        RUN_STORE[run_id] = state

        background_tasks.add_task(run_background_workflow, run_id)

        return {
            "run_id": run_id,
            "status": state["status"],
            "status_url": f"/status/{run_id}",
            "output_url": f"/output/{run_id}",
        }

    @api.get("/status/{run_id}")
    def get_status(run_id: str) -> ProjectState:
        return _get_run_or_404(run_id)

    @api.get("/output/{run_id}")
    def get_output(run_id: str) -> dict[str, Any]:
        state = _get_run_or_404(run_id)
        summary = load_run_summary(run_id) or state.get("summary", {})
        return {
            "run_id": run_id,
            "status": state["status"],
            "output_dir": state.get("output_dir"),
            "summary": summary,
            "requirements": state.get("requirements", {}),
            "architecture": state.get("architecture", {}),
            "generated_files": state.get("generated_files", {}),
            "pitch_deck": state.get("pitch_deck", {}),
            "errors": state.get("errors", []),
        }

    @api.get("/runs")
    def list_runs() -> dict[str, list[ProjectState]]:
        runs = sorted(
            RUN_STORE.values(),
            key=lambda item: item.get("created_at", ""),
            reverse=True,
        )
        return {"runs": [deepcopy(run) for run in runs]}

    @api.get("/artifacts/{run_id}")
    def get_artifacts(run_id: str) -> dict[str, Any]:
        state = _get_run_or_404(run_id)
        _ensure_generated_app_materialized(state)
        return collect_artifact_summary(run_id, state)

    @api.get("/download/{run_id}")
    def download_generated_app(run_id: str) -> FileResponse:
        state = _get_run_or_404(run_id)
        _ensure_generated_app_materialized(state)
        try:
            zip_path = zip_generated_app(run_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return FileResponse(
            zip_path,
            media_type="application/zip",
            filename=f"swarm-generated-app-{run_id}.zip",
        )

    @api.post("/validate/{run_id}")
    def validate_run(run_id: str) -> dict[str, Any]:
        state = _get_run_or_404(run_id)
        _ensure_generated_app_materialized(state)
        return validate_generated_app(run_id)

    @api.post("/quality/{run_id}")
    def score_run_quality(run_id: str) -> dict[str, Any]:
        state = _get_run_or_404(run_id)
        _ensure_generated_app_materialized(state)
        return score_generated_app_quality(run_id, state)

    return api


def run_background_workflow(run_id: str) -> None:
    """Run the LangGraph workflow for a stored run."""
    state = RUN_STORE.get(run_id)
    if state is None:
        return

    try:
        state["status"] = "running"
        state["updated_at"] = utc_now_iso()
        RUN_STORE[run_id] = run_workflow(state)
    except Exception as exc:  # pragma: no cover - defensive background guard
        state["status"] = "failed"
        state["updated_at"] = utc_now_iso()
        state.setdefault("errors", []).append(str(exc))


def _get_run_or_404(run_id: str) -> ProjectState:
    state = RUN_STORE.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return deepcopy(state)


def _ensure_generated_app_materialized(state: ProjectState) -> None:
    run_id = state["run_id"]
    app_dir = get_generated_app_dir(run_id)
    if app_dir.exists():
        return

    generated_files = state.get("generated_files", {})
    if not generated_files:
        raise HTTPException(status_code=404, detail="Generated app not found")
    materialize_generated_app(run_id, generated_files)


app = create_app()
