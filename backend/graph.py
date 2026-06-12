"""LangGraph workflow definition for SWARM agents."""

from __future__ import annotations

from collections.abc import Callable

from langgraph.graph import END, StateGraph

from backend.agents import run_analyst, run_architect, run_builder, run_pitcher
from backend.state import AgentName, ProjectState, set_agent_status, utc_now_iso
from backend.utils import write_run_summary

AgentCallable = Callable[[ProjectState], ProjectState]


def _safe_node(agent: AgentName, handler: AgentCallable) -> AgentCallable:
    """Wrap an agent node with status and error handling."""

    def node(state: ProjectState) -> ProjectState:
        set_agent_status(state, agent, "running")
        state["status"] = "running"

        try:
            next_state = handler(state)
        except Exception as exc:  # pragma: no cover - defensive graph guard
            errors = state.setdefault("errors", [])
            errors.append(f"{agent}: {exc}")
            set_agent_status(state, agent, "failed", str(exc))
            raise

        set_agent_status(next_state, agent, "complete")
        return next_state

    return node


def build_workflow():
    """Build and compile the SWARM LangGraph workflow."""
    graph = StateGraph(ProjectState)

    graph.add_node("analyst", _safe_node("analyst", run_analyst))
    graph.add_node("architect", _safe_node("architect", run_architect))
    graph.add_node("builder", _safe_node("builder", run_builder))
    graph.add_node("pitcher", _safe_node("pitcher", run_pitcher))

    graph.set_entry_point("analyst")
    graph.add_edge("analyst", "architect")
    graph.add_edge("architect", "builder")
    graph.add_edge("builder", "pitcher")
    graph.add_edge("pitcher", END)

    return graph.compile()


workflow = build_workflow()


def run_workflow(state: ProjectState) -> ProjectState:
    """Run the compiled workflow and persist a summary."""
    final_state = workflow.invoke(state)
    final_state["status"] = "complete"
    final_state["current_agent"] = None
    final_state["updated_at"] = utc_now_iso()

    summary = {
        "run_id": final_state["run_id"],
        "status": final_state["status"],
        "prompt": final_state["prompt"],
        "completed_at": final_state["updated_at"],
        "agents": final_state.get("agent_statuses", {}),
        "artifacts": {
            "requirements": bool(final_state.get("requirements")),
            "architecture": bool(final_state.get("architecture")),
            "generated_files": len(final_state.get("generated_files", {})),
            "pitch_deck": bool(final_state.get("pitch_deck")),
        },
    }
    final_state["summary"] = summary
    write_run_summary(final_state["run_id"], summary)

    return final_state
