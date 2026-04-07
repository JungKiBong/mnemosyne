// ──────────────────────────────────────────
// API Registry — All Mories Endpoints
// ──────────────────────────────────────────
const BASE = window.moriesApi ? window.moriesApi.baseUrl.replace(/\/api$/, '') : (window.location.protocol === 'file:' ? 'http://localhost:5001' : window.location.origin);

const API_REGISTRY = {
  "System": [
    { id:"health", method:"GET", path:"/api/health", name:"Health Check", desc:"시스템 상태, Neo4j 연결, LLM 설정, 컴포넌트 상태를 확인합니다." },
    { id:"settings_get", method:"GET", path:"/api/admin/settings", name:"Get Settings", desc:"현재 LLM/Embedding 프로바이더 설정을 조회합니다." },
    { id:"settings_put", method:"PUT", path:"/api/admin/settings", name:"Update Settings", desc:"LLM/Embedding 프로바이더 설정을 런타임에 변경합니다.",
      body: '{"LLM_PROVIDER":"ollama","LLM_BASE_URL":"http://localhost:11434"}',
      params:[{name:"keys",type:"string",required:true,desc:"변경할 설정 키 (.env 변수명)"}] },
    { id:"settings_test_llm", method:"POST", path:"/api/admin/settings/test/llm", name:"Test LLM Connection", desc:"LLM 프로바이더 연결을 테스트합니다." },
    { id:"settings_test_embed", method:"POST", path:"/api/admin/settings/test/embedding", name:"Test Embedding", desc:"Embedding 프로바이더 연결을 테스트합니다." },
  ],

  "Cognitive Memory": [
    { id:"memory_overview", method:"GET", path:"/api/v1/memory/overview", name:"Memory Overview", desc:"STM/LTM 개요, 평균 salience, 감쇠 상태를 반환합니다." },
    { id:"memory_top", method:"GET", path:"/api/v1/memory/top", name:"Top Memories", desc:"salience가 높은 상위 기억을 조회합니다.",
      query:[{name:"limit",type:"int",desc:"조회 개수 (기본: 20)"}] },
    { id:"memory_weakest", method:"GET", path:"/api/v1/memory/weakest", name:"Weakest Memories", desc:"감쇠 위험이 있는 약한 기억을 조회합니다." },
    { id:"memory_get", method:"GET", path:"/api/v1/memory/{uuid}", name:"Get Memory", desc:"특정 UUID의 기억 상세 정보를 조회합니다.",
      params:[{name:"uuid",type:"uuid",required:true,desc:"기억 UUID"}] },
    { id:"stm_add", method:"POST", path:"/api/v1/memory/stm/add", name:"STM Add", desc:"단기 기억(STM) 버퍼에 새 정보를 추가합니다.",
      body: '{"content":"새로운 기억 내용","source":"manual","salience":0.6}' },
    { id:"stm_list", method:"GET", path:"/api/v1/memory/stm/list", name:"STM List", desc:"현재 STM 버퍼의 모든 항목을 조회합니다." },
    { id:"stm_evaluate", method:"POST", path:"/api/v1/memory/stm/evaluate", name:"STM Evaluate", desc:"STM 항목의 salience를 재평가합니다.",
      body: '{"uuid":"stm-item-uuid"}' },
    { id:"stm_promote", method:"POST", path:"/api/v1/memory/stm/promote", name:"STM Promote", desc:"STM 항목을 LTM으로 승격합니다.",
      body: '{"uuid":"stm-item-uuid"}' },
    { id:"stm_discard", method:"POST", path:"/api/v1/memory/stm/discard", name:"STM Discard", desc:"STM 항목을 폐기합니다.",
      body: '{"uuid":"stm-item-uuid"}' },
    { id:"memory_boost", method:"POST", path:"/api/v1/memory/boost", name:"Retrieval Boost", desc:"기억의 salience를 수동으로 강화합니다.",
      body: '{"uuids":["uuid-1","uuid-2"]}' },
    { id:"memory_decay", method:"POST", path:"/api/v1/memory/decay", name:"Run Decay", desc:"에빙하우스 감쇠 사이클을 수동 실행합니다." },
    { id:"memory_config", method:"GET", path:"/api/v1/memory/config", name:"Memory Config", desc:"기억 매니저 설정 (감쇠율, TTL 등)을 조회합니다." },
  ],

  "Memory Scopes": [
    { id:"scopes_summary", method:"GET", path:"/api/v1/memory/scopes/summary", name:"Scope Summary", desc:"각 scope(personal/tribal/social/global)별 기억 개수와 통계를 반환합니다." },
    { id:"scopes_list", method:"GET", path:"/api/v1/memory/scopes/list/{scope}", name:"List by Scope", desc:"특정 scope의 기억 목록을 조회합니다.",
      params:[{name:"scope",type:"string",required:true,desc:"personal|tribal|social|global"}] },
    { id:"scopes_candidates", method:"GET", path:"/api/v1/memory/scopes/candidates", name:"Promotion Candidates", desc:"scope 승격 후보 기억을 조회합니다." },
    { id:"scopes_promote", method:"POST", path:"/api/v1/memory/scopes/promote", name:"Promote Scope", desc:"기억의 scope를 상위로 승격합니다.",
      body: '{"uuid":"memory-uuid","target_scope":"tribal"}' },
    { id:"scopes_source_type", method:"POST", path:"/api/v1/memory/scopes/source-type", name:"Set Source Type", desc:"기억의 source_type을 변경합니다.",
      body: '{"uuid":"memory-uuid","source_type":"code"}' },
  ],

  "Permanent Memory": [
    { id:"pm_imprint", method:"POST", path:"/api/v1/memory/permanent/imprint", name:"Create Imprint", desc:"불변의 각인(Imprint)을 생성합니다. Admin 전용.",
      body: '{"name":"핵심 규칙","summary":"이 시스템은...","scope":"global","created_by":"admin"}' },
    { id:"pm_imprints", method:"GET", path:"/api/v1/memory/permanent/imprints", name:"List Imprints", desc:"모든 각인(Imprint) 목록을 조회합니다." },
    { id:"pm_freeze", method:"POST", path:"/api/v1/memory/permanent/freeze", name:"Freeze Memory", desc:"LTM 기억을 동결하여 감쇠로부터 보호합니다.",
      body: '{"uuid":"memory-uuid","frozen_by":"admin"}' },
    { id:"pm_unfreeze", method:"POST", path:"/api/v1/memory/permanent/unfreeze", name:"Unfreeze Memory", desc:"동결된 기억을 해제합니다.",
      body: '{"uuid":"memory-uuid"}' },
    { id:"pm_frozen", method:"GET", path:"/api/v1/memory/permanent/frozen", name:"List Frozen", desc:"동결된 기억 목록을 조회합니다." },
    { id:"pm_inherit", method:"POST", path:"/api/v1/memory/permanent/inherit", name:"Inherit PM", desc:"에이전트에게 영구 기억을 상속합니다.",
      body: '{"agent_id":"agent-1","scope":"global"}' },
    { id:"pm_chain", method:"GET", path:"/api/v1/memory/permanent/chain/{agent_id}", name:"Inheritance Chain", desc:"에이전트의 영구 기억 상속 체인을 조회합니다." },
    { id:"pm_priority", method:"GET", path:"/api/v1/memory/permanent/priority/{agent_id}", name:"Priority Resolution", desc:"에이전트의 기억 우선순위를 해결합니다." },
    { id:"pm_alerts", method:"GET", path:"/api/v1/memory/permanent/alerts", name:"Priority Alerts", desc:"현재 scope 위반 경고를 조회합니다." },
  ],

  "Synaptic Bridge": [
    { id:"synaptic_register", method:"POST", path:"/api/v1/memory/synaptic/register", name:"Register Agent", desc:"에이전트를 Synaptic Bridge에 등록합니다.",
      body: '{"agent_id":"agent-1","name":"Research Agent","role":"analyst","subscribed_scopes":["personal","tribal"]}' },
    { id:"synaptic_share", method:"POST", path:"/api/v1/memory/synaptic/share", name:"Share Memory", desc:"기억을 다른 에이전트에게 공유합니다.",
      body: '{"uuid":"memory-uuid","scope":"tribal","shared_by":"agent-1"}' },
    { id:"synaptic_empathy", method:"POST", path:"/api/v1/memory/synaptic/empathy", name:"Empathy Boost", desc:"공유받은 기억을 확인(boost)합니다.",
      body: '{"uuid":"memory-uuid","boosted_by":"agent-2","boost_amount":0.1}' },
    { id:"synaptic_events", method:"GET", path:"/api/v1/memory/synaptic/events", name:"Synaptic Events", desc:"최근 공유/부스트 이벤트를 조회합니다." },
    { id:"synaptic_agents", method:"GET", path:"/api/v1/memory/synaptic/agents", name:"List Agents", desc:"등록된 에이전트 목록을 조회합니다." },
    { id:"synaptic_feed", method:"GET", path:"/api/v1/memory/synaptic/feed/{agent_id}", name:"Agent Feed", desc:"특정 에이전트의 구독 피드를 조회합니다." },
  ],

  "Audit Trail": [
    { id:"audit_history", method:"GET", path:"/api/v1/memory/audit/history/{memory_uuid}", name:"Memory History", desc:"특정 기억의 전체 변경 이력을 조회합니다." },
    { id:"audit_activity", method:"GET", path:"/api/v1/memory/audit/activity", name:"Recent Activity", desc:"시스템 전체의 최근 활동 로그를 조회합니다.",
      query:[{name:"limit",type:"int",desc:"조회 개수"},{name:"change_type",type:"string",desc:"필터: update|decay|freeze|..."}] },
    { id:"audit_stats", method:"GET", path:"/api/v1/memory/audit/stats", name:"Audit Stats", desc:"감사 추적 통계를 집계합니다." },
    { id:"audit_decay_cycles", method:"GET", path:"/api/v1/memory/audit/decay-cycles", name:"Decay Cycles", desc:"과거 감쇠 사이클 기록을 조회합니다." },
    { id:"audit_rollback", method:"POST", path:"/api/v1/memory/audit/rollback", name:"Rollback", desc:"기억을 특정 리비전으로 롤백합니다.",
      body: '{"memory_uuid":"...","revision_id":"..."}' },
  ],

  "Data Products": [
    { id:"data_catalog", method:"GET", path:"/api/analytics/data-product/catalog", name:"Product Catalog", desc:"사용 가능한 모든 데이터 프로덕트와 Import/Export 기능을 나열합니다." },
    { id:"data_rag", method:"GET", path:"/api/analytics/data-product/rag", name:"RAG Corpus", desc:"RAG 파이프라인용 임베딩-레디 코퍼스를 JSON으로 반환합니다.",
      query:[{name:"scope",type:"string",desc:"필터 scope"},{name:"min_salience",type:"float",desc:"최소 salience (기본: 0.3)"}] },
    { id:"data_rag_dl", method:"GET", path:"/api/analytics/data-product/rag/download", name:"RAG Download", desc:"RAG 코퍼스를 JSONL 파일로 다운로드합니다." },
    { id:"data_snapshot", method:"GET", path:"/api/analytics/data-product/snapshot", name:"Knowledge Snapshot", desc:"전체 지식 그래프 스냅샷 (노드, 엣지, 에이전트)을 반환합니다." },
    { id:"data_training", method:"GET", path:"/api/analytics/data-product/training", name:"Training Dataset", desc:"LLM 파인튜닝용 Q&A 데이터셋을 생성합니다." },
    { id:"data_training_dl", method:"GET", path:"/api/analytics/data-product/training/download", name:"Training Download", desc:"Training 데이터셋을 JSONL 파일로 다운로드합니다." },
    { id:"data_manifest", method:"POST", path:"/api/analytics/data-product/manifest", name:"Create Manifest", desc:"버전닝된 지식 패키지(Manifest)를 생성합니다.",
      body: '{"name":"My Knowledge Package","description":"...", "scope":"tribal"}' },
    { id:"data_manifest_list", method:"GET", path:"/api/analytics/data-product/manifest/list", name:"List Manifests", desc:"생성된 Manifest 목록을 조회합니다." },
    { id:"data_csv", method:"GET", path:"/api/analytics/data-product/analytics/csv", name:"Analytics CSV", desc:"대시보드/스프레드시트용 분석 CSV를 다운로드합니다." },
    { id:"data_manifest_import", method:"POST", path:"/api/analytics/data-product/manifest/import", name:"Import Manifest", desc:"Manifest JSON을 Neo4j에 가져옵니다. merge(upsert) 또는 create(신규) 전략 선택 가능.",
      query:[{name:"strategy",type:"string",desc:"merge|create"},{name:"graph_id",type:"string",desc:"타겟 graph_id"}],
      body: '{"manifest_id":"...","entities":[...],"relations":[...],"agents":[...]}' },
    { id:"data_rag_import", method:"POST", path:"/api/analytics/data-product/rag/import", name:"Import RAG Corpus", desc:"JSONL RAG 코퍼스를 Entity 노드로 가져옵니다.",
      query:[{name:"graph_id",type:"string",desc:"타겟 graph_id"},{name:"scope",type:"string",desc:"기본 scope"}],
      body: '{"content":"{\\"id\\":\\"1\\",\\"text\\":\\"...\\",...}\\n{\\"id\\":\\"2\\",\\"text\\":\\"...\\",...}"}' },
    { id:"data_imports", method:"GET", path:"/api/analytics/data-product/imports", name:"Import History", desc:"과거 Import 작업 이력과 통계를 조회합니다." },
  ],

  "Data Ingestion": [
    { id:"ingest_post", method:"POST", path:"/api/v1/ingest", name:"Ingest Text", desc:"텍스트/문서를 지식 그래프에 인제스트합니다.",
      body: '{"content":"분석할 텍스트...","source":"manual","graph_id":"project-1"}' },
    { id:"ingest_batch", method:"POST", path:"/api/v1/ingest/batch", name:"Batch Ingest", desc:"여러 문서를 일괄 인제스트합니다." },
    { id:"ingest_streams", method:"GET", path:"/api/v1/ingest/streams", name:"List Streams", desc:"활성 스트리밍 인제스트 목록을 조회합니다." },
  ],

  "External Gateway": [
    { id:"gw_webhook", method:"POST", path:"/api/v1/ingest/gateway/webhook", name:"Webhook / n8n", desc:"n8n, Zapier 등 외부 워크플로우에서 데이터를 수신합니다." },
    { id:"gw_nifi", method:"POST", path:"/api/v1/ingest/gateway/nifi", name:"NiFi Ingest", desc:"Apache NiFi에서 데이터를 수신합니다." },
    { id:"gw_spark", method:"POST", path:"/api/v1/ingest/gateway/spark", name:"Spark Ingest", desc:"Apache Spark에서 배치 데이터를 수신합니다." },
    { id:"gw_batch", method:"POST", path:"/api/v1/ingest/gateway/batch", name:"Batch Gateway", desc:"범용 배치 인제스트 게이트웨이." },
    { id:"gw_status", method:"GET", path:"/api/v1/ingest/gateway/status", name:"Gateway Status", desc:"게이트웨이 상태와 통계를 조회합니다." },
  ],

  "Knowledge Graph": [
    { id:"graph_project_list", method:"GET", path:"/api/graph/project/list", name:"List Projects", desc:"모든 지식 그래프 프로젝트를 나열합니다." },
    { id:"graph_data", method:"GET", path:"/api/graph/data/{graph_id}", name:"Graph Data", desc:"특정 그래프의 노드/관계 데이터를 조회합니다." },
    { id:"graph_build", method:"POST", path:"/api/graph/build", name:"Build Graph", desc:"텍스트에서 지식 그래프를 구축합니다." },
    { id:"graph_ontology", method:"POST", path:"/api/graph/ontology/generate", name:"Generate Ontology", desc:"텍스트에서 온톨로지를 자동 생성합니다." },
  ],

  "Harness Analytics": [
    { id:"harness_overview", method:"GET", path:"/api/analytics/harness/overview", name:"Harness Overview", desc:"하네스 프로세스 패턴에 대한 전반적인 통계 및 요약을 제공합니다." },
    { id:"harness_list", method:"GET", path:"/api/analytics/harness/list", name:"List Harness Patterns", desc:"추출된 하네스 패턴 목록을 조회합니다.",
      query:[{name:"domain",type:"string",desc:"특정 도메인 필터링"},{name:"agent_id",type:"string",desc:"특정 에이전트 필터링"}] },
    { id:"harness_record", method:"POST", path:"/api/analytics/harness/record", name:"Record Harness", desc:"새로운 하네스 프로세스 패턴 또는 실행 결과를 기록합니다.",
      body: '{"uuid":"...", "domain":"engineering", "trigger":"...", "process_type":"harness", "tool_chain":["t1", "t2"], "conditionals":[{"type":"retry","condition":"Timeout","then_action":"Retry specific step"}], "execution_time_ms":120, "success":true}' },
    { id:"harness_detail", method:"GET", path:"/api/analytics/harness/{uuid}", name:"Harness Detail", desc:"특정 UUID를 가진 하네스 패턴의 상세 정보를 조회합니다.",
      params:[{name:"uuid",type:"string",required:true,desc:"하네스 패턴 UUID"}] },
    { id:"harness_tree", method:"GET", path:"/api/analytics/harness/{uuid}/tree", name:"Execution Tree", desc:"하네스 실행 이력을 계층적 트리(Domain → Workflow → Run → Step)로 조회합니다. 대시보드의 Execution Tree 시각화에 사용됩니다.",
      params:[{name:"uuid",type:"string",required:true,desc:"하네스 패턴 UUID"}] },
    { id:"harness_update", method:"PUT", path:"/api/analytics/harness/{uuid}", name:"Update Pattern", desc:"하네스 패턴의 도메인, 트리거, 태그 등 메타데이터를 수정합니다.",
      params:[{name:"uuid",type:"string",required:true,desc:"하네스 패턴 UUID"}],
      body: '{"domain": "engineering", "trigger": "updated trigger", "tags": ["ci", "deploy"]}' },
    { id:"harness_execute", method:"POST", path:"/api/analytics/harness/{uuid}/execute", name:"Record Execution", desc:"하네스 패턴의 실행 결과를 기록합니다. 성공률, 평균 시간 등 통계가 자동 갱신됩니다.",
      params:[{name:"uuid",type:"string",required:true,desc:"하네스 패턴 UUID"}],
      body: '{"success": true, "execution_time_ms": 1200, "result_summary": "All steps passed"}' },
    { id:"harness_recommend", method:"GET", path:"/api/analytics/harness/recommend", name:"Recommend Harness", desc:"자연어 및 키워드 기반으로 관련된 하네스 패턴을 추천받습니다.",
      query:[{name:"q",type:"string",desc:"검색어 (예: code review)"},{name:"domain",type:"string",desc:"특정 도메인"},{name:"limit",type:"string",desc:"결과 개수(기본값 5)"}] },
    { id:"harness_compare", method:"GET", path:"/api/analytics/harness/{uuid}/compare", name:"Compare Versions", desc:"하네스 패턴의 두 버전 간 tool_chain 차이를 비교합니다.",
      params:[{name:"uuid",type:"string",required:true,desc:"하네스 패턴 UUID"}],
      query:[{name:"v1",type:"int",desc:"비교 대상 버전 1 (기본: 1)"},{name:"v2",type:"int",desc:"비교 대상 버전 2 (기본: latest)"}] },
    { id:"harness_generate", method:"POST", path:"/api/analytics/harness/generate", name:"Generate Harness (AI)", desc:"자연어 설명에서 AI가 자동으로 tool_chain과 conditionals를 생성합니다.",
      body: '{"query": "PR 코드 리뷰 자동화 프로세스", "domain": "engineering"}' },
    { id:"harness_rollback", method:"POST", path:"/api/analytics/harness/{uuid}/rollback", name:"Rollback Harness", desc:"패턴을 이전 버전(tool_chain)으로 수동 롤백하고 히스토리를 갱신합니다.",
      params:[{name:"uuid",type:"string",required:true,desc:"하네스 패턴 UUID"}],
      body: '{"to_version": 1}' },
    { id:"harness_suggest", method:"POST", path:"/api/analytics/harness/{uuid}/suggest_evolution", name:"Suggest Evolution (AI)", desc:"낮은 성공률의 하네스 패턴을 최적화하기 위해, AI(LLM)가 tool_chain의 새로운 진화 형태를 제안합니다.",
      params:[{name:"uuid",type:"string",required:true,desc:"하네스 패턴 UUID"}],
      body: '{"context": "최근 잦은 타임아웃 오류 해결 목적"}' },
    { id:"harness_evolve", method:"POST", path:"/api/analytics/harness/{uuid}/evolve", name:"Evolve Harness", desc:"하네스 패턴의 전체 tool_chain을 새로운 형태로 진화(업데이트)시킵니다.",
      params:[{name:"uuid",type:"string",required:true,desc:"하네스 패턴 UUID"}],
      body: '{"new_tool_chain": [{"tool_name": "...", "tool_type": "..."}], "reason": "Optimized by AI"}' },
  ],

  "Maturity": [
    { id:"maturity_overview", method:"GET", path:"/api/analytics/maturity/overview", name:"Maturity Overview", desc:"지식 성숙도 대시보드 — draft/validated/mature/verified 분포." },
    { id:"maturity_check", method:"POST", path:"/api/analytics/maturity/check-promotions", name:"Check Promotions", desc:"성숙도 승격을 자동 확인합니다." },
    { id:"maturity_rules", method:"GET", path:"/api/analytics/maturity/rules", name:"Maturity Rules", desc:"성숙도 승격 규칙을 조회합니다." },
  ],

  "Authentication & Versioning": [
    { id:"auth_me", method:"GET", path:"/api/auth/me", name:"Auth — Who Am I", desc:"현재 JWT 토큰의 사용자 정보를 반환합니다. Keycloak SSO 연동 시 Bearer 토큰 필요.",
      params:[{name:"Authorization",type:"header",required:true,desc:"Bearer <JWT 토큰>"}] },
    { id:"v1_info", method:"GET", path:"/api/v1/info", name:"API v1 Info", desc:"API v1 버전 정보, 지원 엔드포인트 목록, 서버 상태를 반환합니다." },
  ],

  "Search & Query": [
    { id:"search", method:"POST", path:"/api/v1/search", name:"Search Memories", desc:"지식 그래프에서 기억을 검색합니다. 검색된 기억은 자동으로 Retrieval Boost됩니다.",
      body: '{"query":"TurboQuant quantization","limit":10}' },
    { id:"cypher_query", method:"POST", path:"/api/v1/query", name:"Cypher Query", desc:"Neo4j Cypher 쿼리를 직접 실행합니다 (읽기 전용).",
      body: '{"cypher":"MATCH (e:Entity) WHERE e.salience > 0.8 RETURN e.name, e.salience ORDER BY e.salience DESC LIMIT 10"}' },
    { id:"mcp_endpoint", method:"POST", path:"/api/mcp", name:"MCP JSON-RPC", desc:"MCP JSON-RPC 프록시 엔드포인트. AI 에이전트가 도구를 호출합니다.",
      body: '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"mories_search","arguments":{"query":"test"}}}' },
  ],

  "Security & Governance": [
    { id:"sec_principals_create", method:"POST", path:"/api/admin/security/principals", name:"Register Principal", desc:"새 주체(사용자/에이전트/팀)를 RBAC 시스템에 등록합니다.",
      body: '{"principal_id":"agent:cursor","name":"Cursor Agent","type":"agent","roles":["writer"],"team_id":"dev-team"}',
      params:[{name:"principal_id",type:"string",required:true,desc:"주체 ID (예: user:john, agent:cursor)"},{name:"name",type:"string",required:true,desc:"표시 이름"},{name:"type",type:"string",required:false,desc:"user|agent|team (기본: user)"},{name:"roles",type:"array",required:false,desc:"reader|writer|sharer|admin"},{name:"team_id",type:"string",required:false,desc:"소속 팀 ID"}] },
    { id:"sec_principals_list", method:"GET", path:"/api/admin/security/principals", name:"List Principals", desc:"등록된 모든 주체 목록을 조회합니다.",
      query:[{name:"type",type:"string",desc:"필터: user|agent|team"}] },
    { id:"sec_check", method:"POST", path:"/api/admin/security/check", name:"Check Permission", desc:"주체의 특정 액션/스코프 권한을 확인합니다.",
      body: '{"principal_id":"agent:cursor","action":"store","scope":"tribal","owner":"user:admin"}',
      params:[{name:"principal_id",type:"string",required:true,desc:"주체 ID"},{name:"action",type:"string",required:true,desc:"search|store|share|decay|config 등"},{name:"scope",type:"string",required:false,desc:"personal|tribal|social|global"},{name:"owner",type:"string",required:false,desc:"메모리 소유자 ID"}] },
    { id:"sec_roles", method:"GET", path:"/api/admin/security/roles", name:"Role Matrix", desc:"역할별 허용 액션 매트릭스를 조회합니다." },
    { id:"sec_keys_create", method:"POST", path:"/api/admin/security/keys", name:"Generate API Key", desc:"새 API 액세스 키를 생성합니다. 키는 생성 시 1회만 노출됩니다. 만료일 지정 필수(기본 30일, 0=무제한, 최대 3650일).",
      body: '{"owner_id":"admin","name":"Cursor Agent Key","roles":["writer"],"allowed_scopes":["personal","tribal"],"expires_in_days":30}',
      params:[{name:"owner_id",type:"string",required:true,desc:"키 소유자 ID"},{name:"name",type:"string",required:true,desc:"키 이름"},{name:"roles",type:"array",required:false,desc:"reader|writer|sharer|admin"},{name:"allowed_scopes",type:"array",required:false,desc:"접근 가능 scope 목록"},{name:"expires_in_days",type:"int",required:false,desc:"만료일 (0=무제한, 기본:30, 최대:3650)"},{name:"rate_limit",type:"int",required:false,desc:"분당 요청 제한 (기본: 100)"}] },
    { id:"sec_keys_list", method:"GET", path:"/api/admin/security/keys", name:"List API Keys", desc:"활성 API 키 목록을 조회합니다 (해시만, 원본 키 미노출). 만료일, 사용량 포함.",
      query:[{name:"owner_id",type:"string",desc:"소유자별 필터"}] },
    { id:"sec_keys_verify", method:"POST", path:"/api/admin/security/keys/verify", name:"Verify API Key", desc:"API 키를 검증하고 메타데이터(스코프, 역할, 만료 상태)를 반환합니다. 만료된 키는 401 반환.",
      body: '{"api_key":"mnem_xxxxxxxxxx"}',
      params:[{name:"api_key",type:"string",required:true,desc:"검증할 API 키 원문"}] },
    { id:"sec_keys_revoke", method:"DELETE", path:"/api/admin/security/keys/{key_hash}", name:"Revoke API Key", desc:"API 키를 해시로 즉시 폐기합니다.",
      params:[{name:"key_hash",type:"string",required:true,desc:"키 SHA-256 해시"}] },
    { id:"sec_encrypt", method:"POST", path:"/api/admin/security/encrypt", name:"Encrypt Memory", desc:"특정 기억을 필드 레벨에서 암호화합니다.",
      body: '{"uuid":"memory-uuid","fields":null,"encrypted_by":"admin"}' },
    { id:"sec_decrypt", method:"POST", path:"/api/admin/security/decrypt", name:"Decrypt Memory", desc:"암호화된 기억을 복호화하여 반환합니다 (DB 미변경).",
      body: '{"uuid":"memory-uuid","principal":"admin"}' },
    { id:"sec_encrypt_status", method:"GET", path:"/api/admin/security/encrypt/status", name:"Encryption Status", desc:"전체 암호화 통계를 조회합니다." },
  ],
};

