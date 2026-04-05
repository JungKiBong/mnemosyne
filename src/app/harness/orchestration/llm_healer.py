"""
llm_healer.py — LLM 기반 워크플로우 자동 복구 엔진

실패한 하네스 워크플로우의 에러 로그를 LLM에 전달하여,
DSL 스텝을 동적으로 패치(수정)하는 범용 자기수복 모듈.

지원 백엔드:
  1. OpenAI-compatible API (Ollama, vLLM, Dify 등)
  2. Mock (테스트)

작성: 2026-04-04
"""
import json
import logging
import copy
from typing import Dict, Any, Optional, List

logger = logging.getLogger("harness.llm_healer")

# ─────────────────────────────────────────────
# System Prompt — 워크플로우 수리 전문가
# ─────────────────────────────────────────────

HEALER_SYSTEM_PROMPT = """You are a Workflow Auto-Repair Agent.
Given a failed workflow (JSON DSL) and an error message, your job is to:

1. Analyze the error root cause
2. Identify which step failed and why
3. Generate a MINIMAL patch to fix the workflow

Rules:
- Output ONLY valid JSON — the patched workflow
- Change as few fields as possible
- Preserve all step IDs and structure
- If a step's 'action' or 'type' is invalid, replace with a safe default
- Never add new steps; only modify existing ones
- If you cannot fix the error, return the original workflow unchanged

IMPORTANT: Your response must be ONLY the JSON workflow object. No markdown, no explanation."""


