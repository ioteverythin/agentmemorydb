"""MCP tool definitions for AgentMemoryDB.

Each tool is exposed to AI agents via the Model Context Protocol.
Tools are designed to be *intent-based* — agents express what they
want to do ("store a memory", "recall relevant context") rather
than issuing raw CRUD calls.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
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
            scope=arguments.get("scope", "user"),
            content=arguments["content"],
            payload=arguments.get("payload"),
            source_type=arguments.get("source_type", "agent_inference"),
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
            run_id=uuid.UUID(arguments["run_id"]) if arguments.get("run_id") else None,
            event_type=arguments.get("event_type", "agent_message"),
            content=arguments["content"],
            metadata=arguments.get("metadata"),
        )
        event = await svc.create(data)
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
    """Find and merge duplicate/near-duplicate memories."""
    from app.services.consolidation_service import ConsolidationService

    async with async_session_factory() as session:
        svc = ConsolidationService(session)
        report = await svc.auto_consolidate(
            user_id=uuid.UUID(arguments["user_id"]),
        )
        await session.commit()

        return {
            "user_id": arguments["user_id"],
            "dry_run": arguments.get("dry_run", True),
            "duplicates_found": report.get("duplicate_groups_found", 0),
            "merged": report.get("memories_merged", 0),
            "details": [],
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
                        "human_input",
                        "agent_inference",
                        "system_inference",
                        "external_api",
                        "reflection",
                        "consolidated",
                    ],
                    "default": "agent_inference",
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
                        "user_message",
                        "agent_message",
                        "tool_call",
                        "tool_result",
                        "system_event",
                        "observation",
                        "reflection",
                    ],
                    "default": "agent_message",
                },
                "run_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "Optional agent run ID.",
                },
                "metadata": {"type": "object", "description": "Optional structured metadata."},
            },
            "required": ["user_id", "content"],
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
}
