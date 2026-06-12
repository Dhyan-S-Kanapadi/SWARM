"""Filesystem and persistence utilities for SWARM runs."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_OUTPUT_ROOT = Path(os.getenv("SWARM_OUTPUT_DIR", "outputs"))
RUN_SUMMARY_FILE = "summary.json"


def ensure_output_root(root: str | Path | None = None) -> Path:
    """Create and return the output root directory."""
    output_root = Path(root) if root is not None else DEFAULT_OUTPUT_ROOT
    output_root.mkdir(parents=True, exist_ok=True)
    return output_root


def get_run_output_dir(
    run_id: str,
    root: str | Path | None = None,
    create: bool = True,
) -> Path:
    """Return the output directory for a run."""
    output_root = ensure_output_root(root)
    run_dir = _safe_child_path(output_root, run_id)
    if create:
        run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def write_json(path: str | Path, data: Any) -> Path:
    """Write JSON data with stable formatting."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def read_json(path: str | Path, default: Any = None) -> Any:
    """Read JSON data, returning default when the file is absent."""
    source = Path(path)
    if not source.exists():
        return default
    return json.loads(source.read_text(encoding="utf-8"))


def write_text(path: str | Path, content: str) -> Path:
    """Write UTF-8 text content."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def read_text(path: str | Path, default: str | None = None) -> str | None:
    """Read UTF-8 text, returning default when the file is absent."""
    source = Path(path)
    if not source.exists():
        return default
    return source.read_text(encoding="utf-8")


def write_run_summary(
    run_id: str,
    summary: dict[str, Any],
    root: str | Path | None = None,
) -> Path:
    """Persist a run summary file."""
    return write_json(get_run_output_dir(run_id, root) / RUN_SUMMARY_FILE, summary)


def load_run_summary(
    run_id: str,
    root: str | Path | None = None,
) -> dict[str, Any] | None:
    """Load a run summary file if it exists."""
    return read_json(get_run_output_dir(run_id, root, create=False) / RUN_SUMMARY_FILE)


def write_code_file(run_dir: str | Path, relative_path: str | Path, content: str) -> Path:
    """Write a generated code file below a run directory."""
    target = _safe_child_path(Path(run_dir), relative_path)
    return write_text(target, content)


def read_code_file(
    run_dir: str | Path,
    relative_path: str | Path,
    default: str | None = None,
) -> str | None:
    """Read a generated code file below a run directory."""
    target = _safe_child_path(Path(run_dir), relative_path)
    return read_text(target, default)


def _safe_child_path(parent: Path, child: str | Path) -> Path:
    """Resolve child below parent and reject traversal outside parent."""
    parent_resolved = parent.resolve()
    target = (parent / child).resolve()

    try:
        target.relative_to(parent_resolved)
    except ValueError as exc:
        raise ValueError(f"Path escapes allowed directory: {child}") from exc

    return target
