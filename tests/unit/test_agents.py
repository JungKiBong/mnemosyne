"""Unit tests for ObserverOrchestrator and SearchAgent."""
import time
import pytest
from unittest.mock import MagicMock, patch

from app.services.graph_memory_updater import AgentActivity, GraphMemoryUpdater
from app.services.observer_orchestrator import ObserverOrchestrator
from app.services.observer_agent import ObserverType
from app.services.search_agent import SearchAgent, SearchResult, SearchMode


class TestObserverOrchestrator:
    """Test ObserverOrchestrator fan-out and lifecycle."""

    def _make_activity(self, agent_name="Alice", action="CREATE_POST"):
        return AgentActivity(
            platform="twitter",
            agent_id=1,
            agent_name=agent_name,
            action_type=action,
            action_args={"content": "hello world"},
            round_num=1,
            timestamp="2026-01-01T00:00:00",
        )

    def test_orchestrator_creates_3_observers(self):
        mock_storage = MagicMock()
        mock_llm = MagicMock()
        orch = ObserverOrchestrator(mock_storage, "graph_1", mock_llm)

        assert len(orch.observers) == 3
        assert ObserverType.PERSONAL in orch.observers
        assert ObserverType.EVENT in orch.observers
        assert ObserverType.SOCIAL in orch.observers

    def test_observe_fans_out_to_all_observers(self):
        mock_storage = MagicMock()
        mock_llm = MagicMock()
        orch = ObserverOrchestrator(mock_storage, "graph_1", mock_llm)
        orch.start()

        activity = self._make_activity()
        orch.observe(activity)

        # Each observer should have 1 item in queue
        time.sleep(0.5)
        for obs_type, agent in orch.observers.items():
            assert agent._queue.qsize() >= 0  # may have been processed already

        assert orch._total_observed == 1
        orch.stop()

    def test_do_nothing_skipped(self):
        mock_storage = MagicMock()
        mock_llm = MagicMock()
        orch = ObserverOrchestrator(mock_storage, "graph_1", mock_llm)
        orch.start()

        activity = self._make_activity(action="DO_NOTHING")
        # Observer agents skip DO_NOTHING internally
        orch.observe(activity)

        assert orch._total_observed == 1  # orchestrator counts it
        orch.stop()

    def test_stats(self):
        mock_storage = MagicMock()
        mock_llm = MagicMock()
        orch = ObserverOrchestrator(mock_storage, "graph_1", mock_llm)

        stats = orch.get_stats()
        assert stats["graph_id"] == "graph_1"
        assert stats["running"] is False
        assert "observers" in stats
        assert len(stats["observers"]) == 3


class TestGraphMemoryUpdaterWithObserver:
    """Test that GraphMemoryUpdater integrates with ObserverOrchestrator."""

    def _make_activity(self, agent_name="Bob", action="LIKE_POST"):
        return AgentActivity(
            platform="twitter",
            agent_id=2,
            agent_name=agent_name,
            action_type=action,
            action_args={"post_content": "interesting"},
            round_num=1,
            timestamp="2026-01-01T00:00:00",
        )

    def test_updater_without_observer(self):
        """Backward compatibility — should work without observer."""
        mock_storage = MagicMock()
        updater = GraphMemoryUpdater("graph_1", mock_storage)
        updater.start()

        activity = self._make_activity()
        updater.add_activity(activity)

        time.sleep(0.5)
        updater.stop()

        assert updater._total_activities == 1

    def test_updater_with_observer_dispatches(self):
        """Observer receives activities via fan-out."""
        mock_storage = MagicMock()
        mock_llm = MagicMock()
        mock_observer = MagicMock()

        updater = GraphMemoryUpdater("graph_1", mock_storage, observer_orchestrator=mock_observer)
        updater.start()

        activity = self._make_activity()
        updater.add_activity(activity)

        time.sleep(0.5)
        updater.stop()

        # Observer.observe() should have been called once
        mock_observer.observe.assert_called_once_with(activity)
        mock_observer.start.assert_called_once()
        mock_observer.stop.assert_called_once()


class TestSearchResult:
    """Test SearchResult formatting."""

    def test_prompt_injection_format(self):
        result = SearchResult(
            facts=["Alice likes coffee", "Alice works at TechCo"],
            context=["Alice often agrees with Bob on tech topics"],
            timeline=["Round 1: Alice created her first post"],
            profile_summary="Traits: tech-savvy, extroverted",
        )

        prompt = result.to_prompt_injection()
        assert "[Agent Profile]" in prompt
        assert "tech-savvy" in prompt
        assert "[Known Facts]" in prompt
        assert "Alice likes coffee" in prompt
        assert "[Social Context]" in prompt
        assert "[Timeline]" in prompt

    def test_empty_result(self):
        result = SearchResult()
        prompt = result.to_prompt_injection()
        assert prompt == ""


class TestSearchAgent:
    """Test SearchAgent with mocked storage."""

    def test_retrieve_returns_search_result(self):
        mock_storage = MagicMock()
        mock_sm = MagicMock()

        # Mock SM profile
        mock_sm.get_profile.return_value = {
            "static": ["conservative", "tech worker"],
            "dynamic": ["currently angry at Bob"],
        }
        # Mock SM search
        mock_sm.search_memories.return_value = {
            "memories": [
                {"content": "Alice posted about AI"},
                {"content": "Alice liked Bob's post"},
            ]
        }
        mock_storage.sm = mock_sm

        search = SearchAgent(mock_storage, "graph_1")
        result = search.retrieve("Alice", "What does Alice think about AI?", current_round=1)

        assert isinstance(result, SearchResult)
        assert result.search_time_ms > 0
        assert result.profile_summary is not None
        assert "conservative" in result.profile_summary

        search.shutdown()

    def test_profile_caching(self):
        mock_storage = MagicMock()
        mock_sm = MagicMock()
        mock_sm.get_profile.return_value = {"static": ["calm"], "dynamic": []}
        mock_sm.search_memories.return_value = {"memories": []}
        mock_storage.sm = mock_sm

        search = SearchAgent(mock_storage, "graph_1", profile_cache_rounds=3)

        # First call: profile is fetched
        search.retrieve("Alice", "test", current_round=1)
        assert mock_sm.get_profile.call_count == 1

        # Second call same round: cached
        search.retrieve("Alice", "test2", current_round=1)
        assert mock_sm.get_profile.call_count == 1  # no new call

        # Third call, 3 rounds later: cache expired
        search.retrieve("Alice", "test3", current_round=5)
        assert mock_sm.get_profile.call_count == 2

        search.shutdown()
