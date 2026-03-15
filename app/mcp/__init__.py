"""MCP (Model Context Protocol) server for AgentMemoryDB.

Exposes memory operations as MCP tools so AI agents can
directly store, recall, and manage memories through the protocol.

Inspired by InsForge's MCP-first approach to agent interaction.
"""

from app.mcp.server import create_mcp_server

__all__ = ["create_mcp_server"]
