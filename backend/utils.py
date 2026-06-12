import json
import re
import shutil
import subprocess
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.state import AGENT_ORDER, ProjectState, initial_agent_statuses

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
PROMPTS_DIR = BASE_DIR / "prompts"
OUTPUTS_DIR = BASE_DIR / "outputs"
GENERATED_APPS_DIR = PROJECT_ROOT / "generated_apps"
QUALITY_MIN_SCORE = 90
QUALITY_TARGET_SCORE = 90
GENERATED_FILE_EXCLUDES = {
    ".git",
    ".next",
    ".turbo",
    ".vite",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
}


def load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


def strip_markdown_fences(text: str) -> str:
    cleaned = text.strip()
    fence_match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.DOTALL | re.IGNORECASE)
    if fence_match:
        return fence_match.group(1).strip()
    return cleaned


def parse_json_response(text: str) -> dict[str, Any]:
    cleaned = strip_markdown_fences(text)
    try:
        return json.loads(cleaned, strict=False)
    except json.JSONDecodeError:
        extracted = extract_json_object(cleaned)
        if extracted is None:
            raise
        return json.loads(extracted, strict=False)


def extract_json_object(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]

    return None


def output_dir(run_id: str) -> Path:
    path = OUTPUTS_DIR / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(run_id: str, filename: str, data: Any) -> None:
    path = output_dir(run_id) / filename
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def write_text(run_id: str, filename: str, data: str) -> None:
    path = output_dir(run_id) / filename
    path.write_text(data, encoding="utf-8")


def write_code_files(run_id: str, files: dict[str, str]) -> None:
    root = output_dir(run_id) / "code_files"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    for relative_path, content in files.items():
        if _has_excluded_part(Path(relative_path)):
            continue
        safe_path = _safe_output_path(root, relative_path)
        safe_path.parent.mkdir(parents=True, exist_ok=True)
        safe_path.write_text(content, encoding="utf-8")


def write_run_summary(state: dict[str, Any]) -> None:
    summary = {
        "run_id": state.get("run_id"),
        "idea": state.get("idea", ""),
        "current_agent": state.get("current_agent"),
        "agent_statuses": state.get("agent_statuses", initial_agent_statuses()),
        "done": state.get("done", False),
        "errors": state.get("errors", []),
        "llm_calls": state.get("llm_calls", []),
        "created_at": state.get("created_at"),
        "updated_at": state.get("updated_at"),
        "has_requirements": bool(state.get("requirements")),
        "has_architecture": bool(state.get("architecture")),
        "code_file_count": len(state.get("code_files", {})),
        "has_pitch_deck": bool(state.get("pitch_deck")),
    }
    write_json(str(state["run_id"]), "run_summary.json", summary)


def append_error(state: dict[str, Any], message: str, agent: str | None = None) -> None:
    state.setdefault("errors", []).append(message)
    state["updated_at"] = utc_now()
    if agent:
        set_agent_status(state, agent, "error")


def set_agent_status(state: dict[str, Any], agent: str, status: str) -> None:
    state.setdefault("agent_statuses", initial_agent_statuses())
    state["agent_statuses"][agent] = status
    state["current_agent"] = agent
    state["updated_at"] = utc_now()


def complete_agent(state: dict[str, Any], agent: str) -> None:
    statuses = state.setdefault("agent_statuses", initial_agent_statuses())
    if statuses.get(agent) != "error":
        statuses[agent] = "done"
    state["updated_at"] = utc_now()


