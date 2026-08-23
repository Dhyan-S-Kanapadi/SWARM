"""Tests for strict Architect validation and repair behavior."""

from __future__ import annotations

import os
import json
import unittest
from unittest.mock import patch

from backend.agents.architect import (
    ArchitectureContractError,
    complete_known_contract_defaults,
    fallback_architecture,
    run_architect,
    validate_architecture_contract,
)


class ArchitectContractTests(unittest.TestCase):
    def _state(self) -> dict:
        return {
            "run_id": "architect-contract-test",
            "idea": "A salon appointment manager",
            "requirements": {},
            "agent_statuses": {},
            "llm_calls": [],
        }

    @patch("backend.agents.architect.write_json")
    @patch("backend.agents.architect.load_prompt", return_value="architecture prompt")
    @patch("backend.agents.architect.call_llm_json")
    def test_invalid_architecture_is_repaired_before_builder_can_receive_it(
        self, call_llm, _prompt, _write_json
    ) -> None:
        expected = fallback_architecture({})
        call_llm.side_effect = [{"tech_stack": {}}, expected]

        result = run_architect(self._state())

        self.assertEqual(result["architecture"], expected)
        self.assertEqual(result["agent_statuses"]["architect"], "done")
        self.assertEqual(result["llm_calls"][-1]["status"], "repaired")
        self.assertEqual(result["llm_calls"][-1]["repair_attempts"], 1)
        self.assertEqual(call_llm.call_count, 2)
        repair_payload = json.loads(call_llm.call_args_list[1].kwargs["user_content"])
        self.assertNotIn("requirements", repair_payload)
        self.assertEqual(repair_payload["previous_architecture"], {"tech_stack": {}})

    @patch("backend.agents.architect.write_json")
    @patch("backend.agents.architect.load_prompt", return_value="architecture prompt")
    @patch("backend.agents.architect.call_llm_json", return_value={"tech_stack": {}})
    @patch.dict(
        os.environ,
        {
            "SWARM_ALLOW_LLM_FALLBACK": "false",
            "SWARM_ALLOW_ARCHITECT_CONTRACT_FALLBACK": "false",
            "SWARM_ARCHITECT_REPAIR_ATTEMPTS": "1",
        },
        clear=False,
    )
    def test_invalid_architecture_fails_instead_of_generating_generic_app(
        self, _call_llm, _prompt, _write_json
    ) -> None:
        state = self._state()

        with self.assertRaisesRegex(RuntimeError, "did not produce a build-ready architecture"):
            run_architect(state)

        self.assertEqual(state["agent_statuses"]["architect"], "error")
        self.assertNotIn("architecture", state)

    def test_known_state_management_metadata_is_completed_without_llm_repair(self) -> None:
        architecture = fallback_architecture({})
        architecture["state_management"] = {"forms": "controlled form"}

        completed = complete_known_contract_defaults(architecture)

        validate_architecture_contract(completed)
        self.assertEqual(completed["state_management"]["forms"], "controlled form")
        self.assertIn("frontend_state", completed["state_management"])

    def test_database_table_array_is_normalized_to_builder_schema_map(self) -> None:
        architecture = fallback_architecture({})
        work_items = architecture["database_schema"]["work_items"]
        architecture["database_schema"] = {
            "tables": [{"name": "work_items", **work_items}]
        }

        completed = complete_known_contract_defaults(architecture)

        self.assertEqual(completed["database_schema"], {"work_items": work_items})
        validate_architecture_contract(completed)

    def test_screen_data_labels_are_repaired_instead_of_silently_replaced(self) -> None:
        architecture = fallback_architecture({})
        architecture["ui_screens"][0]["data_needed"] = ["record counts"]

        completed = complete_known_contract_defaults(architecture)

        self.assertEqual(completed["ui_screens"][0]["data_needed"], ["record counts"])
        with self.assertRaisesRegex(ArchitectureContractError, "needs missing API route"):
            validate_architecture_contract(completed)

    def test_duplicate_api_endpoint_is_rejected(self) -> None:
        architecture = fallback_architecture({})
        architecture["api_routes"].append(dict(architecture["api_routes"][1]))

        with self.assertRaisesRegex(ArchitectureContractError, "api route is duplicated"):
            validate_architecture_contract(architecture)

    def test_invalid_api_method_is_rejected(self) -> None:
        architecture = fallback_architecture({})
        architecture["api_routes"][1]["method"] = "FETCH"

        with self.assertRaisesRegex(ArchitectureContractError, "unsupported method"):
            validate_architecture_contract(architecture)

    def test_route_validation_rule_string_is_normalized_to_a_list(self) -> None:
        architecture = fallback_architecture({})
        architecture["api_routes"][1]["validation_rules"] = "status query is optional"

        completed = complete_known_contract_defaults(architecture)

        self.assertEqual(completed["api_routes"][1]["validation_rules"], ["status query is optional"])

    def test_missing_route_validation_rules_are_normalized_to_an_empty_list(self) -> None:
        architecture = fallback_architecture({})
        architecture["api_routes"][1]["validation_rules"] = None

        completed = complete_known_contract_defaults(architecture)

        self.assertEqual(completed["api_routes"][1]["validation_rules"], [])

    def test_auth_route_enables_explicit_builder_auth_configuration(self) -> None:
        architecture = fallback_architecture({})
        architecture["api_routes"].append(
            {
                "method": "POST",
                "path": "/api/auth/login",
                "description": "Log in",
                "request_body": {"email": "string", "password": "string"},
                "response_shape": {"user": "object"},
                "validation_rules": [],
            }
        )

        completed = complete_known_contract_defaults(architecture)
        validate_architecture_contract(completed)

        self.assertEqual(completed["auth"], {"required": True})

    def test_route_body_field_shorthand_is_normalized_to_an_object(self) -> None:
        architecture = fallback_architecture({})
        architecture["api_routes"][2]["request_body"] = "{customerName, title?, dueDate}"

        completed = complete_known_contract_defaults(architecture)

        self.assertEqual(
            completed["api_routes"][2]["request_body"],
            {"customerName": "string", "title": "string", "dueDate": "string"},
        )


if __name__ == "__main__":
    unittest.main()
