"""Focused tests for deterministic Builder orchestration and integration."""

from __future__ import annotations

import json
import os
import unittest
from copy import deepcopy
from unittest.mock import patch

from backend.agents.architect import fallback_architecture, validate_architecture_contract
from backend.agents.builder import run_builder
from backend.agents.builder_agent.agent import _openhands_task, run_build, run_deterministic_build
from backend.agents.builder_agent.database import database_url_for_namespace
from backend.agents.builder_agent.tools.generate_ui_screens import generate_ui_screens
from backend.agents.builder_agent.tools.generate_api_routes import generate_api_routes


RUNNABLE_FILES = {
    "package.json",
    "index.html",
    "vite.config.js",
    "README.md",
    "docker-compose.yml",
    ".env.example",
    "server/index.js",
    "server/setup-db.js",
    "server/app.test.js",
    "src/main.jsx",
    "src/App.jsx",
    "src/api.js",
    "src/i18n.js",
    "src/styles.css",
}


class BuilderAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.architecture = fallback_architecture({})
        self.database_env = patch.dict(os.environ, {"DATABASE_URL": ""})
        self.database_env.start()

    def tearDown(self) -> None:
        self.database_env.stop()

    @patch(
        "backend.agents.builder_agent.builder_graph.apply_database_schema",
        return_value={"tables_created": [], "errors": [], "sql": []},
    )
    def test_run_build_returns_complete_npm_project(self, _schema_apply) -> None:
        files = run_deterministic_build(self.architecture, "builder-unit-test")

        self.assertTrue(RUNNABLE_FILES <= set(files))
        package = json.loads(files["package.json"])
        self.assertEqual(package["scripts"]["test"], "node --test server/app.test.js")
        self.assertIn("pg", package["dependencies"])
        self.assertIn("server/setup-db.js", package["scripts"]["dev:server"])
        self.assertIn("search_path=swarm_builder_unit_test", files["server/index.js"])
        self.assertIn("createRoot", files["src/main.jsx"])

    @patch("backend.agents.builder_agent.builder_graph.scaffold_auth")
    @patch(
        "backend.agents.builder_agent.builder_graph.apply_database_schema",
        return_value={"tables_created": [], "errors": [], "sql": []},
    )
    def test_auth_tool_is_skipped_without_requirement(self, _schema_apply, auth_tool) -> None:
        run_deterministic_build(self.architecture, "builder-no-auth")
        auth_tool.assert_not_called()

    @patch(
        "backend.agents.builder_agent.builder_graph.apply_database_schema",
        return_value={"tables_created": [], "errors": [], "sql": []},
    )
    def test_required_auth_is_integrated_into_server_and_ui(self, _schema_apply) -> None:
        architecture = deepcopy(self.architecture)
        architecture["auth"] = {"required": True, "protected_paths": ["/api/items"]}

        files = run_deterministic_build(architecture, "builder-with-auth")
        package = json.loads(files["package.json"])

        self.assertIn("server/auth.js", files)
        self.assertIn('import { configureAuth } from "./auth.js";', files["server/index.js"])
        self.assertIn("await configureAuth(app, pool);", files["server/index.js"])
        self.assertIn("<AuthGate><App /></AuthGate>", files["src/main.jsx"])
        self.assertIn("express-session", package["dependencies"])

    @patch("backend.agents.builder.write_text")
    @patch("backend.agents.builder.write_code_files")
    @patch("backend.agents.builder.run_build")
    def test_pipeline_builder_passes_full_architecture(
        self, graph_run_build, write_code_files, _write_text
    ) -> None:
        generated = {"package.json": "{}"}
        graph_run_build.return_value = generated
        state = {
            "run_id": "pipeline-builder-test",
            "idea": "Salon tracker",
            "requirements": {},
            "architecture": self.architecture,
            "agent_statuses": {"builder": "pending"},
            "llm_calls": [],
        }

        result = run_builder(state)

        graph_run_build.assert_called_once_with(
            self.architecture, "pipeline-builder-test", {}, "Salon tracker"
        )
        write_code_files.assert_called_once_with("pipeline-builder-test", generated)
        self.assertIs(result["code_files"], generated)
        self.assertEqual(result["agent_statuses"]["builder"], "done")
        self.assertEqual(result["llm_calls"][-1]["provider"], "openhands")

    @patch.dict(
        os.environ,
        {
            "DATABASE_URL": "",
            "OPENHANDS_ENABLED": "true",
            "OPENHANDS_MODEL": "openrouter/test",
            "OPENHANDS_API_KEY": "key",
        },
        clear=True,
    )
    @patch("backend.agents.builder_agent.agent.write_json")
    @patch("backend.agents.builder_agent.agent._validate_workspace", return_value={"status": "passed", "checks": []})
    @patch("backend.agents.builder_agent.agent._run_openhands_authoring", return_value={"final_message": "done"})
    @patch("backend.agents.builder_agent.agent.apply_database_schema", return_value={"tables_created": [], "errors": [], "sql": []})
    def test_run_build_uses_openhands_created_source_files(
        self, _schema_apply, _openhands, _validate, write_json
    ) -> None:
        def create_sources(_config, workspace, *_args):
            for relative_path, content in {
                "package.json": '{"scripts":{"build":"vite build"}}',
                "index.html": '<div id="root"></div><script type="module" src="/src/main.jsx"></script>',
                "src/main.jsx": "import './App.jsx';",
                "src/App.jsx": "export default function App(){return <main>Task tracker</main>}",
                "server/index.js": "import express from 'express';",
            }.items():
                path = workspace / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            return {"final_message": "created files"}

        _openhands.side_effect = create_sources

        files = run_build(self.architecture, "builder-openhands-test", {}, "Task tracker")

        self.assertIn("src/App.jsx", files)
        self.assertIn("Task tracker", files["src/App.jsx"])
        diagnostics = write_json.call_args.args[2]
        self.assertEqual(diagnostics["mode"], "openhands_primary")
        self.assertTrue(diagnostics["source_files_changed"])

    @patch.dict(
        os.environ,
        {"DATABASE_URL": "", "OPENHANDS_ENABLED": "true", "OPENHANDS_MODEL": "", "OPENHANDS_API_KEY": ""},
        clear=True,
    )
    @patch("backend.agents.builder_agent.agent.write_json")
    @patch(
        "backend.agents.builder_agent.builder_graph.apply_database_schema",
        return_value={"tables_created": [], "errors": [], "sql": []},
    )
    @patch("backend.agents.builder_agent.agent.apply_database_schema", return_value={"tables_created": [], "errors": [], "sql": []})
    def test_run_build_reports_deterministic_fallback_when_openhands_is_unconfigured(
        self, _primary_schema, _fallback_schema, write_json
    ) -> None:
        with (
            patch("backend.agents.builder_agent.agent.load_dotenv"),
            patch("backend.agents.builder_agent.agent._openhands_config", return_value=None),
        ):
            files = run_build(self.architecture, "builder-fallback-test")

        self.assertIn("src/App.jsx", files)
        diagnostics = write_json.call_args.args[2]
        self.assertEqual(diagnostics["mode"], "deterministic_fallback")
        self.assertIn("fallback_reason", diagnostics)

    def test_openhands_task_declares_windows_powershell_constraints(self) -> None:
        prompt = _openhands_task(self.architecture, {}, "Task tracker")

        self.assertIn("Windows PowerShell", prompt)
        self.assertIn("Do not use Bash", prompt)

    def test_fallback_translates_nested_seed_data_to_schema_rows(self) -> None:
        architecture = fallback_architecture(
            {
                "seed_data": [
                    {
                        "entity": "Customer",
                        "records": [{"full_name": "Ada", "phone": "123"}],
                    }
                ]
            }
        )

        validate_architecture_contract(architecture)
        record = architecture["database_schema"]["work_items"]["seed_records"][0]
        self.assertEqual(record["customerName"], "Ada")
        self.assertEqual(record["category"], "customer")
        self.assertNotIn("entity", record)

    def test_database_namespace_url_uses_libpq_compatible_encoding(self) -> None:
        scoped = database_url_for_namespace(
            "postgresql://postgres:postgres@127.0.0.1:5432/swarm",
            "swarm_test_run",
        )

        self.assertIn("options=-c%20search_path%3Dswarm_test_run", scoped)
        self.assertNotIn("+search_path", scoped)

    def test_ui_generator_recognises_architect_collection_shorthand_and_action_labels(self) -> None:
        files = generate_ui_screens(
            [
                {
                    "name": "LoanForm",
                    "route": "/loans/new",
                    "purpose": "Create a loan",
                    "data_needed": ["/api/books", "/api/members"],
                    "primary_actions": ["Submit Loan", "Cancel"],
                    "states": ["idle", "success"],
                }
            ],
            [
                {"method": "GET", "path": "/api/books", "description": "Books", "request_body": None, "response_shape": "[{id, title}]", "validation_rules": []},
                {"method": "GET", "path": "/api/members", "description": "Members", "request_body": None, "response_shape": "[{id, name}]", "validation_rules": []},
                {"method": "POST", "path": "/api/loans", "description": "Create loan", "request_body": {"book_id": "number", "member_id": "number"}, "response_shape": "{id}", "validation_rules": []},
            ],
        )

        self.assertIn('"createPath": "/api/loans"', files["src/App.jsx"])
        self.assertIn('"isCollection": true', files["src/App.jsx"])
        self.assertIn('hasAction(["add", "create", "register", "submit", "new"])', files["src/App.jsx"])

    def test_api_generator_derives_date_fields_from_architecture_rules(self) -> None:
        server = generate_api_routes(
            [
                {
                    "method": "POST",
                    "path": "/api/loans",
                    "description": "Create loan",
                    "request_body": {"book_id": "number", "member_id": "number"},
                    "response_shape": {"id": "number"},
                    "validation_rules": ["due_date = loan_date+14"],
                }
            ],
            {
                "loans": {
                    "fields": {
                        "id": "SERIAL PRIMARY KEY",
                        "book_id": "INTEGER NOT NULL",
                        "member_id": "INTEGER NOT NULL",
                        "loan_date": "DATE NOT NULL DEFAULT CURRENT_DATE",
                        "due_date": "DATE NOT NULL",
                    }
                }
            },
        )["server/index.js"]

        self.assertIn('"derivedFields": {', server)
        self.assertIn('"due_date": {', server)
        self.assertIn('base.setUTCDate(base.getUTCDate() + definition.days)', server)

    def test_api_generator_adds_preview_health_route_when_architecture_omits_it(self) -> None:
        server = generate_api_routes(
            [
                {
                    "method": "GET",
                    "path": "/api/items",
                    "description": "List items",
                    "request_body": None,
                    "response_shape": [],
                    "validation_rules": [],
                }
            ],
            {"items": {"fields": {"id": "integer primary key"}}},
        )["server/index.js"]

        self.assertIn('"path": "/api/health"', server)


if __name__ == "__main__":
    unittest.main()
