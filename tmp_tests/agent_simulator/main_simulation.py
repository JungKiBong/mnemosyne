import os
import sys
import logging
import uuid
import time
from neo4j import GraphDatabase

# 프로젝트 루트 경로 추가 (sys.path)
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../../"))
sys.path.insert(0, project_root)

from src.app.config import Config
from src.app.storage.memory_manager import MemoryManager, MemoryConfig
from edge_agent import EdgeAgent
from analysis_agent import AnalysisAgent
from director_agent import DirectorAgent

# 로깅 설정 (안정성 규칙)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
logger = logging.getLogger("SimulationMain")

def run_simulation():
    logger.info("자율 연구소 시뮬레이션 시작...")
    
    # 1. Neo4j 드라이버 초기화
    driver = GraphDatabase.driver(Config.NEO4J_URI, auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD))
    
    # 격리된 테스트 그래프 ID 생성
    test_graph_id = f"auto_lab_sim_{uuid.uuid4().hex[:8]}"
    
    memory_config = MemoryConfig(stm_default_ttl=10.0) # 테스트용 10초 TTL
    memory_manager = MemoryManager.get_instance(driver=driver, config=memory_config)
    
    try:
        # 실험을 위한 그래프 노드 세팅
        with driver.session() as session:
            session.run("MERGE (g:Graph {uuid: $uuid, name: 'Simulation Lab'})", uuid=test_graph_id)
            
        edge_agent = EdgeAgent("edge_sensor_1", memory_manager)
        analysis_agent = AnalysisAgent("brain_analyzer", memory_manager, test_graph_id)
        director_agent = DirectorAgent("research_director", driver)

        # Step 1: Edge Agent 가 환경 감지 (온도 스파이크)
        logger.info("==== Step 1. Edge Agent Sensing ====")
        stm_id = edge_agent.detect_event(sensor_type="Reactor-Temp", raw_value=115.5, threshold=100.0)
        
        if not stm_id:
            logger.error("엣지 에이전트 STM 기록 실패. 시뮬레이션 중단.")
            return

        time.sleep(1) # 시뮬레이션 딜레이

        # Step 2: Analysis Agent 가 STM 분석 후 LTM 승격
        logger.info("==== Step 2. Analysis Agent Evaluation ====")
        ltm_uuid = analysis_agent.process_edge_events(stm_id=stm_id)

        if not ltm_uuid:
            logger.error("분석 에이전트 LTM 승격 실패. 시뮬레이션 중단.")
            return

        time.sleep(1)

        # Step 3: Director Agent 가 LTM 조회 및 Hindsight Synthesis 발행
        logger.info("==== Step 3. Director Agent Synthesis ====")
        records = director_agent.review_historical_data(graph_id=test_graph_id)
        
        if records:
            synthesis_id = director_agent.perform_hindsight_synthesis([ltm_uuid], records, graph_id=test_graph_id)
            if synthesis_id:
                logger.info(f"오토노모스 연구소 워크플로우 성공! 최종 도출 노드: {synthesis_id}")
            else:
                logger.warning("Synthesis 노드 생성 실패.")
        else:
            logger.warning("과거 데이터를 조회하지 못했습니다.")

    except Exception as e:
        logger.error(f"시뮬레이션 구동 중 예외 발생: {e}")
    finally:
        # 자원 정리
        logger.info("테스트 데이터 정리 및 드라이버 반환...")
        with driver.session() as session:
            # 테스트 그래프와 연관된 노드들 모두 정리 (안정성 규칙 5 : try-finally)
            session.run("""
            MATCH (g:Graph {uuid: $uuid})
            OPTIONAL MATCH (g)-[:CONTAINS]->(e)
            OPTIONAL MATCH (e)<-[:SYNTHESIZED_FROM]-(s)
            DETACH DELETE s, e, g
            """, uuid=test_graph_id)
            
        memory_manager.close()
        driver.close()
        logger.info("시뮬레이션 종료.")

if __name__ == "__main__":
    run_simulation()
