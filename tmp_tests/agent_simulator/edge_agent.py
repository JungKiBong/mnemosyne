import logging
from typing import Dict, Any

# Mories 내부 모듈 참조 (시뮬레이터 목적)
from src.app.storage.memory_manager import MemoryManager

logger = logging.getLogger(__name__)

class EdgeAgent:
    """
    물리적 AI 및 엣지 디바이스 시뮬레이터.
    센서 데이터를 감지하여 단기 기억(STM)으로 Mories에 전달합니다.
    """
    def __init__(self, agent_id: str, memory_manager: MemoryManager):
        self.agent_id = agent_id
        self.memory_manager = memory_manager
        
    def detect_event(self, sensor_type: str, raw_value: float, threshold: float) -> str | None:
        """이벤트 감지 및 STM 추가"""
        try:
            if raw_value > threshold:
                msg = f"Alert: {sensor_type} spiked to {raw_value} (threshold: {threshold})"
                logger.info(f"[{self.agent_id}] 감지: {msg}")
                
                # STM 기록 (mories_stm_add의 역할을 MemoryManager로 에뮬레이션)
                item = self.memory_manager.stm_add(
                    content=msg,
                    source=self.agent_id,
                    metadata={"sensor": sensor_type, "value": raw_value, "alert": True}
                )
                logger.info(f"[{self.agent_id}] STM 기록 완료 (ID: {item.id})")
                
                # 시냅틱 브릿지를 통한 공유 시뮬레이션 (여기서는 UUID 반환으로 갈음)
                return item.id
            return None
        except Exception as e:
            logger.error(f"[{self.agent_id}] 센서 이벤트 처리 중 오류 발생: {e}")
            return None
