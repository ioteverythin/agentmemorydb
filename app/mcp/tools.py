"""MCP tool definitions for EngramDB.

Each tool is exposed to AI agents via the Model Context Protocol.
Tools are designed to be *intent-based* — agents express what they
want to do ("store a memory", "recall relevant context") rather
than issuing raw CRUD calls.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.db import async_session_factory
from app.schemas.memory import MemorySearchRequest, MemoryUpsert


@dataclass
class ToolDefinition:
    """An MCP tool definition with handler."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
    # API-key scope the caller must hold. Set for destructive tools; the server
    # enforces it before the handler runs.
    requires_scope: str | None = None
    # Settings attribute that must be True for this tool to be listed/callable.
    # Keeps opt-in tools invisible until deliberately enabled.
    requires_flag: str | None = None


# ─── Tool Handlers ───────────────────────────────────────────────


async def handle_store_memory(arguments: dict[str, Any]) -> dict[str, Any]:
    """Store or update a memory in the agent's memory system."""
    from app.services.memory_service import MemoryService

    async with async_session_factory() as session:
        svc = MemoryService(session)
        data = MemoryUpsert(
            user_id=uuid.UUID(arguments["user_id"]),
            memory_key=arguments["memory_key"],
            memory_type=arguments.get("memory_type", "semantic"),
            layer=arguments.get("layer", "atom"),
            scope=arguments.get("scope", "user"),
            content=arguments["content"],
            payload=arguments.get("payload"),
            source_type=arguments.get("source_type", "system_inference"),
            confidence=arguments.get("confidence", 0.7),
            importance_score=arguments.get("importance_score", 0.5),
            project_id=uuid.UUID(arguments["project_id"]) if arguments.get("project_id") else None,
            is_contradiction=arguments.get("is_contradiction", False),
        )
        memory, is_new = await svc.upsert(data)
        await session.commit()

        return {
            "memory_id": str(memory.id),
            "memory_key": memory.memory_key,
            "is_new": is_new,
            "version": memory.version,
            "status": memory.status,
            "message": f"Memory {'created' if is_new else 'updated'} successfully.",
        }


async def handle_recall_memories(arguments: dict[str, Any]) -> dict[str, Any]:
    """Search the memory system for relevant memories."""
    from app.services.retrieval_service import RetrievalService

    async with async_session_factory() as session:
        svc = RetrievalService(session)
        req = MemorySearchRequest(
            user_id=uuid.UUID(arguments["user_id"]),
            query_text=arguments.get("query_text"),
            memory_types=arguments.get("memory_types"),
            scopes=arguments.get("scopes"),
            top_k=arguments.get("top_k", 10),
            min_confidence=arguments.get("min_confidence"),
            project_id=uuid.UUID(arguments["project_id"]) if arguments.get("project_id") else None,
            explain=True,
        )
        response = await svc.search(req)

        results = []
        for item in response.results:
            entry: dict[str, Any] = {
                "memory_id": str(item.memory.id),
                "memory_key": item.memory.memory_key,
                "memory_type": item.memory.memory_type,
                "content": item.memory.content,
                "confidence": item.memory.confidence,
                "importance": item.memory.importance_score,
            }
            if item.score:
                entry["final_score"] = item.score.final_score
                entry["score_breakdown"] = {
                    "vector": item.score.vector_score,
                    "recency": item.score.recency_score,
                    "importance": item.score.importance_score,
                    "authority": item.score.authority_score,
                    "confidence": item.score.confidence_score,
                }
            results.append(entry)

        return {
            "query": arguments.get("query_text", ""),
            "total_candidates": response.total_candidates,
            "results": results,
        }


async def handle_get_memory(arguments: dict[str, Any]) -> dict[str, Any]:
    """Retrieve a specific memory by ID."""
    from app.repositories.memory_repository import MemoryRepository

    async with async_session_factory() as session:
        repo = MemoryRepository(session)
        memory = await repo.get_by_id(uuid.UUID(arguments["memory_id"]))
        if memory is None:
            return {"error": "Memory not found", "memory_id": arguments["memory_id"]}

        return {
            "memory_id": str(memory.id),
            "memory_key": memory.memory_key,
            "memory_type": memory.memory_type,
            "scope": memory.scope,
            "content": memory.content,
            "confidence": memory.confidence,
            "importance_score": memory.importance_score,
            "status": memory.status,
            "version": memory.version,
            "created_at": str(memory.created_at),
            "updated_at": str(memory.updated_at),
            "payload": memory.payload,
        }


