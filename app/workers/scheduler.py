"""Scheduled maintenance worker for AgentMemoryDB.

Inspired by InsForge's scheduled tasks feature. Runs periodic
maintenance jobs on a configurable cron schedule:
- Memory consolidation (find & merge duplicates)
- Stale memory archiving
- Recency score recomputation
- Expired memory cleanup
- Access log pruning

Can be run as a standalone process or embedded in the main app.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from app.core.config import settings
from app.db import async_session_factory

logger = logging.getLogger("agentmemodb.scheduler")


class ScheduledJob:
    """A single scheduled maintenance job."""

    def __init__(
        self,
        name: str,
        handler,
        interval_minutes: int,
        enabled: bool = True,
    ) -> None:
        self.name = name
        self.handler = handler
        self.interval_minutes = interval_minutes
        self.enabled = enabled
        self.last_run: datetime | None = None
        self.run_count: int = 0
        self.last_error: str | None = None

    @property
    def next_run(self) -> datetime | None:
        if self.last_run is None:
            return datetime.now(timezone.utc)
        return self.last_run + timedelta(minutes=self.interval_minutes)

    @property
    def is_due(self) -> bool:
        if not self.enabled:
            return False
        if self.last_run is None:
            return True
        return datetime.now(timezone.utc) >= self.next_run


class MaintenanceScheduler:
    """Runs periodic maintenance jobs for the memory system.

    Jobs:
    1. consolidate_duplicates — find & merge near-duplicate memories
    2. archive_stale — archive memories that haven't been accessed
    3. recompute_recency — refresh recency scores for active memories
    4. cleanup_expired — retract memories past their expires_at
    5. prune_access_logs — remove old access log entries
    """

    def __init__(self) -> None:
        self._running = False
        self._jobs: list[ScheduledJob] = []
        self._setup_jobs()

    def _setup_jobs(self) -> None:
        """Register all maintenance jobs with their schedules."""
        self._jobs = [
            ScheduledJob(
                name="consolidate_duplicates",
                handler=self._consolidate_duplicates,
                interval_minutes=settings.scheduler_consolidation_interval,
                enabled=settings.scheduler_enable_consolidation,
            ),
            ScheduledJob(
                name="archive_stale",
                handler=self._archive_stale_memories,
                interval_minutes=settings.scheduler_archive_interval,
                enabled=settings.scheduler_enable_archive,
            ),
            ScheduledJob(
                name="recompute_recency",
                handler=self._recompute_recency_scores,
                interval_minutes=settings.scheduler_recency_interval,
                enabled=settings.scheduler_enable_recency,
            ),
            ScheduledJob(
                name="cleanup_expired",
                handler=self._cleanup_expired_memories,
                interval_minutes=settings.scheduler_cleanup_interval,
                enabled=settings.scheduler_enable_cleanup,
            ),
            ScheduledJob(
                name="prune_access_logs",
                handler=self._prune_access_logs,
                interval_minutes=settings.scheduler_prune_interval,
                enabled=settings.scheduler_enable_prune,
            ),
        ]

    async def start(self) -> None:
        """Start the scheduler loop."""
        self._running = True
        logger.info(
            "Maintenance scheduler started with %d jobs: %s",
            len([j for j in self._jobs if j.enabled]),
            ", ".join(j.name for j in self._jobs if j.enabled),
        )

        while self._running:
            for job in self._jobs:
                if job.is_due:
                    await self._execute_job(job)
            await asyncio.sleep(30)  # check every 30 seconds

    async def stop(self) -> None:
        """Gracefully stop the scheduler."""
        self._running = False
        logger.info("Maintenance scheduler stopped.")

    async def run_job_now(self, job_name: str) -> dict[str, Any]:
        """Manually trigger a specific job."""
        for job in self._jobs:
            if job.name == job_name:
                return await self._execute_job(job)
        return {"error": f"Job not found: {job_name}"}

    async def get_status(self) -> dict[str, Any]:
        """Return status of all scheduled jobs."""
        return {
            "running": self._running,
            "jobs": [
                {
                    "name": job.name,
                    "enabled": job.enabled,
                    "interval_minutes": job.interval_minutes,
                    "last_run": str(job.last_run) if job.last_run else None,
                    "next_run": str(job.next_run) if job.next_run else None,
                    "run_count": job.run_count,
                    "last_error": job.last_error,
                }
                for job in self._jobs
            ],
        }

    async def _execute_job(self, job: ScheduledJob) -> dict[str, Any]:
        """Execute a single job with error handling and logging."""
        logger.info("Running scheduled job: %s", job.name)
        start = datetime.now(timezone.utc)

        try:
            result = await job.handler()
            job.last_run = datetime.now(timezone.utc)
            job.run_count += 1
            job.last_error = None
            elapsed = (job.last_run - start).total_seconds()
            logger.info("Job %s completed in %.2fs: %s", job.name, elapsed, result)
            return {"job": job.name, "status": "success", "elapsed_seconds": elapsed, "result": result}
        except Exception as exc:
            job.last_error = str(exc)
            job.last_run = datetime.now(timezone.utc)
            logger.error("Job %s failed: %s", job.name, exc)
            return {"job": job.name, "status": "error", "error": str(exc)}

    # ── Job Implementations ──────────────────────────────────────

    async def _consolidate_duplicates(self) -> dict[str, Any]:
        """Find and merge near-duplicate memories across all users."""
        from app.services.consolidation_service import ConsolidationService
        from sqlalchemy import text

        async with async_session_factory() as session:
            # Get distinct user IDs with active memories
            result = await session.execute(
                text("SELECT DISTINCT user_id FROM memories WHERE status = 'active' LIMIT 100")
            )
            user_ids = [row[0] for row in result.fetchall()]

            total_merged = 0
            svc = ConsolidationService(session)
            for uid in user_ids:
                try:
                    report = await svc.auto_consolidate(
                        user_id=uid,
                    )
                    total_merged += report.get("memories_merged", 0)
                except Exception as exc:
                    logger.warning("Consolidation failed for user %s: %s", uid, exc)

            await session.commit()
            return {"users_processed": len(user_ids), "total_merged": total_merged}

    async def _archive_stale_memories(self) -> dict[str, Any]:
        """Archive memories that haven't been accessed in a long time."""
        from sqlalchemy import text

        stale_days = settings.scheduler_stale_threshold_days
        cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)

        async with async_session_factory() as session:
            result = await session.execute(
                text("""
                    UPDATE memories
                    SET status = 'archived', updated_at = NOW()
                    WHERE status = 'active'
                      AND updated_at < :cutoff
                      AND importance_score < 0.3
                    RETURNING id
                """),
                {"cutoff": cutoff},
            )
            archived_ids = [str(row[0]) for row in result.fetchall()]
            await session.commit()
            return {"archived_count": len(archived_ids), "stale_threshold_days": stale_days}

    async def _recompute_recency_scores(self) -> dict[str, Any]:
        """Refresh recency scores for all active memories."""
        from sqlalchemy import text
        from app.utils.scoring import compute_recency_score

        async with async_session_factory() as session:
            result = await session.execute(
                text("SELECT id, updated_at FROM memories WHERE status = 'active'")
            )
            rows = result.fetchall()

            count = 0
            for row in rows:
                recency = compute_recency_score(row[1])
                await session.execute(
                    text("UPDATE memories SET recency_score = :score WHERE id = :id"),
                    {"score": recency, "id": row[0]},
                )
                count += 1

            await session.commit()
            return {"updated_count": count}

    async def _cleanup_expired_memories(self) -> dict[str, Any]:
        """Retract memories that have passed their expires_at timestamp."""
        from sqlalchemy import text

        now = datetime.now(timezone.utc)
        async with async_session_factory() as session:
            result = await session.execute(
                text("""
                    UPDATE memories
                    SET status = 'retracted', updated_at = NOW()
                    WHERE status = 'active'
                      AND expires_at IS NOT NULL
                      AND expires_at < :now
                    RETURNING id
                """),
                {"now": now},
            )
            retracted_ids = [str(row[0]) for row in result.fetchall()]
            await session.commit()
            return {"retracted_count": len(retracted_ids)}

    async def _prune_access_logs(self) -> dict[str, Any]:
        """Remove access log entries older than retention period."""
        from sqlalchemy import text

        retention_days = settings.scheduler_access_log_retention_days
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

        async with async_session_factory() as session:
            result = await session.execute(
                text("DELETE FROM memory_access_logs WHERE accessed_at < :cutoff"),
                {"cutoff": cutoff},
            )
            await session.commit()
            return {"pruned_count": result.rowcount, "retention_days": retention_days}


# ── Singleton ────────────────────────────────────────────────────

_scheduler: MaintenanceScheduler | None = None


def get_scheduler() -> MaintenanceScheduler:
    """Get or create the maintenance scheduler singleton."""
    global _scheduler
    if _scheduler is None:
        _scheduler = MaintenanceScheduler()
    return _scheduler
