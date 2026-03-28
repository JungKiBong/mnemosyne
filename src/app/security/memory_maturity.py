"""
Memory Maturity — Phase 15: Knowledge Lifecycle & Collective Intelligence

기억의 성숙도를 관리하여 집단 지성을 극대화합니다:

  4단계 성숙도 모델:
    1. LEARNING (🌱) — 학습 중. 개인 전용, 외부 접근 차단
    2. UNSTABLE (⚡)  — 불안정. 개인 전용, 검증 대기
    3. MATURE (✅)    — 완성. 공유 가능, 집단 지성에 기여
    4. SECRET (🔒)    — 비밀. 암호화, 접근 제한

  자동 분류 규칙:
    - STM 진입 시: LEARNING
    - LTM 승격 시: UNSTABLE (salience 기반 자동 판정)
    - access_count ≥ 3 AND salience ≥ 0.7: → MATURE 승격 후보
    - admin이 secret 지정 또는 자동 암호화: → SECRET

  접근 제어 연동 (RBAC 통합):
    - LEARNING: owner만 읽기/쓰기
    - UNSTABLE: owner + 같은 팀 reader (읽기만)
    - MATURE: tribal↑ 스코프에서 모두 검색 가능
    - SECRET: admin만 복호화 가능, 일반 검색에서 제외
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from enum import Enum

from neo4j import GraphDatabase

from ..config import Config

logger = logging.getLogger('mirofish.maturity')


class MaturityLevel(Enum):
    LEARNING = "learning"     # 🌱 학습 중
    UNSTABLE = "unstable"     # ⚡ 불안정
    MATURE = "mature"         # ✅ 완성
    SECRET = "secret"         # 🔒 비밀


# Maturity → 접근 규칙
MATURITY_ACCESS = {
    MaturityLevel.LEARNING: {
        "visible_to": ["owner"],
        "searchable": False,
        "shareable": False,
        "auto_encrypt": False,
    },
    MaturityLevel.UNSTABLE: {
        "visible_to": ["owner", "team_reader"],
        "searchable": False,  # 일반 검색 제외
        "shareable": False,
        "auto_encrypt": False,
    },
    MaturityLevel.MATURE: {
        "visible_to": ["owner", "team", "org"],
        "searchable": True,
        "shareable": True,
        "auto_encrypt": False,
    },
    MaturityLevel.SECRET: {
        "visible_to": ["admin"],
        "searchable": False,
        "shareable": False,
        "auto_encrypt": True,
    },
}

# 자동 성숙 승격 조건
MATURITY_PROMOTION_RULES = {
    MaturityLevel.LEARNING: {
        "target": MaturityLevel.UNSTABLE,
        "conditions": {
            "min_salience": 0.3,
            "promoted_to_ltm": True,
        },
    },
    MaturityLevel.UNSTABLE: {
        "target": MaturityLevel.MATURE,
        "conditions": {
            "min_salience": 0.7,
            "min_access_count": 3,
            "min_age_hours": 1,  # 최소 1시간 경과
        },
    },
}


class MemoryMaturityManager:
    """
    기억 성숙도 관리 엔진.

    STM 생성 → LEARNING → UNSTABLE → MATURE 자동 흐름.
    SECRET은 수동 지정 + 자동 암호화.
    """

    def __init__(self, driver=None):
        if driver:
            self._driver = driver
            self._owns_driver = False
        else:
            self._driver = GraphDatabase.driver(
                Config.NEO4J_URI,
                auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD)
            )
            self._owns_driver = True

        self._ensure_schema()

    def close(self):
        if self._owns_driver:
            self._driver.close()

    def _ensure_schema(self):
        queries = [
            """MATCH (e:Entity) WHERE e.maturity IS NULL AND e.salience IS NOT NULL
               SET e.maturity = CASE
                 WHEN e.salience >= 0.7 AND COALESCE(e.access_count, 0) >= 3 THEN 'mature'
                 WHEN e.salience >= 0.3 THEN 'unstable'
                 ELSE 'learning'
               END""",
            "CREATE INDEX entity_maturity IF NOT EXISTS FOR (e:Entity) ON (e.maturity)",
        ]
        with self._driver.session() as session:
            for q in queries:
                try:
                    session.run(q)
                except Exception as e:
                    logger.debug(f"Maturity schema: {e}")

    # ──────────────────────────────────────────
    # Set / Get Maturity
    # ──────────────────────────────────────────

    def set_maturity(
        self,
        uuid: str,
        level: str,
        changed_by: str = "system",
        reason: str = "",
    ) -> Dict[str, Any]:
        """수동으로 기억 성숙도를 설정합니다."""
        now = datetime.now(timezone.utc).isoformat()

        with self._driver.session() as session:
            current = session.run("""
                MATCH (e:Entity {uuid: $uuid})
                RETURN e.name AS name, e.maturity AS maturity,
                       e.salience AS salience, COALESCE(e.scope, 'personal') AS scope
            """, uuid=uuid).single()

            if not current:
                return {"error": "Memory not found"}

            old_maturity = current["maturity"] or "learning"

            session.run("""
                MATCH (e:Entity {uuid: $uuid})
                SET e.maturity = $level,
                    e.maturity_changed_at = $now,
                    e.maturity_changed_by = $by
            """, uuid=uuid, level=level, now=now, by=changed_by)

            # SECRET → 자동 암호화
            if level == "secret":
                try:
                    from ..security.memory_encryption import get_encryption
                    enc = get_encryption()
                    enc.encrypt_memory(uuid, encrypted_by=changed_by)
                except Exception as e:
                    logger.warning(f"Auto-encrypt on SECRET failed: {e}")

            # Audit
            try:
                from ..storage.memory_audit import MemoryAudit
                audit = MemoryAudit(driver=self._driver)
                audit.record(uuid, "maturity", old_maturity, level,
                           "maturity_change", changed_by, reason)
            except Exception:
                pass

        logger.info(f"Maturity: {current['name'][:40]} → {level} (by {changed_by})")
        return {
            "status": "updated",
            "uuid": uuid,
            "name": current["name"],
            "old_maturity": old_maturity,
            "new_maturity": level,
            "auto_encrypted": level == "secret",
        }

    def get_maturity(self, uuid: str) -> Dict[str, Any]:
        """기억의 현재 성숙도와 접근 규칙을 조회합니다."""
        with self._driver.session() as session:
            record = session.run("""
                MATCH (e:Entity {uuid: $uuid})
                RETURN e.uuid AS uuid, e.name AS name,
                       COALESCE(e.maturity, 'learning') AS maturity,
                       e.salience AS salience,
                       COALESCE(e.scope, 'personal') AS scope,
                       COALESCE(e.access_count, 0) AS access_count,
                       e.encrypted AS encrypted,
                       e.owner_id AS owner_id,
                       e.maturity_changed_at AS changed_at
            """, uuid=uuid).single()

        if not record:
            return {"error": "Memory not found"}

        level = MaturityLevel(record["maturity"])
        access = MATURITY_ACCESS.get(level, {})

        return {
            **dict(record),
            "access_rules": access,
            "emoji": {"learning": "🌱", "unstable": "⚡", "mature": "✅", "secret": "🔒"}.get(record["maturity"], "❓"),
        }

    # ──────────────────────────────────────────
    # Auto-Promotion Check
    # ──────────────────────────────────────────

    def check_promotions(self) -> Dict[str, Any]:
        """자동 성숙 승격 후보를 확인하고 승격합니다."""
        result = {"promoted": 0, "candidates": [], "details": []}

        with self._driver.session() as session:
            # LEARNING → UNSTABLE (LTM에 승격된 것)
            learning_candidates = session.run("""
                MATCH (e:Entity)
                WHERE e.maturity = 'learning'
                  AND e.salience IS NOT NULL
                  AND e.salience >= 0.3
                  AND e.promoted_from_stm = true
                RETURN e.uuid AS uuid, e.name AS name, e.salience AS salience
                LIMIT 50
            """).data()

            for c in learning_candidates:
                self.set_maturity(c["uuid"], "unstable", "auto-promoter",
                                f"LTM promoted, salience={c['salience']:.2f}")
                result["promoted"] += 1
                result["details"].append({"uuid": c["uuid"], "name": c["name"],
                                          "from": "learning", "to": "unstable"})

            # UNSTABLE → MATURE (충분한 접근 + 높은 salience)
            unstable_candidates = session.run("""
                MATCH (e:Entity)
                WHERE e.maturity = 'unstable'
                  AND e.salience >= 0.7
                  AND COALESCE(e.access_count, 0) >= 3
                RETURN e.uuid AS uuid, e.name AS name,
                       e.salience AS salience, e.access_count AS access_count
                LIMIT 50
            """).data()

            for c in unstable_candidates:
                self.set_maturity(c["uuid"], "mature", "auto-promoter",
                                f"salience={c['salience']:.2f}, accesses={c['access_count']}")
                result["promoted"] += 1
                result["details"].append({"uuid": c["uuid"], "name": c["name"],
                                          "from": "unstable", "to": "mature"})

        logger.info(f"Maturity check: {result['promoted']} promotions")
        return result

    # ──────────────────────────────────────────
    # Dashboard Data
    # ──────────────────────────────────────────

    def get_overview(self) -> Dict[str, Any]:
        """대시보드용 종합 현황 데이터."""
        with self._driver.session() as session:
            # 성숙도별 카운트
            maturity_counts = session.run("""
                MATCH (e:Entity)
                WHERE e.salience IS NOT NULL
                WITH COALESCE(e.maturity, 'learning') AS mat,
                     count(e) AS cnt,
                     avg(e.salience) AS avg_sal,
                     sum(CASE WHEN e.encrypted = true THEN 1 ELSE 0 END) AS enc_cnt
                RETURN mat, cnt, avg_sal, enc_cnt
                ORDER BY mat
            """).data()

            # 스코프 × 성숙도 매트릭스
            matrix = session.run("""
                MATCH (e:Entity)
                WHERE e.salience IS NOT NULL
                WITH COALESCE(e.scope, 'personal') AS scope,
                     COALESCE(e.maturity, 'learning') AS mat,
                     count(e) AS cnt
                RETURN scope, mat, cnt
                ORDER BY scope, mat
            """).data()

            # 최근 성숙도 변경
            recent_changes = session.run("""
                MATCH (e:Entity)
                WHERE e.maturity_changed_at IS NOT NULL
                RETURN e.uuid AS uuid, e.name AS name,
                       e.maturity AS maturity, e.salience AS salience,
                       COALESCE(e.scope, 'personal') AS scope,
                       e.maturity_changed_at AS changed_at,
                       e.maturity_changed_by AS changed_by
                ORDER BY e.maturity_changed_at DESC
                LIMIT 20
            """).data()

            # 공유 가능한 기억 (mature)
            shareable = session.run("""
                MATCH (e:Entity)
                WHERE e.maturity = 'mature' AND e.salience IS NOT NULL
                RETURN count(e) AS cnt, avg(e.salience) AS avg_sal
            """).single()

            # 학습 중 기억 (아직 불안정)
            in_progress = session.run("""
                MATCH (e:Entity)
                WHERE e.maturity IN ['learning', 'unstable']
                  AND e.salience IS NOT NULL
                RETURN count(e) AS cnt
            """).single()

        # Build scope-maturity matrix
        scope_matrix = {}
        for row in matrix:
            s = row["scope"]
            if s not in scope_matrix:
                scope_matrix[s] = {}
            scope_matrix[s][row["mat"]] = row["cnt"]

        return {
            "maturity": {
                m["mat"]: {
                    "count": m["cnt"],
                    "avg_salience": round(m["avg_sal"] or 0, 3),
                    "encrypted_count": m["enc_cnt"] or 0,
                    "emoji": {"learning": "🌱", "unstable": "⚡", "mature": "✅", "secret": "🔒"}.get(m["mat"], "❓"),
                }
                for m in maturity_counts
            },
            "scope_matrix": scope_matrix,
            "shareable_count": shareable["cnt"] if shareable else 0,
            "shareable_avg_salience": round(shareable["avg_sal"] or 0, 3) if shareable else 0,
            "in_progress_count": in_progress["cnt"] if in_progress else 0,
            "recent_changes": recent_changes,
            "access_rules": {
                level.value: rules for level, rules in MATURITY_ACCESS.items()
            },
        }

    def get_memories_by_maturity(
        self,
        maturity: str,
        scope: str = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """특정 성숙도 레벨의 기억 목록."""
        scope_filter = "AND e.scope = $scope" if scope else ""
        with self._driver.session() as session:
            records = session.run(f"""
                MATCH (e:Entity)
                WHERE COALESCE(e.maturity, 'learning') = $mat
                  AND e.salience IS NOT NULL
                  {scope_filter}
                RETURN e.uuid AS uuid, e.name AS name,
                       e.salience AS salience,
                       COALESCE(e.scope, 'personal') AS scope,
                       COALESCE(e.maturity, 'learning') AS maturity,
                       e.encrypted AS encrypted,
                       COALESCE(e.access_count, 0) AS access_count,
                       e.owner_id AS owner_id,
                       e.created_at AS created_at
                ORDER BY e.salience DESC
                LIMIT $limit
            """, mat=maturity, scope=scope or "", limit=limit).data()
        return records


# Singleton
_maturity_instance: Optional[MemoryMaturityManager] = None

def get_maturity_manager() -> MemoryMaturityManager:
    global _maturity_instance
    if _maturity_instance is None:
        _maturity_instance = MemoryMaturityManager()
    return _maturity_instance
