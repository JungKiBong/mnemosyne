"""
Harness Analytics API — Execution Trend & Tool Reliability Endpoints

Provides REST endpoints for:
  - Execution trend data (daily/weekly success/failure rates)
  - Tool reliability ranking (by success rate across all executions)
  - Domain-level execution summaries
  - Recent execution history
  - Experience detail by run_id

All data is sourced from Neo4j HarnessExperience / HarnessPattern / Reflection nodes.
"""

import json
import logging
import os
from flask import Blueprint, request, jsonify

logger = logging.getLogger("mirofish.api.harness_analytics")
harness_analytics_bp = Blueprint("harness_analytics", __name__)


def _get_neo4j_driver():
    """Lazy-load a standalone Neo4j driver for harness analytics."""
    try:
        from neo4j import GraphDatabase
    except ImportError:
        raise RuntimeError("neo4j not installed — pip install neo4j")

    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    pwd = os.environ.get("NEO4J_PASSWORD", "password")
    return GraphDatabase.driver(uri, auth=(user, pwd))


# ─────────────────────────────────────────────
# 1. Execution Trend  (line chart data)
# ─────────────────────────────────────────────

@harness_analytics_bp.route("/harness/analytics/trend", methods=["GET"])
def execution_trend():
    """
    GET /api/harness/analytics/trend?days=30&domain=<optional>

    Returns daily execution counts grouped by experience_type (SUCCESS/FAILURE/HEALED).
    """
    days = request.args.get("days", 30, type=int)
    domain = request.args.get("domain")

    driver = _get_neo4j_driver()
    try:
        with driver.session() as session:
            params = {"days": days}
            domain_filter = ""
            if domain:
                domain_filter = "AND e.domain = $domain"
                params["domain"] = domain

            result = session.run(
                f"""
                MATCH (e:HarnessExperience)
                WHERE e.created_at >= datetime() - duration({{days: $days}})
                {domain_filter}
                WITH date(e.created_at) AS day,
                     e.experience_type AS exp_type,
                     count(*) AS cnt,
                     avg(e.elapsed_ms) AS avg_ms
                RETURN day, exp_type, cnt, avg_ms
                ORDER BY day
                """,
                **params,
            )

            trends = {}
            for record in result:
                day_str = str(record["day"])
                if day_str not in trends:
                    trends[day_str] = {
                        "date": day_str,
                        "success": 0, "failure": 0, "healed": 0,
                        "total": 0, "avg_ms": 0,
                    }
                exp_type = (record["exp_type"] or "SUCCESS").lower()
                cnt = record["cnt"]
                avg_ms = record["avg_ms"] or 0
                trends[day_str][exp_type] = cnt
                trends[day_str]["total"] += cnt
                trends[day_str]["avg_ms"] = round(avg_ms, 1)

            data = sorted(trends.values(), key=lambda x: x["date"])
            return jsonify({
                "status": "ok",
                "days": days,
                "domain": domain,
                "data": data,
                "total_records": sum(d["total"] for d in data),
            })
    except Exception as e:
        logger.error(f"Execution trend failed: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        driver.close()


# ─────────────────────────────────────────────
# 2. Tool Reliability Ranking
# ─────────────────────────────────────────────

@harness_analytics_bp.route("/harness/analytics/tools", methods=["GET"])
def tool_reliability():
    """
    GET /api/harness/analytics/tools?limit=20

    Returns tools ranked by usage frequency and success rate.
    """
    limit = request.args.get("limit", 20, type=int)

    driver = _get_neo4j_driver()
    try:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (e:HarnessExperience)-[:USED_TOOL]->(t:Tool)
                WITH t.name AS tool_name, t.type AS tool_type,
                     count(e) AS total_uses,
                     sum(CASE WHEN e.experience_type = 'SUCCESS' THEN 1 ELSE 0 END) AS successes,
                     sum(CASE WHEN e.experience_type = 'FAILURE' THEN 1 ELSE 0 END) AS failures,
                     avg(e.elapsed_ms) AS avg_ms
                RETURN tool_name, tool_type, total_uses, successes, failures, avg_ms
                ORDER BY total_uses DESC
                LIMIT $limit
                """,
                limit=limit,
            )

            tools = []
            for record in result:
                total = record["total_uses"]
                succ = record["successes"]
                tools.append({
                    "name": record["tool_name"],
                    "type": record["tool_type"],
                    "total_uses": total,
                    "successes": succ,
                    "failures": record["failures"],
                    "success_rate": round(succ / total * 100, 1) if total > 0 else 0,
                    "avg_ms": round(record["avg_ms"] or 0, 1),
                })

            return jsonify({
                "status": "ok",
                "tools": tools,
                "count": len(tools),
            })
    except Exception as e:
        logger.error(f"Tool reliability query failed: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        driver.close()


# ─────────────────────────────────────────────
# 3. Domain Summary
# ─────────────────────────────────────────────

@harness_analytics_bp.route("/harness/analytics/domains", methods=["GET"])
def domain_summary():
    """
    GET /api/harness/analytics/domains

    Returns per-domain execution stats (count, success rate, avg latency).
    """
    driver = _get_neo4j_driver()
    try:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (e:HarnessExperience)
                WITH e.domain AS domain,
                     count(e) AS total,
                     sum(CASE WHEN e.experience_type = 'SUCCESS' THEN 1 ELSE 0 END) AS successes,
                     avg(e.elapsed_ms) AS avg_ms,
                     max(e.created_at) AS last_run
                RETURN domain, total, successes, avg_ms, last_run
                ORDER BY total DESC
                """
            )

            domains = []
            for record in result:
                total = record["total"]
                succ = record["successes"]
                domains.append({
                    "domain": record["domain"],
                    "total_executions": total,
                    "successes": succ,
                    "success_rate": round(succ / total * 100, 1) if total > 0 else 0,
                    "avg_ms": round(record["avg_ms"] or 0, 1),
                    "last_run": str(record["last_run"]) if record["last_run"] else None,
                })

            return jsonify({
                "status": "ok",
                "domains": domains,
                "count": len(domains),
            })
    except Exception as e:
        logger.error(f"Domain summary failed: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        driver.close()


# ─────────────────────────────────────────────
# 4. Recent Executions
# ─────────────────────────────────────────────

@harness_analytics_bp.route("/harness/analytics/recent", methods=["GET"])
def recent_executions():
    """
    GET /api/harness/analytics/recent?limit=50&domain=<optional>

    Returns recent execution experiences.
    """
    limit = request.args.get("limit", 50, type=int)
    domain = request.args.get("domain")

    driver = _get_neo4j_driver()
    try:
        with driver.session() as session:
            params = {"limit": limit}
            domain_filter = ""
            if domain:
                domain_filter = "WHERE e.domain = $domain"
                params["domain"] = domain

            result = session.run(
                f"""
                MATCH (e:HarnessExperience)
                {domain_filter}
                OPTIONAL MATCH (e)-[:USED_TOOL]->(t:Tool)
                WITH e, collect(t.name) AS tool_names
                RETURN e.uuid AS uuid, e.harness_id AS harness_id,
                       e.domain AS domain, e.experience_type AS exp_type,
                       e.elapsed_ms AS elapsed_ms, e.run_id AS run_id,
                       e.created_at AS created_at, tool_names
                ORDER BY e.created_at DESC
                LIMIT $limit
                """,
                **params,
            )

            items = []
            for record in result:
                items.append({
                    "uuid": record["uuid"],
                    "harness_id": record["harness_id"],
                    "domain": record["domain"],
                    "type": record["exp_type"],
                    "elapsed_ms": record["elapsed_ms"],
                    "run_id": record["run_id"],
                    "created_at": str(record["created_at"]) if record["created_at"] else None,
                    "tools": record["tool_names"],
                })

            return jsonify({
                "status": "ok",
                "executions": items,
                "count": len(items),
            })
    except Exception as e:
        logger.error(f"Recent executions query failed: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        driver.close()


# ─────────────────────────────────────────────
# 5. Execution Detail (by run_id)
# ─────────────────────────────────────────────

@harness_analytics_bp.route("/harness/analytics/run/<run_id>", methods=["GET"])
def execution_detail(run_id: str):
    """
    GET /api/harness/analytics/run/<run_id>

    Returns full execution tree for a specific run.
    """
    driver = _get_neo4j_driver()
    try:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (e:HarnessExperience {run_id: $run_id})
                OPTIONAL MATCH (e)-[ut:USED_TOOL]->(t:Tool)
                OPTIONAL MATCH (e)-[:PRODUCED]->(r:Reflection)
                RETURN e, collect(DISTINCT {tool: t.name, type: t.type, pos: ut.position}) AS tools,
                       collect(DISTINCT {event: r.event, lesson: r.lesson, severity: r.severity}) AS reflections
                ORDER BY e.created_at
                """,
                run_id=run_id,
            )

            experiences = []
            for record in result:
                exp = dict(record["e"])
                exp["tools"] = sorted(
                    [t for t in record["tools"] if t.get("tool")],
                    key=lambda x: x.get("pos", 0),
                )
                exp["reflections"] = [r for r in record["reflections"] if r.get("event")]
                experiences.append(exp)

            if not experiences:
                return jsonify({"error": f"No execution found for run_id: {run_id}"}), 404

            return jsonify({
                "status": "ok",
                "run_id": run_id,
                "experiences": experiences,
                "count": len(experiences),
            })
    except Exception as e:
        logger.error(f"Execution detail failed: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        driver.close()


# ─────────────────────────────────────────────
# 6. Patterns & Reflections
# ─────────────────────────────────────────────

@harness_analytics_bp.route("/harness/analytics/patterns", methods=["GET"])
def list_patterns():
    """
    GET /api/harness/analytics/patterns?domain=<optional>&limit=20

    Returns stored harness patterns.
    """
    limit = request.args.get("limit", 20, type=int)
    domain = request.args.get("domain")

    driver = _get_neo4j_driver()
    try:
        with driver.session() as session:
            params = {"limit": limit}
            domain_filter = ""
            if domain:
                domain_filter = "WHERE p.domain = $domain"
                params["domain"] = domain

            result = session.run(
                f"""
                MATCH (p:HarnessPattern)
                {domain_filter}
                RETURN p.uuid AS uuid, p.domain AS domain,
                       p.tool_chain AS tool_chain, p.trigger AS trigger,
                       p.scope AS scope, p.created_at AS created_at
                ORDER BY p.created_at DESC
                LIMIT $limit
                """,
                **params,
            )

            patterns = []
            for record in result:
                tc = record["tool_chain"]
                if isinstance(tc, str):
                    try:
                        tc = json.loads(tc)
                    except (json.JSONDecodeError, TypeError):
                        tc = [tc]
                patterns.append({
                    "uuid": record["uuid"],
                    "domain": record["domain"],
                    "tool_chain": tc,
                    "trigger": record["trigger"],
                    "scope": record["scope"],
                    "created_at": str(record["created_at"]) if record["created_at"] else None,
                })

            return jsonify({
                "status": "ok",
                "patterns": patterns,
                "count": len(patterns),
            })
    except Exception as e:
        logger.error(f"Pattern list query failed: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        driver.close()


@harness_analytics_bp.route("/harness/analytics/reflections", methods=["GET"])
def list_reflections():
    """
    GET /api/harness/analytics/reflections?domain=<optional>&limit=20

    Returns failure reflections (lessons learned).
    """
    limit = request.args.get("limit", 20, type=int)
    domain = request.args.get("domain")

    driver = _get_neo4j_driver()
    try:
        with driver.session() as session:
            params = {"limit": limit}
            if domain:
                params["domain"] = domain

            result = session.run(
                f"""
                MATCH (r:Reflection)
                WHERE r.source = 'harness'
                {"AND r.domain = $domain" if domain else ""}
                RETURN r.uuid AS uuid, r.event AS event,
                       r.lesson AS lesson, r.severity AS severity,
                       r.domain AS domain, r.created_at AS created_at
                ORDER BY r.created_at DESC
                LIMIT $limit
                """,
                **params,
            )

            reflections = []
            for record in result:
                reflections.append({
                    "uuid": record["uuid"],
                    "event": record["event"],
                    "lesson": record["lesson"],
                    "severity": record["severity"],
                    "domain": record["domain"],
                    "created_at": str(record["created_at"]) if record["created_at"] else None,
                })

            return jsonify({
                "status": "ok",
                "reflections": reflections,
                "count": len(reflections),
            })
    except Exception as e:
        logger.error(f"Reflection list query failed: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        driver.close()
