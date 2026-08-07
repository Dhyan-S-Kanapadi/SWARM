import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcp.server.fastmcp import FastMCP

from backend.graph import post_builder_workflow
from backend.state import initial_agent_statuses
from backend.utils import (
    QUALITY_MIN_SCORE,
    QUALITY_TARGET_SCORE,
    append_error,
    complete_agent,
    evaluate_generated_app,
    list_run_summaries,
    load_run_from_disk,
    read_code_files,
    read_quality_report,
    utc_now,
    write_code_files,
    write_run_summary,
)

load_dotenv(PROJECT_ROOT / ".env")

MCP_HOST = os.getenv("SWARM_MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.getenv("SWARM_MCP_PORT", "8931"))
MCP_TRANSPORT = os.getenv("SWARM_MCP_TRANSPORT", "stdio")

mcp = FastMCP(
    "SWARM.AI",
    instructions=(
        "Use these tools from Trae Builder to fetch SWARM.AI generated build prompts "
        "and submit completed project files back to SWARM.AI."
    ),
    host=MCP_HOST,
    port=MCP_PORT,
    streamable_http_path="/mcp",
    sse_path="/sse",
)


@mcp.tool()
def list_swarm_runs() -> dict[str, Any]:
    """List SWARM.AI runs known from persisted output summaries."""
    return {"runs": list_run_summaries()}


@mcp.tool()
def get_builder_prompt(run_id: str = "") -> dict[str, Any]:
    """Get the builder prompt for a specific run, or for the latest run if run_id is empty."""
    resolved_run_id = run_id or _latest_run_id()
    state = _load_state_or_raise(resolved_run_id)
    return {
        "run_id": resolved_run_id,
        "idea": state.get("idea", ""),
        "builder_prompt": state.get("builder_prompt", ""),
        "status": state.get("agent_statuses", initial_agent_statuses()).get("builder", "unknown"),
    }


@mcp.tool()
def get_project_context(run_id: str = "") -> dict[str, Any]:
    """Get requirements, architecture, and builder prompt for a SWARM.AI run."""
    resolved_run_id = run_id or _latest_run_id()
    state = _load_state_or_raise(resolved_run_id)
    return {
        "run_id": resolved_run_id,
        "idea": state.get("idea", ""),
        "requirements": state.get("requirements", {}),
        "architecture": state.get("architecture", {}),
        "builder_prompt": state.get("builder_prompt", ""),
        "errors": state.get("errors", []),
    }


@mcp.tool()
def get_quality_report(run_id: str = "") -> dict[str, Any]:
    """Get the latest SWARM.AI quality report and revision instructions for a generated app."""
    resolved_run_id = run_id or _latest_run_id()
    _load_state_or_raise(resolved_run_id)
    report = read_quality_report(resolved_run_id)
    if not report:
        raise ValueError(f"No quality report found for run {resolved_run_id}")
    return report


@mcp.tool()
def get_submitted_code_files(run_id: str = "") -> dict[str, Any]:
    """Get the latest source files previously submitted to SWARM.AI for revision."""
    resolved_run_id = run_id or _latest_run_id()
    _load_state_or_raise(resolved_run_id)
    files = read_code_files(resolved_run_id)
    if not files:
        raise ValueError(f"No submitted files found for run {resolved_run_id}")
    return {
        "run_id": resolved_run_id,
        "file_count": len(files),
        "files": files,
    }


@mcp.tool()
def submit_code_files(run_id: str, files: dict[str, str]) -> dict[str, Any]:
    """Submit generated project files from Trae back to SWARM.AI."""
    if not files:
        raise ValueError("files must contain at least one filepath to content entry")

    state = _load_state_or_raise(run_id)
    write_code_files(run_id, files)
    state["code_files"] = read_code_files(run_id)

    quality_report = evaluate_generated_app(run_id)
    if quality_report["score"] < QUALITY_MIN_SCORE:
        state.setdefault("agent_statuses", initial_agent_statuses())["builder"] = "waiting_for_trae"
        state["current_agent"] = "builder"
        state["done"] = False
        state["updated_at"] = utc_now()
        write_run_summary(state)
        return {
            "run_id": run_id,
            "accepted": False,
            "saved_file_count": len(state["code_files"]),
            "quality_report": quality_report,
            "quality_target_score": QUALITY_TARGET_SCORE,
            "message": (
                f"SWARM.AI did not accept this build yet. Minimum score is {QUALITY_MIN_SCORE}; "
                "fix the revision_instructions "
                "and call submit_code_files again with the improved project."
            ),
        }

    complete_agent(state, "builder")
    state = post_builder_workflow.invoke(state)
    state["current_agent"] = "done"
    state["done"] = True
    state["updated_at"] = utc_now()
    write_run_summary(state)
    return {
        "run_id": run_id,
        "accepted": True,
        "saved_file_count": len(state["code_files"]),
        "quality_report": quality_report,
        "quality_target_score": QUALITY_TARGET_SCORE,
        "builder_status": state.get("agent_statuses", {}).get("builder"),
        "pitcher_status": state.get("agent_statuses", {}).get("pitcher"),
        "done": state.get("done", False),
    }


@mcp.tool()
def mark_builder_error(run_id: str, message: str) -> dict[str, Any]:
    """Record a Trae Builder failure on a SWARM.AI run."""
    state = _load_state_or_raise(run_id)
    append_error(state, f"Trae Builder failed: {message}", agent="builder")
    state["current_agent"] = "done"
    state["done"] = True
    write_run_summary(state)
    return {
        "run_id": run_id,
        "builder_status": state.get("agent_statuses", {}).get("builder"),
        "errors": state.get("errors", []),
    }


@mcp.resource("swarm://runs/latest/builder-prompt")
def latest_builder_prompt_resource() -> str:
    """Latest SWARM.AI builder prompt as plain text."""
    state = _load_state_or_raise(_latest_run_id())
    return state.get("builder_prompt", "")


def _latest_run_id() -> str:
    summaries = list_run_summaries()
    if not summaries:
        raise ValueError("No SWARM.AI runs found. Start a run with POST /run first.")
    return max(summaries, key=lambda item: item.get("created_at") or item.get("updated_at") or "")["run_id"]


def _load_state_or_raise(run_id: str):
    if not run_id:
        raise ValueError("run_id is required")
    state = load_run_from_disk(run_id)
    if not state:
        raise ValueError(f"SWARM.AI run not found: {run_id}")
    return state


if __name__ == "__main__":
    if MCP_TRANSPORT not in {"stdio", "sse", "streamable-http"}:
        raise ValueError("SWARM_MCP_TRANSPORT must be one of: stdio, sse, streamable-http")
    mcp.run(transport=MCP_TRANSPORT)