class LLMHealerEngine:
    """
    OpenAI-compatible API를 사용하는 범용 LLM 워크플로우 힐러.

    Ollama, vLLM, Dify, OpenAI — 모든 OpenAI API 호환 서버에서 작동.
    """

    def __init__(
        self,
        api_base_url: str = "http://localhost:11434/v1",
        model: str = "qwen3:8b",
        api_key: str = "ollama",
        timeout: int = 30,
        memory_backend: Optional[Any] = None,
    ):
        self.api_base_url = api_base_url
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.memory_backend = memory_backend

    def heal_workflow(
        self,
        workflow: dict,
        error_msg: str,
        failed_step_id: str,
    ) -> dict:
        """
        워크플로우의 실패한 스텝을 LLM 분석을 통해 수정한다.

        Returns:
            수정된 워크플로우 dict (수정 불가 시 원본 반환)
        """
        memory_context = ""
        if self.memory_backend:
            try:
                # 최근 동일 도메인의 Reflection 및 Instruction 조회
                domain = workflow.get("domain")
                reflections = []
                if hasattr(self.memory_backend, "find_reflections"):
                    reflections = self.memory_backend.find_reflections(domain=domain, limit=3)
                
                # Instruction 조회 (human_feedback 위주)
                instructions = []
                if hasattr(self.memory_backend, "find_instructions"):
                    instructions = self.memory_backend.find_instructions(category="human_feedback", limit=3)

                ctx_lines = []
                if reflections:
                    ctx_lines.append("Previous Reflections:")
                    for r in reflections:
                        ctx_lines.append(f"- Event: {r.get('event')}, Lesson: {r.get('lesson')}")
                if instructions:
                    ctx_lines.append("Human Feedback Rules:")
                    for idx, inst in enumerate(instructions):
                        # dict or node object
                        rule = inst.get("rule") if isinstance(inst, dict) else getattr(inst, "rule", "")
                        ctx_lines.append(f"- Rule {idx+1}: {rule}")
                
                if ctx_lines:
                    memory_context = "\n".join(ctx_lines)
            except Exception as e:
                logger.warning(f"Failed to fetch memory context for healer: {e}")

        user_prompt = self._build_prompt(workflow, error_msg, failed_step_id, memory_context)

        try:
            import requests

            resp = requests.post(
                f"{self.api_base_url}/chat/completions",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": HEALER_SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 4096,
                },
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )

            if not resp.ok:
                logger.error(f"LLM API error: {resp.status_code} {resp.text[:200]}")
                return self._apply_rule_based_fix(workflow, error_msg, failed_step_id)

            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            patched = self._parse_json_response(content)

            if patched:
                logger.info(f"LLM healed workflow for step '{failed_step_id}'")
                return patched
            else:
                logger.warning("LLM response was not valid JSON, falling back to rule-based fix")
                return self._apply_rule_based_fix(workflow, error_msg, failed_step_id)

        except Exception as e:
            logger.warning(f"LLM healer failed: {e}, using rule-based fallback")
            return self._apply_rule_based_fix(workflow, error_msg, failed_step_id)

    def _build_prompt(
        self, workflow: dict, error_msg: str, failed_step_id: str, memory_context: str = ""
    ) -> str:
        """LLM에 보낼 수리 요청 프롬프트 생성."""
        # 워크플로우를 간략화 (토큰 절약)
        slim_wf = copy.deepcopy(workflow)
        # state_storage path 등 불필요한 정보 제거
        slim_wf.pop("state_storage", None)

        prompt = f"""## Failed Workflow

```json
{json.dumps(slim_wf, indent=2, ensure_ascii=False)}
```

## Error Information
- **Failed Step ID**: `{failed_step_id}`
- **Error Message**: `{error_msg}`
"""
        if memory_context:
            prompt += f"\n## Cross-Domain Memory Context\n{memory_context}\n"

        prompt += """
## Task
Analyze the error and return a patched version of the workflow JSON that fixes the issue.
Remember: output ONLY the valid JSON object."""
        return prompt

    def _parse_json_response(self, content: str) -> Optional[dict]:
        """LLM 응답에서 JSON을 추출한다."""
        # 직접 JSON 파싱 시도
        content = content.strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # 코드블록 내 JSON 추출
        import re
        json_match = re.search(r'```(?:json)?\s*\n(.*?)\n```', content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # 마지막 시도: { 로 시작하는 부분 찾기
        brace_start = content.find('{')
        if brace_start >= 0:
            # 가장 바깥 괄호 매칭
            depth = 0
            for i in range(brace_start, len(content)):
                if content[i] == '{':
                    depth += 1
                elif content[i] == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(content[brace_start:i + 1])
                        except json.JSONDecodeError:
                            break

        return None

    def _apply_rule_based_fix(
        self, workflow: dict, error_msg: str, failed_step_id: str
    ) -> dict:
        """
        LLM 불가 시 규칙 기반 자동 수리.
        에러 패턴별 휴리스틱 적용.
        """
        fixed = copy.deepcopy(workflow)
        error_lower = error_msg.lower()

        for step in fixed.get("steps", []):
            if step.get("id") != failed_step_id:
                continue

            # Rule 1: 존재하지 않는 함수/액션
            if "nonexistent" in error_lower or "not defined" in error_lower:
                step["type"] = "wait"
                step["timeout_seconds"] = 0
                step.pop("action", None)
                logger.info(f"Rule-based fix: {failed_step_id} → wait (invalid action)")

            # Rule 2: 타임아웃
            elif "timeout" in error_lower:
                current_timeout = step.get("timeout_seconds", 30)
                step["timeout_seconds"] = current_timeout * 2
                logger.info(f"Rule-based fix: {failed_step_id} → doubled timeout")

            # Rule 3: 키 에러
            elif "keyerror" in error_lower or "key error" in error_lower:
                step.setdefault("default_values", {})
                logger.info(f"Rule-based fix: {failed_step_id} → added default_values")

            # Rule 4: 타입 에러
            elif "typeerror" in error_lower:
                step["type"] = "wait"
                step["timeout_seconds"] = 0
                step.pop("action", None)
                logger.info(f"Rule-based fix: {failed_step_id} → wait (type error)")

            # Rule 5: 연결 에러
            elif "connection" in error_lower or "refused" in error_lower:
                step.setdefault("retry", {"max_attempts": 3, "delay_seconds": 5})
                logger.info(f"Rule-based fix: {failed_step_id} → added retry config")

            else:
                logger.warning(
                    f"No rule-based fix for error: {error_msg[:100]}"
                )

            break

        return fixed
