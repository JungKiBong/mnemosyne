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
- **상태:** **✅ 코드 수정 완료** (`from flask import current_app` 반영 확인)
- **추가조치:** `pytest` 환경에서 application context fixture 연결 확인 필요

### [BUG-2] reconciliation_service.py Neo4j datetime() 호환성
- **상태:** **✅ 코드 수정 완료** (`toString(n.last_accessed) =~ '\\d{4}-\\d{2}-\\d{2}.*'` 반영 확인)
- **추가조치:** `tests/integration/test_reconciliation.py` 파일 내 Pytest fixture(`recon_service`, `test_entity`) 바인딩 오류 수정 필요

---

## 3. 다음 세션 작업 우선순위

### P0 — 즉시 실행
```
1. [ ] 미커밋 변경사항(Phase 16 Cognitive Memory + MCP 포함) 검토 및 커밋/Push
2. [ ] BUG-2 테스트코드 픽스처(Pytest class scope) 바인딩 오류 수정 및 테스트 100% 통과 확보
3. [ ] git push origin main
```

### P1 — 단기 과제
| ID | 작업 | 예상 시간 | 상태 |
|----|------|-----------|------|
| TASK-3 | MCP 서버 패키징 고도화 | 2h | 대기 |
| TASK-4 | 멀티테넌트 지원 | 4h+ | 대기 |
| UI-4 | tokens.css 라이트모드 대비 정비 | 2h | 대기 |
| UI-5 | 인라인 CSS → CSS 변수 치환 | 3h | 대기 |
| **UI-6** | **Harness 오케스트레이션 및 인지 기억 지식(조건부 등) 시각화 UI** | **3h** | **최우선 대기(추천)** |

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
