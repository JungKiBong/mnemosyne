import logging
from typing import List, Dict, Any, Optional

from app.storage.graph_storage import GraphStorage
from app.storage.neo4j_storage import Neo4jStorage
from app.storage.supermemory_client import SupermemoryClientWrapper
from app.resilience.circuit_breaker import CircuitBreaker, CircuitOpenError
from app.resilience.outbox_worker import OutboxWorker, OutboxEntry

logger = logging.getLogger(__name__)

class HybridStorage(GraphStorage):
    """
    Hybrid GraphStorage implementation combining Neo4j (Source of Truth) and Supermemory (Asynchronous cognitive memory).
    """
    
    def __init__(self, neo4j_storage: Neo4jStorage, sm_client: SupermemoryClientWrapper = None):
        if neo4j_storage is None:
            raise ValueError("Neo4jStorage is required as the Source of Truth.")
            
        self.neo4j = neo4j_storage
        self.sm = sm_client or SupermemoryClientWrapper()
        
        # Resilience components
        self.cb = CircuitBreaker(failure_threshold=5, recovery_timeout=30)
        self.outbox = OutboxWorker(self.sm, self.cb)
        self.outbox.start()
        
    def close(self):
        """Shutdown underlying storage and outbox worker."""
        self.neo4j.close()
        self.outbox.stop()

    def health_check(self) -> dict:
        """Combine health checking for Neo4j and SM."""
        neo4j_health = self.neo4j.health_check()
        return {
            "neo4j": neo4j_health,
            "supermemory": {
                "circuit_state": self.cb.state.value,
                "dead_letters": len(self.outbox.get_dead_letters()),
                "sm_available": self.sm.client is not None
            }
        }
        
    # ==========================================
    # Graph Control & Ingestion
    # ==========================================

    def clear_graph(self, graph_id: str):
        """Clear graph operations run synchronously on Neo4j."""
        self.neo4j.clear_graph(graph_id)
        # Note: Depending on Supermemory capabilities, we might want to schedule an outbox entry to clear items by container_tag

    def delete_graph(self, graph_id: str):
        """Delete graph operations run synchronously on Neo4j."""
        self.neo4j.delete_graph(graph_id)
        # In the future: bulk delete by container_tag on SM

    def add_text(self, graph_id: str, text: str) -> str:
        """
        Neo4j is Source of Truth (Sync). Supermemory is eventually consistent (Async Outbox).
        """
        episode_id = self.neo4j.add_text(graph_id, text)
        
        # Determine if text is from an agent by applying heuristics
        agent_id = self._extract_agent_tag(text)
        metadata = {"episode_id": episode_id}
        if agent_id:
            metadata["agent_id"] = agent_id
            
        # Push to outbox for async SM update
        self.outbox.enqueue(OutboxEntry(
            action="add",
            graph_id=graph_id,
            text=text,
            metadata=metadata
        ))
        
        return episode_id

    def add_text_batch(self, graph_id: str, texts: List[str]) -> List[str]:
        episode_ids = self.neo4j.add_text_batch(graph_id, texts)
        
        for text, ep_id in zip(texts, episode_ids):
            agent_id = self._extract_agent_tag(text)
            metadata = {"episode_id": ep_id}
            if agent_id:
                metadata["agent_id"] = agent_id
                
            self.outbox.enqueue(OutboxEntry(
                action="add",
                graph_id=graph_id,
                text=text,
                metadata=metadata
            ))

        return episode_ids

    def verify_ontology(self, graph_id: str) -> dict:
        return self.neo4j.verify_ontology(graph_id)

    # ==========================================
    # Search & Retrieval
    # ==========================================

    def search(self, graph_id: str, query: str, limit: int = 10, search_scope: str = "edges") -> List[Dict]:
        """
        Hybrid search combining Supermemory results and Neo4j BM25+Vector graph results.
        """
        sm_results = []
        try:
            # Fallback wrapper internally handled, but we use Circuit Breaker
            if self.sm.client:
                sm_results = self.cb.call(
                    self.sm.search_memories,
                    query=query,
                    container_tag=graph_id,
                    limit=limit
                )
        except (CircuitOpenError, Exception) as e:
            logger.warning(f"SM search failed -> Fallback to Neo4j only: {e}")
            
        neo4j_results = self.neo4j.search(graph_id, query, limit, search_scope)
        
        return self._merge_search_results(sm_results, neo4j_results, limit)

    def get_context_for_simulation(self, graph_id: str, persona: str, environment: str = None) -> List[Dict]:
        return self.neo4j.get_context_for_simulation(graph_id, persona, environment)

    def get_agent_profile(self, graph_id: str, agent_id: str) -> str:
        """
        Attempt to fetch static/dynamic profile from Supermemory first.
        If unavailable or circuit open, fallback to Neo4j.
        """
        try:
            if self.sm.client:
                # Use containerTag per agent or global graph depending on architecture preference
                # Here we assume agent records are tagged under graph_id, and maybe filtered by metadata...
                # For SM profile, we need a specific tag for an agent.
                agent_tag = f"{graph_id}_{agent_id}"
                sm_profile = self.cb.call(self.sm.get_profile, container_tag=agent_tag)
                
                # Format the returned Dict as string similar to old behavior
                if sm_profile:
                    return f"[Supermemory Profile]\nStatic: {sm_profile.get('static')}\nDynamic: {sm_profile.get('dynamic')}"
        except Exception as e:
            logger.debug(f"SM Profile fetch failed for {agent_id}, falling back to Neo4j: {e}")
            
        return self.neo4j.get_agent_profile(graph_id, agent_id)

    # ==========================================
    # Private Helpers
    # ==========================================

    def _extract_agent_tag(self, text: str) -> Optional[str]:
        """
        Extract agent identifier from string text using heuristics.
        E.g., "Agent test_user_123 liked a post" -> "test_user_123"
        """
        if text.startswith("Agent "):
            parts = text.split(" ", 2)
            if len(parts) >= 2:
                return parts[1]
        elif text.startswith("User "):
            parts = text.split(" ", 2)
            if len(parts) >= 2:
                return parts[1]
        return None

    def _merge_search_results(self, sm_data: List[Any], neo4j_data: List[Dict], limit: int) -> List[Dict]:
        """Merge SM and Neo4j documents, deduplicating appropriately."""
        merged = []
        seen = set()
        
        # Assume SM returns list of strings or dicts
        for item in sm_data:
            content = item.get("content", str(item)) if isinstance(item, dict) else str(item)
            if content not in seen:
                merged.append({"content": content, "source": "supermemory"})
                seen.add(content)
                if len(merged) == limit:
                    break
                    
        for item in neo4j_data:
            if len(merged) == limit:
                break
            content = item.get("content", str(item))
            if content not in seen:
                merged.append(item)
                seen.add(content)
                
        return merged

    # The remaining methods redirect purely to Neo4j for base structure
    def get_all_nodes(self, graph_id: str, limit: int = 100) -> List[Dict]:
        return self.neo4j.get_all_nodes(graph_id, limit)

    def get_all_edges(self, graph_id: str, limit: int = 100) -> List[Dict]:
        return self.neo4j.get_all_edges(graph_id, limit)

    def get_node_by_id(self, graph_id: str, node_id: str) -> Dict:
        return self.neo4j.get_node_by_id(graph_id, node_id)

    def get_edge_by_id(self, graph_id: str, edge_id: str) -> Dict:
        return self.neo4j.get_edge_by_id(graph_id, edge_id)

    def get_graph_summary(self, graph_id: str) -> Dict:
        return self.neo4j.get_graph_summary(graph_id)
