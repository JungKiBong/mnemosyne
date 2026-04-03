/**
 * Mories — Global i18n Translation Module
 *
 * Usage:
 *   1. Include this script BEFORE page-specific scripts: <script src="/i18n.js"></script>
 *   2. Add data-i18n="key" to any translatable HTML element
 *   3. Add data-i18n-placeholder="key" for input placeholders
 *   4. Add data-i18n-title="key" for title/tooltip attributes
 *   5. Call window.t('key') in JS code for dynamic translations
 *   6. Call window.applyI18n() after dynamically adding elements
 *
 * Language is stored in localStorage('moriesLang'), default 'ko'.
 * Listens for 'moriesLangChanged' event to re-apply.
 */
(function () {
  'use strict';

  // ═══════════════════════════════════════════════════════
  //  DICTIONARY — ko / en
  // ═══════════════════════════════════════════════════════
  const DICT = {

    // ─── Common / Shared ───
    'refresh':              { ko: '새로고침',            en: 'Refresh' },
    'loading':              { ko: '로딩 중...',          en: 'Loading...' },
    'close':                { ko: '닫기',                en: 'Close' },
    'cancel':               { ko: '취소',                en: 'Cancel' },
    'save':                 { ko: '저장',                en: 'Save' },
    'delete':               { ko: '삭제',                en: 'Delete' },
    'copy':                 { ko: '복사',                en: 'Copy' },
    'download':             { ko: '다운로드',            en: 'Download' },
    'view':                 { ko: '보기',                en: 'View' },
    'copied':               { ko: '복사됨!',             en: 'Copied!' },
    'change':               { ko: '변경',                en: 'Change' },
    'all':                  { ko: '전체',                en: 'All' },
    'error':                { ko: '오류',                en: 'Error' },
    'success':              { ko: '성공',                en: 'Success' },
    'prev':                 { ko: '이전',                en: 'Previous' },
    'next':                 { ko: '다음',                en: 'Next' },
    'search':               { ko: '검색',                en: 'Search' },
    'actions':              { ko: '작업',                en: 'Actions' },
    'name':                 { ko: '이름',                en: 'Name' },
    'status':               { ko: '상태',                en: 'Status' },
    'time':                 { ko: '시간',                en: 'Time' },
    'source':               { ko: '소스',                en: 'Source' },
    'details':              { ko: '상세',                en: 'Details' },
    'confirm':              { ko: '확인',                en: 'Confirm' },
    'items':                { ko: '건',                  en: 'items' },

    // ─── Dashboard (index.html) ───
    'tab.overview':         { ko: '개요',                en: 'Overview' },
    'tab.agents':           { ko: '에이전트 프로필',      en: 'Agent Profiles' },
    'tab.projects':         { ko: '프로젝트 및 스코프',   en: 'Projects & Scopes' },
    'tab.access':           { ko: '접근 키',              en: 'Access Keys' },
    'tab.settings':         { ko: '설정',                en: 'Settings' },

    'stat.totalAgents':     { ko: '전체 에이전트',        en: 'Total Agents' },
    'stat.memoriesStored':  { ko: '저장된 기억',          en: 'Memories Stored' },
    'stat.graphNodes':      { ko: '그래프 노드',          en: 'Graph Nodes' },
    'stat.avgLatency':      { ko: '평균 검색 지연',       en: 'Avg Search Latency' },
    'stat.activeSimulation':{ ko: '시뮬레이션 활성',      en: 'Active in simulation' },
    'stat.entitiesEpisodes':{ ko: '엔티티 + 에피소드',    en: 'entities + episodes' },
    'stat.asmrParallel':    { ko: 'ASMR 3-way 병렬 처리', en: 'ASMR 3-way parallel' },

    'panel.memoryTimeline': { ko: '기억 타임라인',        en: 'Memory Timeline' },
    'panel.systemStatus':   { ko: '시스템 상태',          en: 'System Status' },

    'sys.storageBackend':   { ko: '스토리지 백엔드',      en: 'Storage Backend' },
    'sys.neo4jConnection':  { ko: 'Neo4j 연결',          en: 'Neo4j Connection' },
    'sys.supermemory':      { ko: 'Supermemory',         en: 'Supermemory' },
    'sys.circuitBreaker':   { ko: '서킷 브레이커',        en: 'Circuit Breaker' },
    'sys.outboxQueue':      { ko: '아웃박스 큐',          en: 'Outbox Queue' },
    'sys.observerAgents':   { ko: '옵저버 에이전트',      en: 'Observer Agents' },
    'sys.llmProvider':      { ko: 'LLM 프로바이더',       en: 'LLM Provider' },
    'sys.dataAdapters':     { ko: '데이터 어댑터',        en: 'Data Adapters' },
    'sys.registered':       { ko: '등록됨',              en: 'registered' },

    'projects.title':       { ko: '메모리 프로젝트 (그래프)',   en: 'Memory Projects (Graphs)' },
    'projects.loading':     { ko: '프로젝트 로딩 중...',  en: 'Loading projects...' },

    'access.title':         { ko: 'API 토큰 (접근 제어)', en: 'API Tokens (Access Control)' },
    'access.loading':       { ko: '접근 키 로딩 중...',   en: 'Loading access keys...' },
    'access.keyName':       { ko: '키 이름 (예: Cursor Agent)',     en: 'Key Name (e.g., Cursor Agent)' },
    'access.scopes':        { ko: '스코프 (쉼표 구분)',             en: 'Scopes (comma separated)' },
    'access.generateKey':   { ko: '키 생성',              en: 'Generate Key' },

    'settings.storageBackend':   { ko: '스토리지 백엔드',   en: 'Storage Backend' },
    'settings.backendMode':      { ko: '백엔드 모드',       en: 'Backend Mode' },
    'settings.backendModeDesc':  { ko: 'Neo4j 전용 또는 하이브리드 모드 전환', en: 'Switch between Neo4j only or Hybrid mode' },
    'settings.cbThreshold':      { ko: '서킷 브레이커 임계치', en: 'CircuitBreaker Threshold' },
    'settings.cbThresholdDesc':  { ko: '회로 개방 전 실패 횟수', en: 'Failures before opening circuit' },
    'settings.asmrAgents':       { ko: 'ASMR 에이전트',     en: 'ASMR Agents' },
    'settings.observerAgents':   { ko: '옵저버 에이전트',    en: 'Observer Agents' },
    'settings.observerDesc':     { ko: 'Personal / Event / Social 추출', en: 'Personal / Event / Social extraction' },
    'settings.searchAgents':     { ko: '검색 에이전트',      en: 'Search Agents' },
    'settings.searchDesc':       { ko: 'Fact / Context / Timeline 검색', en: 'Fact / Context / Timeline retrieval' },
    'settings.profileCaching':   { ko: '프로필 캐싱',       en: 'Profile Caching' },
    'settings.profileCacheDesc': { ko: '라운드 간 에이전트 프로필 캐시', en: 'Cache agent profiles across rounds' },
    'settings.dataIngestion':    { ko: '데이터 수집',       en: 'Data Ingestion' },
    'settings.streamIngestion':  { ko: '스트림 수집',       en: 'Stream Ingestion' },
    'settings.streamDesc':       { ko: 'Kafka / Webhook 실시간 피드',   en: 'Kafka / Webhook real-time feeds' },
    'settings.csvRowLimit':      { ko: 'CSV 행 제한',       en: 'CSV Row Limit' },
    'settings.csvDesc':          { ko: 'CSV 가져오기 당 최대 행 수', en: 'Max rows per CSV import' },
    'settings.llmConfig':        { ko: 'LLM 설정',         en: 'LLM Configuration' },
    'settings.provider':         { ko: '프로바이더',        en: 'Provider' },
    'settings.providerDesc':     { ko: 'NER, 옵저버, 에이전트용 LLM 백엔드', en: 'LLM backend for NER, Observers, and Agents' },

    // ─── Graph Explorer ───
    'graph.title':          { ko: '지식 그래프 탐색기',    en: 'Knowledge Graph Explorer' },
    'graph.query':          { ko: '그래프 쿼리',          en: 'Graph Query' },
    'graph.cypherQuery':    { ko: 'Cypher 쿼리',         en: 'Cypher Query' },
    'graph.executeQuery':   { ko: '▶ 쿼리 실행',         en: '▶ Execute Query' },
    'graph.clustering':     { ko: '클러스터링 및 필터링',  en: 'Clustering & Filtration' },
    'graph.semanticFilter': { ko: '시맨틱 필터링',        en: 'Semantic Filtering' },
    'graph.filterPlaceholder': { ko: '키워드로 노드 필터링...', en: 'Filter nodes by keyword...' },
    'graph.smartClustering':{ ko: '스마트 클러스터링',     en: 'Smart Clustering' },
    'graph.noClustering':   { ko: '클러스터링 없음 (Raw)', en: 'No Clustering (Raw Graph)' },
    'graph.clusterScope':   { ko: '스코프별 클러스터링',   en: 'Cluster by Scope (Personal/Social)' },
    'graph.clusterHub':     { ko: '허브 크기별 클러스터링', en: 'Cluster by Hub Size (Compact view)' },
    'graph.agents':         { ko: '에이전트',              en: 'Agents' },
    'graph.overlayAgents':  { ko: '🧬 에이전트 네트워크 오버레이', en: '🧬 Overlay Agents Network' },
    'graph.overlayDesc':    { ko: '활성 에이전트와 Synaptic Bridge를 통해 공유된 기억이 강조됩니다.', en: 'Active agents and their shared memories via Synaptic Bridge will be highlighted.' },
    'graph.loadingNeural':  { ko: '뉴럴 맵 로딩 중...',    en: 'Loading Neural Map...' },
    'graph.selectNode':     { ko: '노드를 선택하여 기억, 에이전트 스코프, 접근 메트릭을 확인하세요.', en: 'Select a node to view its memory, agent scope, and access metrics.' },
    'graph.legendPersonal': { ko: '메모리 (개인)',         en: 'Memory (Personal)' },
    'graph.legendSocial':   { ko: '메모리 (소셜/팀)',      en: 'Memory (Social/Tribal)' },
    'graph.legendRevision': { ko: '리비전 / 메타데이터',    en: 'Revision / Metadata' },
    'graph.legendAgent':    { ko: '시냅틱 에이전트',       en: 'Synaptic Agent' },

    // ─── Memory Dashboard ───
    'memory.title':         { ko: '인지 기억 대시보드',    en: 'Cognitive Memory Dashboard' },
    'memory.cogTitle':      { ko: '🧠 <span>인지 기억</span> 매니저', en: '🧠 <span>Cognitive Memory</span> Manager' },
    'memory.refresh':       { ko: '🔄 새로고침',          en: '🔄 Refresh' },
    'memory.runDecay':      { ko: '⏳ 망각 실행',         en: '⏳ Run Decay' },
    'memory.simDecay':      { ko: '🔍 망각 시뮬레이션',   en: '🔍 Decay Simulation' },
    'memory.stm':           { ko: '단기 기억 (STM)',       en: 'Short-term (STM)' },
    'memory.stmSub':        { ko: '버퍼 대기 중',         en: 'Buffered' },
    'memory.ltm':           { ko: '장기 기억 (LTM)',       en: 'Long-term (LTM)' },
    'memory.ltmSub':        { ko: '엔티티 + 관계',        en: 'Entities + Relations' },
    'memory.avgSalience':   { ko: '평균 Salience',        en: 'Avg Salience' },
    'memory.avgSalienceSub':{ ko: '기억 건강도',           en: 'Memory Health' },
    'memory.archived':      { ko: '아카이브 (망각됨)',     en: 'Archived (Forgotten)' },
    'memory.archivedSub':   { ko: '임계치 이하로 소멸',   en: 'Decayed below threshold' },
    'memory.totalAccess':   { ko: '총 인출 횟수',         en: 'Total Retrievals' },
    'memory.totalAccessSub':{ ko: '강화 기여',            en: 'Reinforcement contribution' },
    'memory.tabOverview':   { ko: '📊 메모리 분포',       en: '📊 Memory Distribution' },
    'memory.tabSTM':        { ko: '📋 단기 기억(STM)',     en: '📋 Short-term (STM)' },
    'memory.tabList':       { ko: '🧠 기억 목록',         en: '🧠 Memory List' },
    'memory.tabPM':         { ko: '💎 영구 기억(PM)',      en: '💎 Permanent (PM)' },
    'memory.tabConfig':     { ko: '⚙️ 파라미터 설정',     en: '⚙️ Parameters' },
    'memory.salienceDist':  { ko: '📊 Salience 분포도',   en: '📊 Salience Distribution' },
    'memory.salienceDistSub':{ ko: '기억 강도 분포',      en: 'Memory strength distribution' },
    'memory.atRisk':        { ko: '⚠️ 위험 기억 (곧 망각)',en: '⚠️ At-Risk Memories (Near Decay)' },
    'memory.ebbinghaus':    { ko: '📉 Ebbinghaus 망각 곡선 시뮬레이션', en: '📉 Ebbinghaus Decay Curve Simulation' },
    'memory.stmBuffer':     { ko: '📋 단기 기억 버퍼',    en: '📋 Short-term Memory Buffer' },
    'memory.addSTM':        { ko: '+ 새 기억 추가',       en: '+ Add New Memory' },
    'memory.addSTMPanel':   { ko: '단기 기억 추가',       en: 'Add Short-term Memory' },
    'memory.content':       { ko: '내용',                 en: 'Content' },
    'memory.contentPH':     { ko: '기억할 내용을 입력하세요...', en: 'Enter content to remember...' },
    'memory.sourceLbl':     { ko: '출처',                 en: 'Source' },
    'memory.ttl':           { ko: 'TTL (초)',             en: 'TTL (seconds)' },
    'memory.addToSTM':      { ko: '단기 기억에 추가',     en: 'Add to Short-term Memory' },
    'memory.empty':         { ko: '비어 있음',            en: 'Empty' },

    // ─── Memory History / Audit Trail ───
    'history.title':        { ko: '📜 기억 감사 추적',     en: '📜 Memory Audit Trail' },
    'history.totalRevisions':{ ko: '📝 총 리비전',         en: '📝 Total Revisions' },
    'history.totalRevSub':  { ko: '전체 변경 기록',        en: 'All change records' },
    'history.boost':        { ko: '💪 강화 (Boost)',       en: '💪 Boost' },
    'history.boostSub':     { ko: '수동/자동 강화 횟수',   en: 'Manual/auto boost count' },
    'history.decay':        { ko: '📉 감쇠 (Decay)',       en: '📉 Decay' },
    'history.decaySub':     { ko: 'Ebbinghaus 감쇠 횟수',  en: 'Ebbinghaus decay count' },
    'history.rollback':     { ko: '🔄 롤백 (Rollback)',    en: '🔄 Rollback' },
    'history.rollbackSub':  { ko: '상태 복원 횟수',        en: 'State restore count' },
    'history.activityFeed': { ko: '📋 변경 이력 (Activity Feed)', en: '📋 Activity Feed' },
    'history.detailHistory':{ ko: '📊 기억 상세 이력',     en: '📊 Memory Detail History' },
    'history.salienceChart':{ ko: '📈 Salience 변화 그래프', en: '📈 Salience Change Chart' },
    'history.selectMemory': { ko: '왼쪽에서 기억을 선택하세요', en: 'Select a memory from the left' },
    'history.noHistory':    { ko: '이 기억의 이력이 없습니다',  en: 'No history for this memory' },
    'history.noChanges':    { ko: '변경 이력이 없습니다',  en: 'No changes found' },
    'history.loadFailed':   { ko: '로딩 실패',            en: 'Loading failed' },
    'history.allTypes':     { ko: '전체 타입',            en: 'All Types' },
    'history.filterBoost':  { ko: '💪 강화',              en: '💪 Boost' },
    'history.filterDecay':  { ko: '📉 감쇠',              en: '📉 Decay' },
    'history.filterCreate': { ko: '✨ 생성',              en: '✨ Create' },
    'history.filterRollback':{ ko: '🔄 롤백',             en: '🔄 Rollback' },
    'history.filterEdit':   { ko: '✏️ 수정',              en: '✏️ Edit' },
    'history.searchPlaceholder': { ko: '기억 이름 검색...', en: 'Search memory name...' },
    'history.rollbackConfirm':   { ko: '⚠️ 롤백 확인',    en: '⚠️ Rollback Confirmation' },
    'history.rollbackDesc': { ko: '이 리비전의 변경을 되돌리시겠습니까?', en: 'Do you want to revert this revision?' },
    'history.field':        { ko: '필드',                 en: 'Field' },
    'history.currentValue': { ko: '현재값',               en: 'Current Value' },
    'history.restoreValue': { ko: '복원값',               en: 'Restore Value' },
    'history.executeRollback': { ko: '🔄 롤백 실행',      en: '🔄 Execute Rollback' },
    'history.rollbackSuccess': { ko: '✅ 롤백 성공!',     en: '✅ Rollback Success!' },
    'history.rollbackFail':    { ko: '❌ 실패',           en: '❌ Failed' },
    'history.unknownError':    { ko: '알 수 없는 오류',    en: 'Unknown error' },
    'history.rollbackError':   { ko: '롤백 처리 중 오류',  en: 'Error during rollback' },
    'history.btnRollback':     { ko: '🔄 롤백',           en: '🔄 Rollback' },

    // ─── Synaptic Network ───
    'syn.network':          { ko: '🌐 시냅틱 네트워크',    en: '🌐 Synaptic Network' },
    'syn.scopes':           { ko: '🏗️ 기억 스코프',       en: '🏗️ Memory Scopes' },
    'syn.data':             { ko: '📦 데이터 프로덕트',    en: '📦 Data Products' },
    'syn.totalAgents':      { ko: '🤖 전체 에이전트',      en: '🤖 Total Agents' },
    'syn.totalEvents':      { ko: '📡 전체 이벤트',        en: '📡 Total Events' },
    'syn.shareCount':       { ko: '🔗 공유 횟수',          en: '🔗 Share Count' },
    'syn.empathyBoost':     { ko: '💚 공감 강화',          en: '💚 Empathy Boost' },
    'syn.registeredAgents': { ko: '🤖 등록된 에이전트',    en: '🤖 Registered Agents' },
    'syn.eventFeed':        { ko: '📡 이벤트 피드',        en: '📡 Event Feed' },
    'syn.scopeHierarchy':   { ko: '🏗️ 4-Tier 기억 계층',  en: '🏗️ 4-Tier Memory Hierarchy' },
    'syn.scopeDistrib':     { ko: '스코프 분포',           en: 'Scope Distribution' },
    'syn.sourceDistrib':    { ko: '소스 타입 분포',        en: 'Source Type Distribution' },
    'syn.promotionCandidates': { ko: '⬆️ 승격 후보',      en: '⬆️ Promotion Candidates' },
    'syn.dataProducts':     { ko: '📦 AI-Ready 데이터 프로덕트', en: '📦 AI-Ready Data Products' },
    'syn.manifests':        { ko: '📋 생성된 Manifests',   en: '📋 Created Manifests' },
    'syn.shared':           { ko: '공유',                  en: 'Shared' },
    'syn.received':         { ko: '수신',                  en: 'Received' },
    'syn.subscribed':       { ko: '구독',                  en: 'Subscribed' },
    'syn.noAgents':         { ko: '등록된 에이전트 없음',   en: 'No registered agents' },
    'syn.noEvents':         { ko: '이벤트 없음',            en: 'No events' },
    'syn.noCandidates':     { ko: '현재 승격 후보 없음',    en: 'No promotion candidates' },
    'syn.noManifests':      { ko: '아직 생성된 Manifest 없음', en: 'No manifests created yet' },
    'syn.promoteTribal':    { ko: 'Tribal 승격',           en: 'Promote to Tribal' },
    'syn.enterManifestName':{ ko: 'Manifest 이름을 입력하세요:', en: 'Enter manifest name:' },

    // ─── Terminology ───
    'term.title':           { ko: '용어 규칙',            en: 'Terminology Rules' },
    'term.subtitle':        { ko: '스코프 간 용어 정규화 매핑을 통해 엔티티 이름을 표준화합니다.', en: 'Standardize entity names across scopes via term normalization mapping.' },
    'term.activeMappings':  { ko: '활성 매핑',            en: 'Active Mappings' },
    'term.allScopes':       { ko: '전체 스코프',          en: 'All Scopes' },
    'term.addMapping':      { ko: '매핑 추가/수정',       en: 'Add / Update Mapping' },
    'term.sourceTerm':      { ko: '원본 용어',            en: 'Source Term' },
    'term.standardTerm':    { ko: '표준 용어',            en: 'Standard Term' },
    'term.scope':           { ko: '스코프',               en: 'Scope' },
    'term.createdAt':       { ko: '생성일',               en: 'Created At' },
    'term.saveMapping':     { ko: '매핑 저장',            en: 'Save Mapping' },
    'term.entityType':      { ko: '엔티티 유형 (선택)',    en: 'Entity Type (Optional)' },
    'term.description':     { ko: '설명 (선택)',           en: 'Description (Optional)' },
    'term.preview':         { ko: '미리보기',             en: 'Preview' },
    'term.migrationPreview':{ ko: '마이그레이션 미리보기', en: 'Migration Preview' },
    'term.executeMigration':{ ko: '마이그레이션 실행',    en: 'Execute Migration' },
    'term.teamId':          { ko: '팀 ID',               en: 'Team ID' },
    'term.noMappings':      { ko: '활성 매핑이 없습니다.', en: 'No active mappings found.' },

    // ─── Maturity ───
    'mat.totalMemories':    { ko: '전체 기억',            en: 'Total Memories' },
    'mat.learningSub':      { ko: '개인 전용 · 접근 차단', en: 'Personal only · Access blocked' },
    'mat.unstableSub':      { ko: '검증 대기 · 팀 읽기만', en: 'Awaiting verification · Team read-only' },
    'mat.matureSub':        { ko: '공유 가능 · 집단 지성', en: 'Shareable · Collective intelligence' },
    'mat.secretSub':        { ko: '암호화 · Admin만 접근', en: 'Encrypted · Admin only' },
    'mat.maturityDistrib':  { ko: '📊 성숙도 분포',        en: '📊 Maturity Distribution' },
    'mat.scopeMatrix':      { ko: '🗂️ 스코프 × 성숙도 매트릭스', en: '🗂️ Scope × Maturity Matrix' },
    'mat.allMemories':      { ko: '전체 기억',            en: 'All Memories' },
    'mat.autoPromote':      { ko: '⬆️ 자동 승격 실행',    en: '⬆️ Run Auto Promotion' },
    'mat.changeMaturity':   { ko: '✏️ 성숙도 변경',       en: '✏️ Change Maturity' },
    'mat.maturity':         { ko: '성숙도',               en: 'Maturity' },
    'mat.salience':         { ko: 'Salience',            en: 'Salience' },
    'mat.scope':            { ko: '스코프',               en: 'Scope' },
    'mat.accessCount':      { ko: '접근 수',              en: 'Access Count' },
    'mat.encryption':       { ko: '암호화',               en: 'Encryption' },
    'mat.recentChanges':    { ko: '📜 최근 성숙도 변경 이력', en: '📜 Recent Maturity Changes' },
    'mat.scopeMatrixDetail':{ ko: '🗂️ 스코프 × 성숙도 상세 매트릭스', en: '🗂️ Scope × Maturity Detail Matrix' },
    'mat.changedBy':        { ko: '변경자',               en: 'Changed By' },
    'mat.noChanges':        { ko: '변경 이력 없음',       en: 'No change history' },
    'mat.noMemories':       { ko: '해당 성숙도의 기억이 없습니다', en: 'No memories at this maturity level' },
    'mat.changeModal':      { ko: '✏️ 기억 성숙도 변경',   en: '✏️ Change Memory Maturity' },
    'mat.memoryUuid':       { ko: '기억 UUID',            en: 'Memory UUID' },
    'mat.uuidPlaceholder':  { ko: 'UUID 입력...',         en: 'Enter UUID...' },
    'mat.newMaturity':      { ko: '새 성숙도',            en: 'New Maturity' },
    'mat.reason':           { ko: '변경 사유',            en: 'Change Reason' },
    'mat.reasonPlaceholder':{ ko: '사유 입력...',          en: 'Enter reason...' },
    'mat.learningDesc':     { ko: '🌱 Learning — 학습 중 (접근 차단)', en: '🌱 Learning — In training (Access blocked)' },
    'mat.unstableDesc':     { ko: '⚡ Unstable — 검증 대기',         en: '⚡ Unstable — Awaiting verification' },
    'mat.matureDesc':       { ko: '✅ Mature — 공유 가능',           en: '✅ Mature — Shareable' },
    'mat.secretDesc':       { ko: '🔒 Secret — 비밀 (자동 암호화)',   en: '🔒 Secret — Confidential (Auto-encrypted)' },
    'mat.promotionMsg':     { ko: '자동 승격: {n}건 처리됨', en: 'Auto promotion: {n} processed' },
    'mat.enterUuid':        { ko: 'UUID를 입력해주세요',   en: 'Please enter a UUID' },

    // Maturity Rules
    'mat.rule.ownerOnly':   { ko: 'Owner만 접근',         en: 'Owner access only' },
    'mat.rule.noSearch':    { ko: '검색 불가',            en: 'Not searchable' },
    'mat.rule.noShare':     { ko: '공유 불가',            en: 'Not shareable' },
    'mat.rule.noEncrypt':   { ko: '암호화 없음',          en: 'No encryption' },
    'mat.rule.teamRead':    { ko: '팀원 읽기 가능',       en: 'Team read access' },
    'mat.rule.searchExcl':  { ko: '검색 제외',            en: 'Search excluded' },
    'mat.rule.fullAccess':  { ko: '전체 접근 가능',       en: 'Full access' },
    'mat.rule.searchIncl':  { ko: '검색 포함',            en: 'Search included' },
    'mat.rule.shareable':   { ko: '공유 가능',            en: 'Shareable' },
    'mat.rule.encryptOpt':  { ko: '암호화 선택',          en: 'Encryption optional' },
    'mat.rule.adminOnly':   { ko: 'Admin만 접근',         en: 'Admin access only' },
    'mat.rule.autoEncrypt': { ko: '자동 암호화',          en: 'Auto-encrypted' },

    // ─── Workflows ───
    'wf.title':             { ko: '⚡ n8n 워크플로우 카탈로그', en: '⚡ n8n Workflow Catalog' },
    'wf.subtitle':          { ko: '다양한 데이터 소스에서 지식을 수집하여 Mories 메모리로 자동 인제스트하는 즉시 사용 가능한 워크플로우 모음', en: 'Ready-to-use workflow collection for auto-ingesting knowledge from various data sources into Mories memory' },
    'wf.workflows':         { ko: '워크플로우',            en: 'Workflows' },
    'wf.dataSources':       { ko: '데이터 소스',           en: 'Data Sources' },
    'wf.triggerTypes':      { ko: '트리거 유형',           en: 'Trigger Types' },
    'wf.searchPlaceholder': { ko: '워크플로우 검색 (예: github, slack, rss...)', en: 'Search workflows (e.g., github, slack, rss...)' },
    'wf.recentExecutions':  { ko: '📊 최근 실행 현황 (Webhooks)', en: '📊 Recent Executions (Webhooks)' },
    'wf.noExecutions':      { ko: '최근 실행 기록이 없습니다.',    en: 'No recent execution records.' },
    'wf.executionError':    { ko: '실행 로그를 불러오지 못했습니다.', en: 'Failed to load execution logs.' },
    'wf.loadError':         { ko: '워크플로우를 불러올 수 없습니다. 서버 상태를 확인해주세요.', en: 'Cannot load workflows. Please check server status.' },
    'wf.architecture':      { ko: '📐 아키텍처',           en: '📐 Architecture' },
    'wf.envSetup':          { ko: '🔧 환경변수 설정',      en: '🔧 Environment Variables' },
    'wf.variable':          { ko: '변수',                  en: 'Variable' },
    'wf.workflow':          { ko: '워크플로우',             en: 'Workflow' },
    'wf.description':       { ko: '설명',                  en: 'Description' },
    'wf.execTime':          { ko: '시간',                  en: 'Time' },
    'wf.execSource':        { ko: '소스',                  en: 'Source' },
    'wf.execStatus':        { ko: '상태',                  en: 'Status' },
    'wf.execDetails':       { ko: '상세 (생성/승격)',       en: 'Details (Created/Promoted)' },
    'wf.copy':              { ko: '📋 복사',               en: '📋 Copy' },
    'wf.copied':            { ko: '✅ 복사됨!',            en: '✅ Copied!' },
    'wf.download':          { ko: '⬇ 다운로드',            en: '⬇ Download' },
    'wf.execLoadError':     { ko: '실행 로그를 불러오지 못했습니다.', en: 'Failed to load execution logs.' },
    'wf.envAll':            { ko: '전체',                  en: 'All' },
    'wf.envMoriesUrl':      { ko: 'Mories 서버 URL (기본: http://localhost:5001)', en: 'Mories server URL (default: http://localhost:5001)' },
    'wf.envGraphId':        { ko: '대상 그래프 ID (기본: default)', en: 'Target graph ID (default: default)' },
    'wf.envGithubRepo':     { ko: '감시할 저장소 소유자/이름', en: 'Repository owner/name to watch' },
    'wf.envRssUrl':         { ko: 'RSS 피드 URL',          en: 'RSS Feed URL' },

    // ─── API Explorer ───
    'api.title':            { ko: 'Mories API',           en: 'Mories API' },
    'api.subtitle':         { ko: '인터랙티브 API 탐색기 및 테스트 콘솔', en: 'Interactive API Explorer & Testing Console' },
    'api.searchPlaceholder':{ ko: '엔드포인트 검색... (⌘K)', en: 'Search endpoints... (⌘K)' },
    'api.checkingConn':     { ko: '연결 확인 중...',       en: 'Checking connection...' },
    'api.endpoints':        { ko: '엔드포인트',            en: 'endpoints' },
    'api.mcpTools':         { ko: 'MCP 도구',             en: 'MCP tools' },
    'api.welcome':          { ko: 'Mories API 탐색기에 오신 것을 환영합니다', en: 'Welcome to Mories API Explorer' },
    'api.welcomeDesc':      { ko: 'Mories 메모리 시스템의 모든 엔드포인트와 MCP 도구를 탐색, 테스트하고 이해하세요. 사이드바에서 엔드포인트를 선택하거나 아래 퀵 스타트를 사용하세요.', en: 'Browse, test, and understand every endpoint and MCP tool in the Mories Memory System. Select an endpoint from the sidebar or pick a quick start below.' },
    'api.healthCheck':      { ko: '상태 확인',             en: 'Health Check' },
    'api.healthDesc':       { ko: '시스템 상태 확인',       en: 'Check system status' },
    'api.memoryOverview':   { ko: '기억 개요',             en: 'Memory Overview' },
    'api.memoryOverviewDesc':{ ko: '인지 상태 조회',       en: 'View cognitive state' },
    'api.searchMemories':   { ko: '기억 검색',             en: 'Search Memories' },
    'api.searchMemDesc':    { ko: '지식 그래프 질의',       en: 'Query knowledge graph' },
    'api.dataProducts':     { ko: '데이터 프로덕트',       en: 'Data Products' },
    'api.dataProductsDesc': { ko: 'AI-Ready 내보내기',     en: 'AI-Ready exports' },
    'api.createMemory':     { ko: '기억 생성',             en: 'Create Memory' },
    'api.createMemDesc':    { ko: 'STM 버퍼에 추가',       en: 'Add to STM buffer' },
    'api.mcpToolsLabel':    { ko: 'MCP 도구',              en: 'MCP Tools' },
    'api.mcpToolsDesc':     { ko: '에이전트 호출 가능 도구', en: 'Agent-callable tools' },
    'api.parameters':       { ko: '매개변수',              en: 'Parameters' },
    'api.tryIt':            { ko: '⚡ 사용해보기',         en: '⚡ Try It' },
    'api.sendRequest':      { ko: '요청 보내기',           en: 'Send Request' },
    'api.requestUrl':       { ko: '요청 URL',             en: 'Request URL' },
    'api.queryParams':      { ko: '쿼리 매개변수',         en: 'Query Parameters' },
    'api.requestBody':      { ko: '요청 바디 (JSON)',      en: 'Request Body (JSON)' },
    'api.exampleResponse':  { ko: '응답 예시',             en: 'Example Response' },
    'api.testMcp':          { ko: '⚡ MCP 호출 테스트',    en: '⚡ Test MCP Call' },
    'api.sendMcp':          { ko: 'MCP 요청 보내기',       en: 'Send MCP Request' },
    'api.mcpEndpoint':      { ko: 'MCP 엔드포인트',        en: 'MCP Endpoint' },
    'api.jsonRpcBody':      { ko: 'JSON-RPC 바디',        en: 'JSON-RPC Body' },

    // ─── Time formatting ───
    'time.secondsAgo':      { ko: '{n}초 전',             en: '{n}s ago' },
    'time.minutesAgo':      { ko: '{n}분 전',             en: '{n}m ago' },
    'time.hoursAgo':        { ko: '{n}시간 전',           en: '{n}h ago' },

    // ─── Harness (Evolutionary Process Patterns) ───
    'harness.title':        { ko: '♞ 하네스 프로세스 패턴',  en: '♞ Harness Process Patterns' },
    'harness.subtitle':     { ko: '진화형 프로세스 오케스트레이션 — 도구 체인, 실행 통계, 버전 비교', en: 'Evolutionary process orchestration — tool chains, execution stats, version comparison' },
    'harness.totalPatterns': { ko: '전체 패턴',            en: 'Total Patterns' },
    'harness.totalExec':    { ko: '총 실행',              en: 'Total Executions' },
    'harness.avgSuccess':   { ko: '평균 성공률',           en: 'Avg Success Rate' },
    'harness.domains':      { ko: '도메인',               en: 'Domains' },
    'harness.allDomains':   { ko: '전체 도메인',           en: 'All Domains' },
    'harness.searchPH':     { ko: '패턴 검색 (도메인, 트리거, 태그...)', en: 'Search patterns (domain, trigger, tag...)' },
    'harness.tabOverview':  { ko: '📊 개요',              en: '📊 Overview' },
    'harness.tabPatterns':  { ko: '♞ 패턴 목록',           en: '♞ Pattern List' },
    'harness.tabRecord':    { ko: '➕ 패턴 등록',           en: '➕ Record Pattern' },
    'harness.name':         { ko: '패턴명',               en: 'Pattern Name' },
    'harness.domain':       { ko: '도메인',               en: 'Domain' },
    'harness.trigger':      { ko: '트리거',               en: 'Trigger' },
    'harness.processType':  { ko: '프로세스 유형',         en: 'Process Type' },
    'harness.version':      { ko: '버전',                 en: 'Version' },
    'harness.toolCount':    { ko: '도구 수',              en: 'Tool Count' },
    'harness.successRate':  { ko: '성공률',               en: 'Success Rate' },
    'harness.execCount':    { ko: '실행 횟수',            en: 'Executions' },
    'harness.scope':        { ko: '스코프',               en: 'Scope' },
    'harness.tags':         { ko: '태그',                 en: 'Tags' },
    'harness.toolChain':    { ko: '도구 체인',            en: 'Tool Chain' },
    'harness.dataFlow':     { ko: '데이터 흐름',           en: 'Data Flow' },
    'harness.evolution':    { ko: '진화 이력',            en: 'Evolution History' },
    'harness.compare':      { ko: '버전 비교',            en: 'Compare Versions' },
    'harness.evolve':       { ko: '진화',                 en: 'Evolve' },
    'harness.execute':      { ko: '실행 기록',            en: 'Record Execution' },
    'harness.detail':       { ko: '상세 보기',            en: 'View Detail' },
    'harness.noPatterns':   { ko: '등록된 패턴이 없습니다. 아래에서 새 패턴을 등록하세요.', en: 'No patterns found. Record a new pattern below.' },
    'harness.loadError':    { ko: '패턴 데이터를 불러올 수 없습니다.', en: 'Failed to load pattern data.' },
    'harness.recordTitle':  { ko: '새 하네스 패턴 등록',    en: 'Record New Harness Pattern' },
    'harness.domainPH':     { ko: '예: development, ai_research, data_pipeline', en: 'e.g. development, ai_research, data_pipeline' },
    'harness.triggerPH':    { ko: '예: 코드 리뷰 요청 시, PR 생성 시', en: 'e.g. on code review request, on PR creation' },
    'harness.descPH':       { ko: '이 프로세스 패턴에 대한 설명', en: 'Description of this process pattern' },
    'harness.tagsPH':       { ko: '쉼표로 구분 (예: ci, deployment, testing)', en: 'Comma separated (e.g. ci, deployment, testing)' },
    'harness.toolNamePH':   { ko: '도구/단계명', en: 'Tool/Step name' },
    'harness.toolTypePH':   { ko: '유형 선택', en: 'Select type' },
    'harness.addTool':      { ko: '+ 도구 추가', en: '+ Add Tool' },
    'harness.removeTool':   { ko: '삭제', en: 'Remove' },
    'harness.recordBtn':    { ko: '패턴 등록', en: 'Record Pattern' },
    'harness.domainDistrib': { ko: '📊 도메인 분포', en: '📊 Domain Distribution' },
    'harness.typeDistrib':  { ko: '📊 프로세스 유형 분포', en: '📊 Process Type Distribution' },
    'harness.recentExec':   { ko: '📈 최근 실행 현황', en: '📈 Recent Executions' },
  };


  // ═══════════════════════════════════════════════════════
  //  t(key, replacements?) — Translation function
  // ═══════════════════════════════════════════════════════
  function t(key, replacements) {
    const lang = localStorage.getItem('moriesLang') || 'ko';
    const entry = DICT[key];
    if (!entry) return key; // Fallback: return key itself
    let text = entry[lang] || entry['en'] || key;
    if (replacements) {
      for (const [k, v] of Object.entries(replacements)) {
        text = text.replace(`{${k}}`, v);
      }
    }
    return text;
  }

  // ═══════════════════════════════════════════════════════
  //  applyI18n() — Scan DOM and translate data-i18n elements
  // ═══════════════════════════════════════════════════════
  function applyI18n(root) {
    const scope = root || document;

    // data-i18n → textContent
    scope.querySelectorAll('[data-i18n]').forEach(el => {
      const key = el.getAttribute('data-i18n');
      if (key) el.textContent = t(key);
    });

    // data-i18n-html → innerHTML (for icons+text combos)
    scope.querySelectorAll('[data-i18n-html]').forEach(el => {
      const key = el.getAttribute('data-i18n-html');
      if (key) el.innerHTML = t(key);
    });

    // data-i18n-placeholder → placeholder attribute
    scope.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
      const key = el.getAttribute('data-i18n-placeholder');
      if (key) el.placeholder = t(key);
    });

    // data-i18n-title → title attribute
    scope.querySelectorAll('[data-i18n-title]').forEach(el => {
      const key = el.getAttribute('data-i18n-title');
      if (key) el.title = t(key);
    });

    // Update <html lang>
    const lang = localStorage.getItem('moriesLang') || 'ko';
    document.documentElement.setAttribute('lang', lang);
  }

  // ═══════════════════════════════════════════════════════
  //  formatTimeAgo(ts) — Relative time in current language
  // ═══════════════════════════════════════════════════════
  function formatTimeAgo(ts) {
    if (!ts) return '?';
    try {
      const d = new Date(ts);
      const now = new Date();
      const diff = (now - d) / 1000;
      const lang = localStorage.getItem('moriesLang') || 'ko';
      if (diff < 60) return t('time.secondsAgo', { n: Math.floor(diff) });
      if (diff < 3600) return t('time.minutesAgo', { n: Math.floor(diff / 60) });
      if (diff < 86400) return t('time.hoursAgo', { n: Math.floor(diff / 3600) });
      const loc = lang === 'ko' ? 'ko-KR' : 'en-US';
      return d.toLocaleDateString(loc, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    } catch { return ts; }
  }

  // ═══════════════════════════════════════════════════════
  //  getLang() — Current language code
  // ═══════════════════════════════════════════════════════
  function getLang() {
    return localStorage.getItem('moriesLang') || 'ko';
  }

  // ═══════════════════════════════════════════════════════
  //  Auto-apply on load + listen for language change
  // ═══════════════════════════════════════════════════════
  function init() {
    applyI18n();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Re-apply when language changes
  window.addEventListener('moriesLangChanged', () => {
    applyI18n();
  });

  // ═══════════════════════════════════════════════════════
  //  Expose globals
  // ═══════════════════════════════════════════════════════
  window.t = t;
  window.applyI18n = applyI18n;
  window.formatTimeAgo = formatTimeAgo;
  window.getLang = getLang;
})();
