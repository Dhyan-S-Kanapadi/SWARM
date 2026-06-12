import json
import re
from textwrap import dedent

from backend.state import ProjectState
from backend.utils import complete_agent, set_agent_status, write_code_files, write_text


def format_builder_prompt(state: ProjectState) -> str:
    requirements = state.get("requirements", {})
    architecture = state.get("architecture", {})
    return dedent(
        f"""
        You are SWARM Builder, the internal code-generation agent for SWARM.AI.

        Mission:
        Build a complete local-first MVP from one plain-language idea so local business owners can create useful software in their own language.

        Product requirements:
        {json.dumps(requirements, indent=2)}

        Architecture blueprint:
        {json.dumps(architecture, indent=2)}

        Build policy:
        - Generate a runnable React + Express app.
        - Include seed data, CRUD APIs, dashboard metrics, filters, validation, localization, and README demo flow.
        - Do not depend on Trae or any paid builder service.
        - The generated app must run locally with npm scripts.
        """
    ).strip()


def i18n_js(product_name: str) -> str:
    return dedent(
        f"""
        export const translations = {{
          en: {{
            appName: "{product_name}",
            dashboard: "Dashboard",
            records: "Records",
            newRecord: "New record",
            search: "Search",
            status: "Status",
            customer: "Customer",
            dueDate: "Due date",
            followUpDate: "Follow-up date",
            amount: "Amount",
            payment: "Payment",
            service: "Service",
            assignedTo: "Assigned to",
            channel: "Channel",
            nextAction: "Next action",
            queue: "Daily queue",
            followUps: "Follow-ups due",
            pendingPayments: "Pending payments",
            localLanguage: "Local language",
            save: "Save",
            reset: "Reset demo data",
            empty: "No records match the current filters.",
          }},
          hi: {{
            appName: "{product_name}",
            dashboard: "\\u0921\\u0948\\u0936\\u092c\\u094b\\u0930\\u094d\\u0921",
            records: "\\u0930\\u093f\\u0915\\u0949\\u0930\\u094d\\u0921",
            newRecord: "\\u0928\\u092f\\u093e \\u0930\\u093f\\u0915\\u0949\\u0930\\u094d\\u0921",
            search: "\\u0916\\u094b\\u091c\\u0947\\u0902",
            status: "\\u0938\\u094d\\u0925\\u093f\\u0924\\u093f",
            customer: "\\u0917\\u094d\\u0930\\u093e\\u0939\\u0915",
            dueDate: "\\u0921\\u093f\\u0932\\u093f\\u0935\\u0930\\u0940 \\u0924\\u093e\\u0930\\u0940\\u0916",
            followUpDate: "\\u092b\\u0949\\u0932\\u094b-\\u0905\\u092a \\u0924\\u093e\\u0930\\u0940\\u0916",
            amount: "\\u0930\\u093e\\u0936\\u093f",
            payment: "\\u092d\\u0941\\u0917\\u0924\\u093e\\u0928",
            service: "\\u0938\\u0947\\u0935\\u093e",
            assignedTo: "\\u091c\\u093f\\u092e\\u094d\\u092e\\u0947\\u0926\\u093e\\u0930",
            channel: "\\u091a\\u0948\\u0928\\u0932",
            nextAction: "\\u0905\\u0917\\u0932\\u093e \\u0915\\u0926\\u092e",
            queue: "\\u0906\\u091c \\u0915\\u0940 \\u0915\\u0924\\u093e\\u0930",
            followUps: "\\u092b\\u0949\\u0932\\u094b-\\u0905\\u092a \\u092c\\u093e\\u0915\\u0940",
            pendingPayments: "\\u092c\\u0915\\u093e\\u092f\\u093e \\u092d\\u0941\\u0917\\u0924\\u093e\\u0928",
            localLanguage: "\\u0938\\u094d\\u0925\\u093e\\u0928\\u0940\\u092f \\u092d\\u093e\\u0937\\u093e",
            save: "\\u0938\\u0947\\u0935 \\u0915\\u0930\\u0947\\u0902",
            reset: "\\u0921\\u0947\\u092e\\u094b \\u0921\\u0947\\u091f\\u093e \\u0930\\u0940\\u0938\\u0947\\u091f",
            empty: "\\u0907\\u0928 \\u092b\\u093f\\u0932\\u094d\\u091f\\u0930 \\u0915\\u0947 \\u0932\\u093f\\u090f \\u0915\\u094b\\u0908 \\u0930\\u093f\\u0915\\u0949\\u0930\\u094d\\u0921 \\u0928\\u0939\\u0940\\u0902 \\u092e\\u093f\\u0932\\u093e.",
          }},
          kn: {{
            appName: "{product_name}",
            dashboard: "\\u0ca1\\u0ccd\\u0caf\\u0cbe\\u0cb6\\u0ccd\\u0cac\\u0ccb\\u0cb0\\u0ccd\\u0ca1\\u0ccd",
            records: "\\u0ca6\\u0cbe\\u0c96\\u0cb2\\u0cc6\\u0c97\\u0cb3\\u0cc1",
            newRecord: "\\u0cb9\\u0cca\\u0cb8 \\u0ca6\\u0cbe\\u0c96\\u0cb2\\u0cc6",
            search: "\\u0cb9\\u0cc1\\u0ca1\\u0cc1\\u0c95\\u0cbf",
            status: "\\u0cb8\\u0ccd\\u0ca5\\u0cbf\\u0ca4\\u0cbf",
            customer: "\\u0c97\\u0ccd\\u0cb0\\u0cbe\\u0cb9\\u0c95",
            dueDate: "\\u0ca1\\u0cc6\\u0cb2\\u0cbf\\u0cb5\\u0cb0\\u0cbf \\u0ca6\\u0cbf\\u0ca8\\u0cbe\\u0c82\\u0c95",
            followUpDate: "\\u0cab\\u0cbe\\u0cb2\\u0ccb-\\u0c85\\u0caa\\u0ccd \\u0ca6\\u0cbf\\u0ca8\\u0cbe\\u0c82\\u0c95",
            amount: "\\u0cae\\u0cca\\u0ca4\\u0ccd\\u0ca4",
            payment: "\\u0caa\\u0cbe\\u0cb5\\u0ca4\\u0cbf",
            service: "\\u0cb8\\u0cc7\\u0cb5\\u0cc6",
            assignedTo: "\\u0c9c\\u0cb5\\u0cbe\\u0cac\\u0ccd\\u0ca6\\u0cbe\\u0cb0\\u0cb0\\u0cc1",
            channel: "\\u0c9a\\u0ccd\\u0caf\\u0cbe\\u0ca8\\u0cb2\\u0ccd",
            nextAction: "\\u0cae\\u0cc1\\u0c82\\u0ca6\\u0cbf\\u0ca8 \\u0c95\\u0ccd\\u0cb0\\u0cae",
            queue: "\\u0c87\\u0c82\\u0ca6\\u0cbf\\u0ca8 \\u0c95\\u0ca4\\u0cbe\\u0cb0\\u0cc1",
            followUps: "\\u0cab\\u0cbe\\u0cb2\\u0ccb-\\u0c85\\u0caa\\u0ccd \\u0cac\\u0cbe\\u0c95\\u0cbf",
            pendingPayments: "\\u0cac\\u0cbe\\u0c95\\u0cbf \\u0caa\\u0cbe\\u0cb5\\u0ca4\\u0cbf",
            localLanguage: "\\u0cb8\\u0ccd\\u0ca5\\u0cb3\\u0cc0\\u0caf \\u0cad\\u0cbe\\u0cb7\\u0cc6",
            save: "\\u0c89\\u0cb3\\u0cbf\\u0cb8\\u0cbf",
            reset: "\\u0ca1\\u0cc6\\u0cae\\u0ccb \\u0ca1\\u0cc7\\u0c9f\\u0cbe \\u0cae\\u0cb0\\u0cc1\\u0cb9\\u0cca\\u0c82\\u0ca6\\u0cbf\\u0cb8\\u0cbf",
            empty: "\\u0c88 \\u0cab\\u0cbf\\u0cb2\\u0ccd\\u0c9f\\u0cb0\\u0ccd\\u0c97\\u0cb3\\u0cbf\\u0c97\\u0cc6 \\u0ca6\\u0cbe\\u0c96\\u0cb2\\u0cc6\\u0c97\\u0cb3\\u0cbf\\u0cb2\\u0ccd\\u0cb2.",
          }},
        }};

        export function formatCurrency(value, locale) {{
          return new Intl.NumberFormat(locale === "hi" ? "hi-IN" : locale === "kn" ? "kn-IN" : "en-IN", {{
            style: "currency",
            currency: "INR",
            maximumFractionDigits: 0,
          }}).format(value || 0);
        }}

        export function formatDate(value, locale) {{
          return new Intl.DateTimeFormat(locale === "hi" ? "hi-IN" : locale === "kn" ? "kn-IN" : "en-IN").format(new Date(value));
        }}
        """
    ).strip()


