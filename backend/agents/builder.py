"""Internal deterministic Builder agent."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from backend.state import ProjectState
from backend.utils import get_run_output_dir, write_code_file, write_json

DOMAIN_CONFIG: dict[str, dict[str, Any]] = {
    "bakery": {
        "businessType": "Bakery",
        "recordLabel": "Orders",
        "queueLabel": "Order Queue",
        "followUpLabel": "Pickup Follow Ups",
        "recordSlug": "orders",
        "services": ["Custom Cake", "Bread Order", "Pastry Box", "Catering Tray"],
    },
    "salon": {
        "businessType": "Salon",
        "recordLabel": "Appointments",
        "queueLabel": "Appointment Queue",
        "followUpLabel": "Client Follow Ups",
        "recordSlug": "appointments",
        "services": ["Haircut", "Hair Color", "Facial", "Bridal Makeup"],
    },
    "clinic": {
        "businessType": "Clinic",
        "recordLabel": "Patient Visits",
        "queueLabel": "Patient Queue",
        "followUpLabel": "Care Follow Ups",
        "recordSlug": "patient-visits",
        "services": ["Consultation", "Lab Review", "Vaccination", "Follow Up Visit"],
    },
    "fitness studio": {
        "businessType": "Fitness Studio",
        "recordLabel": "Memberships",
        "queueLabel": "Class Queue",
        "followUpLabel": "Renewal Follow Ups",
        "recordSlug": "memberships",
        "services": ["Personal Training", "Yoga Class", "Strength Batch", "Nutrition Review"],
    },
    "tuition center": {
        "businessType": "Tuition Center",
        "recordLabel": "Student Enrollments",
        "queueLabel": "Class Queue",
        "followUpLabel": "Parent Follow Ups",
        "recordSlug": "student-enrollments",
        "services": ["Math Tuition", "Science Batch", "Exam Prep", "Doubt Session"],
    },
    "generic local business": {
        "businessType": "Local Business",
        "recordLabel": "Business Records",
        "queueLabel": "Work Queue",
        "followUpLabel": "Customer Follow Ups",
        "recordSlug": "business-records",
        "services": ["General Service", "Delivery", "Consultation", "Follow Up"],
    },
}


def run_builder(state: ProjectState) -> ProjectState:
    """Generate and materialize a runnable local-business app."""
    run_dir = Path(state.get("output_dir") or get_run_output_dir(state["run_id"]))
    app_dir = run_dir / "generated-app"
    file_map = generate_internal_app(
        state["prompt"],
        state.get("requirements", {}),
        state.get("architecture", {}),
    )

    for relative_path, content in file_map.items():
        write_code_file(app_dir, relative_path, content)

    write_json(run_dir / "generated_files.json", sorted(file_map.keys()))
    state["output_dir"] = str(run_dir)
    state["generated_files"] = file_map
    return state


def format_builder_prompt(
    user_prompt: str,
    requirements: dict[str, Any],
    architecture: dict[str, Any],
) -> str:
    """Return a compact deterministic builder summary for traceability."""
    return json.dumps(
        {
            "user_prompt": user_prompt,
            "requirements": requirements,
            "architecture": architecture,
            "builder": "internal_deterministic",
        },
        indent=2,
        sort_keys=True,
    )


def generate_internal_app(
    user_prompt: str,
    requirements: dict[str, Any],
    architecture: dict[str, Any],
) -> dict[str, str]:
    """Generate the complete file map for a runnable React + Express app."""
    context = _build_context(user_prompt, requirements, architecture)
    seed_records = _seed_records(context)

    return {
        "package.json": _package_json(context),
        "index.html": _index_html(context),
        "vite.config.js": _vite_config_js(),
        "README.md": _readme(context),
        "server/index.js": _server_index_js(context),
        "server/dataStore.js": _server_data_store_js(),
        "server/app.test.js": _server_test_js(),
        "server/seed-data.json": json.dumps(seed_records, indent=2) + "\n",
        "src/main.jsx": _main_jsx(),
        "src/api.js": _api_js(context),
        "src/i18n.js": _i18n_js(context),
        "src/App.jsx": _app_jsx(context),
        "src/styles.css": _styles_css(),
    }


def _build_context(
    user_prompt: str,
    requirements: dict[str, Any],
    architecture: dict[str, Any],
) -> dict[str, Any]:
    business_problem = requirements.get("business_problem") or user_prompt
    domain_key = _detect_domain(user_prompt)
    domain = DOMAIN_CONFIG[domain_key]
    schema = architecture.get("database_schema", {})
    schema_keys = [key for key in schema if key != "metadata"]
    record_slug = domain["recordSlug"] or (schema_keys[0] if schema_keys else "records")
    record_label = domain["recordLabel"]
    metrics = _string_list(
        requirements.get("dashboard_metrics"),
        [f"total {record_label.lower()}", domain["queueLabel"].lower()],
    )
    workflows = _string_list(requirements.get("core_workflows"), ["create records", "track status"])
    services = domain["services"] or _string_list(requirements.get("data_entities"), ["General Service", "Follow Up"])

    return {
        "app_name": f"{domain['businessType']} Manager",
        "business_problem": business_problem,
        "business_type": domain["businessType"],
        "record_slug": record_slug,
        "record_label": record_label,
        "record_label_plural": record_label,
        "queue_label": domain["queueLabel"],
        "follow_up_label": domain["followUpLabel"],
        "metrics": metrics,
        "workflows": workflows,
        "services": [_title(service) for service in services[:5]],
        "builder_prompt": format_builder_prompt(user_prompt, requirements, architecture),
    }


def _package_json(context: dict[str, Any]) -> str:
    package = {
        "name": _slug(context["app_name"]),
        "version": "0.1.0",
        "private": True,
        "type": "module",
        "scripts": {
            "dev": "vite --host 127.0.0.1",
            "server": "node server/index.js",
            "check": "node --check server/index.js && node --check server/dataStore.js",
            "test": "node --test server/app.test.js",
            "build": "vite build",
        },
        "dependencies": {
            "@vitejs/plugin-react": "^5.0.0",
            "cors": "^2.8.5",
            "express": "^4.18.3",
            "vite": "^7.0.0",
            "react": "^19.0.0",
            "react-dom": "^19.0.0",
        },
        "devDependencies": {},
    }
    return json.dumps(package, indent=2) + "\n"


def _index_html(context: dict[str, Any]) -> str:
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{context["app_name"]}</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
"""


