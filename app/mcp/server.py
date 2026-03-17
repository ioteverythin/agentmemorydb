"""MCP server implementation for AgentMemoryDB.

Provides a JSON-RPC 2.0 compliant MCP server that exposes memory
operations as tools. Agents using Claude, Cursor, or any MCP-compatible
client can directly interact with the memory system.

Architecture inspired by InsForge's MCP semantic layer — instead of
exposing raw CRUD, we expose *intent-based* memory operations that
agents can reason about.
"""

from __future__ import annotations

import json
from typing import Any

from app.mcp.tools import TOOL_REGISTRY, ToolDefinition

# ─── MCP Protocol Constants ──────────────────────────────────────
MCP_VERSION = "2024-11-05"
SERVER_NAME = "agentmemorydb"
SERVER_VERSION = "0.1.0"


class MCPServer:
    """Model Context Protocol server for AgentMemoryDB.

    Handles the JSON-RPC 2.0 messages for:
    - initialize / initialized
    - tools/list
    - tools/call
    - resources/list (memory metadata)
    """

    def __init__(self) -> None:
        self._initialized = False
        self._tools: dict[str, ToolDefinition] = TOOL_REGISTRY

    # ── Protocol Handlers ────────────────────────────────────────

    async def handle_message(self, message: dict[str, Any]) -> dict[str, Any]:
        """Route an incoming JSON-RPC 2.0 message to the correct handler."""
        method = message.get("method", "")
        msg_id = message.get("id")
        params = message.get("params", {})

        handler_map = {
            "initialize": self._handle_initialize,
            "initialized": self._handle_initialized,
            "tools/list": self._handle_tools_list,
            "tools/call": self._handle_tools_call,
            "resources/list": self._handle_resources_list,
            "resources/read": self._handle_resources_read,
            "ping": self._handle_ping,
        }

        handler = handler_map.get(method)
        if handler is None:
            return self._error_response(msg_id, -32601, f"Method not found: {method}")

        try:
            result = await handler(params)
            return self._success_response(msg_id, result)
        except Exception as exc:
            return self._error_response(msg_id, -32603, str(exc))

    # ── Initialize ───────────────────────────────────────────────

    async def _handle_initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        """Respond to initialize with server capabilities."""
        return {
            "protocolVersion": MCP_VERSION,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False},
            },
            "serverInfo": {
                "name": SERVER_NAME,
                "version": SERVER_VERSION,
            },
        }

    async def _handle_initialized(self, params: dict[str, Any]) -> dict[str, Any]:
        """Mark server as initialized."""
        self._initialized = True
        return {}

    # ── Tools ────────────────────────────────────────────────────

    async def _handle_tools_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """Return the list of available MCP tools."""
        tools = []
        for name, tool_def in self._tools.items():
            tools.append(
                {
                    "name": name,
                    "description": tool_def.description,
                    "inputSchema": tool_def.input_schema,
                }
            )
        return {"tools": tools}

    async def _handle_tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        """Execute an MCP tool call."""
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        tool_def = self._tools.get(tool_name)
        if tool_def is None:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps({"error": f"Unknown tool: {tool_name}"}),
                    }
                ],
                "isError": True,
            }

        try:
            result = await tool_def.handler(arguments)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, default=str),
                    }
                ],
                "isError": False,
            }
        except Exception as exc:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps({"error": str(exc)}),
                    }
                ],
                "isError": True,
            }

    # ── Resources ────────────────────────────────────────────────

    async def _handle_resources_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """List available MCP resources (memory system metadata)."""
        return {
            "resources": [
                {
                    "uri": "agentmemorydb://stats",
                    "name": "Memory System Statistics",
                    "description": "Overview of the memory system: counts, types, health.",
                    "mimeType": "application/json",
                },
                {
                    "uri": "agentmemorydb://schema",
                    "name": "Memory Schema Reference",
                    "description": "Available memory types, scopes, statuses, and link types.",
                    "mimeType": "application/json",
                },
            ]
        }

    async def _handle_resources_read(self, params: dict[str, Any]) -> dict[str, Any]:
        """Read an MCP resource by URI."""
        uri = params.get("uri", "")

        if uri == "agentmemorydb://schema":
            return {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "application/json",
                        "text": json.dumps(
                            {
                                "memory_types": ["working", "episodic", "semantic", "procedural"],
                                "memory_scopes": ["user", "project", "team", "global"],
                                "memory_statuses": [
                                    "active",
                                    "superseded",
                                    "stale",
                                    "archived",
                                    "retracted",
                                ],
                                "link_types": [
                                    "derived_from",
                                    "contradicts",
                                    "supports",
                                    "related_to",
                                    "supersedes",
                                ],
                                "source_types": [
                                    "human_input",
                                    "agent_inference",
                                    "system_inference",
                                    "external_api",
                                    "reflection",
                                    "consolidated",
                                ],
                                "scoring_weights": {
                                    "vector": 0.45,
                                    "recency": 0.20,
                                    "importance": 0.15,
                                    "authority": 0.10,
                                    "confidence": 0.10,
                                },
                            }
                        ),
                    }
                ]
            }

        if uri == "agentmemorydb://stats":
            return {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "application/json",
                        "text": json.dumps(
                            {
                                "status": "operational",
                                "server": SERVER_NAME,
                                "version": SERVER_VERSION,
                                "protocol_version": MCP_VERSION,
                            }
                        ),
                    }
                ]
            }

        return {"contents": []}

    # ── Ping ─────────────────────────────────────────────────────

    async def _handle_ping(self, params: dict[str, Any]) -> dict[str, Any]:
        return {}

    # ── Helpers ──────────────────────────────────────────────────

    def _success_response(self, msg_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    def _error_response(self, msg_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def create_mcp_server() -> MCPServer:
    """Factory for creating an MCP server instance."""
    return MCPServer()