def run_builder(state: ProjectState) -> ProjectState:
    set_agent_status(state, "builder", "running")
    state["builder_prompt"] = format_builder_prompt(state)
    write_text(state["run_id"], "builder_prompt.txt", state["builder_prompt"])

    state["code_files"] = generate_internal_app(state)
    write_code_files(state["run_id"], state["code_files"])
    complete_agent(state, "builder")
    return state


def generate_internal_app(state: ProjectState) -> dict[str, str]:
    requirements = state.get("requirements", {})
    architecture = state.get("architecture", {})
    idea = state.get("idea", "Local business operations app")
    app_name = app_name_from_idea(idea)
    product_name = title_from_idea(idea)
    profile = infer_business_profile(idea, requirements)
    features = _list_or_default(
        requirements.get("core_features"),
        [
            "Customer and work item management",
            "Due date tracking and reminders",
            "Dashboard metrics",
            "Search and status filters",
            "Local language support",
            "Demo-ready seed data",
        ],
    )
    features = enrich_features(features)
    workflows = requirements.get("workflow_map") or []
    rules = _list_or_default(requirements.get("business_rules"), ["Required customer name", "Required due date", "Status must be valid"])
    metrics = _list_or_default(requirements.get("success_metrics"), ["Open work items", "Upcoming due dates", "Completed work", "Estimated revenue"])
    api_routes = architecture.get("api_routes") or []

    seed_items = build_seed_items(requirements, product_name, profile)
    payload = {
        "appName": app_name,
        "productName": product_name,
        "businessType": profile["businessType"],
        "recordLabel": profile["recordLabel"],
        "queueLabel": profile["queueLabel"],
        "followUpLabel": profile["followUpLabel"],
        "idea": idea,
        "problem": requirements.get("problem_statement", idea),
        "audience": requirements.get("target_audience", "local business teams"),
        "features": features,
        "businessRules": rules,
        "successMetrics": metrics,
        "workflows": workflows,
        "apiRoutes": api_routes,
        "seedItems": seed_items,
    }

    return {
        "package.json": package_json(app_name),
        "index.html": index_html(product_name),
        "vite.config.js": vite_config(),
        "README.md": readme(payload),
        "server/index.js": server_index(),
        "server/dataStore.js": data_store(),
        "server/seed-data.json": json.dumps(seed_items, indent=2),
        "server/app.test.js": server_test(),
        "src/main.jsx": main_jsx(),
        "src/App.jsx": app_jsx(payload),
        "src/styles.css": styles_css(),
        "src/i18n.js": i18n_js(product_name),
        "src/api.js": api_js(),
    }


def app_name_from_idea(idea: str) -> str:
    words = re.findall(r"[a-zA-Z0-9]+", idea.lower())
    stop_words = {"a", "an", "ai", "app", "for", "that", "the", "to", "with"}
    useful = [word for word in words if word not in stop_words][:3]
    return "-".join(useful or ["swarm-generated-app"])


def title_from_idea(idea: str) -> str:
    words = re.findall(r"[a-zA-Z0-9]+", idea)
    stop_words = {"A", "An", "AI", "app", "for", "that", "the", "to", "with"}
    useful = [word for word in words if word not in stop_words][:3]
    return " ".join(useful or ["SWARM LocalOps"])


def enrich_features(features: list[str]) -> list[str]:
    required = [
        "customer records with follow-up history",
        "deadline, reminder, and overdue tracking",
        "daily operations queue for staff",
        "payment status and revenue dashboard",
        "English, Hindi, and Kannada local-language UX",
        "local-first JSON storage with tests and build validation",
    ]
    combined = list(features)
    for feature in required:
        if not any(feature.lower() in str(existing).lower() for existing in combined):
            combined.append(feature)
    return combined[:12]


def infer_business_profile(idea: str, requirements: dict) -> dict:
    idea_source = idea.lower()
    context_source = f"{idea} {json.dumps(requirements, ensure_ascii=True)}".lower()
    profiles = [
        {
            "keywords": ["bakery", "cake", "cakes", "baker"],
            "businessType": "bakery",
            "recordLabel": "cake order",
            "queueLabel": "production queue",
            "followUpLabel": "customer follow-up",
            "services": ["Custom birthday cake", "Wedding cake tasting", "Cupcake bulk order", "Photo cake delivery"],
        },
        {
            "keywords": ["salon", "saloon", "beauty", "spa", "hair", "makeup", "barber"],
            "businessType": "salon",
            "recordLabel": "appointment",
            "queueLabel": "appointment queue",
            "followUpLabel": "client follow-up",
            "services": ["Hair styling appointment", "Bridal makeup booking", "Facial package", "Color touch-up"],
        },
        {
            "keywords": ["clinic", "doctor", "patient", "dental", "health"],
            "businessType": "clinic",
            "recordLabel": "patient visit",
            "queueLabel": "visit queue",
            "followUpLabel": "patient follow-up",
            "services": ["Consultation", "Lab report review", "Dental cleaning", "Follow-up visit"],
        },
        {
            "keywords": ["fitness", "gym", "studio", "class"],
            "businessType": "fitness studio",
            "recordLabel": "member booking",
            "queueLabel": "class queue",
            "followUpLabel": "member follow-up",
            "services": ["Yoga class booking", "Personal training session", "Membership renewal", "Trial class"],
        },
        {
            "keywords": ["tuition", "school", "student", "coaching"],
            "businessType": "tuition center",
            "recordLabel": "student task",
            "queueLabel": "class queue",
            "followUpLabel": "parent follow-up",
            "services": ["Math batch enrolment", "Exam doubt session", "Fee reminder", "Parent meeting"],
        },
    ]

    # Trust the user's original prompt first. LLM-generated requirements can be
    # verbose or occasionally drift, but the user's prompt is the source of truth.
    prompt_profile = _match_business_profile(idea_source, profiles)
    if prompt_profile:
        return prompt_profile

    context_profile = _match_business_profile(context_source, profiles)
    if context_profile:
        return context_profile

    return fallback_business_profile()


def _match_business_profile(source: str, profiles: list[dict]) -> dict | None:
    for profile in profiles:
        if any(keyword in source for keyword in profile["keywords"]):
            return profile

    return None


def fallback_business_profile() -> dict:
    return {
        "businessType": "local business",
        "recordLabel": "customer work item",
        "queueLabel": "operations queue",
        "followUpLabel": "customer follow-up",
        "services": ["New customer request", "Confirmed booking", "In-progress work", "Completed delivery"],
    }


def build_seed_items(requirements: dict, product_name: str, profile: dict) -> list[dict]:
    raw_seed = requirements.get("seed_data")
    if isinstance(raw_seed, list) and raw_seed:
        items = []
        for index, item in enumerate(raw_seed[:6], start=1):
            text = item if isinstance(item, str) else json.dumps(item)
            items.append(seed_item(index, text, product_name, profile))
        return items

    return [
        seed_item(1, f"New {profile['recordLabel']} due next week", product_name, profile, "new", 2400),
        seed_item(2, f"Confirmed {profile['recordLabel']} with reminder tomorrow", product_name, profile, "confirmed", 5200),
        seed_item(3, f"In-progress {profile['recordLabel']} requiring follow-up", product_name, profile, "in_progress", 3100),
        seed_item(4, f"Completed {profile['recordLabel']} awaiting feedback", product_name, profile, "completed", 1800),
    ]


