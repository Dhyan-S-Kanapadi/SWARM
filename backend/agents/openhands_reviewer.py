"""OpenHands post-build verification and repair node for the SWARM graph."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from openhands.sdk import LLM, Conversation
from openhands.sdk.event import MessageEvent
from openhands.tools.preset.default import get_default_agent

from backend.state import ProjectState
from backend.utils import (
    complete_agent,
    output_dir,
    read_code_files,
    set_agent_status,
    write_json,
)


_PLACEHOLDER_KEYS = {"", "your_openrouter_api_key", "your_api_key_here", "replace_me"}
_DEFAULT_REVIEW_TIMEOUT_SECONDS = 90
_DEFAULT_REVIEW_MAX_ITERATIONS = 12


def run_openhands_builder(state: ProjectState) -> ProjectState:
    """Use OpenHands to turn the deterministic baseline into the requested app.

    The deterministic Builder provisions the database and creates a runnable baseline.
    OpenHands is the architecture-aware coding worker: it must customize that baseline
    for the requested product, then run the available validation commands.
    """

    set_agent_status(state, "openhands", "running")
    config = _openhands_config()
    if config is None:
        if _openhands_enabled() and _openhands_is_required():
            set_agent_status(state, "openhands", "error")
            raise RuntimeError(
                "OpenHands Builder is required but no usable OPENHANDS_MODEL and OPENHANDS_API_KEY are configured"
            )
        set_agent_status(state, "openhands", "skipped")
        state.setdefault("llm_calls", []).append(
            {"agent": "openhands", "provider": "none", "status": "skipped"}
        )
        return state

    workspace = output_dir(state["run_id"]) / "code_files"
    if not workspace.exists():
        set_agent_status(state, "openhands", "error")
        state.setdefault("errors", []).append("OpenHands review skipped: Builder produced no code workspace")
        return state

    before = _project_fingerprint(workspace)
    try:
        result = _run_openhands_build(config, workspace, state)
        after = _project_fingerprint(workspace)
        if before == after:
            raise RuntimeError(
                "OpenHands Builder completed without changing application source files; refusing to present the baseline as a custom build"
            )
        state["code_files"] = read_code_files(state["run_id"])
        result["source_files_changed"] = True
        state["openhands_build"] = result
        state["openhands_review"] = result  # Backward-compatible output field.
        write_json(state["run_id"], "openhands_build.json", result)
        state.setdefault("llm_calls", []).append(
            {"agent": "openhands", "provider": _provider_name(config["model"]), "status": "built"}
        )
        complete_agent(state, "openhands")
    except Exception as exc:  # Keep the deterministic Builder output available.
        set_agent_status(state, "openhands", "error")
        state.setdefault("errors", []).append(f"OpenHands review failed: {type(exc).__name__}: {exc}")
        state.setdefault("llm_calls", []).append(
            {"agent": "openhands", "provider": _provider_name(config["model"]), "status": "error"}
        )
        if _openhands_is_required():
            raise
    return state


# Compatibility for code importing the previous post-build reviewer name.
run_openhands_reviewer = run_openhands_builder


def _openhands_config() -> dict[str, str] | None:
    if not _openhands_enabled():
        return None

    api_key = _clean_key(os.getenv("OPENHANDS_API_KEY") or os.getenv("OPENHANDS_SMOKE_API_KEY") or "")
    if not api_key:
        return None
    model = os.getenv("OPENHANDS_MODEL") or os.getenv("OPENHANDS_SMOKE_MODEL") or ""
    if not model.strip():
        return None
    return {
        "model": model.strip(),
        "api_key": api_key,
        "base_url": os.getenv("OPENHANDS_BASE_URL") or os.getenv("OPENHANDS_SMOKE_BASE_URL") or "",
    }


def _run_openhands_build(config: dict[str, str], workspace: Path, state: ProjectState) -> dict[str, Any]:
    timeout_seconds = _positive_int_env(
        "OPENHANDS_REVIEW_TIMEOUT_SECONDS", _DEFAULT_REVIEW_TIMEOUT_SECONDS
    )
    max_iterations = _positive_int_env(
        "OPENHANDS_REVIEW_MAX_ITERATIONS", _DEFAULT_REVIEW_MAX_ITERATIONS
    )
    llm = LLM(
        model=config["model"],
        api_key=config["api_key"],
        base_url=config["base_url"] or None,
        max_output_tokens=_positive_int_env("OPENHANDS_BUILDER_MAX_OUTPUT_TOKENS", 2000),
        timeout=timeout_seconds,
        num_retries=0,
        reasoning_effort="none",
    )
    agent = get_default_agent(llm=llm, cli_mode=True)
    persistence_dir = output_dir(state["run_id"]) / "openhands_persistence"
    conversation = Conversation(
        agent=agent,
        workspace=str(workspace),
        persistence_dir=str(persistence_dir),
        max_iteration_per_run=max_iterations,
        visualizer=None,
    )
    try:
        conversation.send_message(_build_task(state))
        conversation.run()
        final_message = _final_agent_message(conversation)
    finally:
        conversation.close()
    return {
        "model": config["model"],
        "workspace": str(workspace),
        "final_message": final_message,
    }


def _build_task(state: ProjectState) -> str:
    architecture = json.dumps(state.get("architecture", {}), indent=2, ensure_ascii=True)
    return (
        "You are the primary implementation agent for a generated React and Express project. "
        f"The requested product is: {state.get('idea', '')}. "
        "The current workspace contains a deterministic baseline. You must transform it into the requested app, using "
        "the complete validated architecture below as the source of truth. Implement every named UI screen and primary "
        "action, use the declared API routes and PostgreSQL tables, and remove generic labels or flows that are not in "
        "the architecture. Do not replace the project with a generic CRUD dashboard, do not invent tables or APIs, and "
        "do not modify files outside this workspace. Inspect at most two files before editing: start with src/App.jsx "
        "and server/index.js, then make your first concrete source edit by your third tool iteration. Do not spend "
        "iterations repeatedly listing files or reading package metadata. Run the existing npm validation scripts when "
        "available. You must make concrete source-code changes before finishing, then report the commands run and the "
        "changes made.\n\n"
        f"ARCHITECTURE:\n{architecture}"
    )


def _final_agent_message(conversation: Conversation) -> str:
    for event in reversed(list(conversation.state.events)):
        if isinstance(event, MessageEvent) and event.source == "agent":
            parts = [content.text for content in event.llm_message.content if hasattr(content, "text")]
            return "\n".join(parts).strip()
    return ""


def _clean_key(value: str) -> str:
    key = value.strip().strip('"').strip("'")
    return "" if key.lower() in _PLACEHOLDER_KEYS else key


def _provider_name(model: str) -> str:
    return model.split("/", maxsplit=1)[0] if "/" in model else "unknown"


def _positive_int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def _openhands_is_required() -> bool:
    return os.getenv("OPENHANDS_BUILDER_REQUIRED", "true").strip().lower() in {"1", "true", "yes", "on"}


def _openhands_enabled() -> bool:
    return os.getenv("OPENHANDS_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}


def _project_fingerprint(workspace: Path) -> str:
    """Hash editable application sources while excluding dependencies and build output."""

    digest = hashlib.sha256()
    excluded = {"node_modules", "dist", ".swarm-preview", ".git", "openhands_persistence"}
    for path in sorted(workspace.rglob("*")):
        if not path.is_file() or excluded.intersection(path.relative_to(workspace).parts):
            continue
        relative = path.relative_to(workspace)
        if relative.name == "package-lock.json":
            continue
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()
