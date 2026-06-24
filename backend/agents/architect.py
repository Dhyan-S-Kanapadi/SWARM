import json
import os

from backend.agents.llm import allow_fallback_for_idea, call_groq_json
from backend.state import ProjectState
from backend.utils import complete_agent, load_prompt, set_agent_status, write_json

MAX_TOKENS = 2800


def run_architect(state: ProjectState) -> ProjectState:
    set_agent_status(state, "architect", "running")
    try:
        state["architecture"] = call_groq_json(
            agent_name="architect",
            system_prompt=load_prompt("architect_prompt.txt"),
            user_content=json.dumps(compact_requirements(state.get("requirements", {})), separators=(",", ":")),
            temperature=0.25,
            max_tokens=MAX_TOKENS,
        )
        state.setdefault("llm_calls", []).append({"agent": "architect", "provider": "groq", "status": "success"})
        complete_agent(state, "architect")
    except Exception as exc:
        if allow_architect_parse_fallback(exc):
            state.setdefault("errors", []).append(f"Architect used compact architecture after malformed LLM JSON: {exc}")
            state["architecture"] = fallback_architecture(state.get("requirements", {}))
            state.setdefault("llm_calls", []).append({"agent": "architect", "provider": "groq", "status": "json_recovered"})
            complete_agent(state, "architect")
            write_json(state["run_id"], "architecture.json", state["architecture"])
            return state
        if not allow_fallback_for_idea(state.get("idea", "")):
            set_agent_status(state, "architect", "error")
            state["fatal_error"] = True
            raise
        state.setdefault("errors", []).append(f"Architect used fallback after LLM error: {exc}")
        state["architecture"] = fallback_architecture(state.get("requirements", {}))
        state.setdefault("llm_calls", []).append({"agent": "architect", "provider": "groq", "status": "fallback"})
        complete_agent(state, "architect")

    write_json(state["run_id"], "architecture.json", state["architecture"])
    return state


def allow_architect_parse_fallback(exc: Exception) -> bool:
    enabled = os.getenv("SWARM_ALLOW_ARCHITECT_PARSE_FALLBACK", "true").strip().lower() in {"1", "true", "yes", "on"}
    if not enabled:
        return False
    message = str(exc).lower()
    return any(
        signal in message
        for signal in (
            "unterminated string",
            "json",
            "expecting",
            "extra data",
            "invalid control character",
        )
    )


def compact_requirements(requirements: dict) -> dict:
    return {
        "problem_statement": _shorten(requirements.get("problem_statement", "")),
        "target_audience": _shorten(requirements.get("target_audience", "")),
        "local_context": requirements.get("local_context", {}),
        "core_features": _short_list(requirements.get("core_features", []), 8),
        "business_rules": _short_list(requirements.get("business_rules", []), 8),
        "automation_requirements": _short_objects(requirements.get("automation_requirements", []), 5),
        "localization_requirements": requirements.get("localization_requirements", {}),
        "data_entities": _short_objects(requirements.get("data_entities", []), 5),
        "workflow_map": _short_objects(requirements.get("workflow_map", []), 5),
        "seed_data": _short_list(requirements.get("seed_data", []), 6),
        "acceptance_criteria": _short_list(requirements.get("acceptance_criteria", []), 6),
    }


def _short_list(items, limit: int) -> list:
    if not isinstance(items, list):
        return []
    return [_shorten(item) for item in items[:limit]]


def _short_objects(items, limit: int) -> list:
    if not isinstance(items, list):
        return []
    compacted = []
    for item in items[:limit]:
        if isinstance(item, dict):
            compacted.append({key: _shorten(value) for key, value in item.items()})
        else:
            compacted.append(_shorten(item))
    return compacted


def _shorten(value, limit: int = 180):
    if isinstance(value, list):
        return [_shorten(item, limit) for item in value[:6]]
    if isinstance(value, dict):
        return {key: _shorten(item, limit) for key, item in value.items()}
    text = str(value)
    return text if len(text) <= limit else f"{text[: limit - 3]}..."