def seed_item(index: int, source: str, product_name: str, profile: dict, status: str | None = None, amount: int | None = None) -> dict:
    statuses = ["new", "confirmed", "in_progress", "completed"]
    due_day = 12 + index
    follow_day = max(12, due_day - 1)
    service = profile["services"][(index - 1) % len(profile["services"])]
    return {
        "id": index,
        "customerName": ["Asha Rao", "Kiran Stores", "Meera Kumar", "Local Club"][index % 4],
        "phone": f"+91 98{index}00 12{index}45",
        "title": source[:72],
        "category": product_name,
        "serviceType": service,
        "status": status or statuses[index % len(statuses)],
        "priority": ["low", "medium", "high"][index % 3],
        "dueDate": f"2026-06-{due_day:02d}",
        "followUpDate": f"2026-06-{follow_day:02d}",
        "paymentStatus": ["pending", "partial", "paid"][index % 3],
        "assignedTo": ["Owner", "Front desk", "Senior staff", "Delivery staff"][index % 4],
        "channel": ["WhatsApp", "Phone", "Walk-in", "Instagram"][index % 4],
        "progress": min(100, index * 22),
        "amount": amount or (1500 + index * 850),
        "nextAction": f"{profile['followUpLabel'].title()} before due date",
        "notes": f"Local {profile['businessType']} demo record generated from: {source[:120]}",
        "language": "en",
    }


def _list_or_default(value, fallback: list[str]) -> list[str]:
    return value if isinstance(value, list) and value else fallback


def package_json(app_name: str) -> str:
    return json.dumps(
        {
            "name": app_name,
            "version": "1.0.0",
            "private": True,
            "type": "module",
            "scripts": {
                "dev": "concurrently \"npm run dev:server\" \"npm run dev:client\"",
                "dev:server": "node server/index.js",
                "dev:client": "vite --host 127.0.0.1",
                "check": "node --check server/index.js && node --check server/dataStore.js",
                "test": "node --test server/app.test.js",
                "build": "vite build",
                "start": "node server/index.js",
            },
            "dependencies": {
                "@vitejs/plugin-react": "^5.0.0",
                "concurrently": "^9.1.2",
                "cors": "^2.8.5",
                "express": "^4.19.2",
                "vite": "^7.0.0",
                "react": "^19.0.0",
                "react-dom": "^19.0.0",
            },
            "devDependencies": {},
        },
        indent=2,
    )


def index_html(product_name: str) -> str:
    return dedent(
        f"""
        <!doctype html>
        <html lang="en">
          <head>
            <meta charset="UTF-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1.0" />
            <title>{product_name}</title>
          </head>
          <body>
            <div id="root"></div>
            <script type="module" src="/src/main.jsx"></script>
          </body>
        </html>
        """
    ).strip()


def vite_config() -> str:
    return dedent(
        """
        import { defineConfig } from "vite";
        import react from "@vitejs/plugin-react";

        export default defineConfig({
          plugins: [react()],
          server: {
            proxy: {
              "/api": "http://127.0.0.1:3001"
            }
          }
        });
        """
    ).strip()


def server_index() -> str:
    return dedent(
        """
        import express from "express";
        import cors from "cors";
        import { createItem, deleteItem, getItems, getMetrics, resetData, updateItem } from "./dataStore.js";

        const app = express();
        const port = Number(process.env.PORT || 3001);

        app.use(cors());
        app.use(express.json({ limit: "1mb" }));

        app.get("/api/health", (_req, res) => {
          res.json({ ok: true, service: "SWARM generated app" });
        });

        app.get("/api/items", (req, res) => {
          res.json(getItems(req.query));
        });

        app.post("/api/items", (req, res) => {
          try {
            res.status(201).json(createItem(req.body));
          } catch (error) {
            res.status(400).json({ error: error.message });
          }
        });

        app.put("/api/items/:id", (req, res) => {
          try {
            res.json(updateItem(Number(req.params.id), req.body));
          } catch (error) {
            res.status(404).json({ error: error.message });
          }
        });

        app.delete("/api/items/:id", (req, res) => {
          deleteItem(Number(req.params.id));
          res.status(204).end();
        });

        app.get("/api/metrics", (_req, res) => {
          res.json(getMetrics());
        });

        app.post("/api/reset", (_req, res) => {
          resetData();
          res.json({ ok: true });
        });

        app.listen(port, () => {
          console.log(`Generated app API running on http://127.0.0.1:${port}`);
        });
        """
    ).strip()


def data_store() -> str:
    return dedent(
        """
        import fs from "fs";
        import path from "path";
        import { fileURLToPath } from "url";

        const __filename = fileURLToPath(import.meta.url);
        const __dirname = path.dirname(__filename);
        const seedPath = path.join(__dirname, "seed-data.json");
        const dbPath = path.join(__dirname, "local-db.json");
        const statuses = ["new", "confirmed", "in_progress", "completed"];

        function readJson(filePath) {
          return JSON.parse(fs.readFileSync(filePath, "utf-8"));
        }

        function ensureDb() {
          if (!fs.existsSync(dbPath)) {
            fs.writeFileSync(dbPath, JSON.stringify(readJson(seedPath), null, 2));
          }
        }

        function writeItems(items) {
          fs.writeFileSync(dbPath, JSON.stringify(items, null, 2));
        }

        export function resetData() {
          writeItems(readJson(seedPath));
        }

        export function allItems() {
          ensureDb();
          return readJson(dbPath);
        }

        export function getItems(query = {}) {
          let items = allItems();
          if (query.status && query.status !== "all") {
            items = items.filter((item) => item.status === query.status);
          }
          if (query.search) {
            const term = String(query.search).toLowerCase();
            items = items.filter((item) =>
              `${item.customerName} ${item.title} ${item.category} ${item.serviceType} ${item.paymentStatus} ${item.assignedTo} ${item.nextAction}`
                .toLowerCase()
                .includes(term)
            );
          }
          return items.sort((a, b) => String(a.dueDate).localeCompare(String(b.dueDate)));
        }

        export function createItem(payload) {
          const items = allItems();
          const item = normalizeItem({ ...payload, id: nextId(items) });
          items.push(item);
          writeItems(items);
          return item;
        }

        export function updateItem(id, payload) {
          const items = allItems();
          const index = items.findIndex((item) => item.id === id);
          if (index === -1) throw new Error("Record not found");
          items[index] = normalizeItem({ ...items[index], ...payload, id });
          writeItems(items);
          return items[index];
        }

        export function deleteItem(id) {
          writeItems(allItems().filter((item) => item.id !== id));
        }

        export function getMetrics() {
          const items = allItems();
          const today = "2026-06-11";
          const activeItems = items.filter((item) => item.status !== "completed");
          return {
            total: items.length,
            open: activeItems.length,
            completed: items.filter((item) => item.status === "completed").length,
            upcoming: activeItems.filter((item) => item.dueDate >= today).length,
            dueToday: activeItems.filter((item) => item.dueDate === today).length,
            overdue: activeItems.filter((item) => item.dueDate < today).length,
            highPriority: activeItems.filter((item) => item.priority === "high").length,
            followUpsDue: activeItems.filter((item) => item.followUpDate <= today).length,
            pendingPayments: items.filter((item) => item.paymentStatus !== "paid").length,
            revenue: items.reduce((sum, item) => sum + Number(item.amount || 0), 0),
            pendingRevenue: items
              .filter((item) => item.paymentStatus !== "paid")
              .reduce((sum, item) => sum + Number(item.amount || 0), 0),
            productionQueue: activeItems
              .slice()
              .sort((a, b) => String(a.dueDate).localeCompare(String(b.dueDate)))
              .slice(0, 5),
            byStatus: statuses.map((status) => ({ status, count: items.filter((item) => item.status === status).length })),
          };
        }

        function normalizeItem(payload) {
          if (!payload.customerName) throw new Error("Customer name is required");
          if (!payload.title) throw new Error("Title is required");
          if (!payload.dueDate) throw new Error("Due date is required");
          if (!statuses.includes(payload.status)) throw new Error("Invalid status");
          return {
            id: Number(payload.id),
            customerName: String(payload.customerName),
            phone: String(payload.phone || ""),
            title: String(payload.title),
            category: String(payload.category || "General"),
            serviceType: String(payload.serviceType || payload.category || "General"),
            status: String(payload.status),
            priority: String(payload.priority || "medium"),
            dueDate: String(payload.dueDate),
            followUpDate: String(payload.followUpDate || payload.dueDate),
            paymentStatus: String(payload.paymentStatus || "pending"),
            assignedTo: String(payload.assignedTo || "Owner"),
            channel: String(payload.channel || "Walk-in"),
            progress: Number(payload.progress || 0),
            amount: Number(payload.amount || 0),
            nextAction: String(payload.nextAction || "Follow up with customer"),
            notes: String(payload.notes || ""),
            language: String(payload.language || "en"),
          };
        }

        function nextId(items) {
          return items.reduce((max, item) => Math.max(max, Number(item.id)), 0) + 1;
        }
        """
    ).strip()


