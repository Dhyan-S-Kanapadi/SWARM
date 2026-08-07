from collections.abc import Callable

from langgraph.graph import END, StateGraph

from backend.agents.analyst import run_analyst
from backend.agents.architect import run_architect
from backend.agents.builder import run_builder
from backend.agents.pitcher import run_pitcher
from backend.state import ProjectState
from backend.utils import append_error, write_run_summary


def _safe_node(name: str, fn):
    def wrapped(state: ProjectState) -> ProjectState:
        if state.get("fatal_error"):
            write_run_summary(state)
            return state
        try:
            next_state = fn(state)
        except Exception as exc:
            append_error(state, f"{name} node failed: {exc}")
            state["current_agent"] = name
            state["fatal_error"] = True
            next_state = state
        write_run_summary(next_state)
        return next_state

    return wrapped


def build_graph():
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


def build_post_builder_graph(
    pitcher_node: Callable[[ProjectState], ProjectState] = run_pitcher,
):
    """Create the continuation used after an externally submitted Builder result."""

    graph = StateGraph(ProjectState)
    graph.add_node("pitcher", _safe_node("pitcher", pitcher_node))
    graph.set_entry_point("pitcher")
    graph.add_edge("pitcher", END)
    return graph.compile()


workflow = build_graph()
post_builder_workflow = build_post_builder_graph()