def fallback_architecture(requirements: dict) -> dict:
    app_name = "swarm-localops"
    return {
        "tech_stack": {
            "frontend": "React with Vite",
            "backend": "Node.js with Express",
            "database": "Local JSON persistence with seed data",
            "styling": "Plain CSS responsive dashboard",
            "testing": "Node test runner plus vite build",
            "local_run_strategy": "npm install, npm run dev, npm run check, npm run test, npm run build",
        },
        "app_shell": {
            "app_name": app_name,
            "navigation": ["Dashboard", "Records", "Form", "Language switcher"],
            "primary_dashboard_widgets": ["total records", "open records", "upcoming records", "revenue"],
            "empty_states": ["No records match filters", "Loading records", "Validation error"],
            "responsive_requirements": "Single-column mobile layout and two-column desktop layout",
        },
        "database_schema": {
            "work_items": {
                "fields": {
                    "id": "integer primary key",
                    "customerName": "string required",
                    "phone": "string",
                    "title": "string required",
                    "category": "string",
                    "status": "enum new|confirmed|in_progress|completed",
                    "priority": "enum low|medium|high",
                    "dueDate": "date required",
                    "amount": "number",
                    "notes": "string",
                    "language": "string",
                },
                "indexes": ["status", "dueDate", "customerName"],
                "relationships": [],
                "seed_records": requirements.get("seed_data", []),
            }
        },
        "api_routes": [
            {
                "method": "GET",
                "path": "/api/health",
                "description": "Health check",
                "request_body": None,
                "response_shape": {"ok": True},
                "validation_rules": [],
            },
            {
                "method": "GET",
                "path": "/api/items",
                "description": "List, search, and filter records",
                "request_body": None,
                "response_shape": [{"id": "number", "customerName": "string"}],
                "validation_rules": ["status query is optional", "search query is optional"],
            },
            {
                "method": "POST",
                "path": "/api/items",
                "description": "Create record",
                "request_body": {"customerName": "string", "title": "string", "dueDate": "date", "status": "string"},
                "response_shape": {"id": "number"},
                "validation_rules": ["customerName required", "title required", "dueDate required", "valid status"],
            },
            {
                "method": "PUT",
                "path": "/api/items/:id",
                "description": "Update record",
                "request_body": {"status": "string"},
                "response_shape": {"id": "number"},
                "validation_rules": ["record must exist", "valid status"],
            },
            {
                "method": "DELETE",
                "path": "/api/items/:id",
                "description": "Delete record",
                "request_body": None,
                "response_shape": None,
                "validation_rules": ["id must exist or no-op"],
            },
            {
                "method": "GET",
                "path": "/api/metrics",
                "description": "Dashboard metrics",
                "request_body": None,
                "response_shape": {"total": "number", "open": "number", "upcoming": "number", "revenue": "number"},
                "validation_rules": [],
            },
        ],
        "ui_screens": [
            {
                "name": "Dashboard",
                "route": "/",
                "purpose": "Show metrics and operational status",
                "data_needed": ["/api/metrics", "/api/items"],
                "primary_actions": ["filter", "search", "reset demo data"],
                "states": ["loading", "error", "empty", "ready"],
            },
            {
                "name": "Record form",
                "route": "/",
                "purpose": "Create and edit work records",
                "data_needed": ["/api/items"],
                "primary_actions": ["create", "edit", "delete"],
                "states": ["validation error", "saving", "ready"],
            },
        ],
        "project_modules": [
            {"name": "server", "responsibility": "Express API and persistence", "files": ["server/index.js", "server/dataStore.js"]},
            {"name": "frontend", "responsibility": "React dashboard and CRUD UI", "files": ["src/App.jsx", "src/api.js", "src/i18n.js"]},
            {"name": "tests", "responsibility": "Data workflow test", "files": ["server/app.test.js"]},
        ],
        "state_management": {
            "frontend_state": ["items", "metrics", "form", "filters", "locale", "loading", "error"],
            "server_state": "local JSON file resettable from seed-data.json",
            "forms": "controlled React form with required fields",
            "filters": "search and status query params",
            "optimistic_updates": "reload after mutation for reliability",
        },
        "localization_plan": {
            "language_files": ["src/i18n.js"],
            "default_locale": "en",
            "locale_switching": "dropdown in topbar",
            "translated_surfaces": ["labels", "buttons", "empty states", "navigation"],
            "formatting_rules": "Intl DateTimeFormat and NumberFormat for India",
        },
        "automation_jobs": [
            {
                "name": "metric calculation",
                "schedule_or_trigger": "on metrics API request",
                "logic": "aggregate total/open/completed/upcoming/revenue from records",
                "user_visible_result": "dashboard widgets update",
            }
        ],
        "validation_plan": [
            {"scenario": "create record", "steps": ["fill form", "save"], "expected_result": "record appears in list"},
            {"scenario": "filter records", "steps": ["select status"], "expected_result": "only matching records show"},
            {"scenario": "language switch", "steps": ["choose Hindi or Kannada"], "expected_result": "labels translate"},
        ],
        "folder_structure": "package.json\nindex.html\nserver/\n  index.js\n  dataStore.js\n  seed-data.json\n  app.test.js\nsrc/\n  main.jsx\n  App.jsx\n  api.js\n  i18n.js\n  styles.css\nREADME.md",
        "build_constraints": ["no paid APIs", "local-first", "must pass npm run check/test/build", "responsive UI"],
    }
