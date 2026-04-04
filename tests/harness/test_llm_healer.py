"""
test_llm_healer.py

LLM Healer 단위 테스트 + LLM 연동 검증.
- rule-based 폴백 로직은 항상 테스트
- 실제 LLM API는 Ollama 가용 시에만 테스트
"""
import pytest
import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from src.app.harness.orchestration.llm_healer import LLMHealerEngine


# Ollama 가용 여부 확인
_ollama_available = False
try:
    import requests
    r = requests.get("http://localhost:11434/v1/models", timeout=3)
    if r.ok:
        _ollama_available = True
except Exception:
    pass

skip_no_ollama = pytest.mark.skipif(
    not _ollama_available,
    reason="Ollama not available at localhost:11434",
)


class TestLLMHealerRuleBased:
    """Rule-Based Fallback 테스트 (LLM 불필요)."""

    def setup_method(self):
        # 존재하지 않는 API URL → 강제 rule-based fallback
        self.healer = LLMHealerEngine(
            api_base_url="http://127.0.0.1:1/v1",
            model="nonexistent",
            timeout=1,
        )

    def test_fix_nonexistent_action(self):
        """존재하지 않는 액션 → wait 스텝으로 교체."""
        wf = {
            "harness_id": "test",
            "steps": [
                {"id": "bad", "type": "code", "action": "nonexistent_func"},
                {"id": "done", "type": "end"},
            ],
        }
        fixed = self.healer.heal_workflow(
            wf, "name 'nonexistent_func' is not defined", "bad"
        )
        bad_step = [s for s in fixed["steps"] if s["id"] == "bad"][0]
        assert bad_step["type"] == "wait"
        assert "action" not in bad_step

    def test_fix_timeout_doubles(self):
        """타임아웃 에러 → 타임아웃 2배 증가."""
        wf = {
            "harness_id": "test",
            "steps": [
                {"id": "slow", "type": "api_call", "timeout_seconds": 10},
            ],
        }
        fixed = self.healer.heal_workflow(
            wf, "Timeout exceeded", "slow"
        )
        slow_step = [s for s in fixed["steps"] if s["id"] == "slow"][0]
        assert slow_step["timeout_seconds"] == 20

    def test_fix_connection_adds_retry(self):
        """연결 에러 → retry 설정 추가."""
        wf = {
            "harness_id": "test",
            "steps": [
                {"id": "api", "type": "api_call"},
            ],
        }
        fixed = self.healer.heal_workflow(
            wf, "Connection refused", "api"
        )
        api_step = [s for s in fixed["steps"] if s["id"] == "api"][0]
        assert "retry" in api_step
        assert api_step["retry"]["max_attempts"] == 3

    def test_fix_keyerror_adds_defaults(self):
        """KeyError → default_values 추가."""
        wf = {
            "harness_id": "test",
            "steps": [
                {"id": "data", "type": "transform"},
            ],
        }
        fixed = self.healer.heal_workflow(
            wf, "KeyError: 'missing_field'", "data"
        )
        data_step = [s for s in fixed["steps"] if s["id"] == "data"][0]
        assert "default_values" in data_step

    def test_original_preserved_on_unknown_error(self):
        """알 수 없는 에러 → 원본 반환."""
        wf = {
            "harness_id": "test",
            "steps": [
                {"id": "x", "type": "something"},
            ],
        }
        fixed = self.healer.heal_workflow(
            wf, "Some completely random error 123", "x"
        )
        # 구조 변경 없이 반환 (deep copy이므로 원본과 동일)
        assert fixed["steps"][0]["type"] == "something"


class TestLLMHealerJsonParsing:
    """JSON 파싱 견고성 테스트."""

    def setup_method(self):
        self.healer = LLMHealerEngine()

    def test_parse_clean_json(self):
        """깔끔한 JSON 파싱."""
        result = self.healer._parse_json_response('{"key": "value"}')
        assert result == {"key": "value"}

    def test_parse_json_in_codeblock(self):
        """마크다운 코드블록 내 JSON 파싱."""
        content = '일부 설명\n```json\n{"key": "value"}\n```\n추가 설명'
        result = self.healer._parse_json_response(content)
        assert result == {"key": "value"}

    def test_parse_json_with_prefix(self):
        """앞에 텍스트가 있는 JSON 파싱."""
        content = 'Here is the fixed workflow:\n{"key": "value"}'
        result = self.healer._parse_json_response(content)
        assert result == {"key": "value"}

    def test_parse_invalid_returns_none(self):
        """유효하지 않은 입력 → None."""
        result = self.healer._parse_json_response("just some text")
        assert result is None


@skip_no_ollama
class TestLLMHealerWithOllama:
    """실제 Ollama LLM 연동 테스트 (가용 시에만)."""

    def setup_method(self):
        self.healer = LLMHealerEngine(
            api_base_url="http://localhost:11434/v1",
            model="qwen3:8b",
            timeout=60,
        )

    def test_llm_actually_repairs_workflow(self):
        """LLM이 실제로 워크플로우를 수리한다."""
        wf = {
            "harness_id": "llm_test",
            "version": 3,
            "domain": "test",
            "steps": [
                {
                    "id": "broken",
                    "type": "code",
                    "action": "nonexistent_function_call_xyz"
                },
                {"id": "done", "type": "end"},
            ],
        }
        fixed = self.healer.heal_workflow(
            wf,
            "NameError: name 'nonexistent_function_call_xyz' is not defined",
            "broken",
        )
        # LLM이 수정했으므로 원본과 달라야 함
        broken_step = [s for s in fixed["steps"] if s["id"] == "broken"][0]
        # action이 제거되거나 type이 변경되었을 것
        assert (
            broken_step.get("action") != "nonexistent_function_call_xyz"
            or broken_step.get("type") != "code"
        )
