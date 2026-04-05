"""
test_llm_healer_memory.py

LLM Healer 엔진이 메모리(MemoryBackend) 컨텍스트를 주입받아
교훈(Reflection)이나 지침(Instruction)을 잘 활용하는지 검증합니다.
"""

import pytest
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from src.app.harness.orchestration.llm_healer import LLMHealerEngine


class MockMemoryBackend:
    """LLMHealerEngine의 메모리 조회를 흉내내기 위한 Mock 객체"""
    
    def __init__(self, reflections, instructions):
        self._reflections = reflections
        self._instructions = instructions
        
    def find_reflections(self, domain=None, limit=10):
        return [r for r in self._reflections if not domain or r.get("domain") == domain]
        
    def find_instructions(self, category=None, limit=10):
        return [i for i in self._instructions if not category or i.get("category") == category]


def test_healer_build_prompt_with_memory_context():
    """메모리 백엔드가 설정되어 있을 때 프롬프트에 메모리 컨텍스트가 포함되는지 확인한다."""
    reflections = [
        {"domain": "test_domain", "event": "Timeout in API", "lesson": "Always double the timeout for this specific API"}
    ]
    instructions = [
        {"category": "human_feedback", "rule": "Never use the nonexistent_func action"}
    ]
    
    backend = MockMemoryBackend(reflections, instructions)
    
    # Healer 초기화 
    healer = LLMHealerEngine(memory_backend=backend)
    
    wf = {
        "harness_id": "test_wf",
        "domain": "test_domain",
        "steps": [
            {"id": "s1", "type": "code", "action": "nonexistent_func"}
        ]
    }
    
    prompt = healer._build_prompt(wf, "NameError", "s1")
    # memory_context가 비어 있어야 함 (직접 주입하지 않으면 _build_prompt 인자로 들어가지 않기 때문)
    assert "Cross-Domain Memory Context" not in prompt

    # heal_workflow 내부에서 메모리를 조회하고 prompt를 만들때 어떻게 동작하는지
    # LLM API 호출을 막을 수 없으므로, _build_prompt를 통해 memory_context를 명시적으로 주입하는 단위테스트 수행
    memory_context = "Previous Reflections:\n- Event: Timeout in API, Lesson: Always double the timeout for this specific API\nHuman Feedback Rules:\n- Rule 1: Never use the nonexistent_func action"
    
    prompt_with_ctx = healer._build_prompt(wf, "NameError", "s1", memory_context)
    
    assert "Cross-Domain Memory Context" in prompt_with_ctx
    assert "Timeout in API" in prompt_with_ctx
    assert "Never use the nonexistent_func action" in prompt_with_ctx

def test_heal_workflow_fetches_memory(monkeypatch):
    """heal_workflow가 내부적으로 메모리 조회 및 _build_prompt를 정상 수행하는지 확인."""
    reflections = [{"domain": "test_domain", "event": "Slow DB", "lesson": "Add retry"}]
    instructions = [{"category": "human_feedback", "rule": "Use default values"}]
    
    backend = MockMemoryBackend(reflections, instructions)
    healer = LLMHealerEngine(memory_backend=backend)
    
    # _build_prompt를 가로채서 memory_context가 어떻게 들어오는지 확인
    captured_memory_context = None
    
    original_build_prompt = healer._build_prompt
    
    def mock_build_prompt(workflow, error_msg, failed_step_id, memory_context=""):
        nonlocal captured_memory_context
        captured_memory_context = memory_context
        return original_build_prompt(workflow, error_msg, failed_step_id, memory_context)
        
    monkeypatch.setattr(healer, "_build_prompt", mock_build_prompt)
    
    # LLM 요청 방지: requests.post mock
    class MockResponse:
        ok = False
        status_code = 500
        text = "Mock LLM Error"
    
    import requests
    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: MockResponse())
    
    wf = {"harness_id": "test_wf", "domain": "test_domain", "steps": [{"id": "s1", "type": "api"}]}
    
    # heal_workflow 실행 (LLM 에러로 rule-based fallback됨)
    healer.heal_workflow(wf, "Connection refused", "s1")
    
    # memory_context가 잘 수집되었는지 확인
    assert captured_memory_context is not None
    assert "Previous Reflections:" in captured_memory_context
    assert "Slow DB" in captured_memory_context
    assert "Human Feedback Rules:" in captured_memory_context
    assert "Use default values" in captured_memory_context
