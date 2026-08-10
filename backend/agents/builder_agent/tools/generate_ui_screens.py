"""Generate architecture-driven React screens for a generated application.

The functions in this module return the ``{relative_path: content}`` contract
used by the deterministic Builder LangGraph. The generated app uses
plain React, CSS, and the existing English/Hindi/Kannada translation object
pattern; it does not assume a fixed record type or API surface.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from textwrap import dedent
from typing import Any


_SCREEN_KEYS = {"name", "route", "purpose", "data_needed", "primary_actions", "states"}
_ROUTE_KEYS = {"method", "path", "description", "request_body", "response_shape", "validation_rules"}


def generate_ui_screens(
    ui_screens: Sequence[Mapping[str, Any]], api_routes: Sequence[Mapping[str, Any]]
) -> dict[str, str]:
    """Return React frontend files generated from screen and API-route contracts.

    A screen may only request GET routes declared in ``api_routes``. This keeps
    ``data_needed`` executable and prevents the generator from inventing an API
    endpoint when the Architect contract is incomplete.
    """

    routes = _normalise_routes(api_routes)
    screens = _normalise_screens(ui_screens, routes)
    config = {"uiScreens": screens, "apiRoutes": routes}
    encoded_config = json.dumps(config, indent=2)

    app = _APP_TEMPLATE.replace("__CONFIG__", encoded_config)
    i18n = _i18n_source(screens)
    return {
        "src/App.jsx": dedent(app).strip() + "\n",
        "src/api.js": dedent(_API_SOURCE).strip() + "\n",
        "src/i18n.js": i18n,
        "src/styles.css": dedent(_STYLES_SOURCE).strip() + "\n",
    }


def _normalise_routes(api_routes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(api_routes, Sequence) or isinstance(api_routes, (str, bytes)):
        raise ValueError("api_routes must be a list")

    routes: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for route in api_routes:
        if not isinstance(route, Mapping):
            raise ValueError("each api route must be a dictionary")
        missing = sorted(_ROUTE_KEYS - set(route))
        if missing:
            raise ValueError(f"api route is missing required keys: {', '.join(missing)}")
        method = str(route["method"]).upper()
        path = route["path"]
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            raise ValueError(f"unsupported HTTP method '{method}'")
        if not isinstance(path, str) or not path.startswith("/api/"):
            raise ValueError(f"route path '{path}' must start with /api/")
        if (method, path) in seen:
            raise ValueError(f"duplicate route '{method} {path}'")
        if not isinstance(route["request_body"], (Mapping, type(None))):
            raise ValueError(f"request_body for '{method} {path}' must be an object or null")
        seen.add((method, path))
        routes.append(
            {
                "method": method,
                "path": path,
                "description": str(route["description"]),
                "requestBody": dict(route["request_body"] or {}),
                "responseShape": route["response_shape"],
                "isCollection": _is_collection_shape(route["response_shape"]),
                "validationRules": [str(rule) for rule in route["validation_rules"]],
            }
        )
    return routes


def _normalise_screens(
    ui_screens: Sequence[Mapping[str, Any]], routes: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    if not isinstance(ui_screens, Sequence) or isinstance(ui_screens, (str, bytes)) or not ui_screens:
        raise ValueError("ui_screens must be a non-empty list")

    get_paths = {route["path"] for route in routes if route["method"] == "GET" and ":" not in route["path"]}
    screens: list[dict[str, Any]] = []
    names: set[str] = set()
    for screen in ui_screens:
        if not isinstance(screen, Mapping):
            raise ValueError("each ui screen must be a dictionary")
        missing = sorted(_SCREEN_KEYS - set(screen))
        if missing:
            raise ValueError(f"ui screen is missing required keys: {', '.join(missing)}")
        name = screen["name"]
        if not isinstance(name, str) or not name.strip():
            raise ValueError("ui screen name must be a non-empty string")
        if name in names:
            raise ValueError(f"duplicate ui screen name '{name}'")
        names.add(name)
        route = screen["route"]
        if not isinstance(route, str) or not route.startswith("/"):
            raise ValueError(f"ui screen '{name}' has an invalid route")
        data_needed = screen["data_needed"]
        if not isinstance(data_needed, list) or not all(isinstance(path, str) for path in data_needed):
            raise ValueError(f"data_needed for screen '{name}' must be a list of API paths")
        unknown_paths = sorted(set(data_needed) - get_paths)
        if unknown_paths:
            raise ValueError(
                f"screen '{name}' references GET routes that are not declared or need parameters: {', '.join(unknown_paths)}"
            )
        actions = screen["primary_actions"]
        states = screen["states"]
        if not isinstance(actions, list) or not all(isinstance(action, str) for action in actions):
            raise ValueError(f"primary_actions for screen '{name}' must be a list of strings")
        if not isinstance(states, list) or not all(isinstance(state, str) for state in states):
            raise ValueError(f"states for screen '{name}' must be a list of strings")
        resource_path = _screen_resource_path(route, name, data_needed, routes)
        create_path = _screen_create_path(route, name, routes)
        screens.append(
            {
                "name": name,
                "route": route,
                "purpose": str(screen["purpose"]),
                "dataNeeded": data_needed,
                "primaryActions": actions,
                "states": states,
                "resourcePath": resource_path,
                "createPath": create_path,
            }
        )
    return screens


def _is_collection_shape(response_shape: Any) -> bool:
    """Accept both JSON collections and Architect's common ``"[{...}]"`` shorthand."""

    return isinstance(response_shape, list) or (
        isinstance(response_shape, str) and response_shape.lstrip().startswith("[")
    )