async def handle_link_memories(arguments: dict[str, Any]) -> dict[str, Any]:
    """Create a typed relationship between two memories."""
    from app.repositories.memory_repository import MemoryRepository

    async with async_session_factory() as session:
        repo = MemoryRepository(session)
        link = await repo.create_link(
            source_id=uuid.UUID(arguments["source_memory_id"]),
            target_id=uuid.UUID(arguments["target_memory_id"]),
            link_type=arguments["link_type"],
            description=str(arguments.get("metadata", "")) or None,
        )
        await session.commit()

        return {
            "link_id": str(link.id),
            "source_memory_id": arguments["source_memory_id"],
            "target_memory_id": arguments["target_memory_id"],
            "link_type": arguments["link_type"],
            "message": "Memory link created successfully.",
        }


async def handle_record_event(arguments: dict[str, Any]) -> dict[str, Any]:
    """Record a raw event into the memory pipeline."""
    from app.services.event_service import EventService

    async with async_session_factory() as session:
        svc = EventService(session)
        from app.schemas.event import EventCreate

        data = EventCreate(
            user_id=uuid.UUID(arguments["user_id"]),
            run_id=uuid.UUID(arguments["run_id"]),
            event_type=arguments.get("event_type", "model_output"),
            content=arguments["content"],
            payload=arguments.get("payload"),
        )
        event = await svc.create_event(data)
        await session.commit()

        return {
            "event_id": str(event.id),
            "event_type": event.event_type,
            "message": "Event recorded successfully.",
        }


async def handle_explore_graph(arguments: dict[str, Any]) -> dict[str, Any]:
    """Explore the memory graph starting from a memory node."""
    from app.services.graph_service import GraphTraversalService

    async with async_session_factory() as session:
        svc = GraphTraversalService(session)
        nodes = await svc.expand(
            seed_memory_id=uuid.UUID(arguments["memory_id"]),
            max_hops=arguments.get("max_depth", 2),
            link_types=arguments.get("link_types"),
        )

        results = []
        for node in nodes:
            results.append(
                {
                    "memory_id": str(node["memory_id"]),
                    "memory_key": node["memory_key"],
                    "content": node["content"][:200],
                    "memory_type": node.get("memory_type", ""),
                    "status": node.get("status", ""),
                }
            )

        return {
            "origin": arguments["memory_id"],
            "max_depth": arguments.get("max_depth", 2),
            "connected_memories": results,
            "total_found": len(results),
        }


async def handle_consolidate_memories(arguments: dict[str, Any]) -> dict[str, Any]:
    """Find and (unless dry_run) merge duplicate/near-duplicate memories."""
    from app.services.consolidation_service import ConsolidationService

    user_id = uuid.UUID(arguments["user_id"])
    dry_run = arguments.get("dry_run", True)

    async with async_session_factory() as session:
        svc = ConsolidationService(session)

        if dry_run:
            # Preview only: report duplicate groups without any mutation.
            groups = await svc.find_exact_duplicates(user_id)
            details = [
                {
                    "content_hash": group[0].content_hash,
                    "count": len(group),
                    "memory_ids": [str(m.id) for m in group],
                }
                for group in groups
            ]
            # No commit — a preview must not persist anything.
            return {
                "user_id": arguments["user_id"],
                "dry_run": True,
                "duplicates_found": len(groups),
                "merged": 0,
                "details": details,
            }

        report = await svc.auto_consolidate(user_id=user_id)
        await session.commit()
        return {
            "user_id": arguments["user_id"],
            "dry_run": False,
            "duplicates_found": report.get("duplicate_groups_found", 0),
            "merged": report.get("memories_merged", 0),
            "details": [],
        }


async def handle_recall_memories_at_time(arguments: dict[str, Any]) -> dict[str, Any]:
    """Recall what the agent believed at a past instant (point-in-time recall).

    Same ranking as ``recall_memories``, but each fact is projected back to the
    generation that was valid at ``as_of`` — so an agent can answer "what did I
    know last March?" without confusing it with what it knows now.
    """
    from app.services.retrieval_service import RetrievalService

    as_of = datetime.fromisoformat(arguments["as_of"])
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=UTC)

    async with async_session_factory() as session:
        svc = RetrievalService(session)
        req = MemorySearchRequest(
            user_id=uuid.UUID(arguments["user_id"]),
            query_text=arguments.get("query_text"),
            memory_types=arguments.get("memory_types"),
            scopes=arguments.get("scopes"),
            top_k=arguments.get("top_k", 10),
            project_id=uuid.UUID(arguments["project_id"]) if arguments.get("project_id") else None,
            as_of=as_of,
            explain=False,
        )
        response = await svc.search(req)

        results = [
            {
                "memory_id": str(item.memory.id),
                "memory_key": item.memory.memory_key,
                "memory_type": item.memory.memory_type,
                "content": item.memory.content,
                "valid_from": str(item.memory.valid_from),
                "valid_to": str(item.memory.valid_to) if item.memory.valid_to else None,
                "version": item.memory.version,
            }
            for item in response.results
        ]
        return {
            "as_of": as_of.isoformat(),
            "query": arguments.get("query_text", ""),
            "total_candidates": response.total_candidates,
            "results": results,
        }


