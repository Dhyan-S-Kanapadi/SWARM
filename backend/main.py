"""FastAPI application entry point."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.state import ProjectState, create_project_state, utc_now_iso
from backend.utils import get_run_output_dir, load_run_summary, write_run_summary

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

        background_tasks.add_task(run_placeholder_workflow, run_id)

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

    return api


def run_placeholder_workflow(run_id: str) -> None:
    """Placeholder workflow until LangGraph agents are added."""
    state = RUN_STORE.get(run_id)
    if state is None:
        return

    now = utc_now_iso()
    state["status"] = "running"
    state["updated_at"] = now

    summary = {
        "run_id": run_id,
        "status": "complete",
        "message": "Workflow placeholder completed. LangGraph agents are added in a later milestone.",
        "prompt": state["prompt"],
        "completed_at": utc_now_iso(),
    }
    write_run_summary(run_id, summary)

    state["summary"] = summary
    state["status"] = "complete"
    state["updated_at"] = summary["completed_at"]


def _get_run_or_404(run_id: str) -> ProjectState:
    state = RUN_STORE.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return deepcopy(state)


app = create_app()
