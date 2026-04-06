import time
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional

@dataclass
class STMItem:
    """A short-term memory item waiting for consolidation."""
    id: str
    content: str
    source: str
    created_at: float  # Unix timestamp
    ttl: float  # seconds before auto-forget
    salience: float = 0.5  # Initial salience (0~1)
    metadata: Dict[str, Any] = field(default_factory=dict)
    evaluated: bool = False
    evaluation_result: Optional[str] = None  # 'promote' | 'discard' | 'pending_hitl'

    @property
    def is_expired(self) -> bool:
        return time.time() > self.created_at + self.ttl

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at

    def to_dict(self) -> dict:
        d = asdict(self)
        d['is_expired'] = self.is_expired
        d['age_seconds'] = self.age_seconds
        d['age_human'] = self._format_age(self.age_seconds)
        return d

    @staticmethod
    def _format_age(seconds: float) -> str:
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            return f"{int(seconds / 60)}m"
        elif seconds < 86400:
            return f"{int(seconds / 3600)}h"
        return f"{int(seconds / 86400)}d"


@dataclass
class MemoryConfig:
    """Configuration for cognitive memory parameters."""
    # STM settings
    stm_default_ttl: float = 86400.0  # 24 hours
    stm_max_items: int = 100

    # Decay settings
    decay_rate: float = 0.95  # Daily decay multiplier (salience *= 0.95^days)
    decay_archive_threshold: float = 0.05  # Below this = archived
    decay_warn_threshold: float = 0.2  # Below this = warn

    # Reinforcement settings
    retrieval_boost: float = 0.05  # Salience boost per retrieval
    max_salience: float = 1.0
    min_salience: float = 0.0

    # Consolidation settings
    auto_promote_threshold: float = 0.7  # Auto-promote STM → LTM
    auto_discard_threshold: float = 0.3  # Auto-discard from STM
    # Between 0.3 and 0.7 → needs HITL review

    def to_dict(self) -> dict:
        return asdict(self)