def _vite_config_js() -> str:
    return """import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    proxy: {
      "/api": "http://127.0.0.1:3001"
    }
  }
});
"""


def _readme(context: dict[str, Any]) -> str:
    return f"""# {context["app_name"]}

Generated by SWARM.AI's internal deterministic Builder agent.

Business type: {context["business_type"]}
Primary records: {context["record_label"]}
Queue label: {context["queue_label"]}
Follow-up label: {context["follow_up_label"]}

## Problem

{context["business_problem"]}

## Run

```bash
npm install
npm run server
npm run dev
```

The Express API defaults to `http://127.0.0.1:3001`.

## Checks

```bash
npm run check
npm run test
npm run build
```
"""


def _server_index_js(context: dict[str, Any]) -> str:
    record_slug = context["record_slug"]
    return f"""import cors from "cors";
import express from "express";
import {{ pathToFileURL }} from "node:url";
import {{ createDataStore }} from "./dataStore.js";

const PORT = Number(process.env.PORT || 3001);
const RECORD_ROUTE = "/api/{record_slug}";

export function createServer(options = {{}}) {{
  const app = express();
  const store = createDataStore(options);

  app.use(cors());
  app.use(express.json());

  app.get("/api/health", (request, response) => {{
    response.json({{ status: "ok", service: "{context["app_name"]}" }});
  }});

  app.get("/api/metrics", async (request, response, next) => {{
    try {{
      response.json(await store.metrics());
    }} catch (error) {{
      next(error);
    }}
  }});

  app.get(RECORD_ROUTE, async (request, response, next) => {{
    try {{
      response.json(await store.listRecords(request.query));
    }} catch (error) {{
      next(error);
    }}
  }});

  app.post(RECORD_ROUTE, async (request, response, next) => {{
    try {{
      const record = await store.createRecord(request.body);
      response.status(201).json(record);
    }} catch (error) {{
      next(error);
    }}
  }});

  app.put(`${{RECORD_ROUTE}}/:id`, async (request, response, next) => {{
    try {{
      const record = await store.updateRecord(request.params.id, request.body);
      if (!record) {{
        response.status(404).json({{ error: "Record not found" }});
        return;
      }}
      response.json(record);
    }} catch (error) {{
      next(error);
    }}
  }});

  app.delete(`${{RECORD_ROUTE}}/:id`, async (request, response, next) => {{
    try {{
      const deleted = await store.deleteRecord(request.params.id);
      if (!deleted) {{
        response.status(404).json({{ error: "Record not found" }});
        return;
      }}
      response.status(204).send();
    }} catch (error) {{
      next(error);
    }}
  }});

  app.use((error, request, response, next) => {{
    console.error(error);
    response.status(500).json({{ error: "Internal server error" }});
  }});

  return app;
}}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {{
  createServer().listen(PORT, "127.0.0.1", () => {{
    console.log(`Generated app API listening on http://127.0.0.1:${{PORT}}`);
  }});
}}
"""


