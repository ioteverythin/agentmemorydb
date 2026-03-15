"""SQLite-backed vector store for the embedded AgentMemoryDB client.

Uses plain ``sqlite3`` (stdlib) for storage and ``numpy`` for
in-memory cosine-similarity search.  No PostgreSQL, no pgvector,
no server required.

Performance note
----------------
Vector search loads all active embeddings for the target user into
memory and computes cosine similarity in NumPy.  This is efficient
for datasets up to ~100 K memories per user.  For larger workloads,
use the full server with pgvector.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import struct
import uuid
from datetime import datetime, timezone
from typing import Any

import numpy as np

from agentmemodb.types import Memory, MemoryVersion, SearchResult


class SQLiteStore:
    """Synchronous SQLite store with in-memory vector search."""

    def __init__(self, path: str, dimension: int = 128) -> None:
        self._dimension = dimension

        if path != ":memory:":
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)

        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._create_tables()

    # ── Schema ──────────────────────────────────────────────────

    def _create_tables(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id            TEXT PRIMARY KEY,
                user_id       TEXT NOT NULL,
                memory_key    TEXT NOT NULL,
                memory_type   TEXT NOT NULL DEFAULT 'semantic',
                scope         TEXT NOT NULL DEFAULT 'user',
                status        TEXT NOT NULL DEFAULT 'active',
                content       TEXT NOT NULL,
                content_hash  TEXT NOT NULL,
                embedding     BLOB,
                importance_score  REAL NOT NULL DEFAULT 0.5,
                confidence        REAL NOT NULL DEFAULT 0.5,
                authority_level   REAL NOT NULL DEFAULT 0.0,
                payload       TEXT,
                version       INTEGER NOT NULL DEFAULT 1,
                created_at    TEXT NOT NULL,
                updated_at    TEXT NOT NULL,
                UNIQUE(user_id, memory_key)
            );

            CREATE INDEX IF NOT EXISTS idx_mem_user   ON memories(user_id);
            CREATE INDEX IF NOT EXISTS idx_mem_status ON memories(status);
            CREATE INDEX IF NOT EXISTS idx_mem_type   ON memories(memory_type);
            CREATE INDEX IF NOT EXISTS idx_mem_hash   ON memories(content_hash);

            CREATE TABLE IF NOT EXISTS memory_versions (
                id         TEXT PRIMARY KEY,
                memory_id  TEXT NOT NULL,
                version    INTEGER NOT NULL,
                content    TEXT NOT NULL,
                payload    TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_ver_mem ON memory_versions(memory_id);

            CREATE TABLE IF NOT EXISTS thread_messages (
                id         TEXT PRIMARY KEY,
                thread_id  TEXT NOT NULL,
                role       TEXT NOT NULL,
                content    TEXT NOT NULL,
                metadata   TEXT,
                seq        INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_msg_thread ON thread_messages(thread_id);
            CREATE INDEX IF NOT EXISTS idx_msg_seq    ON thread_messages(thread_id, seq);
        """
        )
        self._conn.commit()

    # ── Helpers ─────────────────────────────────────────────────

    @staticmethod
    def _content_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def _serialize_embedding(vec: list[float]) -> bytes:
        return struct.pack(f"<{len(vec)}f", *vec)

    @staticmethod
    def _deserialize_embedding(blob: bytes) -> list[float]:
        n = len(blob) // 4
        return list(struct.unpack(f"<{n}f", blob))

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _row_to_memory(self, row: sqlite3.Row) -> Memory:
        return Memory(
            id=row["id"],
            user_id=row["user_id"],
            key=row["memory_key"],
            content=row["content"],
            memory_type=row["memory_type"],
            scope=row["scope"],
            status=row["status"],
            importance=row["importance_score"],
            confidence=row["confidence"],
            authority=row["authority_level"],
            metadata=json.loads(row["payload"]) if row["payload"] else {},
            version=row["version"],
            content_hash=row["content_hash"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _get_by_id(self, mem_id: str) -> Memory:
        row = self._conn.execute(
            "SELECT * FROM memories WHERE id = ?", (mem_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"Memory {mem_id} not found")
        return self._row_to_memory(row)

    # ── CRUD ────────────────────────────────────────────────────

    def upsert(
        self,
        user_id: str,
        key: str,
        content: str,
        embedding: list[float] | None = None,
        memory_type: str = "semantic",
        scope: str = "user",
        importance: float = 0.5,
        confidence: float = 0.5,
        authority: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[Memory, str]:
        """Upsert a memory.

        Returns ``(Memory, action)`` where *action* is one of
        ``'created'``, ``'updated'``, or ``'skipped'``.
        """
        ch = self._content_hash(content)
        now = self._now_iso()
        emb_blob = self._serialize_embedding(embedding) if embedding else None
        payload_json = json.dumps(metadata) if metadata else None

        row = self._conn.execute(
            "SELECT * FROM memories WHERE user_id = ? AND memory_key = ?",
            (user_id, key),
        ).fetchone()

        if row is None:
            # ── Create ──
            mem_id = str(uuid.uuid4())
            self._conn.execute(
                """INSERT INTO memories
                       (id, user_id, memory_key, memory_type, scope, status,
                        content, content_hash, embedding,
                        importance_score, confidence, authority_level,
                        payload, version, created_at, updated_at)
                   VALUES (?,?,?,?,?,'active', ?,?,?, ?,?,?, ?,1,?,?)""",
                (
                    mem_id, user_id, key, memory_type, scope,
                    content, ch, emb_blob,
                    importance, confidence, authority,
                    payload_json, now, now,
                ),
            )
            self._conn.commit()
            return self._get_by_id(mem_id), "created"

        # ── Dedup: skip if content unchanged ──
        if row["content_hash"] == ch:
            return self._row_to_memory(row), "skipped"

        # ── Update: snapshot previous version, then overwrite ──
        new_version = row["version"] + 1
        self._conn.execute(
            """INSERT INTO memory_versions
                   (id, memory_id, version, content, payload, created_at)
               VALUES (?,?,?,?,?,?)""",
            (
                str(uuid.uuid4()), row["id"], row["version"],
                row["content"], row["payload"], now,
            ),
        )
        self._conn.execute(
            """UPDATE memories
               SET content=?, content_hash=?, embedding=?,
                   importance_score=?, confidence=?, authority_level=?,
                   payload=?, version=?, updated_at=?
               WHERE id=?""",
            (
                content, ch, emb_blob,
                importance, confidence, authority,
                payload_json, new_version, now,
                row["id"],
            ),
        )
        self._conn.commit()
        return self._get_by_id(row["id"]), "updated"

    def get(self, user_id: str, key: str) -> Memory | None:
        row = self._conn.execute(
            "SELECT * FROM memories WHERE user_id = ? AND memory_key = ?",
            (user_id, key),
        ).fetchone()
        return self._row_to_memory(row) if row else None

    def get_by_id(self, memory_id: str) -> Memory | None:
        try:
            return self._get_by_id(memory_id)
        except KeyError:
            return None

    def list(
        self,
        user_id: str,
        memory_type: str | None = None,
        scope: str | None = None,
        status: str = "active",
        limit: int = 100,
        offset: int = 0,
    ) -> list[Memory]:
        query = "SELECT * FROM memories WHERE user_id = ? AND status = ?"
        params: list[Any] = [user_id, status]

        if memory_type:
            query += " AND memory_type = ?"
            params.append(memory_type)
        if scope:
            query += " AND scope = ?"
            params.append(scope)

        query += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_memory(r) for r in rows]

    def delete(self, user_id: str, key: str) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM memories WHERE user_id = ? AND memory_key = ?",
            (user_id, key),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def count(self, user_id: str, status: str = "active") -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS cnt FROM memories WHERE user_id = ? AND status = ?",
            (user_id, status),
        ).fetchone()
        return row["cnt"]  # type: ignore[index]

    def get_versions(self, memory_id: str) -> list[MemoryVersion]:
        rows = self._conn.execute(
            "SELECT * FROM memory_versions WHERE memory_id = ? ORDER BY version DESC",
            (memory_id,),
        ).fetchall()
        return [
            MemoryVersion(
                id=r["id"],
                memory_id=r["memory_id"],
                version=r["version"],
                content=r["content"],
                created_at=datetime.fromisoformat(r["created_at"]),
            )
            for r in rows
        ]

    # ── Vector search ───────────────────────────────────────────

    def search(
        self,
        user_id: str,
        query_embedding: list[float] | None = None,
        query_text: str | None = None,
        top_k: int = 10,
        memory_types: list[str] | None = None,
    ) -> list[SearchResult]:
        """Search by cosine similarity and/or keyword matching."""
        query = "SELECT * FROM memories WHERE user_id = ? AND status = 'active'"
        params: list[Any] = [user_id]

        if memory_types:
            placeholders = ",".join("?" * len(memory_types))
            query += f" AND memory_type IN ({placeholders})"
            params.extend(memory_types)

        rows = self._conn.execute(query, params).fetchall()
        if not rows:
            return []

        results: list[SearchResult] = []

        for row in rows:
            memory = self._row_to_memory(row)
            score = 0.0

            # Vector similarity (primary signal)
            if query_embedding and row["embedding"]:
                stored = np.array(self._deserialize_embedding(row["embedding"]))
                qvec = np.array(query_embedding)
                dot = float(np.dot(qvec, stored))
                norm_q = float(np.linalg.norm(qvec))
                norm_s = float(np.linalg.norm(stored))
                if norm_q > 0 and norm_s > 0:
                    score = dot / (norm_q * norm_s)

            # Keyword fallback when no embeddings available
            elif query_text:
                content_lower = memory.content.lower()
                words = query_text.lower().split()
                matches = sum(1 for w in words if w in content_lower)
                score = matches / max(len(words), 1)

            results.append(SearchResult(memory=memory, score=score))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    # ── Lifecycle ───────────────────────────────────────────────

    def reset(self) -> None:
        """Delete **all** data.  Use with caution."""
        self._conn.executescript(
            "DELETE FROM memory_versions; DELETE FROM thread_messages; DELETE FROM memories;"
        )
        self._conn.commit()

    # ── Thread messages (short-term conversation buffer) ────────

    def add_message(
        self,
        thread_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append a message to a conversation thread.

        Returns the message as a dict with ``id``, ``thread_id``,
        ``role``, ``content``, ``metadata``, ``seq``, ``created_at``.
        """
        now = self._now_iso()
        # Get next sequence number for this thread
        row = self._conn.execute(
            "SELECT COALESCE(MAX(seq), -1) + 1 AS next_seq "
            "FROM thread_messages WHERE thread_id = ?",
            (thread_id,),
        ).fetchone()
        seq = row["next_seq"]  # type: ignore[index]
        msg_id = str(uuid.uuid4())
        meta_json = json.dumps(metadata) if metadata else None

        self._conn.execute(
            """INSERT INTO thread_messages
                   (id, thread_id, role, content, metadata, seq, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (msg_id, thread_id, role, content, meta_json, seq, now),
        )
        self._conn.commit()
        return {
            "id": msg_id,
            "thread_id": thread_id,
            "role": role,
            "content": content,
            "metadata": metadata or {},
            "seq": seq,
            "created_at": now,
        }

    def get_messages(
        self,
        thread_id: str,
        limit: int | None = None,
        before_seq: int | None = None,
        after_seq: int | None = None,
        roles: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve messages for a thread, ordered by sequence.

        Parameters
        ----------
        thread_id : str
            The conversation thread ID.
        limit : int, optional
            Maximum number of messages to return.  When used alone,
            returns the **latest** N messages.
        before_seq : int, optional
            Only messages with ``seq < before_seq``.
        after_seq : int, optional
            Only messages with ``seq > after_seq``.
        roles : list[str], optional
            Filter by role (e.g. ``["user", "assistant"]``).
        """
        query = "SELECT * FROM thread_messages WHERE thread_id = ?"
        params: list[Any] = [thread_id]

        if before_seq is not None:
            query += " AND seq < ?"
            params.append(before_seq)
        if after_seq is not None:
            query += " AND seq > ?"
            params.append(after_seq)
        if roles:
            placeholders = ",".join("?" * len(roles))
            query += f" AND role IN ({placeholders})"
            params.extend(roles)

        query += " ORDER BY seq ASC"

        if limit is not None:
            # Get latest N messages: sub-query trick
            query = (
                f"SELECT * FROM ({query.replace('ASC', 'DESC')} LIMIT ?) "
                "ORDER BY seq ASC"
            )
            params.append(limit)

        rows = self._conn.execute(query, params).fetchall()
        return [
            {
                "id": r["id"],
                "thread_id": r["thread_id"],
                "role": r["role"],
                "content": r["content"],
                "metadata": json.loads(r["metadata"]) if r["metadata"] else {},
                "seq": r["seq"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def count_messages(self, thread_id: str) -> int:
        """Count messages in a thread."""
        row = self._conn.execute(
            "SELECT COUNT(*) AS cnt FROM thread_messages WHERE thread_id = ?",
            (thread_id,),
        ).fetchone()
        return row["cnt"]  # type: ignore[index]

    def clear_thread(self, thread_id: str) -> int:
        """Delete all messages in a thread.  Returns count deleted."""
        cursor = self._conn.execute(
            "DELETE FROM thread_messages WHERE thread_id = ?",
            (thread_id,),
        )
        self._conn.commit()
        return cursor.rowcount

    def list_threads(self) -> list[dict[str, Any]]:
        """List all conversation threads with message counts."""
        rows = self._conn.execute(
            """SELECT thread_id,
                      COUNT(*) AS message_count,
                      MIN(created_at) AS first_message_at,
                      MAX(created_at) AS last_message_at
               FROM thread_messages
               GROUP BY thread_id
               ORDER BY MAX(created_at) DESC"""
        ).fetchall()
        return [
            {
                "thread_id": r["thread_id"],
                "message_count": r["message_count"],
                "first_message_at": r["first_message_at"],
                "last_message_at": r["last_message_at"],
            }
            for r in rows
        ]

    def close(self) -> None:
        self._conn.close()
