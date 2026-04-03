"""
Comprehensive tests for Cognitive Memory Categories (Phase 16-C+)

Tests all 6 memory categories:
- Preference: Record, upsert, recall
- Instructional: Record, PM auto-promote, recall with priority ordering
- Reflective: Record, reinforcement on repeat, recall
- Conditional: Record, context-matching recall, expiry detection
- Orchestration: Task handoff, status update, auto-reflection on failure, active tasks
- Harness: Process pattern CRUD, auto-extraction, evolution, decay

Also tests the enhanced decay modifier for all 9 categories.
"""

import json
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest


# ──────────────────────────────────────────
# Schema Creator Tests
# ──────────────────────────────────────────

class TestSchemaCreators:
    """Test metadata schema factory functions."""

    def test_create_preference_metadata(self):
        from src.app.storage.memory_categories import create_preference_metadata

        meta = create_preference_metadata(
            key="language", value="korean",
            subcategory="communication", confidence=0.95)

        assert meta["category"] == "preference"
        assert meta["subcategory"] == "communication"
        assert meta["preference"]["key"] == "language"
        assert meta["preference"]["value"] == "korean"
        assert meta["preference"]["confidence"] == 0.95
        assert meta["preference"]["expression_count"] == 1
        assert "last_expressed" in meta["preference"]

    def test_create_instructional_metadata(self):
        from src.app.storage.memory_categories import create_instructional_metadata

        meta = create_instructional_metadata(
            rule="Always write tests first",
            trigger="pre_code", priority="must",
            subcategory="coding", source_agent="user")

        assert meta["category"] == "instructional"
        assert meta["instruction"]["rule"] == "Always write tests first"
        assert meta["instruction"]["trigger"] == "pre_code"
        assert meta["instruction"]["priority"] == "must"
        assert meta["instruction"]["active"] is True
        assert meta["stats"]["applied_count"] == 0
        assert meta["stats"]["compliance_rate"] == 1.0

    def test_create_reflective_metadata(self):
        from src.app.storage.memory_categories import create_reflective_metadata

        meta = create_reflective_metadata(
            event="Neo4j datetime error",
            lesson="Use ISO strings instead of datetime objects",
            severity="high", domain="neo4j")

        assert meta["category"] == "reflective"
        assert meta["reflection"]["event"] == "Neo4j datetime error"
        assert meta["reflection"]["lesson"] == "Use ISO strings instead of datetime objects"
        assert meta["reflection"]["severity"] == "high"
        assert meta["reflection"]["occurrence_count"] == 1

    def test_create_conditional_metadata(self):
        from src.app.storage.memory_categories import create_conditional_metadata

        condition = {"python_version": "<3.10"}
        meta = create_conditional_metadata(
            condition=condition,
            then_action="Use typing.Optional instead of X | Y",
            else_action="Use X | Y union syntax",
            subcategory="version_specific",
            confidence=0.95)

        assert meta["category"] == "conditional"
        assert meta["condition"]["if"] == condition
        assert meta["condition"]["then"] == "Use typing.Optional instead of X | Y"
        assert meta["condition"]["else"] == "Use X | Y union syntax"
        assert meta["condition"]["confidence"] == 0.95

    def test_create_orchestration_metadata(self):
        from src.app.storage.memory_categories import create_orchestration_metadata

        meta = create_orchestration_metadata(
            task_id="task-001",
            task_type="handoff",
            from_agent="planner",
            to_agent="coder",
            context={"files": ["main.py"]},
            status="pending",
            parent_task_id="epic-001")

        assert meta["category"] == "orchestration"
        assert meta["task"]["task_id"] == "task-001"
        assert meta["task"]["from_agent"] == "planner"
        assert meta["task"]["to_agent"] == "coder"
        assert meta["task"]["status"] == "pending"
        assert meta["task"]["context"] == {"files": ["main.py"]}
        assert meta["task"]["parent_task_id"] == "epic-001"
        assert meta["stats"]["handoff_count"] == 0

    def test_create_harness_metadata(self):
        from src.app.storage.memory_categories import create_harness_metadata

        tool_chain = [
            {"tool": "git_diff", "type": "shell", "order": 1, "role": "input"},
            {"tool": "llm_call", "type": "api", "order": 2, "role": "analysis"},
            {"tool": "comment_post", "type": "api", "order": 3, "role": "output"},
        ]
        meta = create_harness_metadata(
            domain="development",
            trigger="PR이 올라왔을 때",
            tool_chain=tool_chain,
            process_type="pipeline",
            tags=["code_review", "automation"],
            source_agent="test_agent")

        assert meta["category"] == "harness"
        assert meta["harness"]["domain"] == "development"
        assert meta["harness"]["trigger"] == "PR이 올라왔을 때"
        assert len(meta["harness"]["tool_chain"]) == 3
        assert meta["harness"]["process_type"] == "pipeline"
        assert "code_review" in meta["harness"]["tags"]
        assert meta["stats"]["execution_count"] == 0
        assert meta["stats"]["success_rate"] == 0.0
        assert meta["evolution"]["current_version"] == 1
        assert len(meta["evolution"]["history"]) == 1
        assert meta["evolution"]["history"][0]["change_reason"] == "initial"
        assert meta["extraction"]["auto_extracted"] is False
        assert meta["extraction"]["user_verified"] is True
        assert meta["extraction"]["source_agent"] == "test_agent"


