# 다중 에이전트 자율 협업 시나리오: 오토노모스 연구소 (Autonomous Laboratory)

## 1. 개요
본 시나리오는 Mories 4D Cognitive Engine을 활용하여 물리적 AI(Physical AI) 및 엣지 디바이스 AI(Edge Device AI)가 
소프트웨어 기반의 분석/지휘 에이전트와 어떻게 자율적으로 협업하고 지식을 진화시키는지 실증(Validation)하기 위한 아키텍처 및 워크플로우 명세서입니다.

## 2. 참여 에이전트 정의 (Agent Roles)

### 2.1. 엣지 센싱 에이전트 (Edge Device AI / Physical AI)
* **역할:** 연구소의 물리적 환경(온도, 습도, 장비 상태, 로봇 암의 물리적 피드백 등)을 실시간 모니터링 및 센싱.
* **Mories 시스템 활용:** 
  * 센서 데이터 기반의 1차적 판단 및 이상 징후를 **단기 기억(STM)**에 기록 (`mories_stm_add`).
  * 통신 대역폭이 제한된 엣지 환경을 가정하여 중요 이벤트만 Synaptic Bridge를 통해 전파 (`mories_synaptic_share`).

### 2.2. 중앙 분석 에이전트 (Central Analysis Agent)
* **역할:** 엣지에서 올라온 STM 데이터들을 모니터링하고 패턴을 분석하여 유의미한 연구 기록으로 변환.
* **Mories 시스템 활용:**
  * 엣지의 STM 중 장기 보존이 필요한 데이터를 **장기 기억(LTM)으로 승격** (`mories_stm_promote`).
  * 여러 개별 데이터 포인트를 연결하여 새로운 팩트 노드로 저장.

### 2.3. 연구 디렉터 에이전트 (Research Director Agent)
* **역할:** 실험의 거시적 방향성 결정, 과거 실패/파라미터 리뷰 및 새로운 실험 조건 하달.
* **Mories 시스템 활용:**
  * 과거 실험 데이터 및 LTM 그래프를 질의하여 통찰 도출 (`mories_graph_query`, `Time-Travel Chat`).
  * `Hindsight Synthesis`를 호출하여 과거 데이터 집합으로부터 새로운 가설(Synthesis Node) 생성.

## 3. 시나리오 워크플로우 (Scenario Workflow)

1. **[Edge] 물리 환경 모니터링 및 로깅:**
   * 엣지 시스템이 임계치가 넘는 온도 변화 이벤트를 감지.
   * `mories_stm_add`: "Reaction chamber A temperature spiked by 15% at T+200s."
2. **[Edge -> Analysis] 지식 공유:**
   * 엣지 에이전트가 다른 분석 기기들에게 조기 경보 발송.
   * `mories_synaptic_share`: 엣지 에이전트 -> 중앙 분석 에이전트로 해당 메모리 UUID 전송.
3. **[Analysis] 이상 징후 분석 및 승격:**
   * 중앙 분석 에이전트가 해당 타임라인의 로그를 종합 분석 결과, 이는 단순 노이즈가 아닌 유의미한 촉매 반응임을 인지.
   * `mories_stm_promote`: 해당 STM을 LTM으로 승격 및 지식 그래프에 영구 기록.
4. **[Director] 사후 분석 및 가설 도출:**
   * 연구 디렉터 에이전트가 최근 1주간의 LTM 데이터를 그래프 쿼리로 검색.
   * `Hindsight Synthesis` API 호출을 통해 촉매 반응과 온도 스파이크의 상관관계 통찰(Insight) 노드 생성 및 다음 실험(실행 명령) 파라미터 업데이트 설정.

## 4. 구현 및 검증 목표
본 시나리오를 통해 다음 Mories 핵심 인프라를 외부 에이전트가 완벽하게 다룰 수 있음을 검증합니다.
* **분리된 기억 계층 관리:** 외부 API를 통한 STM 생성 및 LTM 승격 권한 통제.
* **에이전트 간 P2P 메모리 전송:** Synaptic Bridge를 통한 UUID 기반의 맥락(Context) 공유 속도 및 안정성.
* **Cognitive Evolution:** 파편화된 머신 데이터가 지휘 에이전트의 Hindsight Synthesis를 거쳐 개념적 지식(Ontology)으로 융합되는 과정.

---
**문서 업데이트 내역**
* 버전: 1.0 (2026-04-04)
* 작성: Mories 자율 오케스트레이션 설계 모듈