def _server_data_store_js() -> str:
    return """import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import crypto from "node:crypto";

const __dirname = dirname(fileURLToPath(import.meta.url));
const DEFAULT_DATA_FILE = resolve(__dirname, "data", "records.json");
const DEFAULT_SEED_FILE = resolve(__dirname, "seed-data.json");

export function createDataStore(options = {}) {
  const dataFile = options.dataFile || DEFAULT_DATA_FILE;
  const seedFile = options.seedFile || DEFAULT_SEED_FILE;

  async function ensureData() {
    await mkdir(dirname(dataFile), { recursive: true });
    try {
      await readFile(dataFile, "utf-8");
    } catch {
      const seed = JSON.parse(await readFile(seedFile, "utf-8"));
      await writeFile(dataFile, JSON.stringify(seed, null, 2) + "\\n", "utf-8");
    }
  }

  async function readRecords() {
    await ensureData();
    return JSON.parse(await readFile(dataFile, "utf-8"));
  }

  async function writeRecords(records) {
    await mkdir(dirname(dataFile), { recursive: true });
    await writeFile(dataFile, JSON.stringify(records, null, 2) + "\\n", "utf-8");
  }

  return {
    async listRecords(filters = {}) {
      const records = await readRecords();
      const search = String(filters.search || "").trim().toLowerCase();
      const status = String(filters.status || "").trim().toLowerCase();
      return records.filter((record) => {
        const matchesSearch = !search || [record.name, record.service, record.notes]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(search));
        const matchesStatus = !status || String(record.status).toLowerCase() === status;
        return matchesSearch && matchesStatus;
      });
    },

    async createRecord(input) {
      const records = await readRecords();
      const now = new Date().toISOString();
      const record = {
        id: crypto.randomUUID(),
        name: String(input.name || "New record"),
        service: String(input.service || "General"),
        status: String(input.status || "open"),
        notes: String(input.notes || ""),
        createdAt: now,
        updatedAt: now
      };
      records.unshift(record);
      await writeRecords(records);
      return record;
    },

    async updateRecord(id, updates) {
      const records = await readRecords();
      const index = records.findIndex((record) => record.id === id);
      if (index === -1) {
        return null;
      }
      records[index] = {
        ...records[index],
        ...updates,
        id,
        updatedAt: new Date().toISOString()
      };
      await writeRecords(records);
      return records[index];
    },

    async deleteRecord(id) {
      const records = await readRecords();
      const nextRecords = records.filter((record) => record.id !== id);
      if (nextRecords.length === records.length) {
        return false;
      }
      await writeRecords(nextRecords);
      return true;
    },

    async metrics() {
      const records = await readRecords();
      const open = records.filter((record) => record.status === "open").length;
      const inProgress = records.filter((record) => record.status === "in-progress").length;
      const completed = records.filter((record) => record.status === "completed").length;
      const followUps = records.filter((record) => record.status === "follow-up").length;
      return {
        total: records.length,
        open,
        inProgress,
        completed,
        followUps
      };
    }
  };
}
"""