def load_run_from_disk(run_id: str) -> ProjectState | None:
    root = OUTPUTS_DIR / run_id
    summary = _read_json(root / "run_summary.json")
    if not summary:
        return None

    state: ProjectState = {
        "run_id": run_id,
        "idea": summary.get("idea", ""),
        "requirements": _read_json(root / "requirements.json") or {},
        "architecture": _read_json(root / "architecture.json") or {},
        "builder_prompt": _read_text(root / "builder_prompt.txt"),
        "code_files": read_code_files(run_id),
        "pitch_deck": _read_json(root / "pitch_deck.json") or {},
        "current_agent": summary.get("current_agent", "unknown"),
        "agent_statuses": summary.get("agent_statuses", initial_agent_statuses()),
        "errors": summary.get("errors", []),
        "llm_calls": summary.get("llm_calls", []),
        "done": summary.get("done", False),
        "created_at": summary.get("created_at", ""),
        "updated_at": summary.get("updated_at", ""),
    }
    return state


def list_run_summaries() -> list[dict[str, Any]]:
    if not OUTPUTS_DIR.exists():
        return []
    summaries = []
    for path in OUTPUTS_DIR.iterdir():
        if not path.is_dir():
            continue
        summary = _read_json(path / "run_summary.json")
        if summary:
            summaries.append(summary)
    return sorted(summaries, key=lambda item: item.get("run_id", ""), reverse=True)


def read_code_files(run_id: str) -> dict[str, str]:
    root = OUTPUTS_DIR / run_id / "code_files"
    if not root.exists():
        return {}
    files: dict[str, str] = {}
    for path in root.rglob("*"):
        if path.is_file() and not _has_excluded_part(path.relative_to(root)):
            files[path.relative_to(root).as_posix()] = path.read_text(encoding="utf-8")
    return files


def build_artifact_summary(run_id: str) -> dict[str, Any]:
    state = load_run_from_disk(run_id)
    if not state:
        return {}

    code_files = state.get("code_files", {})
    package_json = {}
    if "package.json" in code_files:
        try:
            package_json = json.loads(code_files["package.json"])
        except json.JSONDecodeError:
            package_json = {}

    extensions: dict[str, int] = {}
    for path in code_files:
        suffix = Path(path).suffix.lower() or "[none]"
        extensions[suffix] = extensions.get(suffix, 0) + 1

    return {
        "run_id": run_id,
        "idea": state.get("idea", ""),
        "done": state.get("done", False),
        "current_agent": state.get("current_agent", "unknown"),
        "agent_statuses": state.get("agent_statuses", initial_agent_statuses()),
        "errors": state.get("errors", []),
        "llm_calls": state.get("llm_calls", []),
        "created_at": state.get("created_at", ""),
        "updated_at": state.get("updated_at", ""),
        "artifact_counts": {
            "requirements": int(bool(state.get("requirements"))),
            "architecture": int(bool(state.get("architecture"))),
            "code_files": len(code_files),
            "pitch_deck_fields": len(state.get("pitch_deck", {})),
        },
        "code_file_paths": sorted(code_files.keys()),
        "code_file_extensions": extensions,
        "detected_app": {
            "name": package_json.get("name", ""),
            "scripts": package_json.get("scripts", {}),
            "dependencies": sorted((package_json.get("dependencies") or {}).keys()),
            "dev_dependencies": sorted((package_json.get("devDependencies") or {}).keys()),
        },
        "download_url": f"/download/{run_id}",
        "validation": read_validation_report(run_id),
        "quality": read_quality_report(run_id),
    }


