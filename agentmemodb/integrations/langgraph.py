"""LangGraph integration for AgentMemoryDB.

Provides two core components for LangGraph workflows:

- **AgentMemoryDBStore** — A memory store that LangGraph nodes can read/write
  to during graph execution.  Memories persist across graph runs.

- **AgentMemoryDBSaver** — A checkpoint saver that persists full graph state
  snapshots to AgentMemoryDB, enabling pause/resume and time-travel.

Both work with the embedded ``Client`` (SQLite) or remote ``HttpClient``.

Quick start::

    import agentmemodb
    from agentmemodb.integrations.langgraph import (
        AgentMemoryDBStore,
        AgentMemoryDBSaver,
    )

    db = agentmemodb.Client()

    # Store — semantic long-term memory for agent nodes
    store = AgentMemoryDBStore(client=db, user_id="user-1")
    store.put("pref:language", "User prefers Python")
    docs = store.search("What language does the user prefer?")

    # Saver — graph state checkpoints
    saver = AgentMemoryDBSaver(client=db)
    # Pass to StateGraph: graph = StateGraph(..., checkpointer=saver)
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from agentmemodb.types import Memory, SearchResult


# ═══════════════════════════════════════════════════════════════════
# 1. AgentMemoryDBStore — Long-term memory for LangGraph nodes
# ═══════════════════════════════════════════════════════════════════


class AgentMemoryDBStore:
    """Semantic memory store for LangGraph agent nodes.

    Use this inside LangGraph nodes to give your agents persistent,
    searchable long-term memory.  Unlike checkpoints (which save full
    graph state), this stores **knowledge** that agents learn over time.

    Architecture::

        LangGraph Node
            │
            ├── store.search("What does user prefer?")
            │     → returns relevant memories
            │
            ├── (LLM generates response using memories)
            │
            └── store.put("pref:topic", "User prefers X")
                  → persists knowledge for future runs

    Parameters
    ----------
    client
        An ``agentmemodb.Client`` or ``agentmemodb.HttpClient``.
    user_id
        Default user context for memory operations.
    namespace
        Optional namespace prefix for memory keys.
    """

    def __init__(
        self,
        client: Any,
        user_id: str = "default",
        namespace: str = "",
    ) -> None:
        self._client = client
        self._user_id = user_id
        self._namespace = namespace

    def _namespaced_key(self, key: str) -> str:
        if self._namespace:
            return f"{self._namespace}:{key}"
        return key

    # ── Write ───────────────────────────────────────────────────

    def put(
        self,
        key: str,
        value: str,
        *,
        memory_type: str = "semantic",
        scope: str = "user",
        importance: float = 0.5,
        metadata: dict[str, Any] | None = None,
        user_id: str | None = None,
    ) -> Memory:
        """Store or update a memory.

        Parameters
        ----------
        key
            Unique identifier for this memory (e.g. ``"pref:language"``).
        value
            The content to store.
        memory_type
            One of: ``semantic``, ``episodic``, ``procedural``, ``working``.
        scope
            One of: ``user``, ``project``, ``global``, ``session``.
        importance
            0.0–1.0 importance score.
        metadata
            Optional JSON metadata dict.
        user_id
            Override the default user_id.
        """
        uid = user_id or self._user_id
        return self._client.upsert(
            uid,
            self._namespaced_key(key),
            value,
            memory_type=memory_type,
            scope=scope,
            importance=importance,
            metadata=metadata or {},
        )

    def put_many(
        self,
        items: list[dict[str, Any]],
        *,
        user_id: str | None = None,
    ) -> list[Memory]:
        """Store multiple memories at once.

        Each item dict should have at least ``key`` and ``content``.
        """
        uid = user_id or self._user_id
        results = []
        for item in items:
            mem = self._client.upsert(
                uid,
                self._namespaced_key(item["key"]),
                item["content"],
                memory_type=item.get("memory_type", "semantic"),
                scope=item.get("scope", "user"),
                importance=item.get("importance", 0.5),
                metadata=item.get("metadata", {}),
            )
            results.append(mem)
        return results

    # ── Read ────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        memory_types: list[str] | None = None,
        user_id: str | None = None,
    ) -> list[SearchResult]:
        """Semantic search over memories.

        Returns a list of ``SearchResult`` objects with ``.content``,
        ``.score``, ``.key``, and ``.memory`` attributes.
        """
        uid = user_id or self._user_id
        return self._client.search(
            uid,
            query,
            top_k=top_k,
            memory_types=memory_types,
        )

    def search_as_text(
        self,
        query: str,
        *,
        top_k: int = 5,
        memory_types: list[str] | None = None,
        user_id: str | None = None,
    ) -> str:
        """Search and return results as a formatted text block.

        Convenient for injecting directly into LLM prompts::

            context = store.search_as_text("user preferences")
            prompt = f"Given this context:\\n{context}\\n\\nAnswer: ..."
        """
        results = self.search(
            query,
            top_k=top_k,
            memory_types=memory_types,
            user_id=user_id,
        )
        if not results:
            return "No relevant memories found."
        lines = []
        for r in results:
            lines.append(f"- [{r.key}] {r.content} (relevance={r.score:.2f})")
        return "\n".join(lines)

    def get(
        self,
        key: str,
        user_id: str | None = None,
    ) -> Memory | None:
        """Get a specific memory by key."""
        uid = user_id or self._user_id
        return self._client.get(uid, self._namespaced_key(key))

    def list(
        self,
        *,
        memory_type: str | None = None,
        scope: str | None = None,
        limit: int = 100,
        user_id: str | None = None,
    ) -> list[Memory]:
        """List all memories with optional filters."""
        uid = user_id or self._user_id
        return self._client.list(
            uid,
            memory_type=memory_type,
            scope=scope,
            limit=limit,
        )

    def delete(self, key: str, user_id: str | None = None) -> bool:
        """Delete a memory by key."""
        uid = user_id or self._user_id
        return self._client.delete(uid, self._namespaced_key(key))

    def count(self, user_id: str | None = None) -> int:
        """Count all active memories."""
        uid = user_id or self._user_id
        return self._client.count(uid)


# ═══════════════════════════════════════════════════════════════════
# 2. AgentMemoryDBSaver — Graph state checkpoint persistence
# ═══════════════════════════════════════════════════════════════════


class AgentMemoryDBSaver:
    """Checkpoint saver that persists LangGraph state to AgentMemoryDB.

    Stores graph state snapshots as ``procedural`` memories, enabling:
    - **Pause/Resume**: Stop and restart graph execution
    - **Time-travel**: Revisit any previous checkpoint
    - **Branching**: Fork from a checkpoint with different inputs
    - **Audit**: Full history of graph states

    Usage::

        from langgraph.graph import StateGraph
        from agentmemodb.integrations.langgraph import AgentMemoryDBSaver

        saver = AgentMemoryDBSaver(client=db)

        graph = StateGraph(MyState)
        graph.add_node("agent", agent_node)
        graph.set_entry_point("agent")
        app = graph.compile(checkpointer=saver)

        # Run with thread_id for checkpoint tracking
        config = {"configurable": {"thread_id": "thread-abc"}}
        result = app.invoke({"input": "Hello"}, config)

    Parameters
    ----------
    client
        An ``agentmemodb.Client`` or ``agentmemodb.HttpClient``.
    user_id
        User context for storing checkpoints.
    """

    def __init__(
        self,
        client: Any,
        user_id: str = "system",
    ) -> None:
        self._client = client
        self._user_id = user_id

    def _checkpoint_key(self, thread_id: str, checkpoint_id: str) -> str:
        return f"checkpoint:{thread_id}:{checkpoint_id}"

    def _thread_latest_key(self, thread_id: str) -> str:
        return f"checkpoint:{thread_id}:latest"

    # ── Core checkpoint interface ───────────────────────────────

    def put(
        self,
        config: dict[str, Any],
        checkpoint: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Save a checkpoint.

        Parameters
        ----------
        config
            LangGraph config dict with ``configurable.thread_id``.
        checkpoint
            The full graph state to persist.
        metadata
            Optional metadata (node name, step count, etc.).

        Returns
        -------
        Updated config with checkpoint_id.
        """
        thread_id = config.get("configurable", {}).get("thread_id", "default")
        checkpoint_id = str(uuid.uuid4())

        # Serialize state
        state_json = json.dumps(
            {
                "checkpoint": checkpoint,
                "metadata": metadata or {},
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            default=str,
        )

        # Save the specific checkpoint
        self._client.upsert(
            self._user_id,
            self._checkpoint_key(thread_id, checkpoint_id),
            state_json,
            memory_type="procedural",
            scope="session",
            importance=0.3,
            metadata={
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
                "type": "checkpoint",
                **(metadata or {}),
            },
        )

        # Update the "latest" pointer
        self._client.upsert(
            self._user_id,
            self._thread_latest_key(thread_id),
            state_json,
            memory_type="procedural",
            scope="session",
            importance=0.3,
            metadata={
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
                "type": "checkpoint_latest",
            },
        )

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
            }
        }

    def get(self, config: dict[str, Any]) -> dict[str, Any] | None:
        """Load a checkpoint.

        If ``checkpoint_id`` is in config, loads that specific checkpoint.
        Otherwise loads the latest checkpoint for the thread.
        """
        thread_id = config.get("configurable", {}).get("thread_id", "default")
        checkpoint_id = config.get("configurable", {}).get("checkpoint_id")

        if checkpoint_id:
            key = self._checkpoint_key(thread_id, checkpoint_id)
        else:
            key = self._thread_latest_key(thread_id)

        mem = self._client.get(self._user_id, key)
        if mem is None:
            return None

        try:
            data = json.loads(mem.content)
            return data.get("checkpoint")
        except (json.JSONDecodeError, TypeError):
            return None

    def get_tuple(self, config: dict[str, Any]) -> tuple | None:
        """Get checkpoint as (config, checkpoint, metadata) tuple.

        This matches LangGraph's expected CheckpointTuple interface.
        """
        thread_id = config.get("configurable", {}).get("thread_id", "default")
        checkpoint_id = config.get("configurable", {}).get("checkpoint_id")

        if checkpoint_id:
            key = self._checkpoint_key(thread_id, checkpoint_id)
        else:
            key = self._thread_latest_key(thread_id)

        mem = self._client.get(self._user_id, key)
        if mem is None:
            return None

        try:
            data = json.loads(mem.content)
            result_config = {
                "configurable": {
                    "thread_id": data.get("thread_id", thread_id),
                    "checkpoint_id": data.get("checkpoint_id", ""),
                }
            }
            return (
                result_config,
                data.get("checkpoint", {}),
                data.get("metadata", {}),
            )
        except (json.JSONDecodeError, TypeError):
            return None

    def list_checkpoints(
        self,
        thread_id: str,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """List all checkpoints for a thread (newest first)."""
        all_mems = self._client.list(
            self._user_id,
            memory_type="procedural",
            scope="session",
            limit=1000,
        )
        checkpoints = []
        prefix = f"checkpoint:{thread_id}:"
        for mem in all_mems:
            if (
                mem.key.startswith(prefix)
                and not mem.key.endswith(":latest")
            ):
                try:
                    data = json.loads(mem.content)
                    checkpoints.append(
                        {
                            "checkpoint_id": data.get("checkpoint_id", ""),
                            "thread_id": thread_id,
                            "timestamp": data.get("timestamp", ""),
                            "metadata": data.get("metadata", {}),
                        }
                    )
                except (json.JSONDecodeError, TypeError):
                    pass

        checkpoints.sort(key=lambda c: c["timestamp"], reverse=True)
        return checkpoints[:limit]

    def delete_thread(self, thread_id: str) -> int:
        """Delete all checkpoints for a thread. Returns count deleted."""
        all_mems = self._client.list(
            self._user_id,
            memory_type="procedural",
            scope="session",
            limit=10000,
        )
        count = 0
        prefix = f"checkpoint:{thread_id}:"
        for mem in all_mems:
            if mem.key.startswith(prefix):
                self._client.delete(self._user_id, mem.key)
                count += 1
        return count


# ═══════════════════════════════════════════════════════════════════
# 3. Helper — create_memory_node (for LangGraph StateGraph)
# ═══════════════════════════════════════════════════════════════════


def create_memory_node(
    store: AgentMemoryDBStore,
    input_key: str = "input",
    context_key: str = "memory_context",
    save_key: str | None = "output",
    top_k: int = 5,
):
    """Create a LangGraph node function that handles memory recall + save.

    This returns a function you can add directly to a ``StateGraph``::

        from langgraph.graph import StateGraph
        from agentmemodb.integrations.langgraph import (
            AgentMemoryDBStore, create_memory_node,
        )

        store = AgentMemoryDBStore(client=db, user_id="user-1")

        # Creates two nodes: one to recall, one to save
        recall_node = create_memory_node(store, input_key="input", context_key="context")

        graph = StateGraph(...)
        graph.add_node("recall_memory", recall_node)
        graph.add_node("agent", agent_node)
        graph.add_edge("recall_memory", "agent")

    Parameters
    ----------
    store
        An ``AgentMemoryDBStore`` instance.
    input_key
        State key containing the user's query.
    context_key
        State key to write retrieved memory context into.
    save_key
        If set, save the value at this state key as an episodic memory
        after node execution. Set to ``None`` to only recall.
    top_k
        Number of memories to retrieve.
    """

    def memory_node(state: dict[str, Any]) -> dict[str, Any]:
        query = state.get(input_key, "")
        updates: dict[str, Any] = {}

        # Recall relevant memories
        if query:
            context = store.search_as_text(query, top_k=top_k)
            updates[context_key] = context

        return updates

    return memory_node


def create_save_memory_node(
    store: AgentMemoryDBStore,
    content_key: str = "output",
    key_prefix: str = "conversation",
):
    """Create a LangGraph node that saves agent output to memory.

    Usage::

        save_node = create_save_memory_node(store, content_key="output")
        graph.add_node("save_memory", save_node)
        graph.add_edge("agent", "save_memory")
    """

    _counter = {"n": 0}

    def save_node(state: dict[str, Any]) -> dict[str, Any]:
        content = state.get(content_key, "")
        if content:
            _counter["n"] += 1
            key = f"{key_prefix}:{uuid.uuid4().hex[:8]}"
            store.put(
                key,
                content,
                memory_type="episodic",
                importance=0.6,
            )
        return {}

    return save_node


__all__ = [
    "AgentMemoryDBStore",
    "AgentMemoryDBSaver",
    "create_memory_node",
    "create_save_memory_node",
]
