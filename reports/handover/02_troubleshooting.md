# Mories 트러블슈팅 가이드 (v1.1)

> 반복 이슈 방지를 위한 누적 트러블슈팅 기록
> 최종 업데이트: 2026-04-07

---

## TS-001: pytest가 행(hang)에 빠지는 문제
**증상**: `pytest tests/harness/ -v` 실행 시 출력 없이 무한 대기  
**해결**: 개별 파일 단위로 실행 (`.venv/bin/pytest tests/harness/test_executor_registry.py -v`)

---

## TS-002: `ast.Exec` AttributeError
**증상**: `AttributeError: module 'ast' has no attribute 'Exec'`  
**원인**: `ast.Exec`는 Python 2 전용 노드. Python 3에서 제거됨.
**해결**: `BLOCKED_NODES` 튜플에서 해당 속성 제거.

---

## TS-003: 시스템 python과 가상환경 python 혼동
**증상**: `zsh: no such file or directory: python3` 또는 패키지 찾을 수 없음  
**해결**: 항상 가상환경을 명시적으로 사용. `.venv/bin/python` 및 `.venv/bin/pytest`. bare `python` 절대 금지.

---

## TS-004: requests 패키지 ImportError (nomad_executor)
**해결**: `nomad_executor.py`에서 top-level import 대신 lazy-load(지연 로드) 패턴 적용.

---

## TS-005: CORS 와일드카드(`*`) 보안 위험
**해결**: 기본값을 `http://localhost:5173,http://localhost:3000`으로 좁히고 명시적인 엔드포인트만 화이트리스트에 추가.

---

## TS-006: SECRET_KEY 하드코딩
**해결**: 소스코드에 하드코딩된 키 제거, 프로덕션에선 반드시 환경변수 `.env` 사용.

---

## TS-007: 하드코딩된 내부 IP (192.168.35.x)
**해결**: 모든 환경 구성을 `os.environ.get()`과 `localhost`를 참조하도록 수정.

---

## TS-008: Prometheus 메트릭 중복 등록 에러
**증상**: pytest 수집 시 `ValueError: Duplicated timeseries`  
**해결**: `_get_or_create_metric()` 헬퍼를 통해 REGISTRY에서 기존 메트릭 재사용 처리.

---

## TS-009: CSS WebKit background-clip 경고
**증상**: `-webkit-background-clip: text`만 있으면 CSS Lint 경고 발생.
**해결**: 반드시 `background-clip: text;` 표준 속성도 함께 추가. (예: `-webkit-background-clip: text; background-clip: text;`)