def _server_test_js() -> str:
    return """import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { createDataStore } from "./dataStore.js";

test("data store supports CRUD, search, filters, and metrics", async () => {
  const dir = await mkdtemp(join(tmpdir(), "swarm-generated-"));
  const dataFile = join(dir, "records.json");
  const seedFile = join(dir, "seed-data.json");
  await writeFile(seedFile, JSON.stringify([
    { id: "seed-1", name: "Asha", service: "Consultation", status: "open", notes: "first", createdAt: "2026-01-01T00:00:00.000Z", updatedAt: "2026-01-01T00:00:00.000Z" }
  ]), "utf-8");

  try {
    const store = createDataStore({ dataFile, seedFile });
    assert.equal((await store.listRecords()).length, 1);

    const created = await store.createRecord({ name: "Ravi", service: "Delivery", status: "in-progress", notes: "priority" });
    assert.equal(created.name, "Ravi");
    assert.equal((await store.listRecords({ search: "priority" })).length, 1);
    assert.equal((await store.listRecords({ status: "in-progress" })).length, 1);

    const updated = await store.updateRecord(created.id, { status: "completed" });
    assert.equal(updated.status, "completed");

    const metrics = await store.metrics();
    assert.equal(metrics.total, 2);
    assert.equal(metrics.completed, 1);

    assert.equal(await store.deleteRecord(created.id), true);
    assert.equal(await store.deleteRecord("missing"), false);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});
"""


def _main_jsx() -> str:
    return """import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
"""


def _api_js(context: dict[str, Any]) -> str:
    record_route = f"/api/{context['record_slug']}"
    template = """const API_BASE = import.meta.env.VITE_API_BASE || "";
const RECORD_ROUTE = "__RECORD_ROUTE__";

export async function fetchMetrics() {
  return request("/api/metrics");
}

export async function fetchRecords(filters = {}) {
  const params = new URLSearchParams();
  if (filters.search) params.set("search", filters.search);
  if (filters.status) params.set("status", filters.status);
  const query = params.toString();
  return request(`${RECORD_ROUTE}${query ? `?${query}` : ""}`);
}

export async function createRecord(record) {
  return request(RECORD_ROUTE, {
    method: "POST",
    body: JSON.stringify(record)
  });
}

export async function updateRecord(id, updates) {
  return request(`${RECORD_ROUTE}/${id}`, {
    method: "PUT",
    body: JSON.stringify(updates)
  });
}

export async function deleteRecord(id) {
  await request(`${RECORD_ROUTE}/${id}`, { method: "DELETE" });
}

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  if (response.status === 204) {
    return null;
  }
  return response.json();
}
"""
    return template.replace("__RECORD_ROUTE__", record_route)


def _i18n_js(context: dict[str, Any]) -> str:
    labels = {
        "appName": context["app_name"],
        "businessType": context["business_type"],
        "recordLabel": context["record_label"],
        "queueLabel": context["queue_label"],
        "followUpLabel": context["follow_up_label"],
        "dashboard": "Dashboard",
        "records": "Records",
        "search": "Search",
        "status": "Status",
        "service": "Service",
        "notes": "Notes",
    }
    return f"export const labels = {json.dumps(labels, indent=2)};\n"