def _screen_resource_path(
    screen_route: str, name: str, data_needed: Sequence[str], routes: Sequence[Mapping[str, Any]]
) -> str | None:
    """Find the collection route represented by a screen, if it has one."""

    collection_paths = {
        route["path"] for route in routes if route["method"] == "GET" and route.get("isCollection")
    }
    direct = next((path for path in data_needed if path in collection_paths), None)
    if direct:
        return direct
    return _api_path_for_screen(screen_route, name, [route for route in routes if route["method"] == "GET"])


def _screen_create_path(screen_route: str, name: str, routes: Sequence[Mapping[str, Any]]) -> str | None:
    return _api_path_for_screen(screen_route, name, [route for route in routes if route["method"] == "POST"])


def _api_path_for_screen(screen_route: str, name: str, routes: Sequence[Mapping[str, Any]]) -> str | None:
    screen_segments = {segment.lower() for segment in screen_route.split("/") if segment and segment != "new"}
    name_tokens = {token.lower() for token in name.replace("Form", "").replace("_", " ").split()}
    candidates = []
    for route in routes:
        path = route["path"]
        segments = [segment for segment in path.split("/") if segment and segment != "api" and not segment.startswith(":")]
        resource = segments[0] if segments else ""
        if resource in screen_segments or resource.rstrip("s") in name_tokens or resource in name_tokens:
            candidates.append(path)
    return candidates[0] if len(candidates) == 1 else None


def _i18n_source(screens: Sequence[Mapping[str, Any]]) -> str:
    screen_labels = {screen["name"]: screen["name"] for screen in screens}
    labels = {
        "search": "Search",
        "filter": "Filter",
        "create": "Create",
        "edit": "Edit",
        "delete": "Delete",
        "save": "Save",
        "cancel": "Cancel",
        "loading": "Loading...",
        "empty": "No records match the current view.",
        "refresh": "Refresh",
        "records": "Records",
        "data": "Data",
    }
    translations = {
        locale: {"screens": screen_labels, **labels}
        for locale in ("en", "hi", "kn")
    }
    return dedent(
        """
        export const translations = __TRANSLATIONS__;

        export function formatValue(value, locale) {
          if (value === null || value === undefined) return "-";
          if (typeof value === "number") {
            return new Intl.NumberFormat(locale === "hi" ? "hi-IN" : locale === "kn" ? "kn-IN" : "en-IN").format(value);
          }
          return String(value);
        }
        """
    ).replace("__TRANSLATIONS__", json.dumps(translations, indent=2)).strip() + "\n"


_API_SOURCE = r'''
const headers = { "Content-Type": "application/json" };

async function request(path, options = {}) {
  const response = await fetch(path, { headers, ...options });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.error || `Request failed: ${response.status}`);
  }
  if (response.status === 204) return null;
  return response.json();
}

export const api = {
  get: (path, params = {}) => {
    const query = new URLSearchParams(params);
    const suffix = query.size ? `?${query}` : "";
    return request(`${path}${suffix}`);
  },
  send: (path, method, body) => request(path, { method, body: JSON.stringify(body) }),
  remove: (path) => request(path, { method: "DELETE" }),
};
'''


