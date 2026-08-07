"""Focused tests for deterministic Builder orchestration and integration."""

from __future__ import annotations

import json
import os
import unittest
from copy import deepcopy
from unittest.mock import patch

from backend.agents.architect import fallback_architecture, validate_architecture_contract
from backend.agents.builder import run_builder
from backend.agents.builder_agent.agent import run_build
from backend.agents.builder_agent.database import database_url_for_namespace


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
        files = run_build(self.architecture, "builder-unit-test")

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
        run_build(self.architecture, "builder-no-auth")
        auth_tool.assert_not_called()

    @patch(
        "backend.agents.builder_agent.builder_graph.apply_database_schema",
        return_value={"tables_created": [], "errors": [], "sql": []},
    )
    def test_required_auth_is_integrated_into_server_and_ui(self, _schema_apply) -> None:
        architecture = deepcopy(self.architecture)
        architecture["auth"] = {"required": True, "protected_paths": ["/api/items"]}

        files = run_build(architecture, "builder-with-auth")
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

        graph_run_build.assert_called_once_with(self.architecture, "pipeline-builder-test")
        write_code_files.assert_called_once_with("pipeline-builder-test", generated)
        self.assertIs(result["code_files"], generated)
        self.assertEqual(result["agent_statuses"]["builder"], "done")
        self.assertEqual(result["llm_calls"][-1]["provider"], "langgraph")

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


if __name__ == "__main__":
    unittest.main()
