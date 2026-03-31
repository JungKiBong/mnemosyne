"""
Unit tests for Episodic Memory Pipeline.

Tests the critical path fixes from Phase C:
  - BUG 1/2: Episode context retrieval (ep.data, WITH aggregation)
  - BUG 3: Null filtering in merge results
  - Reconciliation: episodic binding integrity
  - Airgap mode: SM-free operation
"""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock


# ──────────────────────────────────────────
# D3-1: Episodic Binding Tests
# ──────────────────────────────────────────

class TestEpisodicBinding:
    """Verify that episode_ids on RELATION edges correctly link to Episode nodes."""

    def test_edge_with_episode_contexts_returns_data(self):
        """BUG 1 regression: search results must use ep.data (not ep.text)."""
        from app.storage.search_service import _VECTOR_SEARCH_EDGES, _FULLTEXT_SEARCH_EDGES

        # The Cypher queries must reference ep.data, not ep.text
        assert "ep.data" in _VECTOR_SEARCH_EDGES, \
            "Vector search query should reference ep.data (BUG 1 regression)"
        assert "ep.data" in _FULLTEXT_SEARCH_EDGES, \
            "Fulltext search query should reference ep.data (BUG 1 regression)"

    def test_edge_query_has_with_clause_before_collect(self):
        """BUG 2 regression: WITH clause must precede collect() for proper aggregation."""
        from app.storage.search_service import _VECTOR_SEARCH_EDGES, _FULLTEXT_SEARCH_EDGES

        # Both queries must have WITH ... collect(ep.data) pattern
        for name, query in [("vector", _VECTOR_SEARCH_EDGES), ("fulltext", _FULLTEXT_SEARCH_EDGES)]:
            # WITH must appear before collect()
            with_pos = query.find("WITH")
            collect_pos = query.find("collect(ep.data)")
            assert with_pos != -1, f"{name} query missing WITH clause"
            assert collect_pos != -1, f"{name} query missing collect(ep.data)"
            assert with_pos < collect_pos, \
                f"{name} query: WITH must come before collect() (BUG 2 regression)"


# ──────────────────────────────────────────
# D3-2: Context Retrieval Tests
# ──────────────────────────────────────────

class TestContextRetrieval:
    """Verify that HybridStorage._merge_search_results correctly formats episodic context."""

    def _make_hybrid_storage(self):
        """Create a HybridStorage with mocked dependencies."""
        from app.storage.hybrid_storage import HybridStorage

        mock_neo4j = MagicMock()
        mock_sm = MagicMock()
        mock_sm.client = None  # Simulate airgap mode

        with patch('app.resilience.outbox_worker.OutboxWorker.start'):
            storage = HybridStorage(neo4j_storage=mock_neo4j, sm_client=mock_sm)

        return storage

    def test_merge_with_episode_contexts(self):
        """Merged results should include '근거 상황:' when episode_contexts present."""
        storage = self._make_hybrid_storage()

        neo4j_results = {
            "edges": [
                {
                    "fact": "Alice likes technology",
                    "score": 0.95,
                    "episode_contexts": ["Alice posted about AI trends", "Alice shared a tech article"],
                }
            ],
            "nodes": [],
        }

        merged = storage._merge_search_results([], neo4j_results, 10)

        assert len(merged) == 1
        assert "근거 상황:" in merged[0]["content"]
        assert "Alice posted about AI trends" in merged[0]["content"]
        assert merged[0]["source"] == "neo4j"

    def test_merge_filters_none_in_episode_contexts(self):
        """BUG 3 regression: None values in episode_contexts must be filtered out."""
        storage = self._make_hybrid_storage()

        neo4j_results = {
            "edges": [
                {
                    "fact": "Bob follows crypto",
                    "score": 0.8,
                    "episode_contexts": [None, "Bob commented on Bitcoin", None],
                }
            ],
            "nodes": [],
        }

        merged = storage._merge_search_results([], neo4j_results, 10)

        assert len(merged) == 1
        # Should contain context from the non-None episode
        assert "Bob commented on Bitcoin" in merged[0]["content"]
        # Should NOT contain "None" string
        assert "None" not in merged[0]["content"]

    def test_merge_without_context_no_crash(self):
        """No episode_contexts key should still produce valid output."""
        storage = self._make_hybrid_storage()

        neo4j_results = {
            "edges": [
                {
                    "fact": "Simple fact without context",
                    "score": 0.7,
                }
            ],
            "nodes": [],
        }

        merged = storage._merge_search_results([], neo4j_results, 10)

        assert len(merged) == 1
        assert "Simple fact without context" in merged[0]["content"]
        assert "근거 상황:" not in merged[0]["content"]