def build_demo_summary(run_id: str) -> dict[str, Any]:
    state = load_run_from_disk(run_id)
    if not state:
        return {}

    artifacts = build_artifact_summary(run_id)
    requirements = state.get("requirements", {})
    architecture = state.get("architecture", {})
    pitch = state.get("pitch_deck", {})
    validation = artifacts.get("validation") or {}
    quality = artifacts.get("quality") or {}

    return {
        "run_id": run_id,
        "idea": state.get("idea", ""),
        "status": {
            "done": state.get("done", False),
            "current_agent": state.get("current_agent", "unknown"),
            "agent_statuses": state.get("agent_statuses", initial_agent_statuses()),
            "errors": state.get("errors", []),
            "llm_calls": state.get("llm_calls", []),
        },
        "story": {
            "problem": requirements.get("problem_statement", ""),
            "audience": requirements.get("target_audience", ""),
            "local_context": requirements.get("local_context", {}),
            "solution": pitch.get("solution", ""),
            "tagline": pitch.get("tagline", ""),
            "call_to_action": pitch.get("call_to_action", ""),
        },
        "product": {
            "features": requirements.get("core_features", []),
            "personas": requirements.get("primary_personas", []),
            "workflows": requirements.get("workflow_map", []),
            "business_rules": requirements.get("business_rules", []),
            "localization": requirements.get("localization_requirements", {}),
            "acceptance_criteria": requirements.get("acceptance_criteria", []),
            "success_metrics": requirements.get("success_metrics", []),
            "tech_stack": architecture.get("tech_stack", {}),
            "api_routes": architecture.get("api_routes", []),
            "ui_screens": architecture.get("ui_screens", []),
            "validation_plan": architecture.get("validation_plan", []),
        },
        "delivery": {
            "code_file_count": artifacts.get("artifact_counts", {}).get("code_files", 0),
            "app_name": artifacts.get("detected_app", {}).get("name", ""),
            "download_url": artifacts.get("download_url", ""),
            "validation_status": validation.get("status", "not_run"),
            "quality_score": quality.get("score"),
            "quality_grade": quality.get("grade", "not_run"),
            "validation_checks": [
                {
                    "name": check.get("name"),
                    "returncode": check.get("returncode"),
                    "duration_seconds": check.get("duration_seconds"),
                }
                for check in validation.get("checks", [])
            ],
        },
        "pitch": pitch,
    }


def evaluate_generated_app(run_id: str) -> dict[str, Any]:
    state = load_run_from_disk(run_id)
    if not state:
        raise FileNotFoundError(f"Run not found: {run_id}")

    code_files = read_code_files(run_id)
    requirements = state.get("requirements", {})
    architecture = state.get("architecture", {})
    validation = read_validation_report(run_id) or {}

    package_json = _parse_package_json(code_files)
    file_paths = sorted(code_files.keys())
    corpus = _code_corpus(code_files)

    checks = [
        _score_project_completeness(file_paths, package_json, corpus),
        _score_dynamic_workflows(corpus),
        _score_requirement_coverage(requirements, architecture, corpus),
        _score_localization(requirements, architecture, file_paths, corpus),
        _score_runnable_quality(package_json, validation, corpus),
        _score_demo_polish(file_paths, corpus),
    ]

    score = min(100, sum(check["score"] for check in checks))
    report = {
        "run_id": run_id,
        "score": score,
        "grade": quality_grade(score),
        "status": _quality_status(score),
        "minimum_score": QUALITY_MIN_SCORE,
        "target_score": QUALITY_TARGET_SCORE,
        "updated_at": utc_now(),
        "checks": checks,
        "strengths": [item for check in checks for item in check["passed"]],
        "revision_instructions": _revision_instructions(checks),
    }
    write_json(run_id, "quality_report.json", report)
    return report


def read_quality_report(run_id: str) -> dict[str, Any] | None:
    report = _read_json(OUTPUTS_DIR / run_id / "quality_report.json")
    return report if isinstance(report, dict) else None


def quality_grade(score: int) -> str:
    if score >= 90:
        return "10/10"
    if score >= 82:
        return "8.5/10"
    if score >= 70:
        return "demo_ready"
    if score >= 50:
        return "needs_work"
    return "weak"


def _quality_status(score: int) -> str:
    if score >= QUALITY_TARGET_SCORE:
        return "target_met"
    if score >= QUALITY_MIN_SCORE:
        return "accepted"
    return "needs_revision"


def _parse_package_json(code_files: dict[str, str]) -> dict[str, Any]:
    try:
        return json.loads(code_files.get("package.json", "{}"))
    except json.JSONDecodeError:
        return {}


