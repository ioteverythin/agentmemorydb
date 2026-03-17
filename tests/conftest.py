"""Shared test fixtures."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio

# ── SQLite compatibility shims ──────────────────────────────────
# Register type compilers so Postgres-only types degrade to SQLite types.
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.db.base import Base
from app.utils.embedding_provider import DummyEmbeddingProvider, set_embedding_provider

# JSONB → JSON (SQLite stores as TEXT)
if not hasattr(SQLiteTypeCompiler, "visit_JSONB"):
    SQLiteTypeCompiler.visit_JSONB = lambda self, type_, **kw: "JSON"

# pgvector Vector → BLOB (unused by SQLite tests, just avoids compile error)
if not hasattr(SQLiteTypeCompiler, "visit_VECTOR"):

    def _visit_vector(self, type_, **kw):
        return "BLOB"

    SQLiteTypeCompiler.visit_VECTOR = _visit_vector

# ── Use in-memory SQLite for unit tests (no pgvector) ───────────
# Integration tests should point at a real Postgres via DATABASE_URL.

UNIT_TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


def _sqlite_create_all(connection):
    """Create all tables, skipping Postgres-specific indexes that SQLite can't handle."""
    # Temporarily remove Postgres-specific indexes, then create, then restore
    _removed_indexes: list[tuple[Any, Any]] = []
    for table in Base.metadata.sorted_tables:
        indexes_to_remove = []
        for idx in table.indexes:
            kw = idx.dialect_options.get("postgresql", {})
            if kw.get("using") in ("gin", "ivfflat", "hnsw"):
                indexes_to_remove.append(idx)
        for idx in indexes_to_remove:
            table.indexes.discard(idx)
            _removed_indexes.append((table, idx))

    Base.metadata.create_all(connection)

    # Restore indexes so the metadata object isn't permanently mutated
    for table, idx in _removed_indexes:
        table.indexes.add(idx)


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def unit_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an async session backed by in-memory SQLite.

    This is suitable for unit tests that do NOT require pgvector ops.
    Tables are created/dropped per test.
    """
    engine = create_async_engine(UNIT_TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(_sqlite_create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def integration_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an async session against the real Postgres test database.

    Requires DATABASE_URL env var pointing to a pgvector-enabled Postgres.
    Rolls back after each test for isolation.
    """
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        # Use a savepoint so we can roll back after each test
        async with session.begin():
            yield session
            await session.rollback()
    await engine.dispose()


@pytest.fixture(autouse=True)
def _use_dummy_embeddings() -> None:
    """Ensure all tests use the DummyEmbeddingProvider."""
    set_embedding_provider(DummyEmbeddingProvider(dim=8))


# ── Helpers ─────────────────────────────────────────────────────


def make_uuid() -> uuid.UUID:
    return uuid.uuid4()


def make_user_id() -> uuid.UUID:
    return uuid.uuid4()
