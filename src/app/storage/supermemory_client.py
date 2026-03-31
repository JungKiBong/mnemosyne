import os
import logging
from typing import Dict, List, Any

# Lazy import: supermemory SDK is optional (not available in airgap environments)
try:
    from supermemory import Supermemory
    _SM_AVAILABLE = True
except ImportError:
    Supermemory = None  # type: ignore
    _SM_AVAILABLE = False

logger = logging.getLogger(__name__)

class SupermemoryClientWrapper:
    """Wrapper around Supermemory SDK to handle initialization and basic CRUD.
    
    In airgap environments where the supermemory package is not installed,
    all methods will raise RuntimeError and the system falls back to
    Neo4j-only operation via HybridStorage's circuit breaker.
    """
    SM_AVAILABLE = _SM_AVAILABLE

    def __init__(self, api_key: str = None):
        if not _SM_AVAILABLE:
            logger.info("Supermemory SDK not installed — running in Neo4j-only mode (airgap safe)")
            self.client = None
            self.api_key = None
            return

        self.api_key = api_key or os.environ.get("SUPERMEMORY_API_KEY", "placeholder")
        if not self.api_key or self.api_key == "placeholder":
            logger.warning("SUPERMEMORY_API_KEY is not set or placeholder. SDK calls will likely fail.")
        
        try:
            self.client = Supermemory(api_key=self.api_key)
            logger.info("Supermemory SDK client initialized.")
        except Exception as e:
            logger.error(f"Failed to initialize Supermemory SDK: {e}")
            self.client = None

    def add(self, content: str, container_tag: str, metadata: Dict = None) -> Dict:
        """Add memory to supermemory"""
        if not self.client:
            raise RuntimeError("Supermemory client not initialized")
        # Ensure metadata is passed if required by the SDK signature
        return self.client.add(content=content, container_tag=container_tag, metadata=metadata)

    def delete(self, memory_id: str) -> bool:
        """Delete a memory from supermemory"""
        if not self.client:
            raise RuntimeError("Supermemory client not initialized")
        # Wait, the SDK uses internal structure?
        return self.client.delete(memory_id)

    def search_memories(self, query: str, container_tag: str, limit: int = 10, search_mode: str = "hybrid") -> List[Dict]:
        """Search memories"""
        if not self.client:
            raise RuntimeError("Supermemory client not initialized")
        # According to the dir() output, it's client.search.memories()
        try:
            results = self.client.search.memories(q=query, container_tag=container_tag, search_mode=search_mode)
            # Limit the output if SDK does not natively support limit parameter yet
            return results[:limit] if isinstance(results, list) else results
        except Exception as e:
            logger.error(f"Search memories failed: {e}")
            raise e

    def get_profile(self, container_tag: str) -> Dict:
        """Get agent profile"""
        if not self.client:
            raise RuntimeError("Supermemory client not initialized")
        try:
            return self.client.profile(container_tag=container_tag)
        except Exception as e:
            logger.error(f"Get profile failed: {e}")
            raise e