def _app_jsx(context: dict[str, Any]) -> str:
    services = json.dumps(context["services"])
    business_problem = _jsx_text(context["business_problem"])
    domain_markers = json.dumps(
        {
            "businessType": context["business_type"],
            "recordLabel": context["record_label"],
            "queueLabel": context["queue_label"],
            "followUpLabel": context["follow_up_label"],
        },
        indent=2,
    )
    return f"""import {{ useEffect, useMemo, useState }} from "react";
import {{ createRecord, deleteRecord, fetchMetrics, fetchRecords, updateRecord }} from "./api.js";
import {{ labels }} from "./i18n.js";

const SERVICES = {services};
const STATUSES = ["open", "in-progress", "completed", "follow-up"];
const DOMAIN_MARKERS = {domain_markers};

const emptyForm = {{
  name: "",
  service: SERVICES[0] || "General",
  status: "open",
  notes: ""
}};

export default function App() {{
  const [records, setRecords] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function load() {{
    setLoading(true);
    setError("");
    try {{
      const [nextRecords, nextMetrics] = await Promise.all([
        fetchRecords({{ search, status }}),
        fetchMetrics()
      ]);
      setRecords(nextRecords);
      setMetrics(nextMetrics);
    }} catch (loadError) {{
      setError(loadError.message);
    }} finally {{
      setLoading(false);
    }}
  }}

  useEffect(() => {{
    load();
  }}, [search, status]);

  const visibleMetrics = useMemo(() => [
    ["Total", metrics?.total ?? 0],
    ["Open", metrics?.open ?? 0],
    ["In Progress", metrics?.inProgress ?? 0],
    ["Completed", metrics?.completed ?? 0],
    ["Follow Ups", metrics?.followUps ?? 0]
  ], [metrics]);

  async function handleSubmit(event) {{
    event.preventDefault();
    await createRecord(form);
    setForm(emptyForm);
    await load();
  }}

  async function advanceStatus(record) {{
    const index = STATUSES.indexOf(record.status);
    const nextStatus = STATUSES[(index + 1) % STATUSES.length];
    await updateRecord(record.id, {{ status: nextStatus }});
    await load();
  }}

  return (
    <main className="app-shell">
      <section className="hero">
        <div>
          <p className="eyebrow">{{DOMAIN_MARKERS.businessType}} workflow app</p>
          <h1>{{labels.appName}}</h1>
          <p>{business_problem}</p>
        </div>
      </section>

      <section className="metrics-grid">
        {{visibleMetrics.map(([label, value]) => (
          <article className="metric" key={{label}}>
            <span>{{label}}</span>
            <strong>{{value}}</strong>
          </article>
        ))}}
      </section>

      <section className="workspace">
        <form className="panel form-panel" onSubmit={{handleSubmit}}>
          <h2>New {{labels.recordLabel}}</h2>
          <label>
            Name
            <input value={{form.name}} onChange={{(event) => setForm({{ ...form, name: event.target.value }})}} required />
          </label>
          <label>
            {{labels.service}}
            <select value={{form.service}} onChange={{(event) => setForm({{ ...form, service: event.target.value }})}}>
              {{SERVICES.map((service) => <option key={{service}}>{{service}}</option>)}}
            </select>
          </label>
          <label>
            {{labels.status}}
            <select value={{form.status}} onChange={{(event) => setForm({{ ...form, status: event.target.value }})}}>
              {{STATUSES.map((item) => <option key={{item}} value={{item}}>{{item}}</option>)}}
            </select>
          </label>
          <label>
            {{labels.notes}}
            <textarea value={{form.notes}} onChange={{(event) => setForm({{ ...form, notes: event.target.value }})}} />
          </label>
          <button type="submit">Add {{labels.recordLabel}}</button>
        </form>

        <section className="panel list-panel">
          <div className="list-header">
            <div>
              <h2>{{DOMAIN_MARKERS.queueLabel}}</h2>
              <p className="section-note">{{DOMAIN_MARKERS.followUpLabel}}</p>
            </div>
            <div className="filters">
              <input placeholder={{labels.search}} value={{search}} onChange={{(event) => setSearch(event.target.value)}} />
              <select value={{status}} onChange={{(event) => setStatus(event.target.value)}}>
                <option value="">All statuses</option>
                {{STATUSES.map((item) => <option key={{item}} value={{item}}>{{item}}</option>)}}
              </select>
            </div>
          </div>

          {{error && <p className="error">{{error}}</p>}}
          {{loading ? (
            <p className="muted">Loading records...</p>
          ) : records.length === 0 ? (
            <p className="muted">No records match the current filters.</p>
          ) : (
            <div className="records">
              {{records.map((record) => (
                <article className="record" key={{record.id}}>
                  <div>
                    <h3>{{record.name}}</h3>
                    <p>{{record.service}} · {{record.notes || "No notes"}}</p>
                  </div>
                  <span className={{`status ${{record.status}}`}}>{{record.status}}</span>
                  <div className="record-actions">
                    <button type="button" onClick={{() => advanceStatus(record)}}>Next status</button>
                    <button type="button" className="danger" onClick={{async () => {{ await deleteRecord(record.id); await load(); }}}}>Delete</button>
                  </div>
                </article>
              ))}}
            </div>
          )}}
        </section>
      </section>
    </main>
  );
}}
"""


