# Mories 트러블슈팅 가이드 (v1.0)

> 반복 이슈 방지를 위한 누적 트러블슈팅 기록
> 최종 업데이트: 2026-04-06

---

## TS-001: pytest가 행(hang)에 빠지는 문제

**증상**: `pytest tests/harness/ -v` 실행 시 출력 없이 무한 대기  
**원인**: Neo4j 연결 시도 또는 wasm 런타임 초기화에서 타임아웃 발생  
**해결**:
```bash
# ❌ 전체 디렉토리 실행 금지
.venv/bin/pytest tests/harness/ -v

# ✅ 개별 파일 단위로 실행
.venv/bin/pytest tests/harness/test_executor_registry.py tests/harness/test_ray_security.py tests/harness/test_dsl_schema.py -v
```
**예방**: 새 테스트 파일 작성 시 Neo4j fixture가 있으면 `@pytest.mark.integration` 마킹

---

## TS-002: `ast.Exec` AttributeError

**증상**: `AttributeError: module 'ast' has no attribute 'Exec'`  
**원인**: `ast.Exec`는 Python 2 전용 AST 노드. Python 3에서는 제거됨  
**해결**: `BLOCKED_NODES` 튜플에서 `ast.Exec` 제거. `exec`와 `eval`은 `BLOCKED_NAMES` 문자열 집합으로 차단  
**파일**: `src/app/harness/executors/ray_executor.py:17`

---

## TS-003: 시스템 python과 가상환경 python 혼동

**증상**: `zsh: no such file or directory: python3` 또는 잘못된 패키지 참조  
**원인**: macOS 시스템 python 심볼릭 링크가 깨져있음  
**해결**:
```bash
# 항상 가상환경의 python/pytest를 명시적으로 사용
.venv/bin/python -m pytest ...
.venv/bin/pytest ...

# 절대로 bare `python` 또는 `pytest` 사용 금지
```

---

## TS-004: requests 패키지 ImportError (nomad_executor)

**증상**: `ImportError: No module named 'requests'`  
**원인**: 최소 환경에서는 requests가 설치되지 않을 수 있음  
**해결**: `nomad_executor.py`에서 top-level import 대신 lazy-load 패턴 적용
```python
def _get_requests():
    try:
        import requests
        return requests
    except ImportError:
        raise RuntimeError("requests package not installed")
```

---

## TS-005: CORS 와일드카드(`*`) 보안 위험

**증상**: 외부 도메인에서 Mories API에 자유롭게 접근 가능  
**원인**: `config.py`의 기본값이 `CORS_ORIGINS = '*'`였음  
**해결**: 기본값을 `http://localhost:5173,http://localhost:3000`으로 변경  
**주의**: 플래닛 배포 시 `.env` 파일에 실제 도메인 추가 필요
```env
CORS_ORIGINS=http://mories.planet.internal,http://dashboard.planet.internal
```

---

## TS-006: SECRET_KEY 하드코딩

**증상**: Flask 세션 토큰이 예측 가능한 키로 서명됨  
**원인**: `SECRET_KEY = 'mirofish-secret-key'`가 소스코드에 하드코딩  
**해결**: 기본값 제거, 프로덕션(`DEBUG=False`)에서는 `.env`의 `SECRET_KEY` 필수  
```bash
# .env에 랜덤 키 생성해서 넣기
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## TS-007: 하드코딩된 내부 IP (192.168.35.x)

**증상**: 개발 환경 변경 시 API 연결 실패  
**원인**: MCP 서버 설정에 `192.168.35.86`, `192.168.35.101` 하드코딩  
**해결**: 모두 `os.environ.get(...)` + `localhost` 기본값으로 전환 완료  
**영향 파일**:
- `mcp_server/config.py` (LLM_BASE_URL, EMBEDDING_BASE_URL)
- `mcp_server/mories_mcp.py` (MORIES_URL)
- `mcp_server/mcp_config.json` (MORIES_URL)
- `src/app/harness/executors/nomad_executor.py` (NOMAD_ADDR)

---

## TS-008: Prometheus 메트릭 중복 등록 에러

**증상**: pytest 수집 시 `ValueError: Duplicated timeseries`  
**원인**: Flask app factory가 여러 번 호출될 때 Prometheus 메트릭 재등록  
**해결**: `_get_or_create_metric()` 헬퍼로 REGISTRY에서 기존 메트릭 재사용  
**파일**: `src/app/__init__.py:25-30`
