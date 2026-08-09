"""Tests for strict Architect validation and repair behavior."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from backend.agents.architect import fallback_architecture, run_architect


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


if __name__ == "__main__":
    unittest.main()
