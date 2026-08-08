"""Tests for SWARM's LangGraph orchestration boundaries."""

from __future__ import annotations

import unittest

from backend.agents.builder import format_builder_context
from backend.graph import build_post_builder_graph


class GraphOrchestrationTests(unittest.TestCase):
    def test_builder_context_describes_nested_langgraph_sequence(self) -> None:
        context = format_builder_context(
            {
                "idea": "Salon booking tracker",
                "requirements": {"core_features": ["Bookings"]},
                "architecture": {"api_routes": []},
            }
        )

        self.assertIn('"orchestration": "langgraph:schema_apply->generate_api_routes->generate_ui_screens->scaffold_auth"', context)

    def test_post_builder_continuation_executes_pitcher_as_a_graph_node(self) -> None:
        calls: list[str] = []

        def pitcher_node(state: dict) -> dict:
            calls.append("pitcher")
            state["pitch_deck"] = {"tagline": "Ready"}
            return state

        result = build_post_builder_graph(pitcher_node, lambda state: state).invoke(
            {
                "run_id": "post-builder-graph-test",
                "idea": "Salon booking tracker",
                "agent_statuses": {"pitcher": "pending"},
            }
        )

        self.assertEqual(calls, ["pitcher"])
        self.assertEqual(result["pitch_deck"], {"tagline": "Ready"})

    def test_post_builder_continuation_propagates_pitcher_failures(self) -> None:
        def failing_pitcher(_state: dict) -> dict:
            raise RuntimeError("Pitcher unavailable")

        with self.assertRaisesRegex(RuntimeError, "Pitcher unavailable"):
            build_post_builder_graph(failing_pitcher, lambda state: state).invoke(
                {
                    "run_id": "post-builder-graph-failure",
                    "idea": "Salon booking tracker",
                }
            )

    def test_post_builder_continuation_runs_openhands_before_pitcher(self) -> None:
        calls: list[str] = []

        def openhands_node(state: dict) -> dict:
            calls.append("openhands")
            return state

        def pitcher_node(state: dict) -> dict:
            calls.append("pitcher")
            return state

        build_post_builder_graph(pitcher_node, openhands_node).invoke(
            {"run_id": "post-builder-order", "idea": "Salon booking tracker"}
        )

        self.assertEqual(calls, ["openhands", "pitcher"])


if __name__ == "__main__":
    unittest.main()
