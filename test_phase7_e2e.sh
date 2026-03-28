#!/bin/bash
# Phase 7 Cognitive Memory E2E Test
set -e
BASE="http://localhost:5001"

echo "=== Phase 7 Cognitive Memory E2E Test ==="
echo ""

echo "1️⃣  STM 추가 (4건)"
ID1=$(curl -s -X POST "$BASE/api/memory/stm/add" \
  -H "Content-Type: application/json" \
  -d '{"content":"NVIDIA가 H200 GPU를 대량 출하 시작","source":"Bloomberg","ttl":86400}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "   [1] $ID1"

ID2=$(curl -s -X POST "$BASE/api/memory/stm/add" \
  -H "Content-Type: application/json" \
  -d '{"content":"테슬라 중국 공장 2배 확장 발표","source":"Reuters","ttl":86400}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "   [2] $ID2"

ID3=$(curl -s -X POST "$BASE/api/memory/stm/add" \
  -H "Content-Type: application/json" \
  -d '{"content":"한국은행 기준금리 0.25%p 인하 결정","source":"한국은행","ttl":43200}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "   [3] $ID3"

ID4=$(curl -s -X POST "$BASE/api/memory/stm/add" \
  -H "Content-Type: application/json" \
  -d '{"content":"중요하지 않은 테스트 메모","source":"test","ttl":3600}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "   [4] $ID4"

echo ""
echo "2️⃣  STM 목록 확인"
curl -s "$BASE/api/memory/stm/list" | python3 -c "
import sys,json
items = json.load(sys.stdin)
print(f'   총 {len(items)}개 STM 아이템')
for i in items:
    print(f'     [{i[\"id\"][:8]}] {i[\"source\"]}: {i[\"content\"][:40]}...')
"

echo ""
echo "3️⃣  STM 평가 (salience 부여)"
curl -s -X POST "$BASE/api/memory/stm/evaluate" \
  -H "Content-Type: application/json" \
  -d "{\"id\":\"$ID1\",\"salience\":0.85}" | python3 -c "
import sys,json; d=json.load(sys.stdin)
print(f'   NVIDIA 기억: salience={d.get(\"salience\")}, result={d.get(\"evaluation_result\")}')
"

curl -s -X POST "$BASE/api/memory/stm/evaluate" \
  -H "Content-Type: application/json" \
  -d "{\"id\":\"$ID4\",\"salience\":0.15}" | python3 -c "
import sys,json; d=json.load(sys.stdin)
print(f'   테스트 메모: salience={d.get(\"salience\")}, result={d.get(\"evaluation_result\")}')
"

echo ""
echo "4️⃣  메모리 개요 (Overview)"
curl -s "$BASE/api/memory/overview" | python3 -c "
import sys,json
d = json.load(sys.stdin)
print(f'   STM: {d[\"stm\"][\"count\"]}개')
print(f'   LTM: {d[\"ltm\"][\"entity_count\"]} entities, {d[\"ltm\"][\"relation_count\"]} relations')
print(f'   Avg Salience: {d[\"ltm\"][\"avg_salience\"]}')
print(f'   Archived: {d[\"archived_count\"]}')
print(f'   Config: decay_rate={d[\"config\"][\"decay_rate\"]}')
"

echo ""
echo "5️⃣  망각 시뮬레이션 (dry_run)"
curl -s -X POST "$BASE/api/memory/decay" \
  -H "Content-Type: application/json" \
  -d '{"dry_run":true}' | python3 -c "
import sys,json
d = json.load(sys.stdin)
print(f'   처리: {d[\"total_processed\"]} | 감쇠: {d[\"decayed\"]} | 아카이브: {d[\"archived\"]} | 경고: {d[\"warned\"]}')
"

echo ""
echo "6️⃣  Salience 강화 (boost)"
curl -s -X POST "$BASE/api/memory/boost" \
  -H "Content-Type: application/json" \
  -d '{"entity_names":["NVIDIA","H200"]}' | python3 -c "
import sys,json; d=json.load(sys.stdin)
print(f'   강화 결과: boosted={d.get(\"boosted\",0)}, errors={d.get(\"errors\",[])}')
"

echo ""
echo "7️⃣  파라미터 설정 변경"
curl -s -X POST "$BASE/api/memory/config" \
  -H "Content-Type: application/json" \
  -d '{"decay_rate":0.92}' | python3 -c "
import sys,json; d=json.load(sys.stdin)
print(f'   새 decay_rate: {d.get(\"decay_rate\")}')
print(f'   retrieval_boost: {d.get(\"retrieval_boost\")}')
"

echo ""
echo "8️⃣  파라미터 복원"
curl -s -X POST "$BASE/api/memory/config" \
  -H "Content-Type: application/json" \
  -d '{"decay_rate":0.95}' > /dev/null

echo ""
echo "✅ Phase 7 E2E Test Complete!"
