"""MCP endpoint — HTTP transport for the Model Context Protocol."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.mcp.server import create_mcp_server

router = APIRouter()

# Singleton server instance
_mcp_server = create_mcp_server()


@router.post("/message")
async def mcp_message(request: Request):
    """Handle an MCP JSON-RPC 2.0 message.

    This endpoint receives MCP protocol messages and routes them to the
    appropriate handler. AI agents and MCP clients POST JSON-RPC requests here.

    Example request body:
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {}
        }
    """
    body = await request.json()
    response = await _mcp_server.handle_message(body)
    return JSONResponse(content=response)


@router.get("/tools")
async def list_mcp_tools():
    """List all available MCP tools (convenience endpoint).

    Returns the tools in a simplified format for documentation/discovery.
    """
    result = await _mcp_server.handle_message({
        "jsonrpc": "2.0",
        "id": "list",
        "method": "tools/list",
        "params": {},
    })
    tools = result.get("result", {}).get("tools", [])
    return {"tools": tools, "count": len(tools)}


@router.get("/schema")
async def mcp_schema():
    """Return the MCP server capabilities and schema reference."""
    result = await _mcp_server.handle_message({
        "jsonrpc": "2.0",
        "id": "init",
        "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "docs", "version": "0.0.0"}},
    })
    return result.get("result", {})
