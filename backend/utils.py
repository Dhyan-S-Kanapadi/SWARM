"""Filesystem and persistence utilities for SWARM runs."""

from __future__ import annotations

import json
import os
import re
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


def strip_markdown_fences(text: str) -> str:
    """Remove a single wrapping Markdown code fence from text."""
    stripped = text.strip()
    fence_match = re.fullmatch(r"```(?:json|JSON)?\s*(.*?)\s*```", stripped, re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()
    return stripped


def extract_json_text(text: str) -> str:
    """Extract the first complete JSON object or array from model output."""
    stripped = strip_markdown_fences(text)
    starts = [index for index in (stripped.find("{"), stripped.find("[")) if index != -1]
    if not starts:
        raise ValueError("No JSON object or array found in text.")

    start = min(starts)
    opening = stripped[start]
    closing = "}" if opening == "{" else "]"
    depth = 0
    in_string = False
    escaped = False

    for index in range(start, len(stripped)):
        char = stripped[index]

        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return stripped[start : index + 1]

    raise ValueError("JSON text is incomplete.")


def repair_json_text(text: str) -> str:
    """Apply conservative repairs for common LLM JSON formatting mistakes."""
    repaired = extract_json_text(text)
    repaired = re.sub(r",(\s*[}\]])", r"\1", repaired)
    repaired = repaired.replace("\u201c", '"').replace("\u201d", '"')
    repaired = repaired.replace("\u2018", "'").replace("\u2019", "'")
    return repaired


def parse_json_text(text: str) -> Any:
    """Parse JSON from raw text, fenced Markdown, or prose-wrapped output."""
    json_text = extract_json_text(text)
    try:
        return json.loads(json_text)
    except json.JSONDecodeError:
        return json.loads(repair_json_text(json_text))


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
