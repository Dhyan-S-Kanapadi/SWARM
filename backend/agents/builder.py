"""Placeholder internal Builder agent."""

from __future__ import annotations

from backend.state import ProjectState


def run_builder(state: ProjectState) -> ProjectState:
    """Create a placeholder generated file map."""
    state["generated_files"] = {
        "README.md": "# Generated SWARM App\n\nPlaceholder app output.",
        "package.json": '{"scripts":{"build":"vite build","test":"node --test"}}',
        "src/App.jsx": "export default function App() { return <h1>Generated app</h1>; }",
    }
    return state
