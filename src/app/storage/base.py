"""
Base Interfaces for Storage Backends
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any

from .models import STMItem

class BaseSTMBackend(ABC):
    @abstractmethod
    def add(self, item: Any) -> None:
        pass

    @abstractmethod
    def list_all(self) -> List[dict]:
        pass

    @abstractmethod
    def get(self, item_id: str) -> Optional[dict]:
        pass

    @abstractmethod
    def evaluate(self, item_id: str, salience: float, config: Any) -> Optional[dict]:
        pass

    @abstractmethod
    def discard(self, item_id: str) -> bool:
        pass

    @abstractmethod
    def pop(self, item_id: str) -> Optional[Any]:
        pass

    @abstractmethod
    def cleanup(self) -> int:
        pass

class BaseLTMBackend(ABC):
    @abstractmethod
    def promote(self, item: Any, graph_id: str = "") -> dict:
        pass

    @abstractmethod
    def run_decay(self, config: Any, dry_run: bool = False) -> dict:
        pass

    @abstractmethod
    def boost_on_retrieval(self, uuids: List[str], config: Any) -> int:
        pass

    @abstractmethod
    def manual_boost(self, uuid: str, amount: float, config: Any) -> dict:
        pass

    @abstractmethod
    def get_overview(self) -> dict:
        pass

    @abstractmethod
    def ensure_schema(self) -> None:
        pass
