"""
E2E smoke test for Cognitive Memory Categories against live Neo4j.

Tests the full record → recall lifecycle for each new category:
- preference, instructional, reflective, conditional, orchestration

Requires: mirofish-neo4j running on localhost:7687
"""

import json
import uuid
import pytest
from datetime import datetime, timezone


@pytest.fixture(scope="module")
def category_manager():
    """Create a MemoryCategoryManager connected to live Neo4j."""
    from neo4j import GraphDatabase

    uri = "bolt://localhost:7687"
    driver = GraphDatabase.driver(uri, auth=("neo4j", "mirofish"))

    # Verify connectivity
    with driver.session() as session:
        session.run("RETURN 1").single()

    from src.app.storage.memory_categories import MemoryCategoryManager
    mgr = MemoryCategoryManager(driver=driver)
    yield mgr

    # Cleanup: remove test nodes
    with driver.session() as session:
        session.run("""
            MATCH (e:Entity)
            WHERE e.name STARTS WITH '[PREF] __test_'
               OR e.name STARTS WITH '[RULE] __test_'
               OR e.name STARTS WITH '[REFL] __test_'
               OR e.name STARTS WITH '[COND] __test_'
               OR e.name STARTS WITH '[TASK] __test_'
            DETACH DELETE e
        """)

    driver.close()


class TestPreferenceE2E:

    def test_record_and_recall(self, category_manager):
        result = category_manager.record_preference(
            key="__test_language",
            value="korean",
            subcategory="communication",
            confidence=0.9,
        )
        assert result["status"] == "created"
        assert result["key"] == "__test_language"

        # Recall
        prefs = category_manager.recall_preferences(key="__test_language")
        assert len(prefs) >= 1
        found = [p for p in prefs if p["key"] == "__test_language"]
        assert found[0]["value"] == "korean"
        assert found[0]["confidence"] == 0.9

    def test_upsert_increments_expression_count(self, category_manager):
        category_manager.record_preference(key="__test_theme", value="dark")
        result2 = category_manager.record_preference(key="__test_theme", value="light")
        assert result2["status"] == "updated"
        assert result2["expression_count"] == 2


class TestInstructionalE2E:

    def test_record_should_priority(self, category_manager):
        result = category_manager.record_instruction(
            rule="__test_always run linting",
            trigger="pre_commit",
            priority="should",
            subcategory="coding",
        )
        assert result["status"] == "created"
        assert result["initial_salience"] == 0.8

    def test_recall_with_trigger_filter(self, category_manager):
        instructions = category_manager.recall_instructions(trigger="pre_commit")
        rules = [i["rule"] for i in instructions]
        assert any("__test_always run linting" in r for r in rules)

    def test_priority_ordering(self, category_manager):
        # Create a must-priority rule
        category_manager.record_instruction(
            rule="__test_must rule for ordering",
            priority="must",
        )
        category_manager.record_instruction(
            rule="__test_may rule for ordering",
            priority="may",
        )

        instructions = category_manager.recall_instructions()
        # must rules should come first
        priorities = [i["priority"] for i in instructions
                      if "__test_" in i.get("rule", "")]
        if len(priorities) >= 2:
            must_idx = next((i for i, p in enumerate(priorities) if p == "must"), None)
            may_idx = next((i for i, p in enumerate(priorities) if p == "may"), None)
            if must_idx is not None and may_idx is not None:
                assert must_idx < may_idx


class TestReflectiveE2E:

    def test_record_and_recall(self, category_manager):
        result = category_manager.record_reflection(
            event="__test_neo4j datetime error",
            lesson="__test_use ISO strings not datetime objects",
            severity="high",
            domain="neo4j",
        )
        assert result["status"] == "created"

        reflections = category_manager.recall_reflections(domain="neo4j")
        assert any("__test_use ISO strings" in r.get("lesson", "") for r in reflections)

    def test_reinforcement_on_repeat(self, category_manager):
        # First occurrence
        r1 = category_manager.record_reflection(
            event="__test_repeated error",
            lesson="__test_always check types",
            severity="medium",
            domain="general",
        )
        # Second occurrence — should reinforce
        r2 = category_manager.record_reflection(
            event="__test_repeated error again",
            lesson="__test_always check types",
            severity="medium",
            domain="general",
        )
        assert r2["status"] == "reinforced"
        assert r2["occurrence_count"] >= 2


class TestConditionalE2E:

    def test_record_and_recall(self, category_manager):
        result = category_manager.record_conditional(
            condition={"python_version": "3.9"},
            then_action="__test_use typing.Optional",
            subcategory="version_specific",
        )
        assert result["status"] == "created"

        conditionals = category_manager.recall_conditionals(
            subcategory="version_specific"
        )
        assert any("__test_use typing.Optional" in c.get("then", "") for c in conditionals)

    def test_context_matching(self, category_manager):
        # Record a conditional
        category_manager.record_conditional(
            condition={"env": "production"},
            then_action="__test_enable caching",
            subcategory="env_specific",
        )

        # Match with correct context
        matched = category_manager.recall_conditionals(
            context={"env": "production"},
            subcategory="env_specific",
        )
        assert any("__test_enable caching" in c.get("then", "") for c in matched)

        # Non-matching context should filter out
        unmatched = category_manager.recall_conditionals(
            context={"env": "development"},
            subcategory="env_specific",
        )
        cache_rules = [c for c in unmatched if "__test_enable caching" in c.get("then", "")]
        assert len(cache_rules) == 0


class TestOrchestrationE2E:

    def test_task_handoff_lifecycle(self, category_manager):
        task_id = f"__test_task_{uuid.uuid4().hex[:8]}"

        # Create handoff
        result = category_manager.record_task_handoff(
            task_id=task_id,
            task_description="__test_implement feature X",
            from_agent="planner",
            to_agent="coder",
            context={"branch": "feature/x"},
        )
        assert result["status"] == "created"

        # Check active tasks
        active = category_manager.get_active_tasks(agent_id="coder")
        task_ids = [t["task_id"] for t in active]
        assert task_id in task_ids

        # Update to in_progress
        update = category_manager.update_task_status(task_id, "in_progress")
        assert update["new_status"] == "in_progress"

        # Complete
        update = category_manager.update_task_status(
            task_id, "completed", result_summary="Feature X done"
        )
        assert update["new_status"] == "completed"

        # Should no longer appear in active tasks
        active_after = category_manager.get_active_tasks(agent_id="coder")
        assert task_id not in [t["task_id"] for t in active_after]

    def test_failure_auto_reflects(self, category_manager):
        task_id = f"__test_fail_{uuid.uuid4().hex[:8]}"

        category_manager.record_task_handoff(
            task_id=task_id,
            task_description="__test_failing task",
            from_agent="planner",
            to_agent="coder",
        )

        # Fail the task — should auto-generate a reflection
        category_manager.update_task_status(
            task_id, "failed", result_summary="timeout on API call"
        )

        reflections = category_manager.recall_reflections(domain="orchestration", agent_id="all")
        assert any("Task failure" in r.get("lesson", "") for r in reflections)
