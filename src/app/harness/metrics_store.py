"""
metrics_store.py — Harness v3 Quality Metrics & Cost Tracking

SQLite 기반 실행 메트릭 저장소.
각 스텝/런의 성공률, 실행시간, 토큰/비용을 추적한다.
OpenSpace GDPVal 벤치마크 패턴 적용.

작성: 2026-04-04
"""
import sqlite3
import os
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone


@dataclass
class StepMetric:
    """개별 스텝 실행 메트릭."""
    run_id: str
    harness_id: str
    step_id: str
    step_type: str
    success: bool
    elapsed_ms: int
    token_input: int = 0
    token_output: int = 0
    cost_usd: float = 0.0
    error: Optional[str] = None
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


@dataclass
class RunSummary:
    """워크플로우 런 요약 메트릭."""
    run_id: str
    harness_id: str
    domain: str
    success: bool
    total_steps: int
    elapsed_ms: int
    total_cost_usd: float = 0.0
    evolution_mode: Optional[str] = None  # FIX / DERIVED / CAPTURED / None
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class MetricsStore:
    """SQLite 기반 실행 메트릭 저장소."""

    def __init__(self, db_path: str = "./harness_state/metrics.db"):
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS step_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    harness_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    step_type TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    elapsed_ms INTEGER NOT NULL,
                    token_input INTEGER DEFAULT 0,
                    token_output INTEGER DEFAULT 0,
                    cost_usd REAL DEFAULT 0.0,
                    error TEXT,
                    timestamp TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS run_summaries (
                    run_id TEXT PRIMARY KEY,
                    harness_id TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    total_steps INTEGER NOT NULL,
                    elapsed_ms INTEGER NOT NULL,
                    total_cost_usd REAL DEFAULT 0.0,
                    evolution_mode TEXT,
                    timestamp TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_step_run
                    ON step_metrics(run_id);
                CREATE INDEX IF NOT EXISTS idx_step_harness
                    ON step_metrics(harness_id);
                CREATE INDEX IF NOT EXISTS idx_run_harness
                    ON run_summaries(harness_id);
            """)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def record_step(self, metric: StepMetric):
        """스텝 실행 메트릭을 기록한다."""
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO step_metrics
                   (run_id, harness_id, step_id, step_type, success,
                    elapsed_ms, token_input, token_output, cost_usd,
                    error, timestamp)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (metric.run_id, metric.harness_id, metric.step_id,
                 metric.step_type, int(metric.success), metric.elapsed_ms,
                 metric.token_input, metric.token_output, metric.cost_usd,
                 metric.error, metric.timestamp),
            )

    def record_run(self, summary: RunSummary):
        """런 요약 메트릭을 기록한다."""
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO run_summaries
                   (run_id, harness_id, domain, success, total_steps,
                    elapsed_ms, total_cost_usd, evolution_mode, timestamp)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (summary.run_id, summary.harness_id, summary.domain,
                 int(summary.success), summary.total_steps,
                 summary.elapsed_ms, summary.total_cost_usd,
                 summary.evolution_mode, summary.timestamp),
            )

    def get_steps_by_run(self, run_id: str) -> List[Dict[str, Any]]:
        """특정 런의 모든 스텝 메트릭을 조회한다."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM step_metrics WHERE run_id = ? ORDER BY id",
                (run_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """특정 런 요약을 조회한다."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM run_summaries WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_runs_by_harness(self, harness_id: str) -> List[Dict[str, Any]]:
        """특정 하네스의 모든 런 요약을 최신순으로 조회한다."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM run_summaries WHERE harness_id = ? ORDER BY timestamp DESC",
                (harness_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_harness_stats(self, harness_id: str) -> Dict[str, Any]:
        """하네스별 통합 통계를 반환한다."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM run_summaries WHERE harness_id = ?",
                (harness_id,),
            ).fetchall()

        if not rows:
            return {
                "harness_id": harness_id,
                "total_runs": 0,
                "success_rate": 0.0,
                "avg_elapsed_ms": 0,
                "total_cost_usd": 0.0,
            }

        total = len(rows)
        successes = sum(1 for r in rows if r["success"])
        avg_ms = sum(r["elapsed_ms"] for r in rows) / total
        total_cost = sum(r["total_cost_usd"] for r in rows)

        return {
            "harness_id": harness_id,
            "total_runs": total,
            "success_rate": successes / total,
            "avg_elapsed_ms": int(avg_ms),
            "total_cost_usd": round(total_cost, 6),
        }