// ──────────────────────────────────────────
// Render sidebar
// ──────────────────────────────────────────

let allEndpoints = [];
let currentEndpoint = null;

function renderSidebar(filter = '') {
  const list = document.getElementById('categoryList');
  list.innerHTML = '';
  allEndpoints = [];
  let totalCount = 0;

  for (const [cat, endpoints] of Object.entries(API_REGISTRY)) {
    const filtered = filter
      ? endpoints.filter(ep =>
          ep.name.toLowerCase().includes(filter) ||
          ep.path.toLowerCase().includes(filter) ||
          ep.desc.toLowerCase().includes(filter))
      : endpoints;

    if (filtered.length === 0) continue;
    totalCount += filtered.length;

    const group = document.createElement('div');
    group.className = 'cat-group';
    group.innerHTML = `
      <div class="cat-header" onclick="this.parentElement.classList.toggle('collapsed')">
        <span>${cat}</span>
        <div style="display:flex;align-items:center;gap:6px">
          <span class="count">${filtered.length}</span>
          <span class="arrow">▼</span>
        </div>
      </div>
      <div class="cat-items">${filtered.map(ep => `
        <div class="endpoint-item" id="item-${ep.id}" onclick="selectEndpoint('${ep.id}')">
          <span class="method-badge method-${ep.method}">${ep.method}</span>
          <span class="endpoint-path">${ep.path.replace('/api/v1/memory/', '/…/').replace('/api/', '/')}</span>
        </div>
      `).join('')}</div>
    `;
    list.appendChild(group);

    allEndpoints.push(...filtered);
  }

  document.getElementById('statEndpoints').textContent = totalCount;
}

