# Mories 핸드오버 — Part 2: 작업 현황 & 로드맵 (v2.0)
# 문서 경로: docs/handover/HANDOVER_v2.0_part2_status.md
# 버전: v2.0 | 갱신일: 2026-04-02

---

## 1. Phase 완료 현황

| Phase | 이름 | 상태 |
|-------|------|------|
| A | 아키텍처 정리 (싱글톤,레거시 제거) | ✅ 완료 |
| B | 시뮬레이션 기반 인지 기억 엔진 통합 | ✅ 완료 |
| C | Supermemory 선택적 가속/동기화 | ✅ 완료 |
| D | 에어갭 호환 + E2E 테스트 21건 | ✅ 완료 |
| E | 용어집(Terminology) 서비스 + UI | ✅ 완료 |
| F | Air-gap LLM/Embedding 전환 | ✅ 완료 |
| G-A | Tech Debt Sprint (6개 버그 수정) | ✅ 완료 |
| G-B | Harness Architecture | ✅ 완료 |
| G-C | Data Pipeline 경량화 | ✅ 완료 |
| **UI-1** | **사이드바 네비게이션 전환** | **✅ 완료** |
| **UI-2** | **다국어(i18n) 전체 적용 (ko/en)** | **✅ 완료** |
| **UI-3** | **사이드바 접기/펴기** | **✅ 완료** |
| UI-4 | 라이트/다크 테마 대비 정비 | 🟡 부분 (tokens.css 기본 구성) |

---

## 2. 미완료 P0 버그 (즉시 수정 필요)

### [BUG-1] `memory.py` current_app 미임포트
- **파일:** `src/app/api/memory.py`, `_get_audit()` 함수
- **오류:** `NameError: name 'current_app' is not defined`
- **수정:** 파일 상단에 `from flask import current_app` 추가
- **영향:** TestAuditAPI 2건 실패

### [BUG-2] reconciliation_service.py Neo4j datetime() 호환성
- **파일:** `src/app/storage/reconciliation_service.py`, Line 233, 356
- **오류:** Neo4j datetime() 파싱 실패 (Long 입력)
- **수정:** Cypher 쿼리에 정규식 검증 선행 추가
- **영향:** TestReconciliationAPI 3건 실패

---

## 3. 다음 세션 작업 우선순위

### P0 — 즉시 실행
```
1. [ ] 미커밋 변경사항 검토 & 커밋/Push
2. [ ] BUG-1, BUG-2 수정 후 테스트 재실행
3. [ ] git push origin main
```

### P1 — 단기 과제
| ID | 작업 | 예상 시간 | 상태 |
|----|------|-----------|------|
| TASK-3 | MCP 서버 패키징 고도화 | 2h | 대기 |
| TASK-4 | 멀티테넌트 지원 | 4h+ | 대기 |
| UI-4 | tokens.css 라이트모드 대비 정비 | 2h | 대기 |
| UI-5 | 인라인 CSS → CSS 변수 치환 | 3h | 대기 |

### P2 — 중기 로드맵
| Phase | 이름 | 설명 |
|-------|------|------|
| H | Multi-Agent 완성 | ADK/LangGraph 에이전트 + MCP 완전 연동 |
| I | Vector Search 고도화 | Neo4j Vector Index + HNSW |
| J | Federation | 다수 Mories 인스턴스 간 기억 연합 |

---

## 4. 테스트 현황 (2026-03-31 기준, BUG 수정 전)

- **전체:** 98 passed / 13 failed (111 total)
- **핵심 E2E:** 21/21 통과 ✅
- **실패 원인:** BUG-1(2건), BUG-2(4건), 기타 환경 의존(7건)

---

## 5. Docker 서비스 현황

| 컨테이너 | 이미지 | 포트 | 비고 |
|----------|--------|------|------|
| mirofish-dashboard | nginx:alpine | 8080→80 | 프론트엔드 |
| mirofish-api | 커스텀 빌드 | 5001→5000 | Flask API |
| mirofish-neo4j | neo4j:5.18-community | 7474, 7687 | 그래프 DB |
| mirofish-grafana | grafana/grafana:latest | 3000 | 모니터링 |
| mirofish-prometheus | prom/prometheus:latest | 9090 | 메트릭 |

> ⚠️ `mories_gitlab` (포트 8081) — 공용 서비스. 절대 변경/중지 금지.
> ⚠️ `presenton-production-1` (포트 5050) — 다른 프로젝트. 변경 금지.
