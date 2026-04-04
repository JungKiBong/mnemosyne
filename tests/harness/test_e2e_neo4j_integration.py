"""
test_e2e_neo4j_integration.py

전체 파이프라인 E2E 통합 테스트:
  HarnessOrchestrator → MemoryBridge → Neo4jMemoryBackend → 실제 Neo4j

Neo4j 실제 연결이 필요하므로, 연결 불가 시 skip 처리.
테스트 데이터는 독립 네임스페이스(test_e2e_*)를 사용하여 기존 데이터에 영향 없음.
"""
import pytest
import os
import sys
import uuid
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

# Neo4j 연결 가능 여부 확인
_neo4j_available = False
_driver = None
try:
    from neo4j import GraphDatabase
    _driver = GraphDatabase.driver(
        "bolt://localhost:7687", auth=("neo4j", "mirofish")
    )
    with _driver.session() as s:
        s.run("RETURN 1").single()
    _neo4j_available = True
except Exception:
    pass

skip_no_neo4j = pytest.mark.skipif(
    not _neo4j_available,
    reason="Neo4j not available at bolt://localhost:7687",
)


@skip_no_neo4j
class TestE2ENeo4jIntegration:
    """E2E: 전체 Harness → Mories Knowledge Graph 파이프라인 검증."""

    TEST_DOMAIN = f"test_e2e_{uuid.uuid4().hex[:8]}"

    @classmethod
    def setup_class(cls):
        from src.app.harness.orchestration.neo4j_memory_backend import (
            Neo4jMemoryBackend,
        )
        cls.backend = Neo4jMemoryBackend(driver=_driver)

    @classmethod
    def teardown_class(cls):
        """테스트 네임스페이스 데이터 정리."""
        if _driver:
            with _driver.session() as s:
                s.run(
                    "MATCH (n) WHERE n.domain = $domain DETACH DELETE n",
                    domain=cls.TEST_DOMAIN,
                )
                s.run(
                    "MATCH (d:Domain {name: $domain}) DETACH DELETE d",
                    domain=cls.TEST_DOMAIN,
                )

    def test_01_ingest_experience_to_neo4j(self):
        """경험 데이터가 Neo4j에 HarnessExperience 노드로 실제 저장된다."""
        result = self.backend.ingest(
            content="E2E 테스트 성공 경험 기록",
            salience=0.8,
            scope="personal",
            source="harness:e2e_test",
            metadata={
                "harness_id": "e2e_pipeline",
                "domain": self.TEST_DOMAIN,
                "run_id": "e2e_run_001",
                "experience_type": "SUCCESS",
                "tool_chain": ["step_a", "step_b", "step_c"],
                "elapsed_ms": 150,
            },
        )
        assert result["status"] == "ingested"
        assert result["id"]  # UUID 반환

        # Neo4j에서 직접 확인
        with _driver.session() as s:
            record = s.run(
                "MATCH (h:HarnessExperience {uuid: $uuid}) RETURN h",
                uuid=result["id"],
            ).single()
            assert record is not None
            node = record["h"]
            assert node["salience"] == 0.8
            assert node["domain"] == self.TEST_DOMAIN

    def test_02_record_pattern_to_neo4j(self):
        """성공 패턴이 HarnessPattern 노드로 등록된다."""
        result = self.backend.record_pattern(
            domain=self.TEST_DOMAIN,
            tool_chain=["collect", "analyze", "report"],
            trigger="Captured from e2e test",
            metadata={"tags": [self.TEST_DOMAIN, "e2e"]},
        )
        assert result["status"] == "recorded"

        # 패턴 검색 API로 검증
        patterns = self.backend.find_patterns(domain=self.TEST_DOMAIN)
        assert len(patterns) >= 1
        assert patterns[0]["tool_chain"] == ["collect", "analyze", "report"]

    def test_03_record_reflection_to_neo4j(self):
        """실패 교훈이 Reflection 노드로 기록된다."""
        result = self.backend.record_reflection(
            event="E2E test simulated failure: timeout in step_x",
            lesson="step_x에서 timeout 발생 시, retry 로직 추가 필요",
            domain=self.TEST_DOMAIN,
            severity="medium",
        )
        assert result["status"] == "recorded"

        # 교훈 검색 API로 검증
        reflections = self.backend.find_reflections(
            domain=self.TEST_DOMAIN
        )
        assert len(reflections) >= 1
        assert "timeout" in reflections[0]["event"]

    def test_04_duplicate_pattern_increments_counter(self):
        """동일 tool_chain 패턴 재등록 시 실행 카운터만 증가한다."""
        # 같은 패턴 2회 추가
        for _ in range(2):
            self.backend.record_pattern(
                domain=self.TEST_DOMAIN,
                tool_chain=["collect", "analyze", "report"],
                trigger="Re-captured",
                metadata={},
            )

        patterns = self.backend.find_patterns(domain=self.TEST_DOMAIN)
        # MERGE 기반이므로 패턴은 1개, 카운터는 증가
        matching = [
            p for p in patterns
            if p.get("tool_chain") == ["collect", "analyze", "report"]
        ]
        assert len(matching) == 1
        assert matching[0]["execution_count"] >= 3  # 원래 1 + 추가 2

    def test_05_domain_stats(self):
        """도메인별 실행 통계가 정확히 집계된다."""
        stats = self.backend.get_domain_stats()
        my_domain = [
            s for s in stats if s["domain"] == self.TEST_DOMAIN
        ]
        assert len(my_domain) >= 1
        assert my_domain[0]["total_runs"] >= 1

    def test_06_full_orchestrator_pipeline(self):
        """Orchestrator → MemoryBridge → Neo4j 전체 파이프라인 E2E."""
        from src.app.harness.orchestration.memory_bridge import MemoryBridge
        from src.app.harness.orchestration.harness_orchestrator import (
            HarnessOrchestrator,
        )

        bridge = MemoryBridge(memory_backend=self.backend)

        workflow = {
            "harness_id": f"e2e_full_{uuid.uuid4().hex[:6]}",
            "version": 3,
            "domain": self.TEST_DOMAIN,
            "steps": [
                {"id": "s1", "type": "wait", "timeout_seconds": 0},
                {"id": "done", "type": "end"},
            ],
            "state_storage": {
                "type": "json_file",
                "path": tempfile.mkdtemp(),
            },
            "evolution": {"capture_new_patterns": True},
        }

        orchestrator = HarnessOrchestrator(
            initial_workflow=workflow,
            memory_bridge=bridge,
        )

        result = orchestrator.run_with_auto_heal()
        assert result["success"] is True
        assert result["metadata"]["experience_type"] == "CAPTURED"

        # Neo4j에 경험이 실제로 기록되었는지 확인
        with _driver.session() as s:
            count = s.run(
                """
                MATCH (h:HarnessExperience)
                WHERE h.domain = $domain
                  AND h.harness_id = $hid
                RETURN count(h) AS cnt
                """,
                domain=self.TEST_DOMAIN,
                hid=workflow["harness_id"],
            ).single()["cnt"]
            assert count >= 1