def _code_corpus(code_files: dict[str, str]) -> str:
    searchable_extensions = {
        ".css",
        ".html",
        ".js",
        ".jsx",
        ".json",
        ".md",
        ".mjs",
        ".sql",
        ".ts",
        ".tsx",
    }
    chunks = []
    for path, content in code_files.items():
        if Path(path).suffix.lower() in searchable_extensions:
            chunks.append(f"\n--- {path} ---\n{content[:12000]}")
    return "\n".join(chunks).lower()


def _score_project_completeness(file_paths: list[str], package_json: dict[str, Any], corpus: str) -> dict[str, Any]:
    passed = []
    missing = []
    score = 0

    if package_json:
        score += 3
        passed.append("Includes package.json")
    else:
        missing.append("Add package.json with runnable scripts and dependencies")

    scripts = package_json.get("scripts") or {}
    for script_name in ("dev", "build"):
        if script_name in scripts:
            score += 2
            passed.append(f"Includes npm script: {script_name}")
        else:
            missing.append(f"Add npm script: {script_name}")

    if any(path.lower() == "readme.md" for path in file_paths):
        score += 2
        passed.append("Includes README.md")
    else:
        missing.append("Add README.md with setup and demo flow")

    if any(path.startswith(("src/", "client/", "frontend/")) for path in file_paths):
        score += 2
        passed.append("Includes frontend source")
    else:
        missing.append("Add frontend source files")

    if any(path.startswith(("server/", "api/", "backend/")) for path in file_paths) or "express" in corpus:
        score += 2
        passed.append("Includes backend/API implementation")
    else:
        missing.append("Add backend/API implementation")

    if any("seed" in path.lower() or "demo" in path.lower() for path in file_paths) or "seed" in corpus:
        score += 2
        passed.append("Includes seed or demo data")
    else:
        missing.append("Add realistic seed/demo data")

    return _quality_check("Project completeness", 15, min(score, 15), passed, missing)


def _score_dynamic_workflows(corpus: str) -> dict[str, Any]:
    signals = {
        "CRUD create/update/delete flows": ("post(", "put(", "patch(", "delete(", "create", "update", "delete"),
        "API/data fetching": ("fetch(", "axios", "query", "api."),
        "Forms and validation": ("form", "textfield", "input", "required", "validate", "zod"),
        "Filtering or search": ("filter(", "search", "query", "sort("),
        "Dashboard metrics": ("dashboard", "metric", "total", "count", "forecast", "summary"),
        "Client state management": ("usestate", "zustand", "reducer", "context", "store"),
        "Loading and error states": ("loading", "error", "empty"),
    }
    return _score_signals("Dynamic workflows", 20, corpus, signals)


def _score_requirement_coverage(requirements: dict[str, Any], architecture: dict[str, Any], corpus: str) -> dict[str, Any]:
    terms = []
    terms.extend(_important_terms(requirements.get("core_features", [])))
    terms.extend(_important_terms(requirements.get("business_rules", [])))
    terms.extend(_important_terms([screen.get("name", "") for screen in architecture.get("ui_screens", []) if isinstance(screen, dict)]))
    terms.extend(_important_terms([route.get("path", "") for route in architecture.get("api_routes", []) if isinstance(route, dict)]))
    terms = sorted(set(terms))[:25]

    if not terms:
        return _quality_check(
            "Requirement coverage",
            20,
            8,
            ["No rich requirements were available, so coverage was partially credited"],
            ["Generate richer Analyst and Architect context for stronger coverage scoring"],
        )

    matched = [term for term in terms if term in corpus]
    missing_terms = [term for term in terms if term not in corpus][:8]
    score = round(20 * (len(matched) / len(terms)))
    missing = [f"Cover requirement term in UI/API/code: {term}" for term in missing_terms]
    return _quality_check("Requirement coverage", 20, score, [f"Covers: {term}" for term in matched[:10]], missing)