def server_test() -> str:
    return dedent(
        """
        import test from "node:test";
        import assert from "node:assert/strict";
        import { createItem, getItems, getMetrics, resetData, updateItem } from "./dataStore.js";

        test("data workflow supports create, update, filter, and metrics", () => {
          resetData();
          const created = createItem({
            customerName: "Test Customer",
            title: "Test work item",
            dueDate: "2026-06-25",
            followUpDate: "2026-06-20",
            status: "new",
            paymentStatus: "partial",
            amount: 999
          });
          assert.equal(created.customerName, "Test Customer");
          const updated = updateItem(created.id, { status: "completed" });
          assert.equal(updated.status, "completed");
          assert.ok(getItems({ search: "test" }).length >= 1);
          assert.ok(getMetrics().total >= 1);
          assert.ok(Array.isArray(getMetrics().productionQueue));
          assert.ok("pendingPayments" in getMetrics());
        });
        """
    ).strip()


def main_jsx() -> str:
    return dedent(
        """
        import React from "react";
        import { createRoot } from "react-dom/client";
        import App from "./App.jsx";
        import "./styles.css";

        createRoot(document.getElementById("root")).render(<App />);
        """
    ).strip()


def api_js() -> str:
    return dedent(
        """
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
          items: (params = {}) => request(`/api/items?${new URLSearchParams(params)}`),
          metrics: () => request("/api/metrics"),
          create: (payload) => request("/api/items", { method: "POST", body: JSON.stringify(payload) }),
          update: (id, payload) => request(`/api/items/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
          remove: (id) => request(`/api/items/${id}`, { method: "DELETE" }),
          reset: () => request("/api/reset", { method: "POST" }),
        };
        """
    ).strip()


def i18n_js(product_name: str) -> str:
    return dedent(
        f"""
        export const translations = {{
          en: {{
            appName: "{product_name}",
            dashboard: "Dashboard",
            records: "Records",
            newRecord: "New record",
            search: "Search",
            status: "Status",
            customer: "Customer",
            dueDate: "Due date",
            amount: "Amount",
            save: "Save",
            reset: "Reset demo data",
            empty: "No records match the current filters.",
          }},
          hi: {{
            appName: "{product_name}",
            dashboard: "डैशबोर्ड",
            records: "रिकॉर्ड",
            newRecord: "नया रिकॉर्ड",
            search: "खोजें",
            status: "स्थिति",
            customer: "ग्राहक",
            dueDate: "तारीख",
            amount: "राशि",
            save: "सेव करें",
            reset: "डेमो डेटा रीसेट",
            empty: "इन फिल्टर के लिए कोई रिकॉर्ड नहीं मिला.",
          }},
          kn: {{
            appName: "{product_name}",
            dashboard: "ಡ್ಯಾಶ್ಬೋರ್ಡ್",
            records: "ದಾಖಲೆಗಳು",
            newRecord: "ಹೊಸ ದಾಖಲೆ",
            search: "ಹುಡುಕಿ",
            status: "ಸ್ಥಿತಿ",
            customer: "ಗ್ರಾಹಕ",
            dueDate: "ದಿನಾಂಕ",
            amount: "ಮೊತ್ತ",
            save: "ಉಳಿಸಿ",
            reset: "ಡೆಮೊ ಡೇಟಾ ಮರುಹೊಂದಿಸಿ",
            empty: "ಈ ಫಿಲ್ಟರ್‌ಗಳಿಗೆ ದಾಖಲೆಗಳಿಲ್ಲ.",
          }},
        }};

        export function formatCurrency(value, locale) {{
          return new Intl.NumberFormat(locale === "hi" ? "hi-IN" : locale === "kn" ? "kn-IN" : "en-IN", {{
            style: "currency",
            currency: "INR",
            maximumFractionDigits: 0,
          }}).format(value || 0);
        }}

        export function formatDate(value, locale) {{
          return new Intl.DateTimeFormat(locale === "hi" ? "hi-IN" : locale === "kn" ? "kn-IN" : "en-IN").format(new Date(value));
        }}
        """
    ).strip()


def app_jsx(payload: dict) -> str:
    config = json.dumps(payload, indent=2)
    return dedent(
        f"""
        import {{ useEffect, useMemo, useState }} from "react";
        import {{ api }} from "./api.js";
        import {{ formatCurrency, formatDate, translations }} from "./i18n.js";

        const config = {config};
        const emptyForm = {{
          customerName: "",
          phone: "",
          title: "",
          category: config.productName,
          status: "new",
          priority: "medium",
          dueDate: "2026-06-20",
          amount: 0,
          notes: "",
          language: "en",
        }};

        export default function App() {{
          const [items, setItems] = useState([]);
          const [metrics, setMetrics] = useState(null);
          const [form, setForm] = useState(emptyForm);
          const [editingId, setEditingId] = useState(null);
          const [search, setSearch] = useState("");
          const [status, setStatus] = useState("all");
          const [locale, setLocale] = useState("en");
          const [loading, setLoading] = useState(true);
          const [error, setError] = useState("");
          const t = translations[locale];

          async function load() {{
            setLoading(true);
            setError("");
            try {{
              const [nextItems, nextMetrics] = await Promise.all([api.items({{ search, status }}), api.metrics()]);
              setItems(nextItems);
              setMetrics(nextMetrics);
            }} catch (err) {{
              setError(err.message);
            }} finally {{
              setLoading(false);
            }}
          }}

          useEffect(() => {{
            load();
          }}, [search, status]);

          const statusSummary = useMemo(() => metrics?.byStatus || [], [metrics]);

          async function saveRecord(event) {{
            event.preventDefault();
            try {{
              if (editingId) await api.update(editingId, form);
              else await api.create(form);
              setForm(emptyForm);
              setEditingId(null);
              await load();
            }} catch (err) {{
              setError(err.message);
            }}
          }}

          async function deleteRecord(id) {{
            await api.remove(id);
            await load();
          }}

          async function resetDemo() {{
            await api.reset();
            setSearch("");
            setStatus("all");
            await load();
          }}

          function editRecord(item) {{
            setEditingId(item.id);
            setForm(item);
            window.scrollTo({{ top: 0, behavior: "smooth" }});
          }}

          return (
            <main className="app-shell">
              <header className="topbar">
                <div>
                  <p className="eyebrow">SWARM-generated local app</p>
                  <h1>{{t.appName}}</h1>
                  <p>{{config.problem}}</p>
                </div>
                <div className="toolbar">
                  <select value={{locale}} onChange={{(event) => setLocale(event.target.value)}} aria-label="Language">
                    <option value="en">English</option>
                    <option value="hi">हिन्दी</option>
                    <option value="kn">ಕನ್ನಡ</option>
                  </select>
                  <button onClick={{resetDemo}}>{{t.reset}}</button>
                </div>
              </header>

              {{error && <div className="alert">{{error}}</div>}}

              <section className="metrics-grid">
                <Metric label="Total" value={{metrics?.total ?? 0}} />
                <Metric label="Open" value={{metrics?.open ?? 0}} />
                <Metric label="Upcoming" value={{metrics?.upcoming ?? 0}} />
                <Metric label="Revenue" value={{formatCurrency(metrics?.revenue ?? 0, locale)}} />
              </section>

              <section className="layout">
                <form className="panel form-panel" onSubmit={{saveRecord}}>
                  <div className="section-title">
                    <h2>{{editingId ? "Edit record" : t.newRecord}}</h2>
                    <span>{{config.audience}}</span>
                  </div>
                  <div className="form-grid">
                    <Input label={{t.customer}} value={{form.customerName}} onChange={{(value) => setForm({{ ...form, customerName: value }})}} required />
                    <Input label="Phone" value={{form.phone}} onChange={{(value) => setForm({{ ...form, phone: value }})}} />
                    <Input label="Work title" value={{form.title}} onChange={{(value) => setForm({{ ...form, title: value }})}} required />
                    <Input label={{t.dueDate}} type="date" value={{form.dueDate}} onChange={{(value) => setForm({{ ...form, dueDate: value }})}} required />
                    <label>
                      {{t.status}}
                      <select value={{form.status}} onChange={{(event) => setForm({{ ...form, status: event.target.value }})}}>
                        <option value="new">New</option>
                        <option value="confirmed">Confirmed</option>
                        <option value="in_progress">In progress</option>
                        <option value="completed">Completed</option>
                      </select>
                    </label>
                    <label>
                      Priority
                      <select value={{form.priority}} onChange={{(event) => setForm({{ ...form, priority: event.target.value }})}}>
                        <option value="low">Low</option>
                        <option value="medium">Medium</option>
                        <option value="high">High</option>
                      </select>
                    </label>
                    <Input label={{t.amount}} type="number" value={{form.amount}} onChange={{(value) => setForm({{ ...form, amount: Number(value) }})}} />
                    <label className="wide">
                      Notes
                      <textarea value={{form.notes}} onChange={{(event) => setForm({{ ...form, notes: event.target.value }})}} />
                    </label>
                  </div>
                  <button className="primary" type="submit">{{t.save}}</button>
                </form>

                <section className="panel">
                  <div className="section-title">
                    <h2>{{t.records}}</h2>
                    <span>{{loading ? "Loading..." : `${{items.length}} visible`}}</span>
                  </div>
                  <div className="filters">
                    <input placeholder={{t.search}} value={{search}} onChange={{(event) => setSearch(event.target.value)}} />
                    <select value={{status}} onChange={{(event) => setStatus(event.target.value)}}>
                      <option value="all">All</option>
                      <option value="new">New</option>
                      <option value="confirmed">Confirmed</option>
                      <option value="in_progress">In progress</option>
                      <option value="completed">Completed</option>
                    </select>
                  </div>
                  <div className="status-row">
                    {{statusSummary.map((entry) => <span key={{entry.status}}>{{entry.status}}: {{entry.count}}</span>)}}
                  </div>
                  {{items.length === 0 && !loading ? <div className="empty">{{t.empty}}</div> : (
                    <div className="records">
                      {{items.map((item) => (
                        <article className="record-card" key={{item.id}}>
                          <div>
                            <h3>{{item.title}}</h3>
                            <p>{{item.customerName}} · {{item.phone}}</p>
                          </div>
                          <div className="record-meta">
                            <span>{{item.status.replace("_", " ")}}</span>
                            <span>{{formatDate(item.dueDate, locale)}}</span>
                            <strong>{{formatCurrency(item.amount, locale)}}</strong>
                          </div>
                          <p>{{item.notes}}</p>
                          <div className="actions">
                            <button onClick={{() => editRecord(item)}}>Edit</button>
                            <button className="danger" onClick={{() => deleteRecord(item.id)}}>Delete</button>
                          </div>
                        </article>
                      ))}}
                    </div>
                  )}}
                </section>
              </section>

              <section className="panel">
                <div className="section-title">
                  <h2>What this MVP covers</h2>
                  <span>Generated from one prompt</span>
                </div>
                <div className="feature-grid">
                  {{config.features.map((feature) => <span key={{feature}}>{{feature}}</span>)}}
                </div>
              </section>
            </main>
          );
        }}

        function Metric({{ label, value }}) {{
          return (
            <div className="metric">
              <span>{{label}}</span>
              <strong>{{value}}</strong>
            </div>
          );
        }}

        function Input({{ label, value, onChange, type = "text", required = false }}) {{
          return (
            <label>
              {{label}}
              <input type={{type}} value={{value}} required={{required}} onChange={{(event) => onChange(event.target.value)}} />
            </label>
          );
        }}
        """
    ).strip()