// ──────────────────────────────────────────
// Select endpoint
// ──────────────────────────────────────────

function selectEndpoint(id) {
  if (id === 'mcp_tools') {
    document.getElementById('welcomeView').style.display = 'none';
    document.getElementById('detailView').classList.remove('visible');
    document.getElementById('mcpView').classList.add('visible');
    return;
  }

  const ep = allEndpoints.find(e => e.id === id);
  if (!ep) return;
  currentEndpoint = ep;

  // Activate sidebar item
  document.querySelectorAll('.endpoint-item').forEach(el => el.classList.remove('active'));
  const item = document.getElementById(`item-${id}`);
  if (item) item.classList.add('active');

  // Show detail view
  document.getElementById('welcomeView').style.display = 'none';
  document.getElementById('mcpView').classList.remove('visible');
  document.getElementById('detailView').classList.add('visible');

  // Fill header
  const methodEl = document.getElementById('epMethod');
  methodEl.textContent = ep.method;
  methodEl.className = `method-badge method-${ep.method}`;
  document.getElementById('epName').textContent = ep.name;
  document.getElementById('epUrl').textContent = BASE + ep.path;
  document.getElementById('epDesc').textContent = ep.desc;

  // Fill params
  const allParams = [...(ep.params || []), ...(ep.query || [])];
  const paramsSection = document.getElementById('paramsSection');
  if (allParams.length > 0) {
    paramsSection.style.display = '';
    document.getElementById('paramsBody').innerHTML = allParams.map(p => `
      <tr>
        <td><span class="param-name">${p.name}</span></td>
        <td><span class="param-type">${p.type}</span></td>
        <td><span class="${p.required ? 'param-required' : 'param-optional'}">${p.required ? 'Required' : 'Optional'}</span></td>
        <td>${p.desc}</td>
      </tr>
    `).join('');
  } else {
    paramsSection.style.display = 'none';
  }

  // Fill try-it
  document.getElementById('tryUrl').value = BASE + ep.path;

  const queryRow = document.getElementById('queryRow');
  if (ep.query && ep.query.length > 0) {
    queryRow.style.display = '';
    document.getElementById('tryQuery').value = ep.query.map(q => `${q.name}=`).join('&');
  } else {
    queryRow.style.display = 'none';
  }

  const bodyRow = document.getElementById('bodyRow');
  if (ep.method === 'POST' || ep.method === 'PUT') {
    bodyRow.style.display = '';
    document.getElementById('tryBody').value = ep.body || '{}';
  } else {
    bodyRow.style.display = 'none';
  }

  // Reset response
  document.getElementById('responsePanel').classList.remove('visible');
}

