"""
Tool Memory Index — per-tool execution statistics persisted to SQLite.

Tracks success rate, latency, cost, and reliability for each tool/executor,
enabling memory-guided tool selection for autonomous planning.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ToolMemoryRecord:
    """Aggregated statistics for a single tool."""
    tool_name: str
    tool_type: str                   # "code", "api_call", "webhook", "container_exec", etc.
    total_executions: int = 0
    success_count: int = 0
    fail_count: int = 0
    avg_latency_ms: float = 0.0
    total_cost_usd: float = 0.0
    last_error: Optional[str] = None
    last_used: Optional[str] = None
    domains_used: List[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.total_executions == 0:
            return 0.0
        return self.success_count / self.total_executions

    @property
    def reliability_score(self) -> float:
        """
        Composite reliability: weighted blend of success rate and recency.
        Score: 0.0 ~ 1.0
        """
        if self.total_executions == 0:
            return 0.0
        sr = self.success_rate
        # Penalize tools with very few executions
        volume_factor = min(self.total_executions / 10, 1.0)
        return sr * 0.7 + volume_factor * 0.3


@dataclass
class ToolExecution:
    """A single tool execution event."""
    tool_name: str
    tool_type: str
    success: bool
    elapsed_ms: int
    cost_usd: float = 0.0
    error: Optional[str] = None
    domain: str = "unknown"
    metadata: Dict[str, Any] = field(default_factory=dict)


class ToolMemoryIndex:
    """
    SQLite-backed store for per-tool execution statistics.

    Sits alongside MetricsStore, but focuses on tool-level aggregation
    rather than per-run summaries.
    """

    def __init__(self, db_path: str = "./harness_state/tool_memory.db"):
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS tool_executions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                tool_name   TEXT NOT NULL,
                tool_type   TEXT NOT NULL,
                success     INTEGER NOT NULL,
                elapsed_ms  INTEGER NOT NULL,
                cost_usd    REAL DEFAULT 0.0,
                error       TEXT,
                domain      TEXT DEFAULT 'unknown',
                metadata    TEXT DEFAULT '{}',
                created_at  TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_tool_name
            ON tool_executions(tool_name);

            CREATE INDEX IF NOT EXISTS idx_tool_type
            ON tool_executions(tool_type);
        """)
        self._conn.commit()

    # ── Record ──────────────────────────────
    def record(self, execution: ToolExecution) -> None:
        """Record a single tool execution event."""
        import json
        self._conn.execute(
            """
            INSERT INTO tool_executions
            (tool_name, tool_type, success, elapsed_ms, cost_usd, error, domain, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                execution.tool_name,
                execution.tool_type,
                1 if execution.success else 0,
                execution.elapsed_ms,
                execution.cost_usd,
                execution.error,
                execution.domain,
                json.dumps(execution.metadata),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._conn.commit()

    # ── Query ───────────────────────────────
    def get_tool_stats(self, tool_name: str) -> Optional[ToolMemoryRecord]:
        """Get aggregated stats for a specific tool."""
        row = self._conn.execute(
            """
            SELECT
                tool_name,
                tool_type,
                COUNT(*) as total,
                SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) as successes,
                SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) as fails,
                AVG(elapsed_ms) as avg_ms,
                SUM(cost_usd) as total_cost,
                MAX(created_at) as last_used
            FROM tool_executions
            WHERE tool_name = ?
            GROUP BY tool_name
            """,
            (tool_name,),
        ).fetchone()

        if not row:
            return None

        # Get last error
        last_err_row = self._conn.execute(
            "SELECT error FROM tool_executions WHERE tool_name=? AND success=0 ORDER BY id DESC LIMIT 1",
            (tool_name,),
        ).fetchone()

        # Get domains
        domain_rows = self._conn.execute(
            "SELECT DISTINCT domain FROM tool_executions WHERE tool_name=?",
            (tool_name,),
        ).fetchall()

        return ToolMemoryRecord(
            tool_name=row["tool_name"],
            tool_type=row["tool_type"],
            total_executions=row["total"],
            success_count=row["successes"],
            fail_count=row["fails"],
            avg_latency_ms=round(row["avg_ms"], 1),
            total_cost_usd=round(row["total_cost"], 4),
            last_error=last_err_row["error"] if last_err_row else None,
            last_used=row["last_used"],
            domains_used=[r["domain"] for r in domain_rows],
        )

    def get_all_stats(self) -> List[ToolMemoryRecord]:
        """Get stats for all tools."""
        rows = self._conn.execute(
            "SELECT DISTINCT tool_name FROM tool_executions"
        ).fetchall()
        results = []
        for row in rows:
            record = self.get_tool_stats(row["tool_name"])
            if record:
                results.append(record)
        return results

    def get_reliability_ranking(self, min_executions: int = 3) -> List[ToolMemoryRecord]:
        """
        Get all tools ranked by reliability score (desc).

        Args:
            min_executions: Minimum number of executions to be included.
        """
        all_stats = self.get_all_stats()
        filtered = [t for t in all_stats if t.total_executions >= min_executions]
        return sorted(filtered, key=lambda t: t.reliability_score, reverse=True)

    def get_best_tool_for_type(self, tool_type: str, min_executions: int = 2) -> Optional[ToolMemoryRecord]:
        """Find the most reliable tool of a given type."""
        all_stats = self.get_all_stats()
        candidates = [
            t for t in all_stats
            if t.tool_type == tool_type and t.total_executions >= min_executions
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda t: t.reliability_score)

    def close(self):
        self._conn.close()