def styles_css() -> str:
    return dedent(
        """
        * { box-sizing: border-box; }
        body { margin: 0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f4f6f8; color: #111827; }
        button, input, select, textarea { font: inherit; }
        button { border: 0; border-radius: 6px; padding: 10px 14px; background: #e5e7eb; color: #111827; cursor: pointer; font-weight: 700; }
        button:hover { background: #d1d5db; }
        .primary { background: #2563eb; color: white; width: 100%; }
        .primary:hover { background: #1d4ed8; }
        .danger { color: #991b1b; background: #fee2e2; }
        .app-shell { max-width: 1280px; margin: 0 auto; padding: 24px; }
        .topbar { display: flex; align-items: flex-start; justify-content: space-between; gap: 24px; padding: 28px; border-radius: 10px; background: #111827; color: white; }
        .topbar h1 { margin: 8px 0; font-size: 36px; line-height: 1.1; }
        .topbar p { margin: 0; color: #cbd5e1; max-width: 760px; line-height: 1.6; }
        .eyebrow { color: #93c5fd !important; text-transform: uppercase; letter-spacing: 0.14em; font-size: 12px; font-weight: 800; }
        .toolbar { display: flex; gap: 10px; min-width: 260px; justify-content: flex-end; }
        .toolbar select, .filters select, .filters input { min-height: 42px; border-radius: 6px; border: 1px solid #cbd5e1; padding: 0 12px; background: white; }
        .alert { margin-top: 16px; border: 1px solid #fecaca; background: #fff1f2; color: #9f1239; padding: 12px 14px; border-radius: 8px; }
        .metrics-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin: 18px 0; }
        .metric { background: white; border: 1px solid #d9dee7; border-radius: 8px; padding: 18px; }
        .metric span { color: #64748b; font-size: 13px; text-transform: uppercase; letter-spacing: 0.1em; }
        .metric strong { display: block; margin-top: 8px; font-size: 26px; }
        .layout { display: grid; grid-template-columns: 390px minmax(0, 1fr); gap: 18px; align-items: start; }
        .panel { background: white; border: 1px solid #d9dee7; border-radius: 8px; padding: 18px; box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04); }
        .section-title { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; margin-bottom: 16px; }
        .section-title h2 { margin: 0; font-size: 18px; }
        .section-title span { color: #64748b; font-size: 13px; }
        .form-grid { display: grid; grid-template-columns: 1fr; gap: 12px; }
        label { display: grid; gap: 6px; color: #334155; font-weight: 700; font-size: 13px; }
        input, select, textarea { width: 100%; border: 1px solid #cbd5e1; border-radius: 6px; min-height: 42px; padding: 10px 12px; background: #fbfdff; }
        textarea { min-height: 92px; resize: vertical; }
        .form-panel .primary { margin-top: 14px; }
        .filters { display: grid; grid-template-columns: minmax(0, 1fr) 180px; gap: 10px; margin-bottom: 12px; }
        .status-row { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
        .status-row span, .feature-grid span { border-radius: 999px; background: #eff6ff; color: #1d4ed8; padding: 7px 10px; font-size: 12px; font-weight: 800; }
        .records { display: grid; gap: 12px; }
        .record-card { border: 1px solid #e5e7eb; border-radius: 8px; padding: 14px; background: #fbfdff; }
        .record-card h3 { margin: 0 0 5px; font-size: 16px; }
        .record-card p { margin: 6px 0; color: #475569; line-height: 1.5; }
        .record-meta { display: flex; flex-wrap: wrap; gap: 8px; margin: 10px 0; }
        .record-meta span, .record-meta strong { border-radius: 6px; background: #f1f5f9; padding: 6px 8px; font-size: 12px; }
        .actions { display: flex; gap: 8px; justify-content: flex-end; }
        .empty { min-height: 220px; border: 1px dashed #cbd5e1; border-radius: 8px; display: grid; place-items: center; color: #64748b; background: #f8fafc; }
        .feature-grid { display: flex; flex-wrap: wrap; gap: 10px; }
        @media (max-width: 900px) {
          .topbar, .layout { grid-template-columns: 1fr; display: grid; }
          .metrics-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
          .toolbar, .filters { grid-template-columns: 1fr; display: grid; min-width: 0; }
        }
        """
    ).strip()