_APP_TEMPLATE = r'''
import { useEffect, useMemo, useState } from "react";
import { api } from "./api.js";
import { formatValue, translations } from "./i18n.js";

const config = __CONFIG__;

export default function App() {
  const [activeScreenName, setActiveScreenName] = useState(config.uiScreens[0].name);
  const [locale, setLocale] = useState("en");
  const activeScreen = config.uiScreens.find((screen) => screen.name === activeScreenName) || config.uiScreens[0];
  const t = translations[locale];

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">SWARM-generated local app</p>
          <h1>{t.screens[activeScreen.name] || activeScreen.name}</h1>
          <p>{activeScreen.purpose}</p>
        </div>
        <div className="toolbar">
          <select value={locale} onChange={(event) => setLocale(event.target.value)} aria-label="Language">
            <option value="en">English</option>
            <option value="hi">Hindi</option>
            <option value="kn">Kannada</option>
          </select>
        </div>
      </header>

      <nav className="screen-tabs" aria-label="Application screens">
        {config.uiScreens.map((screen) => (
          <button
            className={screen.name === activeScreen.name ? "active" : ""}
            key={screen.name}
            onClick={() => setActiveScreenName(screen.name)}
          >
            {t.screens[screen.name] || screen.name}
          </button>
        ))}
      </nav>

      <Screen key={activeScreen.name} screen={activeScreen} locale={locale} t={t} />
    </main>
  );
}

function Screen({ screen, locale, t }) {
  const [data, setData] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [form, setForm] = useState(null);
  const [editing, setEditing] = useState(null);
  const actions = screen.primaryActions.map((action) => action.toLowerCase());
  const hasAction = (keywords) => actions.some((action) => keywords.some((keyword) => action.includes(keyword)));
  const dataRoutes = screen.dataNeeded.map((path) => config.apiRoutes.find((route) => route.method === "GET" && route.path === path));
  const collectionRoute = dataRoutes.find((route) => route && route.isCollection);
  const resourcePath = screen.resourcePath || collectionRoute?.path;
  const createRoute = config.apiRoutes.find((route) => route.method === "POST" && route.path === (screen.createPath || resourcePath));
  const updateRoute = config.apiRoutes.find((route) => (route.method === "PUT" || route.method === "PATCH") && route.path.startsWith(`${resourcePath}/:`));
  const deleteRoute = config.apiRoutes.find((route) => route.method === "DELETE" && route.path.startsWith(`${resourcePath}/:`));

  async function load() {
    setLoading(true);
    setError("");
    try {
      const entries = await Promise.all(screen.dataNeeded.map(async (path) => [path, await api.get(path)]));
      setData(Object.fromEntries(entries));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [screen.name]);

  const records = data[resourcePath] || [];
  const filteredRecords = useMemo(() => {
    if (!search) return records;
    const term = search.toLowerCase();
    return records.filter((record) => JSON.stringify(record).toLowerCase().includes(term));
  }, [records, search]);
  const formFields = createRoute?.requestBody || updateRoute?.requestBody || {};

  function startCreate() {
    setEditing(null);
    setForm(Object.fromEntries(Object.keys(formFields).map((field) => [field, ""])));
  }

  function startEdit(record) {
    setEditing(record);
    setForm(Object.fromEntries(Object.keys(formFields).map((field) => [field, record[field] ?? ""])));
  }

  async function save(event) {
    event.preventDefault();
    try {
      if (editing && updateRoute) {
        await api.send(updateRoute.path.replace(":id", editing.id), updateRoute.method, form);
      } else if (createRoute) {
        await api.send(createRoute.path, createRoute.method, form);
      }
      setForm(null);
      setEditing(null);
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function remove(record) {
    if (!deleteRoute) return;
    try {
      await api.remove(deleteRoute.path.replace(":id", record.id));
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <>
      {error && <div className="alert">{error}</div>}

      <section className="screen-header">
        <div>
          <h2>{t.screens[screen.name] || screen.name}</h2>
          <p>{screen.purpose}</p>
        </div>
        <button onClick={load}>{t.refresh}</button>
      </section>

      <section className="screen-layout">
        <section className="panel data-panel">
          <div className="section-title">
            <h2>{t.data}</h2>
            <span>{loading ? t.loading : `${filteredRecords.length} ${t.records.toLowerCase()}`}</span>
          </div>
          {hasAction(["search", "filter"]) && (
            <div className="filters">
              <input placeholder={t.search} value={search} onChange={(event) => setSearch(event.target.value)} />
            </div>
          )}
          {loading ? <div className="empty">{t.loading}</div> : (
            <DataViews data={data} records={filteredRecords} locale={locale} emptyLabel={t.empty} onEdit={hasAction(["edit"]) ? startEdit : null} onDelete={hasAction(["delete"]) ? remove : null} />
          )}
        </section>

        {(hasAction(["add", "create", "register", "submit", "new"]) || form) && createRoute && (
          <section className="panel form-panel">
            <div className="section-title">
              <h2>{editing ? t.edit : t.create}</h2>
              {!form && <button onClick={startCreate}>{t.create}</button>}
            </div>
            {form && <RecordForm fields={formFields} value={form} onChange={setForm} onSubmit={save} onCancel={() => { setForm(null); setEditing(null); }} t={t} />}
          </section>
        )}
      </section>

      <section className="screen-states" aria-label="Screen states">
        {screen.states.map((state) => <span key={state}>{state}</span>)}
      </section>
    </>
  );
}

function DataViews({ data, records, locale, emptyLabel, onEdit, onDelete }) {
  const entries = Object.entries(data);
  if (!entries.length || (records.length === 0 && entries.every(([, value]) => Array.isArray(value)))) {
    return <div className="empty">{emptyLabel}</div>;
  }
  return (
    <div className="data-views">
      {entries.map(([path, value]) => Array.isArray(value) ? (
        <RecordList key={path} records={path === entries.find(([, candidate]) => Array.isArray(candidate))?.[0] ? records : value} locale={locale} onEdit={onEdit} onDelete={onDelete} />
      ) : (
        <MetricGrid key={path} data={value} locale={locale} />
      ))}
    </div>
  );
}

function MetricGrid({ data, locale }) {
  if (!data || typeof data !== "object") return null;
  return <div className="metrics-grid">{Object.entries(data).map(([label, value]) => <div className="metric" key={label}><span>{label}</span><strong>{formatValue(value, locale)}</strong></div>)}</div>;
}

function RecordList({ records, locale, onEdit, onDelete }) {
  if (!records.length) return null;
  return <div className="records">{records.map((record, index) => <article className="record-card" key={record.id ?? index}><div className="record-values">{Object.entries(record).map(([label, value]) => <span key={label}><strong>{label}</strong>{formatValue(value, locale)}</span>)}</div>{(onEdit || onDelete) && <div className="actions">{onEdit && <button onClick={() => onEdit(record)}>Edit</button>}{onDelete && <button className="danger" onClick={() => onDelete(record)}>Delete</button>}</div>}</article>)}</div>;
}

function RecordForm({ fields, value, onChange, onSubmit, onCancel, t }) {
  return <form className="form-grid" onSubmit={onSubmit}>{Object.entries(fields).map(([field, type]) => <label key={field}>{field}<input type={inputType(type, field)} value={value[field] ?? ""} onChange={(event) => onChange({ ...value, [field]: inputType(type, field) === "number" ? Number(event.target.value) : event.target.value })} required={String(type).toLowerCase().includes("required")} /></label>)}<div className="actions"><button className="primary" type="submit">{t.save}</button><button type="button" onClick={onCancel}>{t.cancel}</button></div></form>;
}

function inputType(type, field) {
  const text = `${type} ${field}`.toLowerCase();
  if (text.includes("date")) return "date";
  if (text.includes("number") || text.includes("amount") || text.includes("count")) return "number";
  return "text";
}
'''


