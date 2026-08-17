"""Tests for the MCP forgetting/temporal tools and their gates.

``forget_memory`` is the only MCP tool that destroys data, so it is gated twice:
by the ``MCP_ENABLE_FORGET`` flag and by the ``erase`` API-key scope. Both gates
are asserted here, along with the tool being invisible while disabled.
"""

from __future__ import annotations

import json
import uuid

import pytest

from app.core.config import settings
from app.mcp.server import MCPServer
from app.mcp.tools import TOOL_REGISTRY
from app.models.api_key import APIKey


def _key(scopes: str | None) -> APIKey:
    return APIKey(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        name="mcp",
        key_hash="x" * 64,
        key_prefix="amdb_test",
        scopes=scopes,
        is_active=True,
    )


async def _call(server: MCPServer, name: str, arguments: dict, **kwargs) -> dict:
    resp = await server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
        **kwargs,
    )
    result = resp["result"]
    return {
        "isError": result["isError"],
        "payload": json.loads(result["content"][0]["text"]),
    }


@pytest.mark.unit
class TestToolRegistry:
    def test_new_tools_are_registered(self):
        assert "recall_memories_at_time" in TOOL_REGISTRY
        assert "forget_memory" in TOOL_REGISTRY

    def test_recall_at_time_requires_as_of(self):
        schema = TOOL_REGISTRY["recall_memories_at_time"].input_schema
        assert schema["required"] == ["user_id", "as_of"]

    def test_forget_declares_its_gates(self):
        tool = TOOL_REGISTRY["forget_memory"]
        assert tool.requires_scope == "erase"
        assert tool.requires_flag == "mcp_enable_forget"

    def test_existing_tools_are_ungated(self):
        """Adding gates must not accidentally restrict the pre-existing tools."""
        for name in ("store_memory", "recall_memories", "get_memory"):
            assert TOOL_REGISTRY[name].requires_scope is None
            assert TOOL_REGISTRY[name].requires_flag is None


@pytest.mark.unit
class TestForgetToolGates:
    @pytest.mark.asyncio
    async def test_hidden_from_tools_list_by_default(self):
        assert settings.mcp_enable_forget is False
        resp = await MCPServer().handle_message(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        )
        names = {t["name"] for t in resp["result"]["tools"]}
        assert "forget_memory" not in names
        assert "recall_memories_at_time" in names

    @pytest.mark.asyncio
    async def test_listed_when_flag_enabled(self, monkeypatch):
        monkeypatch.setattr(settings, "mcp_enable_forget", True)
        resp = await MCPServer().handle_message(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        )
        assert "forget_memory" in {t["name"] for t in resp["result"]["tools"]}

    @pytest.mark.asyncio
    async def test_call_refused_while_flag_off(self):
        out = await _call(MCPServer(), "forget_memory", {"memory_id": str(uuid.uuid4())})
        assert out["isError"] is True
        assert "MCP_ENABLE_FORGET" in out["payload"]["error"]

    @pytest.mark.asyncio
    async def test_call_refused_without_erase_scope(self, monkeypatch):
        monkeypatch.setattr(settings, "mcp_enable_forget", True)
        out = await _call(
            MCPServer(),
            "forget_memory",
            {"memory_id": str(uuid.uuid4())},
            api_key=_key("memory:read,memory:write"),
        )
        assert out["isError"] is True
        assert "erase" in out["payload"]["error"]

    @pytest.mark.asyncio
    async def test_call_refused_for_unscoped_key(self, monkeypatch):
        monkeypatch.setattr(settings, "mcp_enable_forget", True)
        out = await _call(
            MCPServer(),
            "forget_memory",
            {"memory_id": str(uuid.uuid4())},
            api_key=_key(None),
        )
        assert out["isError"] is True

    @pytest.mark.asyncio
    async def test_scoped_key_passes_the_gate(self, monkeypatch):
        """With both gates satisfied the handler runs (and reports not-found)."""
        monkeypatch.setattr(settings, "mcp_enable_forget", True)
        out = await _call(
            MCPServer(),
            "forget_memory",
            {"memory_id": str(uuid.uuid4())},
            api_key=_key("erase"),
        )
        # It got past the gates and into the handler, which cannot find the row.
        assert out["isError"] is True
        assert "erase" not in out["payload"]["error"].lower()

    @pytest.mark.asyncio
    async def test_ungated_tools_are_not_blocked_without_a_key(self):
        """The new gates must not start rejecting the pre-existing tools."""
        out = await _call(MCPServer(), "get_memory", {"memory_id": str(uuid.uuid4())})
        # It reaches the handler (which needs a real DB here) rather than being
        # refused by a flag or scope gate.
        error = out["payload"].get("error", "")
        assert "scope" not in error
        assert "disabled" not in error