def readme(payload: dict) -> str:
    return dedent(
        f"""
        # {payload["productName"]}

        This app was generated by SWARM.AI from one local-business prompt.

        ## Problem

        {payload["problem"]}

        ## Audience

        {payload["audience"]}

        ## Features Covered

        {chr(10).join(f"- {feature}" for feature in payload["features"])}

        ## Business Rules

        {chr(10).join(f"- {rule}" for rule in payload["businessRules"])}

        ## Local Language Support

        The app includes English, Hindi, and Kannada translation dictionaries, a language switcher, and `Intl` date/currency formatting for India.

        ## Run Locally

        ```bash
        npm install
        npm run dev
        ```

        API runs on `http://127.0.0.1:3001`.
        Frontend runs on the Vite URL shown in the terminal.

        ## Demo Flow

        1. Review dashboard metrics.
        2. Search and filter records by status.
        3. Create a new record with customer, due date, priority, amount, and notes.
        4. Edit the status to completed.
        5. Switch language between English, Hindi, and Kannada.
        6. Reset demo data.

        ## Validation

        ```bash
        npm run check
        npm run test
        npm run build
        ```
        """
    ).strip()


def i18n_js(product_name: str) -> str:
    return dedent(
        f"""
        export const translations = {{
          en: {{ appName: "{product_name}", dashboard: "Dashboard", records: "Records", newRecord: "New record", search: "Search", status: "Status", customer: "Customer", dueDate: "Due date", followUpDate: "Follow-up date", amount: "Amount", payment: "Payment", service: "Service", assignedTo: "Assigned to", channel: "Channel", nextAction: "Next action", queue: "Daily queue", followUps: "Follow-ups due", pendingPayments: "Pending payments", localLanguage: "Local language", save: "Save", reset: "Reset demo data", empty: "No records match the current filters." }},
          hi: {{ appName: "{product_name}", dashboard: "\\u0921\\u0948\\u0936\\u092c\\u094b\\u0930\\u094d\\u0921", records: "\\u0930\\u093f\\u0915\\u0949\\u0930\\u094d\\u0921", newRecord: "\\u0928\\u092f\\u093e \\u0930\\u093f\\u0915\\u0949\\u0930\\u094d\\u0921", search: "\\u0916\\u094b\\u091c\\u0947\\u0902", status: "\\u0938\\u094d\\u0925\\u093f\\u0924\\u093f", customer: "\\u0917\\u094d\\u0930\\u093e\\u0939\\u0915", dueDate: "\\u0921\\u093f\\u0932\\u093f\\u0935\\u0930\\u0940 \\u0924\\u093e\\u0930\\u0940\\u0916", followUpDate: "\\u092b\\u0949\\u0932\\u094b-\\u0905\\u092a \\u0924\\u093e\\u0930\\u0940\\u0916", amount: "\\u0930\\u093e\\u0936\\u093f", payment: "\\u092d\\u0941\\u0917\\u0924\\u093e\\u0928", service: "\\u0938\\u0947\\u0935\\u093e", assignedTo: "\\u091c\\u093f\\u092e\\u094d\\u092e\\u0947\\u0926\\u093e\\u0930", channel: "\\u091a\\u0948\\u0928\\u0932", nextAction: "\\u0905\\u0917\\u0932\\u093e \\u0915\\u0926\\u092e", queue: "\\u0906\\u091c \\u0915\\u0940 \\u0915\\u0924\\u093e\\u0930", followUps: "\\u092b\\u0949\\u0932\\u094b-\\u0905\\u092a \\u092c\\u093e\\u0915\\u0940", pendingPayments: "\\u092c\\u0915\\u093e\\u092f\\u093e \\u092d\\u0941\\u0917\\u0924\\u093e\\u0928", localLanguage: "\\u0938\\u094d\\u0925\\u093e\\u0928\\u0940\\u092f \\u092d\\u093e\\u0937\\u093e", save: "\\u0938\\u0947\\u0935 \\u0915\\u0930\\u0947\\u0902", reset: "\\u0921\\u0947\\u092e\\u094b \\u0921\\u0947\\u091f\\u093e \\u0930\\u0940\\u0938\\u0947\\u091f", empty: "\\u0907\\u0928 \\u092b\\u093f\\u0932\\u094d\\u091f\\u0930 \\u0915\\u0947 \\u0932\\u093f\\u090f \\u0915\\u094b\\u0908 \\u0930\\u093f\\u0915\\u0949\\u0930\\u094d\\u0921 \\u0928\\u0939\\u0940\\u0902 \\u092e\\u093f\\u0932\\u093e." }},
          kn: {{ appName: "{product_name}", dashboard: "\\u0ca1\\u0ccd\\u0caf\\u0cbe\\u0cb6\\u0ccd\\u0cac\\u0ccb\\u0cb0\\u0ccd\\u0ca1\\u0ccd", records: "\\u0ca6\\u0cbe\\u0c96\\u0cb2\\u0cc6\\u0c97\\u0cb3\\u0cc1", newRecord: "\\u0cb9\\u0cca\\u0cb8 \\u0ca6\\u0cbe\\u0c96\\u0cb2\\u0cc6", search: "\\u0cb9\\u0cc1\\u0ca1\\u0cc1\\u0c95\\u0cbf", status: "\\u0cb8\\u0ccd\\u0ca5\\u0cbf\\u0ca4\\u0cbf", customer: "\\u0c97\\u0ccd\\u0cb0\\u0cbe\\u0cb9\\u0c95", dueDate: "\\u0ca1\\u0cc6\\u0cb2\\u0cbf\\u0cb5\\u0cb0\\u0cbf \\u0ca6\\u0cbf\\u0ca8\\u0cbe\\u0c82\\u0c95", followUpDate: "\\u0cab\\u0cbe\\u0cb2\\u0ccb-\\u0c85\\u0caa\\u0ccd \\u0ca6\\u0cbf\\u0ca8\\u0cbe\\u0c82\\u0c95", amount: "\\u0cae\\u0cca\\u0ca4\\u0ccd\\u0ca4", payment: "\\u0caa\\u0cbe\\u0cb5\\u0ca4\\u0cbf", service: "\\u0cb8\\u0cc7\\u0cb5\\u0cc6", assignedTo: "\\u0c9c\\u0cb5\\u0cbe\\u0cac\\u0ccd\\u0ca6\\u0cbe\\u0cb0\\u0cb0\\u0cc1", channel: "\\u0c9a\\u0ccd\\u0caf\\u0cbe\\u0ca8\\u0cb2\\u0ccd", nextAction: "\\u0cae\\u0cc1\\u0c82\\u0ca6\\u0cbf\\u0ca8 \\u0c95\\u0ccd\\u0cb0\\u0cae", queue: "\\u0c87\\u0c82\\u0ca6\\u0cbf\\u0ca8 \\u0c95\\u0ca4\\u0cbe\\u0cb0\\u0cc1", followUps: "\\u0cab\\u0cbe\\u0cb2\\u0ccb-\\u0c85\\u0caa\\u0ccd \\u0cac\\u0cbe\\u0c95\\u0cbf", pendingPayments: "\\u0cac\\u0cbe\\u0c95\\u0cbf \\u0caa\\u0cbe\\u0cb5\\u0ca4\\u0cbf", localLanguage: "\\u0cb8\\u0ccd\\u0ca5\\u0cb3\\u0cc0\\u0caf \\u0cad\\u0cbe\\u0cb7\\u0cc6", save: "\\u0c89\\u0cb3\\u0cbf\\u0cb8\\u0cbf", reset: "\\u0ca1\\u0cc6\\u0cae\\u0ccb \\u0ca1\\u0cc7\\u0c9f\\u0cbe \\u0cae\\u0cb0\\u0cc1\\u0cb9\\u0cca\\u0c82\\u0ca6\\u0cbf\\u0cb8\\u0cbf", empty: "\\u0c88 \\u0cab\\u0cbf\\u0cb2\\u0ccd\\u0c9f\\u0cb0\\u0ccd\\u0c97\\u0cb3\\u0cbf\\u0c97\\u0cc6 \\u0ca6\\u0cbe\\u0c96\\u0cb2\\u0cc6\\u0c97\\u0cb3\\u0cbf\\u0cb2\\u0ccd\\u0cb2." }},
        }};

        export function formatCurrency(value, locale) {{
          return new Intl.NumberFormat(locale === "hi" ? "hi-IN" : locale === "kn" ? "kn-IN" : "en-IN", {{ style: "currency", currency: "INR", maximumFractionDigits: 0 }}).format(value || 0);
        }}

        export function formatDate(value, locale) {{
          return new Intl.DateTimeFormat(locale === "hi" ? "hi-IN" : locale === "kn" ? "kn-IN" : "en-IN").format(new Date(value));
        }}
        """
    ).strip()