_STYLES_SOURCE = r'''
* { box-sizing: border-box; }
body { margin: 0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f4f6f8; color: #111827; }
button, input, select { font: inherit; }
button { border: 0; border-radius: 6px; padding: 10px 14px; background: #e5e7eb; color: #111827; cursor: pointer; font-weight: 700; }
button:hover { background: #d1d5db; }
button.active, .primary { background: #2563eb; color: white; }
.danger { color: #991b1b; background: #fee2e2; }
.app-shell { max-width: 1280px; margin: 0 auto; padding: 24px; }
.topbar { display: flex; align-items: flex-start; justify-content: space-between; gap: 24px; padding: 28px; border-radius: 10px; background: #111827; color: white; }
.topbar h1 { margin: 8px 0; font-size: 36px; line-height: 1.1; }
.topbar p { margin: 0; color: #cbd5e1; max-width: 760px; line-height: 1.6; }
.eyebrow { color: #93c5fd !important; text-transform: uppercase; letter-spacing: .14em; font-size: 12px; font-weight: 800; }
.toolbar select, .filters input, input { min-height: 42px; width: 100%; border: 1px solid #cbd5e1; border-radius: 6px; padding: 10px 12px; background: white; }
.screen-tabs { display: flex; gap: 8px; overflow-x: auto; padding: 16px 0; }
.screen-tabs button { white-space: nowrap; }
.screen-header { display: flex; align-items: start; justify-content: space-between; gap: 16px; margin: 12px 0; }
.screen-header h2 { margin: 0 0 6px; font-size: 22px; }
.screen-header p { margin: 0; color: #64748b; }
.screen-layout { display: grid; grid-template-columns: minmax(0, 1fr) 360px; gap: 18px; align-items: start; }
.panel { background: white; border: 1px solid #d9dee7; border-radius: 8px; padding: 18px; box-shadow: 0 1px 2px rgba(15, 23, 42, .04); }
.section-title { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; margin-bottom: 16px; }
.section-title h2 { margin: 0; font-size: 18px; }
.section-title span { color: #64748b; font-size: 13px; }
.filters { margin-bottom: 14px; }
.metrics-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-bottom: 14px; }
.metric { background: white; border: 1px solid #d9dee7; border-radius: 8px; padding: 18px; }
.metric span { color: #64748b; font-size: 13px; text-transform: uppercase; letter-spacing: .1em; }
.metric strong { display: block; margin-top: 8px; font-size: 24px; }
.records { display: grid; gap: 12px; }
.record-card { border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px; }
.record-values { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.record-values span { display: grid; gap: 2px; color: #475569; overflow-wrap: anywhere; }
.record-values strong { color: #0f172a; font-size: 12px; text-transform: uppercase; letter-spacing: .06em; }
.actions { display: flex; gap: 8px; margin-top: 14px; flex-wrap: wrap; }
.form-grid { display: grid; gap: 12px; }
label { display: grid; gap: 6px; color: #334155; font-weight: 700; font-size: 13px; }
.empty, .alert { margin-top: 16px; border-radius: 8px; padding: 12px 14px; }
.empty { background: #f8fafc; color: #64748b; border: 1px dashed #cbd5e1; }
.alert { border: 1px solid #fecaca; background: #fff1f2; color: #9f1239; }
.screen-states { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 18px; }
.screen-states span { background: #e0e7ff; color: #3730a3; border-radius: 999px; padding: 5px 9px; font-size: 12px; }
@media (max-width: 860px) { .app-shell { padding: 14px; } .topbar, .screen-header { flex-direction: column; } .screen-layout { grid-template-columns: 1fr; } .metrics-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .record-values { grid-template-columns: 1fr 1fr; } }
'''