def _score_localization(requirements: dict[str, Any], architecture: dict[str, Any], file_paths: list[str], corpus: str) -> dict[str, Any]:
    language_need = requirements.get("localization_requirements") or architecture.get("localization_plan") or {}
    required = bool(language_need)
    signals = {
        "Language/locale files": ("locale", "i18n", "translations", "language"),
        "Locale switcher": ("setlocale", "switch language", "language", "locale"),
        "Formatted dates/numbers": ("intl.", "tolocaledatestring", "tolocalestring", "currency"),
        "Non-English/local copy support": ("kn", "hi", "ta", "te", "mr", "ml", "bn", "gu", "pa"),
    }
    check = _score_signals("Localization readiness", 15, corpus + "\n".join(file_paths).lower(), signals)
    if not required and check["score"] < 6:
        check["score"] = 6
        check["passed"].append("No explicit localization requirement was generated")
    return check


def _score_runnable_quality(package_json: dict[str, Any], validation: dict[str, Any], corpus: str) -> dict[str, Any]:
    passed = []
    missing = []
    score = 0
    scripts = package_json.get("scripts") or {}

    for script_name, points in (("check", 3), ("test", 3), ("build", 3)):
        if script_name in scripts:
            score += points
            passed.append(f"Includes {script_name} script")
        else:
            missing.append(f"Add npm script: {script_name}")

    if validation.get("status") == "passed":
        score += 7
        passed.append("Validation report passed")
    elif validation:
        missing.append("Fix failing validation report")
    else:
        missing.append("Run SWARM validation after preview install")

    if "readme" in corpus and ("npm install" in corpus or "npm run" in corpus):
        score += 2
        passed.append("README explains local run commands")
    else:
        missing.append("Document local run commands in README")

    if ".env" in corpus or "environment" in corpus or "port" in corpus:
        score += 2
        passed.append("Documents environment/runtime configuration")
    else:
        missing.append("Document ports/env variables")

    return _quality_check("Runnable quality", 20, min(score, 20), passed, missing)


def _score_demo_polish(file_paths: list[str], corpus: str) -> dict[str, Any]:
    signals = {
        "Realistic demo data": ("seed", "demo", "sample", "mock"),
        "Daily-use dashboard": ("dashboard", "today", "upcoming", "overdue", "summary"),
        "Empty states": ("empty", "no records", "no data"),
        "Responsive layout": ("responsive", "breakpoint", "grid", "@media", "md:"),
        "README demo flow": ("demo flow", "demo", "walkthrough"),
    }
    check = _score_signals("Demo polish", 10, corpus + "\n".join(file_paths).lower(), signals)
    check["score"] = min(check["score"], 10)
    return check


def _score_signals(name: str, max_score: int, corpus: str, signals: dict[str, tuple[str, ...]]) -> dict[str, Any]:
    score_per_signal = max_score / len(signals)
    score = 0.0
    passed = []
    missing = []
    for label, keywords in signals.items():
        if any(keyword in corpus for keyword in keywords):
            score += score_per_signal
            passed.append(label)
        else:
            missing.append(label)
    return _quality_check(name, max_score, round(score), passed, [f"Add {item.lower()}" for item in missing])


def _quality_check(name: str, max_score: int, score: int, passed: list[str], missing: list[str]) -> dict[str, Any]:
    return {
        "name": name,
        "score": max(0, min(score, max_score)),
        "max_score": max_score,
        "passed": passed,
        "missing": missing,
    }