def app_jsx(payload: dict) -> str:
    config = json.dumps(payload, indent=2)
    return dedent(
        f"""
        import {{ useEffect, useMemo, useState }} from "react";
        import {{ api }} from "./api.js";
        import {{ formatCurrency, formatDate, translations }} from "./i18n.js";

        const config = {config};
        const emptyForm = {{
          customerName: "",
          phone: "",
          title: "",
          category: config.productName,
          serviceType: "",
          status: "new",
          priority: "medium",
          dueDate: "2026-06-20",
          followUpDate: "2026-06-18",
          paymentStatus: "pending",
          assignedTo: "Owner",
          channel: "WhatsApp",
          progress: 0,
          amount: 0,
          nextAction: "",
          notes: "",
          language: "en",
        }};

        export default function App() {{
          const [items, setItems] = useState([]);
          const [metrics, setMetrics] = useState(null);
          const [form, setForm] = useState(emptyForm);
          const [editingId, setEditingId] = useState(null);
          const [search, setSearch] = useState("");
          const [status, setStatus] = useState("all");
          const [locale, setLocale] = useState("en");
          const [loading, setLoading] = useState(true);
          const [error, setError] = useState("");
          const t = translations[locale];

          async function load() {{
            setLoading(true);
            setError("");
            try {{
              const [nextItems, nextMetrics] = await Promise.all([api.items({{ search, status }}), api.metrics()]);
              setItems(nextItems);
              setMetrics(nextMetrics);
            }} catch (err) {{
              setError(err.message);
            }} finally {{
              setLoading(false);
            }}
          }}

          useEffect(() => {{ load(); }}, [search, status]);

          const statusSummary = useMemo(() => metrics?.byStatus || [], [metrics]);
          const queue = metrics?.productionQueue || [];

          async function saveRecord(event) {{
            event.preventDefault();
            try {{
              const payload = {{ ...form, serviceType: form.serviceType || form.title, nextAction: form.nextAction || "Follow up before due date" }};
              if (editingId) await api.update(editingId, payload);
              else await api.create(payload);
              setForm(emptyForm);
              setEditingId(null);
              await load();
            }} catch (err) {{
              setError(err.message);
            }}
          }}

          async function deleteRecord(id) {{
            await api.remove(id);
            await load();
          }}

          async function resetDemo() {{
            await api.reset();
            setSearch("");
            setStatus("all");
            await load();
          }}

          function editRecord(item) {{
            setEditingId(item.id);
            setForm({{ ...emptyForm, ...item }});
            window.scrollTo({{ top: 0, behavior: "smooth" }});
          }}

          return (
            <main className="app-shell">
              <header className="topbar">
                <div>
                  <p className="eyebrow">SWARM local-business app</p>
                  <h1>{{t.appName}}</h1>
                  <p>{{config.problem}}</p>
                  <div className="hero-tags">
                    <span>{{config.businessType}}</span>
                    <span>{{config.recordLabel}}</span>
                    <span>{{t.localLanguage}}</span>
                  </div>
                </div>
                <div className="toolbar">
                  <select value={{locale}} onChange={{(event) => setLocale(event.target.value)}} aria-label="Language">
                    <option value="en">English</option>
                    <option value="hi">\\u0939\\u093f\\u0928\\u094d\\u0926\\u0940</option>
                    <option value="kn">\\u0c95\\u0ca8\\u0ccd\\u0ca8\\u0ca1</option>
                  </select>
                  <button onClick={{resetDemo}}>{{t.reset}}</button>
                </div>
              </header>

              {{error && <div className="alert">{{error}}</div>}}

              <section className="metrics-grid">
                <Metric label="Open" value={{metrics?.open ?? 0}} />
                <Metric label="Overdue" value={{metrics?.overdue ?? 0}} urgent />
                <Metric label={{t.followUps}} value={{metrics?.followUpsDue ?? 0}} />
                <Metric label={{t.pendingPayments}} value={{metrics?.pendingPayments ?? 0}} />
                <Metric label="Revenue" value={{formatCurrency(metrics?.revenue ?? 0, locale)}} />
                <Metric label="Pending value" value={{formatCurrency(metrics?.pendingRevenue ?? 0, locale)}} />
              </section>

              <section className="layout">
                <form className="panel form-panel" onSubmit={{saveRecord}}>
                  <div className="section-title">
                    <h2>{{editingId ? "Edit " + config.recordLabel : t.newRecord}}</h2>
                    <span>{{config.audience}}</span>
                  </div>
                  <div className="form-grid">
                    <Input label={{t.customer}} value={{form.customerName}} onChange={{(value) => setForm({{ ...form, customerName: value }})}} required />
                    <Input label="Phone" value={{form.phone}} onChange={{(value) => setForm({{ ...form, phone: value }})}} />
                    <Input label="Work title" value={{form.title}} onChange={{(value) => setForm({{ ...form, title: value }})}} required />
                    <Input label={{t.service}} value={{form.serviceType}} onChange={{(value) => setForm({{ ...form, serviceType: value }})}} />
                    <Input label={{t.dueDate}} type="date" value={{form.dueDate}} onChange={{(value) => setForm({{ ...form, dueDate: value }})}} required />
                    <Input label={{t.followUpDate}} type="date" value={{form.followUpDate}} onChange={{(value) => setForm({{ ...form, followUpDate: value }})}} />
                    <Select label={{t.status}} value={{form.status}} onChange={{(value) => setForm({{ ...form, status: value }})}} options={{["new", "confirmed", "in_progress", "completed"]}} />
                    <Select label="Priority" value={{form.priority}} onChange={{(value) => setForm({{ ...form, priority: value }})}} options={{["low", "medium", "high"]}} />
                    <Select label={{t.payment}} value={{form.paymentStatus}} onChange={{(value) => setForm({{ ...form, paymentStatus: value }})}} options={{["pending", "partial", "paid"]}} />
                    <Input label={{t.assignedTo}} value={{form.assignedTo}} onChange={{(value) => setForm({{ ...form, assignedTo: value }})}} />
                    <Input label={{t.channel}} value={{form.channel}} onChange={{(value) => setForm({{ ...form, channel: value }})}} />
                    <Input label={{t.amount}} type="number" value={{form.amount}} onChange={{(value) => setForm({{ ...form, amount: Number(value) }})}} />
                    <Input label="Progress %" type="number" value={{form.progress}} onChange={{(value) => setForm({{ ...form, progress: Number(value) }})}} />
                    <Input label={{t.nextAction}} value={{form.nextAction}} onChange={{(value) => setForm({{ ...form, nextAction: value }})}} />
                    <label className="wide">Notes<textarea value={{form.notes}} onChange={{(event) => setForm({{ ...form, notes: event.target.value }})}} /></label>
                  </div>
                  <button className="primary" type="submit">{{t.save}}</button>
                </form>

                <section className="panel">
                  <div className="section-title">
                    <h2>{{t.records}}</h2>
                    <span>{{loading ? "Loading..." : String(items.length) + " visible"}}</span>
                  </div>
                  <div className="filters">
                    <input placeholder={{t.search}} value={{search}} onChange={{(event) => setSearch(event.target.value)}} />
                    <select value={{status}} onChange={{(event) => setStatus(event.target.value)}}>
                      <option value="all">All</option>
                      <option value="new">New</option>
                      <option value="confirmed">Confirmed</option>
                      <option value="in_progress">In progress</option>
                      <option value="completed">Completed</option>
                    </select>
                  </div>
                  <div className="status-row">{{statusSummary.map((entry) => <span key={{entry.status}}>{{entry.status}}: {{entry.count}}</span>)}}</div>
                  {{items.length === 0 && !loading ? <div className="empty">{{t.empty}}</div> : (
                    <div className="records">
                      {{items.map((item) => (
                        <article className="record-card" key={{item.id}}>
                          <div className="record-head">
                            <div><h3>{{item.title}}</h3><p>{{item.customerName}} - {{item.phone}}</p></div>
                            <strong>{{formatCurrency(item.amount, locale)}}</strong>
                          </div>
                          <div className="record-meta">
                            <span>{{item.status.replace("_", " ")}}</span>
                            <span>{{item.paymentStatus}}</span>
                            <span>{{item.priority}}</span>
                            <span>{{formatDate(item.dueDate, locale)}}</span>
                          </div>
                          <div className="progress"><span style={{{{ width: Math.min(100, Number(item.progress || 0)) + "%" }}}} /></div>
                          <p><b>{{t.service}}:</b> {{item.serviceType}} | <b>{{t.assignedTo}}:</b> {{item.assignedTo}} | <b>{{t.channel}}:</b> {{item.channel}}</p>
                          <p><b>{{t.nextAction}}:</b> {{item.nextAction}}</p>
                          <p>{{item.notes}}</p>
                          <div className="actions"><button onClick={{() => editRecord(item)}}>Edit</button><button className="danger" onClick={{() => deleteRecord(item.id)}}>Delete</button></div>
                        </article>
                      ))}}
                    </div>
                  )}}
                </section>
              </section>

              <section className="insight-grid">
                <div className="panel">
                  <div className="section-title"><h2>{{t.queue}}</h2><span>{{config.queueLabel}}</span></div>
                  <div className="queue-list">
                    {{queue.map((item) => <div key={{item.id}}><strong>{{item.title}}</strong><span>{{formatDate(item.dueDate, locale)}} - {{item.assignedTo}}</span></div>)}}
                  </div>
                </div>
                <div className="panel">
                  <div className="section-title"><h2>What this MVP covers</h2><span>Generated from one prompt</span></div>
                  <div className="feature-grid">{{config.features.map((feature) => <span key={{feature}}>{{feature}}</span>)}}</div>
                </div>
              </section>
            </main>
          );
        }}

        function Metric({{ label, value, urgent = false }}) {{
          return <div className={{"metric " + (urgent ? "urgent" : "")}}><span>{{label}}</span><strong>{{value}}</strong></div>;
        }}

        function Input({{ label, value, onChange, type = "text", required = false }}) {{
          return <label>{{label}}<input type={{type}} value={{value}} required={{required}} onChange={{(event) => onChange(event.target.value)}} /></label>;
        }}

        function Select({{ label, value, onChange, options }}) {{
          return <label>{{label}}<select value={{value}} onChange={{(event) => onChange(event.target.value)}}>{{options.map((option) => <option key={{option}} value={{option}}>{{option.replace("_", " ")}}</option>)}}</select></label>;
        }}
        """
    ).strip()