// ──────────────────────────────────────────
// Send request
// ──────────────────────────────────────────

async function sendRequest() {
  const btn = document.getElementById('btnSend');
  const label = document.getElementById('btnLabel');
  btn.classList.add('loading');
  label.innerHTML = '<span class="spinner"></span> Loading';

  let url = document.getElementById('tryUrl').value;
  const query = document.getElementById('tryQuery').value;
  if (query) url += '?' + query;

  const method = currentEndpoint?.method || 'GET';
  const body = document.getElementById('tryBody').value;

  const options = {
    method,
    headers: window.moriesApi ? window.moriesApi.getHeaders() : { 'Content-Type': 'application/json' },
  };
  if ((method === 'POST' || method === 'PUT') && body) {
    options.body = body;
  }

  const start = performance.now();
  try {
    const resp = await (window.moriesApi 
      ? window.moriesApi.rawRequest(method, url, body, options) 
      : fetch(url, options));
    const elapsed = Math.round(performance.now() - start);
    const text = await resp.text();

    let formatted;
    try { formatted = JSON.stringify(JSON.parse(text), null, 2); }
    catch { formatted = text; }

    showResponse(resp.status, elapsed, formatted);
  } catch (err) {
    showResponse(0, 0, `Connection failed: ${err.message}\n\nMake sure the server is running at ${BASE}`);
  }

  btn.classList.remove('loading');
  label.textContent = 'Send Request';
}