# ──────────────────────────────────────────
# D3-3: Reconciliation Episodic Tests
# ──────────────────────────────────────────

class TestReconciliationEpisodic:
    """Test episodic binding integrity checks in ReconciliationService."""

    def test_check_episodic_binding_detects_broken_links(self):
        """_check_episodic_binding should report broken episode_ids."""
        from app.storage.reconciliation_service import ReconciliationService, ReconciliationResult

        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)

        # Simulate: 1 relation has a broken episode_id
        mock_session.run.side_effect = [
            MagicMock(data=MagicMock(return_value=[
                {"rel_uuid": "rel-1", "fact": "Alice likes tech", "missing_episode": "ep-dead-1234"}
            ])),
            MagicMock(data=MagicMock(return_value=[])),  # no orphan relations
        ]

        service = ReconciliationService(driver=mock_driver)
        result = ReconciliationResult()

        service._check_episodic_binding(result, auto_fix=False)

        assert len(result.issues) == 1
        assert "Broken episode binding" in result.issues[0]["description"]
        assert result.issues[0]["severity"] == "warning"

    def test_check_episodic_binding_auto_fix(self):
        """auto_fix=True should execute repair query and mark as auto_fixed."""
        from app.storage.reconciliation_service import ReconciliationService, ReconciliationResult

        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)

        mock_session.run.side_effect = [
            MagicMock(data=MagicMock(return_value=[
                {"rel_uuid": "rel-2", "fact": "Bob follows crypto news", "missing_episode": "ep-gone-5678"}
            ])),
            MagicMock(),  # auto-fix SET query
            MagicMock(data=MagicMock(return_value=[])),  # no orphan relations
        ]

        service = ReconciliationService(driver=mock_driver)
        result = ReconciliationResult()

        service._check_episodic_binding(result, auto_fix=True)

        assert len(result.issues) == 1
        assert result.issues[0]["auto_fixed"] is True
        assert "cleaned" in result.issues[0]["description"]

    def test_sm_drift_skipped_without_client(self):
        """When SM is unavailable, drift check should skip gracefully."""
        from app.storage.reconciliation_service import ReconciliationService, ReconciliationResult

        mock_driver = MagicMock()
        service = ReconciliationService(driver=mock_driver, sm_client=None)
        result = ReconciliationResult()

        # Should not raise, should just return silently
        service._check_neo4j_sm_drift(result)

        assert len(result.issues) == 0


# ──────────────────────────────────────────
# D3-4: Airgap Mode Tests
# ──────────────────────────────────────────

class TestAirgapMode:
    """Verify system works without Supermemory SDK installed."""

    def test_sm_client_graceful_without_sdk(self):
        """SupermemoryClientWrapper should work when supermemory package is not installed."""
        from app.storage.supermemory_client import SupermemoryClientWrapper

        # Whether or not the SDK is installed, creating the wrapper shouldn't crash
        client = SupermemoryClientWrapper()
        # If SDK is not installed, client should be None
        # If SDK IS installed but no API key, it may still initialize
        assert isinstance(client, SupermemoryClientWrapper)

    def test_hybrid_storage_neo4j_only_search(self):
        """With SM client=None, search should still work via Neo4j fallback."""
        from app.storage.hybrid_storage import HybridStorage

        mock_neo4j = MagicMock()
        mock_neo4j.search.return_value = {
            "edges": [
                {"fact": "Test fact", "score": 0.9, "episode_contexts": ["original event"]}
            ],
            "nodes": [],
        }

        mock_sm = MagicMock()
        mock_sm.client = None  # Airgap: no SM

        with patch('app.resilience.outbox_worker.OutboxWorker.start'):
            storage = HybridStorage(neo4j_storage=mock_neo4j, sm_client=mock_sm)

        results = storage.search("graph_1", "test query", limit=5)

        assert len(results) == 1
        assert "Test fact" in results[0]["content"]
        mock_neo4j.search.assert_called_once()

    def test_hybrid_health_shows_sm_unavailable(self):
        """Health check should report SM as unavailable in airgap mode."""
        from app.storage.hybrid_storage import HybridStorage

        mock_neo4j = MagicMock()
        mock_neo4j.health_check.return_value = {"status": "ok"}

        mock_sm = MagicMock()
        mock_sm.client = None

        with patch('app.resilience.outbox_worker.OutboxWorker.start'):
            storage = HybridStorage(neo4j_storage=mock_neo4j, sm_client=mock_sm)

        health = storage.health_check()
        assert health["supermemory"]["sm_available"] is False
        assert health["neo4j"]["status"] == "ok"
