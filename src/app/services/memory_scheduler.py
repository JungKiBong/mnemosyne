"""
Memory Scheduler — Automated Lifecycle Management

Background jobs for cognitive memory maintenance:
  1. Daily Decay — Ebbinghaus forgetting curve (midnight)
  2. STM Cleanup — Remove expired short-term memories (every 5 min)
  3. Scope Promotion Check — Auto-promote qualifying memories (every hour)
  4. Health Metrics — Update system health stats (every 10 min)

Uses APScheduler for reliable background job execution.
Falls back to threading if APScheduler is not installed.
"""

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger('mirofish.memory_scheduler')


class MemoryScheduler:
    """
    Background scheduler for memory lifecycle automation.

    Start with scheduler.start() and stop with scheduler.shutdown().
    """

    def __init__(self):
        self._running = False
        self._scheduler = None
        self._fallback_thread = None
        self._use_apscheduler = False

        # Try APScheduler
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            self._scheduler = BackgroundScheduler(timezone='UTC')
            self._use_apscheduler = True
            logger.info("MemoryScheduler: Using APScheduler")
        except ImportError:
            logger.info("MemoryScheduler: APScheduler not found, using threading fallback")

    def start(self):
        """Start the scheduler with all jobs."""
        if self._running:
            logger.warning("Scheduler already running")
            return

        self._running = True

        if self._use_apscheduler:
            self._setup_apscheduler_jobs()
            self._scheduler.start()
        else:
            self._start_fallback()

        logger.info("✅ MemoryScheduler started")

    def shutdown(self):
        """Stop the scheduler."""
        self._running = False
        if self._use_apscheduler and self._scheduler:
            self._scheduler.shutdown(wait=False)
        logger.info("MemoryScheduler stopped")

    def get_status(self) -> dict:
        """Get scheduler status and next run times."""
        status = {
            "running": self._running,
            "backend": "apscheduler" if self._use_apscheduler else "threading",
            "jobs": [],
        }

        if self._use_apscheduler and self._scheduler:
            for job in self._scheduler.get_jobs():
                status["jobs"].append({
                    "id": job.id,
                    "name": job.name,
                    "next_run": str(job.next_run_time) if job.next_run_time else None,
                })

        return status

    # ──────────────────────────────────────────
    # APScheduler Jobs
    # ──────────────────────────────────────────

    def _setup_apscheduler_jobs(self):
        """Register all scheduled jobs with APScheduler."""

        # 1. Daily Decay — every day at midnight UTC
        self._scheduler.add_job(
            self._job_daily_decay,
            'cron', hour=0, minute=0,
            id='daily_decay',
            name='Daily Ebbinghaus Decay',
            replace_existing=True,
        )

        # 2. STM Cleanup — every 5 minutes
        self._scheduler.add_job(
            self._job_stm_cleanup,
            'interval', minutes=5,
            id='stm_cleanup',
            name='STM Expired Cleanup',
            replace_existing=True,
        )

        # 3. Scope Promotion Check — every hour
        self._scheduler.add_job(
            self._job_scope_promotion,
            'interval', hours=1,
            id='scope_promotion',
            name='Auto Scope Promotion',
            replace_existing=True,
        )

        # 4. Health Metrics — every 10 minutes
        self._scheduler.add_job(
            self._job_health_update,
            'interval', minutes=10,
            id='health_update',
            name='Health Metrics Update',
            replace_existing=True,
        )

        # 5. Maturity Promotion — every 30 minutes
        self._scheduler.add_job(
            self._job_maturity_promotion,
            'interval', minutes=30,
            id='maturity_promotion',
            name='Auto Maturity Promotion',
            replace_existing=True,
        )

        logger.info(f"Registered {len(self._scheduler.get_jobs())} scheduled jobs")

    # ──────────────────────────────────────────
    # Threading Fallback
    # ──────────────────────────────────────────

    def _start_fallback(self):
        """Simple threading-based scheduler fallback."""
        def run():
            last_decay = 0
            last_stm = 0
            last_promo = 0
            last_health = 0
            last_maturity = 0

            while self._running:
                now = time.time()

                # STM cleanup every 5 min
                if now - last_stm >= 300:
                    self._safe_run(self._job_stm_cleanup)
                    last_stm = now

                # Health every 10 min
                if now - last_health >= 600:
                    self._safe_run(self._job_health_update)
                    last_health = now

                # Scope promotion every hour
                if now - last_promo >= 3600:
                    self._safe_run(self._job_scope_promotion)
                    last_promo = now

                # Maturity promotion every 30 min
                if now - last_maturity >= 1800:
                    self._safe_run(self._job_maturity_promotion)
                    last_maturity = now

                # Daily decay: check if midnight passed
                current_hour = datetime.now(timezone.utc).hour
                if current_hour == 0 and now - last_decay >= 82800:  # 23h gap
                    self._safe_run(self._job_daily_decay)
                    last_decay = now

                time.sleep(30)

        self._fallback_thread = threading.Thread(target=run, daemon=True, name="memory-scheduler")
        self._fallback_thread.start()

    # ──────────────────────────────────────────
    # Job Implementations
    # ──────────────────────────────────────────

    def _job_daily_decay(self):
        """Run Ebbinghaus decay on all LTM memories."""
        logger.info("🕐 Running daily decay cycle...")
        from ..storage.memory_manager import MemoryManager
        manager = MemoryManager()
        try:
            result = manager.run_decay(dry_run=False)
            logger.info(
                f"✅ Decay complete: {result['decayed']} decayed, "
                f"{result['archived']} archived, {result['warned']} warned"
            )
        except Exception as e:
            logger.error(f"❌ Decay failed: {e}", exc_info=True)
        finally:
            manager.close()

    def _job_stm_cleanup(self):
        """Remove expired STM items."""
        from ..storage.memory_manager import MemoryManager
        manager = MemoryManager()
        try:
            before = len(manager._stm_buffer)
            items = manager.stm_list()  # triggers cleanup
            after = len(items)
            cleaned = max(0, before - after)
            if cleaned > 0:
                logger.info(f"🧹 STM cleanup: removed {cleaned} expired items")
        except Exception as e:
            logger.debug(f"STM cleanup: {e}")
        finally:
            manager.close()

    def _job_scope_promotion(self):
        """Check and auto-promote qualifying memories."""
        logger.info("⬆️ Checking scope promotion candidates...")
        from ..storage.memory_scopes import MemoryScopeManager
        scopes = MemoryScopeManager()
        try:
            for source_scope in ['personal', 'tribal', 'social']:
                candidates = scopes.find_promotion_candidates(source_scope)
                for c in candidates:
                    target = {'personal': 'tribal', 'tribal': 'social', 'social': 'global'}.get(source_scope)
                    if target:
                        try:
                            result = scopes.promote_memory(
                                c['uuid'], target,
                                reason=f"Auto-promoted by scheduler (salience={c['salience']:.3f})"
                            )
                            if result.get("status") == "promoted":
                                logger.info(f"⬆️ Auto-promoted: {c['name']} → {target}")
                        except Exception as e:
                            logger.debug(f"Promotion failed for {c.get('uuid','?')}: {e}")
        except Exception as e:
            logger.error(f"Scope promotion check failed: {e}", exc_info=True)
        finally:
            scopes.close()

    def _job_maturity_promotion(self):
        """Auto-promote memory maturity: learning→unstable→mature."""
        logger.info("🌱 Checking maturity promotions...")
        try:
            from ..security.memory_maturity import get_maturity_manager
            mgr = get_maturity_manager()
            result = mgr.check_promotions()
            if result['promoted'] > 0:
                logger.info(f"🌱 Maturity promoted: {result['promoted']} memories")
        except Exception as e:
            logger.error(f"Maturity promotion failed: {e}", exc_info=True)

    def _job_health_update(self):
        """Log current memory health metrics."""
        from ..storage.memory_manager import MemoryManager
        manager = MemoryManager()
        try:
            overview = manager.get_memory_overview()
            ltm = overview.get('ltm', {})
            stm = overview.get('stm', {})
            logger.info(
                f"📊 Health: STM={stm.get('count',0)}, "
                f"LTM={ltm.get('entity_count',0)}, "
                f"avg_salience={ltm.get('avg_salience',0):.3f}, "
                f"archived={overview.get('archived_count',0)}"
            )
        except Exception as e:
            logger.debug(f"Health update: {e}")
        finally:
            manager.close()

    def _safe_run(self, func):
        """Safely run a job function."""
        try:
            func()
        except Exception as e:
            logger.error(f"Scheduler job failed: {func.__name__} — {e}")


# ──────────────────────────────────────────
# Global instance management
# ──────────────────────────────────────────

_scheduler_instance: Optional[MemoryScheduler] = None


def get_scheduler() -> MemoryScheduler:
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = MemoryScheduler()
    return _scheduler_instance


def start_scheduler():
    """Start the global memory scheduler."""
    scheduler = get_scheduler()
    scheduler.start()
    return scheduler


def shutdown_scheduler():
    """Stop the global memory scheduler."""
    global _scheduler_instance
    if _scheduler_instance:
        _scheduler_instance.shutdown()
        _scheduler_instance = None