if __name__ == "__main__":
    example_routes = [
        {"method": "GET", "path": "/api/metrics", "description": "Dashboard metrics", "request_body": None, "response_shape": {"total": "number"}, "validation_rules": []},
        {"method": "GET", "path": "/api/items", "description": "List records", "request_body": None, "response_shape": [{"id": "number", "title": "string"}], "validation_rules": []},
        {"method": "POST", "path": "/api/items", "description": "Create record", "request_body": {"title": "string"}, "response_shape": {"id": "number"}, "validation_rules": ["title required"]},
        {"method": "PUT", "path": "/api/items/:id", "description": "Update record", "request_body": {"title": "string"}, "response_shape": {"id": "number"}, "validation_rules": ["record must exist"]},
        {"method": "DELETE", "path": "/api/items/:id", "description": "Delete record", "request_body": None, "response_shape": None, "validation_rules": []},
    ]
    example_screens = [
        {"name": "Dashboard", "route": "/", "purpose": "View metrics and records", "data_needed": ["/api/metrics", "/api/items"], "primary_actions": ["search"], "states": ["loading", "error", "empty", "ready"]},
        {"name": "Record form", "route": "/records", "purpose": "Create and edit records", "data_needed": ["/api/items"], "primary_actions": ["create", "edit", "delete"], "states": ["saving", "validation error", "ready"]},
    ]
    for path, content in generate_ui_screens(example_screens, example_routes).items():
        print(f"--- {path} ---")
        print(content)
