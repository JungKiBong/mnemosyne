import logging
from typing import Dict, Any

from neo4j import GraphDatabase

logger = logging.getLogger(__name__)

class DirectorAgent:
    """
    연구 디렉터 에이전트.
    과거 LTM 기록들을 조회하고 큰 틀에서의 인사이트(Synthesis)를 도출 및 실험 파라미터 업데이트를 결의합니다.
    """
    def __init__(self, agent_id: str, driver: GraphDatabase.driver):
        self.agent_id = agent_id
        self.driver = driver

    def review_historical_data(self, graph_id: str) -> list:
        """LTM을 쿼리하여 최근 이상 트렌드를 파악 (mories_graph_query 에뮬레이터)"""
        try:
            logger.info(f"[{self.agent_id}] LTM 데이터 기반 사후 분석 시작...")
            cypher = """
            MATCH (e:Entity:Memory {graph_id: $graph_id})
            WHERE e.source CONTAINS 'edge_sensor'
            RETURN e.uuid AS id, e.description AS desc, e.salience AS salience
            ORDER BY e.created_at DESC
            LIMIT 10
            """
            
            with self.driver.session() as session:
                results = session.run(cypher, graph_id=graph_id)
                records = [r.data() for r in results]
                
            logger.info(f"[{self.agent_id}] 과거 LTM 데이터 {len(records)}건 확보 완료.")
            return records
        except Exception as e:
            logger.error(f"[{self.agent_id}] 사후 분석 중 오류: {e}")
            return []

    def perform_hindsight_synthesis(self, ltm_uuids: list, ltm_records: list, graph_id: str):
        """복수의 LTM으로부터 Hindsight Synthesis 실행 (Dify 연동)"""
        import requests
        import os
        try:
            logger.info(f"[{self.agent_id}] Dify AI(100.75.95.45) 기반 Hindsight Synthesis 수행 (대상: {ltm_uuids})")
            
            # 1. Dify API 연동을 통한 분석 요청 (Director 에뮬레이션 ➡️ 실제 LLM 호출)
            dify_url = "http://100.75.95.45:5001/v1/chat-messages"
            dify_api_key = "app-4ElPP6OBpbEdCINmPDBrSnxq"  # 임시 하드코딩 (또는 os.environ 사용)
            
            payload = {
                "inputs": {},
                "query": f"다음의 엣지 센서 LTM 기록을 분석하여 핵심 Insight(통찰)를 1문장으로 요약해줘.\n기록: {ltm_records}",
                "response_mode": "streaming",
                "user": self.agent_id
            }
            
            headers = {
                "Authorization": f"Bearer {dify_api_key}",
                "Content-Type": "application/json"
            }
            
            ai_insight = "Insight: (Dify API 연동 실패/기본값 사용) Catalyst reaction correlates with temperature spike"
            
            try:
                # Agent Chat App requires streaming mode
                res = requests.post(dify_url, json=payload, headers=headers, timeout=15, stream=True)
                if res.status_code == 200:
                    import json
                    full_answer = ""
                    for line in res.iter_lines():
                        if line:
                            line_str = line.decode('utf-8')
                            if line_str.startswith('data: '):
                                data_str = line_str[6:]
                                try:
                                    data_json = json.loads(data_str)
                                    if data_json.get('event') == 'message':
                                        full_answer += data_json.get('answer', '')
                                except json.JSONDecodeError:
                                    pass
                    if full_answer:
                        ai_insight = full_answer.strip()
                    logger.info(f"[{self.agent_id}] Dify AI 응답 성공: {ai_insight}")
                else:
                    logger.warning(f"[{self.agent_id}] Dify AI 오류 ({res.status_code}): {res.text[:100]}")
            except Exception as e:
                logger.error(f"[{self.agent_id}] Dify API Network Error: {e}")
            
            # 2. Neo4j에 Synthesis 노드 생성
            with self.driver.session() as session:
                new_insight_cypher = """
                MATCH (g:Graph {uuid: $graph_id})
                CREATE (s:Entity:Memory:Synthesis {
                    uuid: randomUUID(),
                    name: $insight_text,
                    salience: 0.95,
                    created_at: datetime()
                })
                MERGE (g)-[:CONTAINS]->(s)
                WITH s
                UNWIND $sources AS src_uuid
                MATCH (e:Entity {uuid: src_uuid})
                MERGE (s)-[:SYNTHESIZED_FROM]->(e)
                RETURN s.uuid AS id
                """
                res = session.run(new_insight_cypher, graph_id=graph_id, sources=ltm_uuids, insight_text=ai_insight).single()

            if res:
                logger.info(f"[{self.agent_id}] 새로운 통찰력(Synthesis) 노드 생성 완료: {res['id']}")
                return res['id']
            return None
        except Exception as e:
            logger.error(f"[{self.agent_id}] Synthesis 도출 에러: {e}")
            return None
