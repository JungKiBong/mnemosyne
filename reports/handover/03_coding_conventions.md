# Mories 코딩 컨벤션 & 안전 규칙 (v1.0)

> 모든 세션의 코드 작성 시 반드시 준수할 규칙
> 최종 업데이트: 2026-04-06

---

## 1. 절대 건드리면 안 되는 것들

| 항목 | 경로/설명 |
|------|-----------|
| `.env` 파일 | 절대 내용을 출력하거나 커밋하지 말 것 (키/비밀번호 포함) |
| `src/.env` 파일 | 위와 동일 |
| `docker-compose.yml` | 다른 프로젝트(Keycloak, n8n 등)의 공용 자원. 수정 전 반드시 확인 |
| Neo4j 데이터 삭제 | `MATCH (n) DETACH DELETE n` 같은 전체 삭제 쿼리 금지 |
| 시스템 패키지 설치 | `brew install`, `pip install` (글로벌) 금지. `.venv` 안에서만 |

---

## 2. 파이썬 실행 환경

```bash
# ✅ 올바른 사용법
.venv/bin/python script.py
.venv/bin/pytest tests/harness/test_xxx.py -v

# ❌ 절대 금지
python script.py        # 시스템 python이 깨져있음
pytest tests/ -v        # 가상환경 바깥의 pytest
```

---

## 3. 테스트 파일 관리

- 테스트 파일은 `tests/harness/` 디렉토리에 집중 배치
- 파일명 규칙: `test_{기능명}.py`
- 나중에 한번에 지울 수 있도록 `tests/tmp/` 디렉토리를 임시 테스트용으로 사용
- Neo4j 연결이 필요한 테스트는 `@pytest.mark.integration` 데코레이터 필수

---

## 4. 예외 처리 & 로깅

```python
import logging

logger = logging.getLogger(__name__)

def some_function():
    try:
        # 핵심 로직
        result = do_work()
        logger.info(f"작업 완료: {result}")
        return result
    except SpecificError as e:
        # 구체적 예외를 먼저 잡고, 복구 가능한 경우 처리
        logger.warning(f"복구 가능한 오류 발생: {e}")
        return fallback_value
    except Exception as e:
        # 예상치 못한 오류는 반드시 로깅 후 재발생
        logger.error(f"예상치 못한 오류: {e}", exc_info=True)
        raise
    finally:
        # 자원 반환 (DB 커넥션, 파일 핸들 등)
        cleanup_resources()
```

---

## 5. 자원 관리 (누수 방지)

```python
# ✅ context manager 사용
with open("file.txt") as f:
    data = f.read()

# ✅ DB 드라이버 세션
with driver.session() as session:
    session.run("MATCH (n) RETURN n LIMIT 10")

# ❌ 금지: 열고 닫지 않는 패턴
f = open("file.txt")  # finally에서 close 안 하면 누수
session = driver.session()  # close 안 하면 커넥션 풀 고갈
```

---

## 6. 주석 작성 규칙

- **언어**: 한글로 최대한 쉽고 상세하게
- **함수/클래스**: docstring 필수, 매개변수와 반환값 설명
- **복잡한 로직**: 설명 문서가 필요하면 `docs/` 폴더에 별도 작성하고 주석에 경로 기입

```python
def validate_script(code: str) -> None:
    """
    사용자 스크립트의 보안 검증을 수행합니다.
    
    AST(추상 구문 트리)를 파싱하여 위험한 구문(import, exec 등)을
    사전에 차단합니다.
    
    Args:
        code: 검증할 파이썬 코드 문자열
        
    Raises:
        SecurityError: 차단된 구문이 발견된 경우
        
    참고 문서: docs/security_policy.md (v1.0)
    """
```

---

## 7. 파일 길이 제한

- 단일 파일 **300줄 이하** 유지 목표
- 300줄 초과 시 모듈 분리 검토
- 핸드오버/보고서 문서도 **150줄 이하**로 분리