async function sendMcpRequest() {
  const url = document.getElementById('mcpUrl').value;
  const body = document.getElementById('mcpBody').value;

  const start = performance.now();
  try {
    const resp = await (window.moriesApi
      ? window.moriesApi.rawRequest('POST', url, body)
      : fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body,
        }));
    const elapsed = Math.round(performance.now() - start);
    const text = await resp.text();

    let formatted;
    try { formatted = JSON.stringify(JSON.parse(text), null, 2); }
    catch { formatted = text; }

    const panel = document.getElementById('mcpResponsePanel');
    panel.classList.add('visible');
    document.getElementById('mcpRespStatus').textContent = `${resp.status} ${resp.statusText}`;
    document.getElementById('mcpRespStatus').className = `response-status status-${Math.floor(resp.status/100)}xx`;
    document.getElementById('mcpRespTime').textContent = `${elapsed}ms`;
    document.getElementById('mcpRespBody').textContent = formatted;
  } catch (err) {
    const panel = document.getElementById('mcpResponsePanel');
    panel.classList.add('visible');
    document.getElementById('mcpRespStatus').textContent = 'Error';
    document.getElementById('mcpRespStatus').className = 'response-status status-5xx';
    document.getElementById('mcpRespBody').textContent = `Connection failed: ${err.message}`;
  }
}

