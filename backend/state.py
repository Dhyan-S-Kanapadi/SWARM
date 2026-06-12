"""Shared workflow state definitions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, TypedDict
from uuid import uuid4

AgentName = Literal["analyst", "architect", "builder", "pitcher"]
AgentRunStatus = Literal["pending", "running", "complete", "failed"]
RunStatus = Literal["queued", "running", "complete", "failed"]

AGENT_ORDER: tuple[AgentName, ...] = ("analyst", "architect", "builder", "pitcher")


class AgentStatus(TypedDict, total=False):
    """Progress details for one workflow agent."""

    name: AgentName
    status: AgentRunStatus
    started_at: str | None
    completed_at: str | None
    error: str | None


class ProjectState(TypedDict, total=False):
    """State object passed through the SWARM workflow."""

    run_id: str
    prompt: str
    status: RunStatus
    current_agent: AgentName | None
    created_at: str
    updated_at: str
    output_dir: str
    agent_statuses: dict[AgentName, AgentStatus]
    requirements: dict[str, Any]
    architecture: dict[str, Any]
    generated_files: dict[str, str]
    pitch_deck: dict[str, Any]
    errors: list[str]
    summary: dict[str, Any]


def utc_now_iso() -> str:
    """Return a stable UTC timestamp for persisted run metadata."""
    return datetime.now(timezone.utc).isoformat()


def initialize_agent_statuses() -> dict[AgentName, AgentStatus]:
    """Create the default status block for all workflow agents."""
    return {
        agent: {
            "name": agent,
            "status": "pending",
            "started_at": None,
            "completed_at": None,
            "error": None,
        }
        for agent in AGENT_ORDER
    }


def create_project_state(prompt: str, run_id: str | None = None) -> ProjectState:
    """Create the initial state for a new SWARM run."""
    now = utc_now_iso()
    return {
        "run_id": run_id or str(uuid4()),
        "prompt": prompt,
        "status": "queued",
        "current_agent": None,
        "created_at": now,
        "updated_at": now,
        "agent_statuses": initialize_agent_statuses(),
        "requirements": {},
        "architecture": {},
        "generated_files": {},
        "pitch_deck": {},
        "errors": [],
        "summary": {},
    }


def set_agent_status(
    state: ProjectState,
    agent: AgentName,
    status: AgentRunStatus,
    error: str | None = None,
) -> ProjectState:
    """Update one agent status in-place and return the state."""
    now = utc_now_iso()
    agent_status = state.setdefault("agent_statuses", initialize_agent_statuses())[agent]
    agent_status["status"] = status
    agent_status["error"] = error
    state["current_agent"] = agent
    state["updated_at"] = now

    if status == "running":
        agent_status["started_at"] = agent_status.get("started_at") or now
    if status in {"complete", "failed"}:
        agent_status["completed_at"] = now
    if status == "failed":
        state["status"] = "failed"

    return state