def styles_css() -> str:
    return dedent(
        """
        * { box-sizing: border-box; }
        body { margin: 0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f4f6f8; color: #111827; }
        button, input, select, textarea { font: inherit; }
        button { border: 0; border-radius: 6px; padding: 10px 14px; background: #e5e7eb; color: #111827; cursor: pointer; font-weight: 700; }
        button:hover { background: #d1d5db; }
        .primary { background: #2563eb; color: white; width: 100%; }
        .danger { color: #991b1b; background: #fee2e2; }
        .app-shell { max-width: 1360px; margin: 0 auto; padding: 24px; }
        .topbar { display: flex; align-items: flex-start; justify-content: space-between; gap: 24px; padding: 28px; border-radius: 10px; background: #102033; color: white; }
        .topbar h1 { margin: 8px 0; font-size: 36px; line-height: 1.1; }
        .topbar p { margin: 0; color: #d5dee9; max-width: 780px; line-height: 1.6; }
        .eyebrow { color: #93c5fd !important; text-transform: uppercase; letter-spacing: 0.14em; font-size: 12px; font-weight: 800; }
        .hero-tags, .status-row, .feature-grid { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
        .hero-tags span, .status-row span, .feature-grid span { border-radius: 999px; background: #eff6ff; color: #1d4ed8; padding: 7px 10px; font-size: 12px; font-weight: 800; }
        .hero-tags span { background: rgba(255,255,255,0.12); color: white; }
        .toolbar { display: flex; gap: 10px; min-width: 280px; justify-content: flex-end; }
        .toolbar select, .filters select, .filters input { min-height: 42px; border-radius: 6px; border: 1px solid #cbd5e1; padding: 0 12px; background: white; }
        .alert { margin-top: 16px; border: 1px solid #fecaca; background: #fff1f2; color: #9f1239; padding: 12px 14px; border-radius: 8px; }
        .metrics-grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 14px; margin: 18px 0; }
        .metric { background: white; border: 1px solid #d9dee7; border-radius: 8px; padding: 16px; }
        .metric.urgent { border-color: #fecaca; background: #fff7f7; }
        .metric span { color: #64748b; font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; }
        .metric strong { display: block; margin-top: 8px; font-size: 23px; }
        .layout { display: grid; grid-template-columns: 430px minmax(0, 1fr); gap: 18px; align-items: start; }
        .insight-grid { display: grid; grid-template-columns: 0.9fr 1.1fr; gap: 18px; margin-top: 18px; }
        .panel { background: white; border: 1px solid #d9dee7; border-radius: 8px; padding: 18px; box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04); }
        .section-title { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; margin-bottom: 16px; }
        .section-title h2 { margin: 0; font-size: 18px; }
        .section-title span { color: #64748b; font-size: 13px; }
        .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
        .wide { grid-column: 1 / -1; }
        label { display: grid; gap: 6px; color: #334155; font-weight: 700; font-size: 13px; }
        input, select, textarea { width: 100%; border: 1px solid #cbd5e1; border-radius: 6px; min-height: 42px; padding: 10px 12px; background: #fbfdff; }
        textarea { min-height: 92px; resize: vertical; }
        .form-panel .primary { margin-top: 14px; }
        .filters { display: grid; grid-template-columns: minmax(0, 1fr) 180px; gap: 10px; margin-bottom: 12px; }
        .records, .queue-list { display: grid; gap: 12px; }
        .record-card, .queue-list div { border: 1px solid #e5e7eb; border-radius: 8px; padding: 14px; background: #fbfdff; }
        .record-head { display: flex; justify-content: space-between; gap: 16px; }
        .record-card h3 { margin: 0 0 5px; font-size: 16px; }
        .record-card p, .queue-list span { margin: 6px 0; color: #475569; line-height: 1.5; font-size: 14px; }
        .record-meta { display: flex; flex-wrap: wrap; gap: 8px; margin: 10px 0; }
        .record-meta span, .record-meta strong { border-radius: 6px; background: #f1f5f9; padding: 6px 8px; font-size: 12px; }
        .progress { height: 8px; border-radius: 999px; overflow: hidden; background: #e5e7eb; margin: 10px 0; }
        .progress span { display: block; height: 100%; background: #16a34a; }
        .actions { display: flex; gap: 8px; justify-content: flex-end; }
        .empty { min-height: 220px; border: 1px dashed #cbd5e1; border-radius: 8px; display: grid; place-items: center; color: #64748b; background: #f8fafc; }
        @media (max-width: 980px) {
          .topbar, .layout, .insight-grid { grid-template-columns: 1fr; display: grid; }
          .metrics-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
          .toolbar, .filters, .form-grid { grid-template-columns: 1fr; display: grid; min-width: 0; }
        }
        """
    ).strip()


def readme(payload: dict) -> str:
    return dedent(
        f"""
        # {payload["productName"]}

        This runnable local-business app was generated by SWARM.AI from one plain-language prompt.

        ## Why This Is Different

        SWARM.AI generated a domain-aware operations app for a {payload["businessType"]}, not a generic landing page. The app includes customer records, daily queue tracking, reminders, payment status, dashboard metrics, seed data, local-language UX, tests, and a local API.

        ## Problem

        {payload["problem"]}

        ## Audience

        {payload["audience"]}

        ## Features Covered

        {chr(10).join(f"- {feature}" for feature in payload["features"])}

        ## Business Rules

        {chr(10).join(f"- {rule}" for rule in payload["businessRules"])}

        ## Local Language Support

        The app includes English, Hindi, and Kannada translation dictionaries, a language switcher, and `Intl` date/currency formatting for India.

        ## Run Locally

        ```bash
        npm install
        npm run dev
        ```

        API runs on `http://127.0.0.1:3001`.
        Frontend runs on the Vite URL shown in the terminal.

        ## Demo Flow

        1. Review open, overdue, follow-up, payment, and revenue metrics.
        2. Use the daily queue to see work due next.
        3. Search/filter records by customer, service, staff, status, or payment state.
        4. Create a new {payload["recordLabel"]} with customer, due date, follow-up date, payment status, assigned staff, amount, progress, and next action.
        5. Edit status/progress/payment and confirm the dashboard updates.
        6. Switch language between English, Hindi, and Kannada.
        7. Reset demo data.

        ## Validation

        ```bash
        npm run check
        npm run test
        npm run build
        ```
        """
    ).strip()
