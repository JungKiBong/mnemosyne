import logging
from typing import Dict, Any

from src.app.storage.memory_manager import MemoryManager

logger = logging.getLogger(__name__)

class AnalysisAgent:
    """
    중앙 분석 에이전트.
    엣지에서 발생한 STM 이벤트들을 검토하여 중요한 이벤트를 LTM으로 승격합니다.
    """
    def __init__(self, agent_id: str, memory_manager: MemoryManager, graph_id: str):
        self.agent_id = agent_id
        self.memory_manager = memory_manager
        self.graph_id = graph_id

    def process_edge_events(self, stm_id: str):
        """엣지로부터 Synaptic Share된 STM의 식별자를 받아 분석 및 LTM 승격"""
        try:
            logger.info(f"[{self.agent_id}] 엣지 이벤트(ID: {stm_id}) 분석 시작...")
            
            # STM 검증 (evaluate)
            eval_result = self.memory_manager.stm_evaluate(stm_id, salience=0.85)
            logger.info(f"[{self.agent_id}] 평가 결과: {eval_result['evaluation_result']}")
            
            if eval_result['evaluation_result'] == 'promote':
                promote_result = self.memory_manager.stm_promote(stm_id, graph_id=self.graph_id)
                if 'status' in promote_result and promote_result['status'] == 'promoted':
                    ltm_uuid = promote_result.get('ltm_uuid')
                    logger.info(f"[{self.agent_id}] LTM 승격 완료. (Neo4j UUID: {ltm_uuid})")
                    return ltm_uuid
                else:
                    logger.warning(f"[{self.agent_id}] 승격 실패: {promote_result}")
            
            return None
        except Exception as e:
            logger.error(f"[{self.agent_id}] 엣지 이벤트 프로세싱 에러: {e}")
            return None
