"""Scheduler API routes for triggering and monitoring maintenance jobs."""

from __future__ import annotations

from fastapi import APIRouter

from app.workers.scheduler import get_scheduler

router = APIRouter()


@router.get("/status")
async def scheduler_status():
    """Get the status of all scheduled maintenance jobs."""
    scheduler = get_scheduler()
    return await scheduler.get_status()


@router.post("/run/{job_name}")
async def run_job(job_name: str):
    """Manually trigger a specific maintenance job."""
    scheduler = get_scheduler()
    return await scheduler.run_job_now(job_name)


@router.get("/jobs")
async def list_jobs():
    """List all registered maintenance jobs with their configuration."""
    scheduler = get_scheduler()
    status = await scheduler.get_status()
    return {"jobs": status["jobs"]}