async def handle_forget_memory(arguments: dict[str, Any]) -> dict[str, Any]:
    """Hard-erase a memory, leaving an auditable tombstone.

    Irreversible. Gated twice: the ``MCP_ENABLE_FORGET`` flag must be on, and the
    calling API key must hold the ``erase`` scope.
    """
    from app.services.forgetting_service import ForgettingService

    async with async_session_factory() as session:
        report = await ForgettingService(session).erase_memory(
            uuid.UUID(arguments["memory_id"]),
            action="user_erasure",
            reason=arguments.get("reason"),
            triggered_by="mcp:forget_memory",
        )
        await session.commit()
        return {
            **report,
            "message": (
                "Memory erased. A forgetting-log tombstone retains only the "
                "SHA-256 of the deleted content."
            ),
        }


# ─── Tool Registry ──────────────────────────────────────────────

TOOL_REGISTRY: dict[str, ToolDefinition] = {
    "store_memory": ToolDefinition(
        name="store_memory",
        description=(
            "Store or update a memory in the agent's long-term memory system. "
            "Memories are versioned, deduplicated by content hash, and scored "
            "for relevance. Use this to persist facts, decisions, user preferences, "
            "or any knowledge the agent should remember across sessions."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "The user/owner of the memory.",
                },
                "memory_key": {
                    "type": "string",
                    "description": "A unique identifier key for this memory (e.g. 'user_preference_language').",
                },
                "content": {"type": "string", "description": "The textual content of the memory."},
                "memory_type": {
                    "type": "string",
                    "enum": ["working", "episodic", "semantic", "procedural"],
                    "default": "semantic",
                    "description": "The cognitive type of memory.",
                },
                "scope": {
                    "type": "string",
                    "enum": ["user", "project", "team", "global"],
                    "default": "user",
                    "description": "Visibility scope of the memory.",
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "default": 0.7,
                    "description": "How confident the agent is in this memory.",
                },
                "importance_score": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "default": 0.5,
                    "description": "How important this memory is.",
                },
                "source_type": {
                    "type": "string",
                    "enum": [
                        "user_input",
                        "tool_output",
                        "system_inference",
                        "human_verified",
                        "imported",
                    ],
                    "default": "system_inference",
                    "description": "Provenance (matches the server SourceType vocabulary).",
                },
                "layer": {
                    "type": "string",
                    "enum": ["raw", "atom", "scenario", "persona"],
                    "default": "atom",
                    "description": "Memory-pyramid layer.",
                },
                "project_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "Optional project scope.",
                },
                "payload": {"type": "object", "description": "Optional structured metadata."},
                "is_contradiction": {
                    "type": "boolean",
                    "default": False,
                    "description": "Whether this contradicts an existing memory.",
                },
            },
            "required": ["user_id", "memory_key", "content"],
        },
        handler=handle_store_memory,
    ),
    "recall_memories": ToolDefinition(
        name="recall_memories",
        description=(
            "Search and retrieve relevant memories using hybrid scoring. "
            "Combines vector similarity, recency, importance, authority, and "
            "confidence into a final relevance score. Use this to find context "
            "before answering questions or making decisions."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "The user whose memories to search.",
                },
                "query_text": {
                    "type": "string",
                    "description": "Natural language query to find relevant memories.",
                },
                "memory_types": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["working", "episodic", "semantic", "procedural"],
                    },
                    "description": "Filter to specific memory types.",
                },
                "scopes": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["user", "project", "team", "global"]},
                    "description": "Filter to specific scopes.",
                },
                "top_k": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "default": 10,
                    "description": "Number of results to return.",
                },
                "min_confidence": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "description": "Minimum confidence threshold.",
                },
                "project_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "Optional project filter.",
                },
            },
            "required": ["user_id"],
        },
        handler=handle_recall_memories,
    ),
    "get_memory": ToolDefinition(
        name="get_memory",
        description="Retrieve a specific memory by its ID. Returns full details including content, metadata, and versioning info.",
        input_schema={
            "type": "object",
            "properties": {
                "memory_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "The ID of the memory to retrieve.",
                },
            },
            "required": ["memory_id"],
        },
        handler=handle_get_memory,
    ),
    "link_memories": ToolDefinition(
        name="link_memories",
        description=(
            "Create a typed relationship between two memories in the knowledge graph. "
            "Use to express that one memory supports, contradicts, derives from, "
            "or is related to another."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "source_memory_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "The source memory.",
                },
                "target_memory_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "The target memory.",
                },
                "link_type": {
                    "type": "string",
                    "enum": ["derived_from", "contradicts", "supports", "related_to", "supersedes"],
                    "description": "The type of relationship.",
                },
                "metadata": {"type": "object", "description": "Optional metadata about the link."},
            },
            "required": ["source_memory_id", "target_memory_id", "link_type"],
        },
        handler=handle_link_memories,
    ),
    "record_event": ToolDefinition(
        name="record_event",
        description=(
            "Record a raw event into the memory pipeline. Events are the entry "
            "point for the Event → Observation → Memory lifecycle. Use for "
            "logging agent actions, user inputs, or system events."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "The user associated with the event.",
                },
                "content": {"type": "string", "description": "The event content/description."},
                "event_type": {
                    "type": "string",
                    "enum": [
                        "user_input",
                        "tool_call",
                        "tool_result",
                        "planner_step",
                        "action_taken",
                        "model_output",
                        "system_note",
                    ],
                    "default": "model_output",
                    "description": "Event category (matches the server EventType vocabulary).",
                },
                "run_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "The agent run this event belongs to (required — events are run-scoped).",
                },
                "payload": {"type": "object", "description": "Optional structured metadata."},
            },
            "required": ["user_id", "content", "run_id"],
        },
        handler=handle_record_event,
    ),
    "explore_graph": ToolDefinition(
        name="explore_graph",
        description=(
            "Explore the memory knowledge graph starting from a specific memory. "
            "Uses breadth-first traversal to discover connected memories through "
            "typed relationships (supports, contradicts, derived_from, etc.)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "memory_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "The starting memory node.",
                },
                "max_depth": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5,
                    "default": 2,
                    "description": "Maximum traversal depth.",
                },
                "link_types": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "derived_from",
                            "contradicts",
                            "supports",
                            "related_to",
                            "supersedes",
                        ],
                    },
                    "description": "Filter to specific link types.",
                },
            },
            "required": ["memory_id"],
        },
        handler=handle_explore_graph,
    ),
    "consolidate_memories": ToolDefinition(
        name="consolidate_memories",
        description=(
            "Find and optionally merge duplicate or near-duplicate memories for "
            "a user. Detects exact and semantic duplicates. Use dry_run=true to "
            "preview what would be merged."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "The user whose memories to consolidate.",
                },
                "similarity_threshold": {
                    "type": "number",
                    "minimum": 0.5,
                    "maximum": 1.0,
                    "default": 0.92,
                    "description": "Similarity threshold for near-duplicates.",
                },
                "dry_run": {
                    "type": "boolean",
                    "default": True,
                    "description": "If true, only preview without merging.",
                },
            },
            "required": ["user_id"],
        },
        handler=handle_consolidate_memories,
    ),
    "recall_memories_at_time": ToolDefinition(
        name="recall_memories_at_time",
        description=(
            "Recall memories as they stood at a past instant — point-in-time "
            "retrieval over the bitemporal fact history. Use this when the "
            "question is about the past ('what did we believe in March?', 'what "
            "was the user's address before they moved?') rather than the present. "
            "Facts that have since been superseded are returned in the generation "
            "that was valid at that time."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "The user whose memories to search.",
                },
                "as_of": {
                    "type": "string",
                    "format": "date-time",
                    "description": "ISO-8601 instant to recall at (assumed UTC if no offset).",
                },
                "query_text": {
                    "type": "string",
                    "description": "Natural language query to find relevant memories.",
                },
                "memory_types": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["working", "episodic", "semantic", "procedural"],
                    },
                    "description": "Filter to specific memory types.",
                },
                "scopes": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["user", "project", "team", "global"]},
                    "description": "Filter to specific scopes.",
                },
                "top_k": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "default": 10,
                    "description": "Number of results to return.",
                },
                "project_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "Optional project filter.",
                },
            },
            "required": ["user_id", "as_of"],
        },
        handler=handle_recall_memories_at_time,
    ),
    "forget_memory": ToolDefinition(
        name="forget_memory",
        description=(
            "Permanently erase a memory (GDPR right-to-be-forgotten). This is "
            "IRREVERSIBLE: the content and all its versions are deleted, and only "
            "an audit tombstone with a SHA-256 of the erased content remains. "
            "Prefer archiving via memory status for ordinary cleanup; use this "
            "only for an explicit deletion request."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "memory_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "The memory to erase.",
                },
                "reason": {
                    "type": "string",
                    "description": "Why it is being erased — recorded in the forgetting log.",
                },
            },
            "required": ["memory_id"],
        },
        handler=handle_forget_memory,
        requires_scope="erase",
        requires_flag="mcp_enable_forget",
    ),
}
