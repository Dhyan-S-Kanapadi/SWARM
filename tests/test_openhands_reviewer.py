"""Tests for the optional OpenHands post-build graph node."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.agents.openhands_reviewer import run_openhands_builder, run_openhands_reviewer


class OpenHandsReviewerTests(unittest.TestCase):
    @patch.dict(os.environ, {"OPENHANDS_ENABLED": "false"}, clear=True)
    def test_missing_or_disabled_configuration_skips_without_failing_build(self) -> None:
        state = {"run_id": "openhands-skip", "agent_statuses": {}, "llm_calls": []}

        result = run_openhands_reviewer(state)

        self.assertIs(result, state)
        self.assertEqual(result["agent_statuses"]["openhands"], "skipped")
        self.assertEqual(result["llm_calls"][-1]["status"], "skipped")

    def test_openhands_builder_requires_a_source_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            workspace = root / "code_files"
            workspace.mkdir()
            source = workspace / "src" / "App.jsx"
            source.parent.mkdir()
            source.write_text("export default function App() { return null; }\n", encoding="utf-8")
            state = {"run_id": "openhands-build", "agent_statuses": {}, "llm_calls": [], "architecture": {}}

            with (
                patch("backend.agents.openhands_reviewer.output_dir", return_value=root),
                patch("backend.agents.openhands_reviewer.read_code_files", return_value={"src/App.jsx": "changed"}),
                patch("backend.agents.openhands_reviewer.write_json"),
                patch("backend.agents.openhands_reviewer._openhands_config", return_value={"model": "openrouter/test", "api_key": "key", "base_url": ""}),
                patch("backend.agents.openhands_reviewer._openhands_is_required", return_value=True),
                patch("backend.agents.openhands_reviewer._run_openhands_build", side_effect=lambda *_: {"final_message": "done"}),
            ):
                with self.assertRaisesRegex(RuntimeError, "without changing application source files"):
                    run_openhands_builder(state)

            self.assertEqual(state["agent_statuses"]["openhands"], "error")

    def test_previous_reviewer_name_remains_compatible(self) -> None:
        self.assertIs(run_openhands_reviewer, run_openhands_builder)


if __name__ == "__main__":
    unittest.main()
