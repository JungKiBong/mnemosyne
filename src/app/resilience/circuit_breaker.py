from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Any
import threading
import logging

logger = logging.getLogger(__name__)

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitOpenError(Exception):
    """Exception raised when the circuit breaker is open."""
    pass

@dataclass
class CircuitBreaker:
    failure_threshold: int = 5
    recovery_timeout: int = 30  # seconds
    
    state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    fail_count: int = field(default=0, init=False)
    last_failure_time: datetime = field(default=None, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        with self._lock:
            if self.state == CircuitState.OPEN:
                if self._should_try_reset():
                    self.state = CircuitState.HALF_OPEN
                    logger.info("Circuit Breaker -> HALF_OPEN (testing recovery)")
                else:
                    raise CircuitOpenError(
                        f"Circuit is OPEN. Retry after {self.recovery_timeout}s"
                    )
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
    
    def _on_success(self):
        with self._lock:
            self.fail_count = 0
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.CLOSED
                logger.info("Circuit Breaker -> CLOSED (recovered)")
    
    def _on_failure(self):
        with self._lock:
            self.fail_count += 1
            self.last_failure_time = datetime.now()
            if self.fail_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                logger.warning(
                    f"Circuit Breaker -> OPEN (failures: {self.fail_count})"
                )
    
    def _should_try_reset(self) -> bool:
        if self.last_failure_time is None:
            return True
        return datetime.now() - self.last_failure_time > timedelta(
            seconds=self.recovery_timeout
        )
