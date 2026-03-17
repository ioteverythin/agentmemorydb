"""MCP transport layer — SSE (Server-Sent Events) and stdio transports.

Provides the communication layer between MCP clients and the
AgentMemoryDB MCP server. Supports:
- SSE transport for web-based agents (HTTP endpoint)
- Stdio transport for local agent processes (CLI pipe)
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from app.mcp.server import MCPServer, create_mcp_server


class SSETransport:
    """Server-Sent Events transport for MCP over HTTP.

    Used when agents connect via HTTP (e.g., Cursor, Claude Desktop).
    Mounted as a FastAPI endpoint.
    """

    def __init__(self, server: MCPServer | None = None) -> None:
        self._server = server or create_mcp_server()

    async def handle_sse_request(self, body: dict[str, Any]) -> dict[str, Any]:
        """Process a single JSON-RPC request and return the response."""
        return await self._server.handle_message(body)

    async def handle_sse_stream(self, body: dict[str, Any]):
        """Generator for SSE streaming responses."""
        response = await self._server.handle_message(body)
        yield {
            "event": "message",
            "data": json.dumps(response),
        }


class StdioTransport:
    """Stdio transport for MCP over stdin/stdout.

    Used when agents connect via subprocess pipes (local development,
    CLI-based agents). Reads JSON-RPC messages from stdin, writes
    responses to stdout.
    """

    def __init__(self, server: MCPServer | None = None) -> None:
        self._server = server or create_mcp_server()

    async def run(self) -> None:
        """Main loop: read from stdin, process, write to stdout."""
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)

        loop = asyncio.get_event_loop()
        await loop.connect_read_pipe(lambda: protocol, sys.stdin.buffer)

        writer_transport, writer_protocol = await loop.connect_write_pipe(
            asyncio.streams.FlowControlMixin, sys.stdout.buffer
        )
        writer = asyncio.StreamWriter(writer_transport, writer_protocol, None, loop)

        while True:
            try:
                line = await reader.readline()
                if not line:
                    break

                message = json.loads(line.decode("utf-8").strip())
                response = await self._server.handle_message(message)

                output = json.dumps(response) + "\n"
                writer.write(output.encode("utf-8"))
                await writer.drain()

            except json.JSONDecodeError:
                continue
            except Exception:
                break


async def run_stdio_server() -> None:
    """Entry point for running the MCP server in stdio mode."""
    transport = StdioTransport()
    await transport.run()
