# Step 1.3 실행 가이드: OASIS 코드 분리 (v1.0)

> Step 1.3의 목표, 범위, 위험 요소, 실행 순서를 정리한 문서
> 최종 업데이트: 2026-04-06

---

## 1. 목표

Mories의 핵심 인지 엔진(메모리, 하네스, 검색)과 무관한 **OASIS 소셜 시뮬레이션 코드**를
`src/app/plugins/` 디렉토리로 이동하여, 코어 엔진의 무게를 줄이고 의존성을 분리한다.

---

## 2. 분리 대상 파일 식별 방법

```bash
# OASIS 관련 파일 찾기
.venv/bin/python -c "
import os
for root, dirs, files in os.walk('src/app'):
    for f in files:
        if 'oasis' in f.lower() or 'simulation' in f.lower() or 'twitter' in f.lower() or 'reddit' in f.lower():
            print(os.path.join(root, f))
"
```

config.py의 OASIS 관련 설정도 확인:
- `OASIS_DEFAULT_MAX_ROUNDS`
- `OASIS_SIMULATION_DATA_DIR`
- `OASIS_TWITTER_ACTIONS`
- `OASIS_REDDIT_ACTIONS`

---

## 3. 실행 순서 (핵심 기능 보호 우선)

### Phase A: 기준선 테스트 확보
```bash
# 이동 전에 반드시 핵심 테스트 통과 확인
.venv/bin/pytest tests/harness/test_executor_registry.py tests/harness/test_ray_security.py tests/harness/test_dsl_schema.py -v
```

### Phase B: 디렉토리 구조 생성
```bash
mkdir -p src/app/plugins/oasis
touch src/app/plugins/__init__.py
touch src/app/plugins/oasis/__init__.py
```

### Phase C: 파일 이동 (git mv 사용)
```bash
# git mv로 이동해야 히스토리 추적 가능
git mv src/app/api/oasis_*.py src/app/plugins/oasis/
git mv src/app/models/simulation*.py src/app/plugins/oasis/
```

### Phase D: import 경로 수정
- `__init__.py`(Flask app factory)에서 OASIS 블루프린트 등록을 조건부로 변경
- `try/except ImportError`로 감싸서 플러그인 미설치 시에도 핵심 앱 정상 기동

### Phase E: 기준선 테스트 재확인
```bash
# 이동 후에도 핵심 테스트가 여전히 통과하는지 확인
.venv/bin/pytest tests/harness/test_executor_registry.py tests/harness/test_ray_security.py tests/harness/test_dsl_schema.py -v
```

---

## 4. 위험 요소 & 주의사항

| 위험 | 대응 |
|------|------|
| `__init__.py`에서 OASIS 블루프린트를 import하는 코드가 있을 수 있음 | `try/except`로 감싸서 graceful 처리 |
| config.py의 OASIS 설정이 다른 곳에서 참조될 수 있음 | grep으로 사전 검색 후 이동 |
| Flask app이 부팅 실패할 수 있음 | 이동 후 `.venv/bin/python -c "from src.app import create_app; create_app()"` 로 즉시 확인 |

---

## 5. 완료 기준

- [ ] 핵심 테스트 24개 전부 통과 (test_executor_registry + test_ray_security + test_dsl_schema)
- [ ] Flask 앱 정상 기동 확인
- [ ] OASIS 관련 파일이 `src/app/plugins/oasis/`로 이동됨
- [ ] `__init__.py`에서 OASIS 블루프린트가 조건부 로딩으로 변경됨