function showResponse(status, elapsed, body) {
  const panel = document.getElementById('responsePanel');
  panel.classList.add('visible');
  document.getElementById('respStatus').textContent = `${status} ${status >= 200 && status < 300 ? 'OK' : status >= 400 ? 'Error' : ''}`;
  document.getElementById('respStatus').className = `response-status status-${Math.floor(status/100)}xx`;
  document.getElementById('respTime').textContent = `${elapsed}ms`;
  document.getElementById('respBody').textContent = body;
}

function copyUrl() {
  const url = document.getElementById('epUrl').textContent;
  navigator.clipboard.writeText(url);
  const btn = event.target;
  btn.textContent = '✅ Copied!';
  btn.classList.add('copied');
  setTimeout(() => { btn.textContent = '📋 Copy'; btn.classList.remove('copied'); }, 1500);
}

// ──────────────────────────────────────────
// Health check
// ──────────────────────────────────────────

async function checkConnection() {
  try {
    const options = { signal: AbortSignal.timeout(3000) };
    const resp = await (window.moriesApi 
      ? window.moriesApi.rawRequest('GET', BASE + '/api/health', null, options) 
      : fetch(BASE + '/api/health', options));
    const data = await resp.json();
    document.getElementById('connDot').className = 'conn-dot online';
    document.getElementById('connLabel').textContent = `Connected — Neo4j: ${data.neo4j?.status || 'unknown'}, ${data.neo4j?.node_count || 0} nodes`;
  } catch {
    document.getElementById('connDot').className = 'conn-dot offline';
    document.getElementById('connLabel').textContent = 'Disconnected — start server first';
  }
}

// ──────────────────────────────────────────
// Keyboard shortcut
// ──────────────────────────────────────────

document.addEventListener('keydown', (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
    e.preventDefault();
    document.getElementById('searchInput').focus();
  }
});

document.getElementById('searchInput').addEventListener('input', (e) => {
  renderSidebar(e.target.value.toLowerCase());
});

// ──────────────────────────────────────────
// Init
// ──────────────────────────────────────────

renderSidebar();
// Set MCP URL dynamically
const mcpUrlEl = document.getElementById('mcpUrl');
if (mcpUrlEl && !mcpUrlEl.value) mcpUrlEl.value = BASE + '/api/mcp';
checkConnection();
setInterval(checkConnection, 15000);