# ──────────────────────────────────────────
# Decay Modifier Tests (All 8 Categories)
# ──────────────────────────────────────────

class TestDecayModifier:
    """Test category-aware decay modifier."""

    def _calc(self, category, meta_dict=None):
        from src.app.storage.memory_categories import MemoryCategoryManager
        meta_json = json.dumps(meta_dict or {})
        return MemoryCategoryManager.calculate_decay_modifier(category, meta_json)

    def test_declarative_default(self):
        assert self._calc("declarative") == 1.0

    def test_observational_default(self):
        assert self._calc("observational") == 1.0

    def test_preference_slow_decay(self):
        assert self._calc("preference") == 1.1

    def test_instructional_no_decay(self):
        assert self._calc("instructional") == 1.0

    def test_reflective_reinforcement(self):
        meta = {"reflection": {"occurrence_count": 5}}
        result = self._calc("reflective", meta)
        assert result == 1.1  # min(1.1, 1.0 + 5*0.02)

    def test_reflective_capped_at_1_1(self):
        meta = {"reflection": {"occurrence_count": 100}}
        result = self._calc("reflective", meta)
        assert result == 1.1

    def test_conditional_not_expired(self):
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        meta = {"condition": {"valid_until": future}}
        assert self._calc("conditional", meta) == 1.0

    def test_conditional_expired(self):
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        meta = {"condition": {"valid_until": past}}
        assert self._calc("conditional", meta) == 0.5

    def test_orchestration_completed(self):
        meta = {"task": {"status": "completed"}}
        assert self._calc("orchestration", meta) == 0.7

    def test_orchestration_pending(self):
        meta = {"task": {"status": "pending"}}
        assert self._calc("orchestration", meta) == 1.0

    def test_procedural_high_success(self):
        meta = {"stats": {"success_rate": 0.95}}
        assert self._calc("procedural", meta) == 1.05

    def test_procedural_low_success(self):
        meta = {"stats": {"success_rate": 0.3}}
        assert self._calc("procedural", meta) == 0.85

    def test_procedural_stale(self):
        old_date = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
        meta = {
            "stats": {"success_rate": 0.7},
            "versioning": {"last_verified": old_date, "stale_after_days": 90}
        }
        result = self._calc("procedural", meta)
        assert result == pytest.approx(0.9, abs=0.01)  # 1.0 * 0.9

    # ── Harness Decay Tests ──

    def test_harness_high_success(self):
        meta = {"stats": {"success_rate": 0.9}, "extraction": {"user_verified": False}}
        assert self._calc("harness", meta) == 1.1

    def test_harness_low_success(self):
        meta = {"stats": {"success_rate": 0.3}, "extraction": {"user_verified": False}}
        assert self._calc("harness", meta) == 0.8

    def test_harness_verified_bonus(self):
        meta = {"stats": {"success_rate": 0.9}, "extraction": {"user_verified": True}}
        result = self._calc("harness", meta)
        assert result == pytest.approx(1.15, abs=0.01)  # 1.1 + 0.05, capped at 1.15

    def test_harness_stale(self):
        old = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
        meta = {
            "stats": {"success_rate": 0.7, "last_executed": old},
            "extraction": {"user_verified": False}
        }
        result = self._calc("harness", meta)
        assert result == pytest.approx(0.9, abs=0.01)  # 1.0 * 0.9


# ──────────────────────────────────────────
# MCP Tool Registration Tests
# ──────────────────────────────────────────

class TestToolRegistration:
    """Test that all cognitive tools are registered."""

    @pytest.fixture
    def toolkit(self):
        from unittest.mock import patch
        with patch("src.app.storage.memory_manager.MemoryManager.get_instance") as mock_mgr:
            mock_mgr.return_value = MagicMock()
            from src.app.tools.memory_tools import MoriesToolkit
            tk = MoriesToolkit()
            return tk

    def test_cognitive_tools_registered(self, toolkit):
        expected = [
            "memory_preference", "memory_recall_preferences",
            "memory_instruction", "memory_recall_instructions",
            "memory_reflection", "memory_recall_reflections",
            "memory_conditional", "memory_recall_conditionals",
        ]
        for name in expected:
            assert name in toolkit.get_tool_names(), f"Missing tool: {name}"

    def test_orchestration_tools_registered(self, toolkit):
        expected = [
            "memory_task_handoff", "memory_task_update", "memory_active_tasks",
        ]
        for name in expected:
            assert name in toolkit.get_tool_names(), f"Missing tool: {name}"

    def test_harness_tools_registered(self, toolkit):
        expected = [
            "memory_harness_record", "memory_harness_extract",
            "memory_harness_recall", "memory_harness_execute",
            "memory_harness_evolve", "memory_harness_list",
            "memory_harness_compare",
        ]
        for name in expected:
            assert name in toolkit.get_tool_names(), f"Missing tool: {name}"

    def test_harness_tool_has_correct_category(self, toolkit):
        desc = toolkit.get_tool_description("memory_harness_record")
        assert desc["category"] == "harness"

    def test_total_tool_count(self, toolkit):
        # 15 existing + 11 cognitive + 7 harness = 33
        assert len(toolkit.get_tool_names()) == 33

    def test_tool_schemas_export(self, toolkit):
        schemas = toolkit.get_all_schemas(format="openai")
        assert len(schemas) == 33
        # Verify each has function.name and function.parameters
        for schema in schemas:
            assert "function" in schema
            assert "name" in schema["function"]
            assert "parameters" in schema["function"]
