"""AgentMemoryDB CLI — management commands for ops and development.

Usage:
    python -m app.cli stats --user-id <UUID>
    python -m app.cli health
    python -m app.cli export --user-id <UUID> --output memories.json
    python -m app.cli import --user-id <UUID> --input memories.json
    python -m app.cli archive-stale
    python -m app.cli recompute-recency
    python -m app.cli consolidate --user-id <UUID>
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from typing import Any

import click


def _run_async(coro: Any) -> Any:
    """Run an async coroutine from synchronous Click commands."""
    return asyncio.run(coro)


async def _get_session():
    """Get a fresh async session for CLI operations."""
    from app.db.session import async_session_factory

    async with async_session_factory() as session:
        yield session
        await session.commit()


async def _session_context():
    """Context manager for CLI session."""
    from app.db.session import async_session_factory

    session = async_session_factory()
    s = await session.__aenter__()
    return s, session


@click.group()
@click.version_option(version="0.1.0", prog_name="agentmemorydb")
def cli() -> None:
    """AgentMemoryDB CLI — management and operations tool."""
    pass


@cli.command()
def health() -> None:
    """Check if the database is reachable."""

    async def _health() -> None:
        from sqlalchemy import text

        from app.db.session import engine

        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                click.echo(click.style("✓ Database connection: OK", fg="green"))

                # Check pgvector
                try:
                    await conn.execute(text("SELECT 'test'::vector(3)"))
                    click.echo(click.style("✓ pgvector extension: OK", fg="green"))
                except Exception:
                    click.echo(click.style("✗ pgvector extension: NOT AVAILABLE", fg="yellow"))

                # Table count
                r = await conn.execute(
                    text(
                        "SELECT count(*) FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                )
                table_count = r.scalar()
                click.echo(f"  Tables in database: {table_count}")

            await engine.dispose()
        except Exception as exc:
            click.echo(click.style(f"✗ Database connection failed: {exc}", fg="red"))
            sys.exit(1)

    _run_async(_health())


@cli.command()
@click.option("--user-id", required=True, help="User UUID")
def stats(user_id: str) -> None:
    """Show memory statistics for a user."""

    async def _stats() -> None:
        from sqlalchemy import func, select

        from app.db.session import async_session_factory
        from app.models.memory import Memory

        uid = uuid.UUID(user_id)
        async with async_session_factory() as session:
            # Total memories
            total = (
                await session.execute(select(func.count()).where(Memory.user_id == uid))
            ).scalar() or 0

            # By status
            status_stmt = (
                select(Memory.status, func.count())
                .where(Memory.user_id == uid)
                .group_by(Memory.status)
            )
            status_result = await session.execute(status_stmt)
            by_status = {row[0]: row[1] for row in status_result.all()}

            # By type
            type_stmt = (
                select(Memory.memory_type, func.count())
                .where(Memory.user_id == uid)
                .group_by(Memory.memory_type)
            )
            type_result = await session.execute(type_stmt)
            by_type = {row[0]: row[1] for row in type_result.all()}

            # By scope
            scope_stmt = (
                select(Memory.scope, func.count())
                .where(Memory.user_id == uid)
                .group_by(Memory.scope)
            )
            scope_result = await session.execute(scope_stmt)
            by_scope = {row[0]: row[1] for row in scope_result.all()}

            # Average scores
            avg_stmt = select(
                func.avg(Memory.importance_score),
                func.avg(Memory.confidence),
                func.avg(Memory.recency_score),
            ).where(Memory.user_id == uid, Memory.status == "active")
            avg_result = await session.execute(avg_stmt)
            avgs = avg_result.one()

        click.echo(f"\n📊 Memory Statistics for user {user_id[:8]}…\n")
        click.echo(f"  Total memories:    {total}")
        click.echo("\n  By status:")
        for s, c in sorted(by_status.items()):
            click.echo(f"    {s:15s}  {c}")
        click.echo("\n  By type:")
        for t, c in sorted(by_type.items()):
            click.echo(f"    {t:15s}  {c}")
        click.echo("\n  By scope:")
        for s, c in sorted(by_scope.items()):
            click.echo(f"    {s:15s}  {c}")
        if avgs[0] is not None:
            click.echo(f"\n  Avg importance:    {avgs[0]:.3f}")
            click.echo(f"  Avg confidence:    {avgs[1]:.3f}")
            click.echo(f"  Avg recency:       {avgs[2]:.3f}")

    _run_async(_stats())


@cli.command("export")
@click.option("--user-id", required=True, help="User UUID")
@click.option("--output", "-o", default="-", help="Output file (default: stdout)")
@click.option("--no-versions", is_flag=True, help="Exclude version history")
@click.option("--no-links", is_flag=True, help="Exclude memory links")
def export_cmd(user_id: str, output: str, no_versions: bool, no_links: bool) -> None:
    """Export all memories for a user to JSON."""

    async def _export() -> None:
        from app.db.session import async_session_factory
        from app.services.import_export_service import ImportExportService

        uid = uuid.UUID(user_id)
        async with async_session_factory() as session:
            svc = ImportExportService(session)
            data = await svc.export_memories(
                uid,
                include_versions=not no_versions,
                include_links=not no_links,
            )

        json_str = json.dumps(data, indent=2, default=str)
        if output == "-":
            click.echo(json_str)
        else:
            with open(output, "w") as f:
                f.write(json_str)
            click.echo(f"✓ Exported {data['memory_count']} memories to {output}")

    _run_async(_export())


@cli.command("import")
@click.option("--user-id", required=True, help="User UUID")
@click.option("--input", "-i", "input_file", required=True, help="Input JSON file")
@click.option(
    "--strategy",
    type=click.Choice(["upsert", "skip_existing", "overwrite"]),
    default="upsert",
)
def import_cmd(user_id: str, input_file: str, strategy: str) -> None:
    """Import memories from a JSON export file."""

    async def _import() -> None:
        from app.db.session import async_session_factory
        from app.services.import_export_service import ImportExportService

        uid = uuid.UUID(user_id)
        with open(input_file) as f:
            data = json.load(f)

        async with async_session_factory() as session:
            svc = ImportExportService(session)
            result = await svc.import_memories(uid, data, strategy=strategy)
            await session.commit()

        click.echo(
            f"✓ Import complete: {result['imported']} imported, "
            f"{result['skipped']} skipped, {result['errors']} errors"
        )

    _run_async(_import())


@cli.command("archive-stale")
def archive_stale() -> None:
    """Archive memories past their expiration or validity window."""

    async def _archive() -> None:
        from app.db.session import async_session_factory
        from app.workers.stale_memory_archiver import archive_stale_memories

        async with async_session_factory() as session:
            count = await archive_stale_memories(session)
        click.echo(f"✓ Archived {count} stale memories")

    _run_async(_archive())


@cli.command("recompute-recency")
def recompute_recency() -> None:
    """Recompute recency scores for all active memories."""

    async def _recompute() -> None:
        from app.db.session import async_session_factory
        from app.workers.stale_memory_archiver import recompute_recency_scores

        async with async_session_factory() as session:
            count = await recompute_recency_scores(session)
        click.echo(f"✓ Updated recency scores for {count} memories")

    _run_async(_recompute())


@cli.command("consolidate")
@click.option("--user-id", required=True, help="User UUID")
def consolidate(user_id: str) -> None:
    """Auto-consolidate duplicate memories for a user."""

    async def _consolidate() -> None:
        from app.db.session import async_session_factory
        from app.services.consolidation_service import ConsolidationService

        uid = uuid.UUID(user_id)
        async with async_session_factory() as session:
            svc = ConsolidationService(session)
            result = await svc.auto_consolidate(uid)
            await session.commit()

        click.echo(
            f"✓ Found {result['duplicate_groups_found']} duplicate groups, "
            f"merged {result['memories_merged']} memories"
        )

    _run_async(_consolidate())


@cli.command("boost-importance")
@click.option("--user-id", required=True, help="User UUID")
@click.option("--window-hours", default=168, help="Lookback window in hours (default: 168 = 7d)")
def boost_importance(user_id: str, window_hours: int) -> None:
    """Auto-boost importance scores based on access frequency."""

    async def _boost() -> None:
        from app.db.session import async_session_factory
        from app.services.access_tracking_service import AccessTrackingService

        uid = uuid.UUID(user_id)
        async with async_session_factory() as session:
            svc = AccessTrackingService(session)
            boosted = await svc.auto_boost_importance(uid, window_hours=window_hours)
            await session.commit()

        click.echo(f"✓ Boosted importance for {boosted} memories")

    _run_async(_boost())


if __name__ == "__main__":
    cli()