def _important_terms(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []

    ignored = {
        "and",
        "app",
        "for",
        "from",
        "into",
        "local",
        "management",
        "system",
        "that",
        "the",
        "their",
        "with",
    }
    terms = []
    for item in items:
        text = item if isinstance(item, str) else json.dumps(item)
        for term in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{3,}", text.lower()):
            if term not in ignored:
                terms.append(term)
    return terms


def _revision_instructions(checks: list[dict[str, Any]]) -> list[str]:
    instructions = []
    for check in checks:
        for item in check["missing"][:4]:
            instructions.append(f"{check['name']}: {item}")
    return instructions[:12]


def create_code_zip(run_id: str) -> Path:
    root = OUTPUTS_DIR / run_id / "code_files"
    if not root.exists():
        raise FileNotFoundError(f"No generated code files found for run {run_id}")

    zip_path = output_dir(run_id) / "generated_app.zip"
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in root.rglob("*"):
            if path.is_file() and not _has_excluded_part(path.relative_to(root)):
                archive.write(path, path.relative_to(root).as_posix())
    return zip_path


def materialize_generated_app(run_id: str) -> Path:
    files = read_code_files(run_id)
    if not files:
        raise FileNotFoundError(f"No generated code files found for run {run_id}")

    root = GENERATED_APPS_DIR / run_id
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)

    for relative_path, content in files.items():
        target = _safe_output_path(root, relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return root


def validate_generated_app(run_id: str, timeout_seconds: int = 180) -> dict[str, Any]:
    root = GENERATED_APPS_DIR / run_id
    if not root.exists():
        root = materialize_generated_app(run_id)

    package_json_path = root / "package.json"
    if not package_json_path.exists():
        report = {
            "run_id": run_id,
            "status": "failed",
            "updated_at": utc_now(),
            "checks": [
                {
                    "name": "package.json",
                    "command": "read package.json",
                    "returncode": 1,
                    "stdout": "",
                    "stderr": "Generated app does not include package.json",
                    "duration_seconds": 0,
                }
            ],
        }
        write_json(run_id, "validation_report.json", report)
        return report

    package_json = json.loads(package_json_path.read_text(encoding="utf-8"))
    scripts = package_json.get("scripts") or {}
    checks: list[dict[str, Any]] = []

    if not (root / "node_modules").exists():
        checks.append(_run_command(root, "install", ["npm.cmd", "install"], timeout_seconds))

    for script_name in ("check", "test", "build"):
        if script_name in scripts:
            checks.append(_run_command(root, script_name, ["npm.cmd", "run", script_name], timeout_seconds))

    status = "passed" if checks and all(check["returncode"] == 0 for check in checks) else "failed"
    report = {
        "run_id": run_id,
        "status": status,
        "updated_at": utc_now(),
        "checks": checks,
    }
    write_json(run_id, "validation_report.json", report)
    return report


def read_validation_report(run_id: str) -> dict[str, Any] | None:
    report = _read_json(OUTPUTS_DIR / run_id / "validation_report.json")
    return report if isinstance(report, dict) else None


def _safe_output_path(root: Path, relative_path: str) -> Path:
    target = (root / relative_path).resolve()
    root_resolved = root.resolve()
    try:
        target.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"Unsafe output path: {relative_path}")
    return target


def _has_excluded_part(path: Path) -> bool:
    return any(part in GENERATED_FILE_EXCLUDES for part in path.parts)


def _run_command(root: Path, name: str, command: list[str], timeout_seconds: int) -> dict[str, Any]:
    started_at = datetime.now(UTC)
    try:
        result = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return {
            "name": name,
            "command": " ".join(command),
            "returncode": result.returncode,
            "stdout": clean_process_output(result.stdout)[-5000:],
            "stderr": clean_process_output(result.stderr)[-5000:],
            "duration_seconds": round((datetime.now(UTC) - started_at).total_seconds(), 2),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "name": name,
            "command": " ".join(command),
            "returncode": 124,
            "stdout": clean_process_output(exc.stdout or "")[-5000:] if isinstance(exc.stdout, str) else "",
            "stderr": f"Command timed out after {timeout_seconds} seconds",
            "duration_seconds": round((datetime.now(UTC) - started_at).total_seconds(), 2),
        }


def clean_process_output(text: str) -> str:
    ansi_escape = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
    cleaned = ansi_escape.sub("", text or "")
    return cleaned.encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def utc_now() -> str:
    return datetime.now(UTC).isoformat()
