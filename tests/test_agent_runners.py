"""Focused runner tests for the LLM-backed Analyst and Pitcher agents."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.agents.analyst import run_analyst
from backend.agents.pitcher import run_pitcher


class AgentRunnerTests(unittest.TestCase):
    def _state(self) -> dict:
        return {
            "run_id": "agent-runner-test",
            "idea": "A neighborhood task tracker",
            "requirements": {"problem_statement": "Track neighborhood tasks", "core_features": ["CRUD"]},
            "architecture": {"tech_stack": {}, "ui_screens": []},
            "code_files": {"src/App.jsx": "export default function App() {}"},
            "agent_statuses": {},
            "llm_calls": [],
            "errors": [],
        }

    @patch("backend.agents.analyst.write_json")
    @patch("backend.agents.analyst.load_prompt", return_value="analyst prompt")
    @patch("backend.agents.analyst.call_llm_json", return_value={"problem_statement": "Track tasks"})
    def test_analyst_records_successful_llm_result(self, call_llm, _prompt, write_json) -> None:
        state = run_analyst(self._state())

        self.assertEqual(state["requirements"], {"problem_statement": "Track tasks"})
        self.assertEqual(state["agent_statuses"]["analyst"], "done")
        self.assertEqual(state["llm_calls"][-1]["status"], "success")
        self.assertEqual(call_llm.call_args.kwargs["agent_name"], "analyst")
        write_json.assert_called_once_with("agent-runner-test", "requirements.json", state["requirements"])

    @patch("backend.agents.analyst.write_json")
    @patch("backend.agents.analyst.allow_fallback_for_idea", return_value=True)
    @patch("backend.agents.analyst.call_llm_json", side_effect=RuntimeError("provider unavailable"))
    def test_analyst_uses_fallback_only_when_allowed(self, _call_llm, _fallback_allowed, write_json) -> None:
        state = run_analyst(self._state())

        self.assertEqual(state["agent_statuses"]["analyst"], "done")
        self.assertEqual(state["llm_calls"][-1]["status"], "fallback")
        self.assertIn("Analyst used fallback", state["errors"][-1])
        write_json.assert_called_once_with("agent-runner-test", "requirements.json", state["requirements"])

    @patch("backend.agents.analyst.allow_fallback_for_idea", return_value=False)
    @patch("backend.agents.analyst.call_llm_json", side_effect=RuntimeError("provider unavailable"))
    def test_analyst_marks_state_fatal_when_fallback_is_not_allowed(self, _call_llm, _fallback_allowed) -> None:
        state = self._state()

        with self.assertRaisesRegex(RuntimeError, "provider unavailable"):
            run_analyst(state)

        self.assertTrue(state["fatal_error"])
        self.assertEqual(state["agent_statuses"]["analyst"], "error")

    @patch("backend.agents.pitcher.write_json")
    @patch("backend.agents.pitcher.load_prompt", return_value="pitcher prompt")
    @patch("backend.agents.pitcher.call_llm_json", return_value={"tagline": "Task tracking made simple"})
    def test_pitcher_records_successful_llm_result(self, call_llm, _prompt, write_json) -> None:
        state = run_pitcher(self._state())

        self.assertEqual(state["pitch_deck"], {"tagline": "Task tracking made simple"})
        self.assertEqual(state["agent_statuses"]["pitcher"], "done")
        self.assertEqual(state["llm_calls"][-1]["status"], "success")
        self.assertEqual(call_llm.call_args.kwargs["agent_name"], "pitcher")
        write_json.assert_called_once_with("agent-runner-test", "pitch_deck.json", state["pitch_deck"])

    @patch("backend.agents.pitcher.write_json")
    @patch("backend.agents.pitcher.allow_fallback_for_idea", return_value=True)
    @patch("backend.agents.pitcher.call_llm_json", side_effect=RuntimeError("provider unavailable"))
    def test_pitcher_uses_fallback_only_when_allowed(self, _call_llm, _fallback_allowed, write_json) -> None:
        state = run_pitcher(self._state())

        self.assertEqual(state["agent_statuses"]["pitcher"], "done")
        self.assertEqual(state["llm_calls"][-1]["status"], "fallback")
        self.assertIn("Pitcher used fallback", state["errors"][-1])
        write_json.assert_called_once_with("agent-runner-test", "pitch_deck.json", state["pitch_deck"])

    @patch("backend.agents.pitcher.allow_fallback_for_idea", return_value=False)
    @patch("backend.agents.pitcher.call_llm_json", side_effect=RuntimeError("provider unavailable"))
    def test_pitcher_marks_state_fatal_when_fallback_is_not_allowed(self, _call_llm, _fallback_allowed) -> None:
        state = self._state()

        with self.assertRaisesRegex(RuntimeError, "provider unavailable"):
            run_pitcher(state)

        self.assertTrue(state["fatal_error"])
        self.assertEqual(state["agent_statuses"]["pitcher"], "error")


if __name__ == "__main__":
    unittest.main()
