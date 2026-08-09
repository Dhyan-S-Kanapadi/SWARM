"""Tests for LiteLLM agent routing without provider network calls."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.agents.llm import LLMUnavailableError, call_llm_json, llm_configuration_status


def _completion_response(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


class LiteLLMRoutingTests(unittest.TestCase):
    @patch.dict(
        os.environ,
        {
            "LLM_ANALYST_MODEL": "openai/gpt-4o-mini",
            "LLM_ANALYST_API_KEY": "analyst-key",
            "LLM_ANALYST_FALLBACK_MODELS": "",
            "LLM_REQUEST_TOKEN_BUDGET": "10000",
        },
        clear=True,
    )
    @patch("backend.agents.llm.completion")
    def test_agent_uses_its_own_model_and_api_key(self, mocked_completion) -> None:
        mocked_completion.return_value = _completion_response('{"ok": true}')

        result = call_llm_json(
            agent_name="analyst",
            system_prompt="Return JSON.",
            user_content="test",
            max_tokens=20,
            temperature=0.1,
        )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(mocked_completion.call_args.kwargs["model"], "openai/gpt-4o-mini")
        self.assertEqual(mocked_completion.call_args.kwargs["api_key"], "analyst-key")
        self.assertEqual(mocked_completion.call_args.kwargs["max_tokens"], 2200)

    @patch.dict(
        os.environ,
        {
            "LLM_ANALYST_MODEL": "groq/llama-3.3-70b-versatile",
            "LLM_ANALYST_API_KEY": "analyst-key",
            "LLM_ARCHITECT_MODEL": "anthropic/claude-sonnet-4-5-20250929",
            "LLM_ARCHITECT_API_KEY": "architect-key",
            "LLM_PITCHER_MODEL": "openai/gpt-4o-mini",
            "LLM_PITCHER_API_KEY": "pitcher-key",
        },
        clear=True,
    )
    def test_health_configuration_reports_independent_agent_routes(self) -> None:
        status = llm_configuration_status()

        self.assertEqual(status["analyst"]["provider"], "groq")
        self.assertEqual(status["architect"]["provider"], "anthropic")
        self.assertEqual(status["pitcher"]["provider"], "openai")
        self.assertTrue(all(route["configured"] for route in status.values()))

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_agent_credentials_fail_before_provider_call(self) -> None:
        with self.assertRaises(LLMUnavailableError):
            call_llm_json(
                agent_name="pitcher",
                system_prompt="Return JSON.",
                user_content="test",
                max_tokens=10,
                temperature=0.1,
            )


if __name__ == "__main__":
    unittest.main()