def _styles_css() -> str:
    return """:root {
  color: #1f2933;
  background: #f6f8fb;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
}

button,
input,
select,
textarea {
  font: inherit;
}

button {
  border: 0;
  border-radius: 8px;
  background: #1565c0;
  color: white;
  cursor: pointer;
  padding: 0.7rem 0.9rem;
}

button.danger {
  background: #b42318;
}

.app-shell {
  margin: 0 auto;
  max-width: 1180px;
  padding: 24px;
}

.hero {
  align-items: center;
  background: linear-gradient(135deg, #0f5f8f, #18836f);
  border-radius: 8px;
  color: white;
  display: flex;
  min-height: 210px;
  padding: 32px;
}

.hero h1 {
  font-size: clamp(2rem, 4vw, 3.7rem);
  line-height: 1;
  margin: 0 0 12px;
}

.hero p {
  max-width: 760px;
}

.eyebrow {
  font-size: 0.8rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.metrics-grid {
  display: grid;
  gap: 16px;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  margin: 22px 0;
}

.metric,
.panel {
  background: white;
  border: 1px solid #d9e2ec;
  border-radius: 8px;
}

.metric {
  padding: 18px;
}

.metric span {
  color: #52606d;
  display: block;
}

.metric strong {
  display: block;
  font-size: 2rem;
  margin-top: 6px;
}

.workspace {
  display: grid;
  gap: 18px;
  grid-template-columns: minmax(280px, 360px) 1fr;
}

.panel {
  padding: 20px;
}

.form-panel {
  align-self: start;
}

.form-panel label {
  display: grid;
  gap: 6px;
  margin-bottom: 14px;
}

input,
select,
textarea {
  border: 1px solid #bcccdc;
  border-radius: 8px;
  padding: 0.65rem;
  width: 100%;
}

textarea {
  min-height: 96px;
  resize: vertical;
}

.list-header {
  align-items: center;
  display: flex;
  gap: 16px;
  justify-content: space-between;
}

.filters {
  display: grid;
  gap: 10px;
  grid-template-columns: minmax(170px, 1fr) minmax(130px, 160px);
}

.records {
  display: grid;
  gap: 12px;
}

.record {
  align-items: center;
  border: 1px solid #e4e7eb;
  border-radius: 8px;
  display: grid;
  gap: 14px;
  grid-template-columns: 1fr auto auto;
  padding: 14px;
}

.record h3,
.record p {
  margin: 0;
}

.section-note {
  color: #697586;
  margin: 0;
}

.status {
  background: #e0f2fe;
  border-radius: 999px;
  color: #075985;
  padding: 0.35rem 0.7rem;
}

.status.completed {
  background: #dcfce7;
  color: #166534;
}

.status.follow-up {
  background: #fef3c7;
  color: #92400e;
}

.record-actions {
  display: flex;
  gap: 8px;
}

.muted {
  color: #697586;
}

.error {
  color: #b42318;
}

@media (max-width: 780px) {
  .app-shell {
    padding: 16px;
  }

  .workspace,
  .record,
  .list-header,
  .filters {
    grid-template-columns: 1fr;
  }

  .list-header {
    align-items: stretch;
    display: grid;
  }
}
"""


def _seed_records(context: dict[str, Any]) -> list[dict[str, str]]:
    services = context["services"] or ["General"]
    names = ["Asha", "Ravi", "Meera", "Kabir"]
    statuses = ["open", "in-progress", "completed", "follow-up"]
    return [
        {
            "id": f"seed-{index + 1}",
            "name": f"{name} {context['record_label']}",
            "service": services[index % len(services)],
            "status": statuses[index % len(statuses)],
            "notes": (
                f"{context['business_type']} seed data for {context['queue_label']} "
                f"and {context['follow_up_label']}"
            ),
            "createdAt": f"2026-01-0{index + 1}T09:00:00.000Z",
            "updatedAt": f"2026-01-0{index + 1}T09:00:00.000Z",
        }
        for index, name in enumerate(names)
    ]


def _string_list(value: Any, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return fallback
    cleaned = [str(item).strip() for item in value if str(item).strip()]
    return cleaned or fallback


def _detect_domain(prompt: str) -> str:
    normalized = prompt.lower()
    if any(term in normalized for term in ("salon", "saloon", "beauty", "spa", "hair", "makeup", "barber")):
        return "salon"
    if any(term in normalized for term in ("bakery", "baker", "cake", "bread", "pastry")):
        return "bakery"
    if any(term in normalized for term in ("clinic", "doctor", "patient", "medical", "dentist", "therapy")):
        return "clinic"
    if any(term in normalized for term in ("fitness", "gym", "trainer", "yoga", "workout")):
        return "fitness studio"
    if any(term in normalized for term in ("tuition", "coaching", "student", "class", "teacher", "academy")):
        return "tuition center"
    return "generic local business"


def _title(value: str) -> str:
    return " ".join(word.capitalize() for word in re.split(r"[\s_-]+", value) if word)


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "swarm-generated-app"


def _jsx_text(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("{", "&#123;")
        .replace("}", "&#125;")
    )


def _app_name(problem: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", problem)[:4]
    if not words:
        return "SWARM Generated App"
    return f"{_title(' '.join(words))} Manager"
