"""Comprehensive tests for InsForge-inspired features.

Covers:
- MCP Server (JSON-RPC 2.0 protocol)
- MCP Tool Registry and definitions
- WebSocket ConnectionManager + MemoryEvent
- Maintenance Scheduler (ScheduledJob + MaintenanceScheduler)
- Settings defaults for all new config options
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

# ═══════════════════════════════════════════════════════════════════
# 1. MCP Server Tests
# ═══════════════════════════════════════════════════════════════════
from app.mcp.server import MCP_VERSION, SERVER_NAME, SERVER_VERSION, MCPServer, create_mcp_server


@pytest.mark.unit
class TestMCPServerFactory:
    """Test MCPServer construction and factory."""

    def test_create_mcp_server(self):
        server = create_mcp_server()
        assert isinstance(server, MCPServer)

    def test_server_has_tools_registered(self):
        server = MCPServer()
        assert len(server._tools) > 0


@pytest.mark.unit
class TestMCPInitialize:
    """Test the initialize / initialized handshake."""

    @pytest.mark.asyncio
    async def test_initialize_returns_capabilities(self):
        server = MCPServer()
        msg = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        resp = await server.handle_message(msg)

        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 1
        assert "result" in resp
        result = resp["result"]
        assert result["protocolVersion"] == MCP_VERSION
        assert result["serverInfo"]["name"] == SERVER_NAME
        assert result["serverInfo"]["version"] == SERVER_VERSION
        assert "tools" in result["capabilities"]
        assert "resources" in result["capabilities"]

    @pytest.mark.asyncio
    async def test_initialized_marks_server(self):
        server = MCPServer()
        msg = {"jsonrpc": "2.0", "id": 2, "method": "initialized", "params": {}}
        resp = await server.handle_message(msg)

        assert resp["id"] == 2
        assert resp["result"] == {}
        assert server._initialized is True


@pytest.mark.unit
class TestMCPPing:
    """Test the ping handler."""

    @pytest.mark.asyncio
    async def test_ping_returns_empty(self):
        server = MCPServer()
        msg = {"jsonrpc": "2.0", "id": 3, "method": "ping", "params": {}}
        resp = await server.handle_message(msg)

        assert resp["result"] == {}


@pytest.mark.unit
class TestMCPToolsList:
    """Test tools/list returns all registered tools."""

    @pytest.mark.asyncio
    async def test_tools_list_returns_all_tools(self):
        server = MCPServer()
        msg = {"jsonrpc": "2.0", "id": 4, "method": "tools/list", "params": {}}
        resp = await server.handle_message(msg)

        tools = resp["result"]["tools"]
        assert len(tools) == 7
        tool_names = {t["name"] for t in tools}
        assert tool_names == {
            "store_memory",
            "recall_memories",
            "get_memory",
            "link_memories",
            "record_event",
            "explore_graph",
            "consolidate_memories",
        }

    @pytest.mark.asyncio
    async def test_each_tool_has_required_fields(self):
        server = MCPServer()
        msg = {"jsonrpc": "2.0", "id": 5, "method": "tools/list", "params": {}}
        resp = await server.handle_message(msg)

        for tool in resp["result"]["tools"]:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool
            assert tool["inputSchema"]["type"] == "object"
            assert "properties" in tool["inputSchema"]


@pytest.mark.unit
class TestMCPToolsCall:
    """Test tools/call dispatching."""

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self):
        server = MCPServer()
        msg = {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {"name": "nonexistent_tool", "arguments": {}},
        }
        resp = await server.handle_message(msg)
        result = resp["result"]
        assert result["isError"] is True
        content_text = json.loads(result["content"][0]["text"])
        assert "Unknown tool" in content_text["error"]

    @pytest.mark.asyncio
    async def test_tool_call_dispatches_to_handler(self):
        """Patch a tool handler and verify it gets called."""
        server = MCPServer()

        mock_handler = AsyncMock(return_value={"test": "result"})
        from app.mcp.tools import ToolDefinition

        server._tools["test_tool"] = ToolDefinition(
            name="test_tool",
            description="Test tool",
            input_schema={"type": "object", "properties": {}},
            handler=mock_handler,
        )

        msg = {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": "test_tool", "arguments": {"foo": "bar"}},
        }
        resp = await server.handle_message(msg)

        mock_handler.assert_called_once_with({"foo": "bar"})
        result = resp["result"]
        assert result["isError"] is False
        content = json.loads(result["content"][0]["text"])
        assert content["test"] == "result"

    @pytest.mark.asyncio
    async def test_tool_call_error_handling(self):
        """Tool handler that raises should return isError=True."""
        server = MCPServer()

        async def failing_handler(args):
            raise ValueError("something went wrong")

        from app.mcp.tools import ToolDefinition

        server._tools["failing_tool"] = ToolDefinition(
            name="failing_tool",
            description="Fails",
            input_schema={"type": "object", "properties": {}},
            handler=failing_handler,
        )

        msg = {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "tools/call",
            "params": {"name": "failing_tool", "arguments": {}},
        }
        resp = await server.handle_message(msg)
        result = resp["result"]
        assert result["isError"] is True
        content = json.loads(result["content"][0]["text"])
        assert "something went wrong" in content["error"]


@pytest.mark.unit
class TestMCPResources:
    """Test resources/list and resources/read."""

    @pytest.mark.asyncio
    async def test_resources_list(self):
        server = MCPServer()
        msg = {"jsonrpc": "2.0", "id": 9, "method": "resources/list", "params": {}}
        resp = await server.handle_message(msg)

        resources = resp["result"]["resources"]
        assert len(resources) == 2
        uris = {r["uri"] for r in resources}
        assert "agentmemorydb://stats" in uris
        assert "agentmemorydb://schema" in uris

    @pytest.mark.asyncio
    async def test_resources_read_schema(self):
        server = MCPServer()
        msg = {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "resources/read",
            "params": {"uri": "agentmemorydb://schema"},
        }
        resp = await server.handle_message(msg)

        contents = resp["result"]["contents"]
        assert len(contents) == 1
        schema = json.loads(contents[0]["text"])
        assert "memory_types" in schema
        assert "semantic" in schema["memory_types"]
        assert "scoring_weights" in schema

    @pytest.mark.asyncio
    async def test_resources_read_stats(self):
        server = MCPServer()
        msg = {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "resources/read",
            "params": {"uri": "agentmemorydb://stats"},
        }
        resp = await server.handle_message(msg)

        contents = resp["result"]["contents"]
        stats = json.loads(contents[0]["text"])
        assert stats["status"] == "operational"
        assert stats["server"] == SERVER_NAME

    @pytest.mark.asyncio
    async def test_resources_read_unknown(self):
        server = MCPServer()
        msg = {
            "jsonrpc": "2.0",
            "id": 12,
            "method": "resources/read",
            "params": {"uri": "agentmemorydb://nonexistent"},
        }
        resp = await server.handle_message(msg)
        assert resp["result"]["contents"] == []


@pytest.mark.unit
class TestMCPErrorHandling:
    """Test protocol-level error responses."""

    @pytest.mark.asyncio
    async def test_unknown_method_returns_error(self):
        server = MCPServer()
        msg = {"jsonrpc": "2.0", "id": 13, "method": "nonexistent/method", "params": {}}
        resp = await server.handle_message(msg)

        assert "error" in resp
        assert resp["error"]["code"] == -32601
        assert "Method not found" in resp["error"]["message"]

    @pytest.mark.asyncio
    async def test_response_structure(self):
        server = MCPServer()
        msg = {"jsonrpc": "2.0", "id": 42, "method": "ping", "params": {}}
        resp = await server.handle_message(msg)

        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 42


# ═══════════════════════════════════════════════════════════════════
# 2. MCP Tool Registry Tests
# ═══════════════════════════════════════════════════════════════════

from app.mcp.tools import TOOL_REGISTRY, ToolDefinition


@pytest.mark.unit
class TestToolRegistry:
    """Test the tool registry structure."""

    def test_all_tools_are_tool_definitions(self):
        for name, tool in TOOL_REGISTRY.items():
            assert isinstance(tool, ToolDefinition)
            assert tool.name == name

    def test_all_tools_have_handlers(self):
        for tool in TOOL_REGISTRY.values():
            assert callable(tool.handler)

    def test_store_memory_requires_fields(self):
        tool = TOOL_REGISTRY["store_memory"]
        required = tool.input_schema.get("required", [])
        assert "user_id" in required
        assert "memory_key" in required
        assert "content" in required

    def test_recall_memories_schema(self):
        tool = TOOL_REGISTRY["recall_memories"]
        props = tool.input_schema["properties"]
        assert "query_text" in props
        assert "top_k" in props
        assert "user_id" in tool.input_schema["required"]

    def test_link_memories_schema(self):
        tool = TOOL_REGISTRY["link_memories"]
        required = tool.input_schema["required"]
        assert "source_memory_id" in required
        assert "target_memory_id" in required
        assert "link_type" in required

    def test_explore_graph_schema(self):
        tool = TOOL_REGISTRY["explore_graph"]
        props = tool.input_schema["properties"]
        assert "memory_id" in props
        assert "max_depth" in props
        assert "memory_id" in tool.input_schema["required"]

    def test_consolidate_memories_schema(self):
        tool = TOOL_REGISTRY["consolidate_memories"]
        assert "user_id" in tool.input_schema["required"]

    def test_record_event_schema(self):
        tool = TOOL_REGISTRY["record_event"]
        required = tool.input_schema["required"]
        assert "user_id" in required
        assert "content" in required


# ═══════════════════════════════════════════════════════════════════
# 3. WebSocket ConnectionManager + MemoryEvent Tests
# ═══════════════════════════════════════════════════════════════════

from app.ws import ConnectionManager, MemoryEvent, MemoryEventTypes


@pytest.mark.unit
class TestMemoryEvent:
    """Test MemoryEvent construction and serialization."""

    def test_event_construction(self):
        event = MemoryEvent(
            event_type="memory.created",
            data={"memory_id": "abc123"},
            channels=["user:u1"],
        )
        assert event.event_type == "memory.created"
        assert event.data == {"memory_id": "abc123"}
        assert event.channels == ["user:u1"]
        assert event.id is not None
        assert event.timestamp is not None

    def test_event_to_dict(self):
        event = MemoryEvent(
            event_type="memory.updated",
            data={"key": "val"},
            channels=["global"],
        )
        d = event.to_dict()
        assert d["event"] == "memory.updated"
        assert d["data"] == {"key": "val"}
        assert d["channels"] == ["global"]
        assert "id" in d
        assert "timestamp" in d

    def test_event_default_channels(self):
        event = MemoryEvent(event_type="test", data={})
        assert event.channels == []

    def test_event_unique_ids(self):
        e1 = MemoryEvent(event_type="a", data={})
        e2 = MemoryEvent(event_type="b", data={})
        assert e1.id != e2.id


@pytest.mark.unit
class TestMemoryEventTypes:
    """Test predefined event type constants."""

    def test_standard_event_types_exist(self):
        assert MemoryEventTypes.MEMORY_CREATED == "memory.created"
        assert MemoryEventTypes.MEMORY_UPDATED == "memory.updated"
        assert MemoryEventTypes.MEMORY_ARCHIVED == "memory.archived"
        assert MemoryEventTypes.MEMORY_RETRACTED == "memory.retracted"
        assert MemoryEventTypes.MEMORY_LINKED == "memory.linked"
        assert MemoryEventTypes.MEMORY_CONSOLIDATED == "memory.consolidated"
        assert MemoryEventTypes.EVENT_RECORDED == "event.recorded"
        assert MemoryEventTypes.OBSERVATION_CREATED == "observation.created"
        assert MemoryEventTypes.SEARCH_EXECUTED == "search.executed"
        assert MemoryEventTypes.GRAPH_TRAVERSED == "graph.traversed"


@pytest.mark.unit
class TestConnectionManager:
    """Test WebSocket ConnectionManager logic using mock WebSockets."""

    @pytest.mark.asyncio
    async def test_connect_adds_connection(self):
        mgr = ConnectionManager()
        ws = AsyncMock()
        await mgr.connect(ws, channels=["user:u1"])

        assert mgr.active_connections == 1
        ws.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_removes_connection(self):
        mgr = ConnectionManager()
        ws = AsyncMock()
        await mgr.connect(ws, channels=["global"])
        await mgr.disconnect(ws)

        assert mgr.active_connections == 0

    @pytest.mark.asyncio
    async def test_default_channel_is_global(self):
        mgr = ConnectionManager()
        ws = AsyncMock()
        await mgr.connect(ws)  # no channels specified

        assert "global" in mgr.subscription_counts
        assert mgr.subscription_counts["global"] == 1

    @pytest.mark.asyncio
    async def test_subscribe_adds_channel(self):
        mgr = ConnectionManager()
        ws = AsyncMock()
        await mgr.connect(ws, channels=["user:u1"])
        await mgr.subscribe(ws, "project:p1")

        assert "project:p1" in mgr.subscription_counts
        assert mgr.subscription_counts["project:p1"] == 1

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_channel(self):
        from app.ws import ConnectionManager as CM

        mgr = CM()
        ws = AsyncMock()
        await mgr.connect(ws, channels=["user:u1"])
        await mgr.unsubscribe(ws, "user:u1")

        assert mgr.subscription_counts.get("user:u1", 0) == 0

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_subscribers(self):
        mgr = ConnectionManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()

        await mgr.connect(ws1, channels=["user:u1"])
        await mgr.connect(ws2, channels=["user:u2"])

        event = MemoryEvent(
            event_type="memory.created",
            data={"id": "test"},
            channels=["user:u1"],
        )
        await mgr.broadcast(event)

        # ws1 should receive (subscribed to user:u1)
        ws1.send_text.assert_called()
        sent = json.loads(ws1.send_text.call_args[0][0])
        assert sent["event"] == "memory.created"

    @pytest.mark.asyncio
    async def test_broadcast_global_reaches_all(self):
        mgr = ConnectionManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()

        await mgr.connect(ws1)  # default global
        await mgr.connect(ws2)

        event = MemoryEvent(
            event_type="test.event",
            data={},
            channels=[],  # no specific channel, but broadcast always includes 'global'
        )
        await mgr.broadcast(event)

        ws1.send_text.assert_called()
        ws2.send_text.assert_called()

    @pytest.mark.asyncio
    async def test_broadcast_cleans_dead_connections(self):
        mgr = ConnectionManager()
        ws_good = AsyncMock()
        ws_dead = AsyncMock()
        ws_dead.send_text.side_effect = Exception("connection closed")

        await mgr.connect(ws_good)
        await mgr.connect(ws_dead)

        event = MemoryEvent(event_type="test", data={}, channels=[])
        await mgr.broadcast(event)

        # Dead connection should be removed
        assert mgr.active_connections == 1

    @pytest.mark.asyncio
    async def test_multiple_channels_subscription(self):
        mgr = ConnectionManager()
        ws = AsyncMock()
        await mgr.connect(ws, channels=["user:u1", "project:p1", "global"])

        assert mgr.subscription_counts.get("user:u1") == 1
        assert mgr.subscription_counts.get("project:p1") == 1
        assert mgr.subscription_counts.get("global") == 1


# ═══════════════════════════════════════════════════════════════════
# 4. Scheduler Tests
# ═══════════════════════════════════════════════════════════════════

from app.workers.scheduler import MaintenanceScheduler, ScheduledJob, get_scheduler


@pytest.mark.unit
class TestScheduledJob:
    """Test ScheduledJob properties and state."""

    def test_new_job_is_due(self):
        job = ScheduledJob(
            name="test_job",
            handler=AsyncMock(),
            interval_minutes=60,
            enabled=True,
        )
        assert job.is_due is True
        assert job.last_run is None
        assert job.run_count == 0

    def test_disabled_job_is_not_due(self):
        job = ScheduledJob(
            name="disabled",
            handler=AsyncMock(),
            interval_minutes=60,
            enabled=False,
        )
        assert job.is_due is False

    def test_recently_run_job_is_not_due(self):
        job = ScheduledJob(
            name="recent",
            handler=AsyncMock(),
            interval_minutes=60,
        )
        job.last_run = datetime.now(UTC)
        assert job.is_due is False

    def test_overdue_job_is_due(self):
        job = ScheduledJob(
            name="overdue",
            handler=AsyncMock(),
            interval_minutes=60,
        )
        job.last_run = datetime.now(UTC) - timedelta(minutes=120)
        assert job.is_due is True

    def test_next_run_when_never_run(self):
        job = ScheduledJob(
            name="new",
            handler=AsyncMock(),
            interval_minutes=30,
        )
        # Should be approximately now
        assert job.next_run is not None
        assert (job.next_run - datetime.now(UTC)).total_seconds() < 5

    def test_next_run_after_execution(self):
        job = ScheduledJob(
            name="executed",
            handler=AsyncMock(),
            interval_minutes=30,
        )
        run_time = datetime.now(UTC) - timedelta(minutes=10)
        job.last_run = run_time
        expected = run_time + timedelta(minutes=30)
        assert job.next_run == expected


@pytest.mark.unit
class TestMaintenanceScheduler:
    """Test MaintenanceScheduler setup and control."""

    def test_scheduler_has_five_jobs(self):
        scheduler = MaintenanceScheduler()
        assert len(scheduler._jobs) == 5

    def test_job_names(self):
        scheduler = MaintenanceScheduler()
        names = {j.name for j in scheduler._jobs}
        assert names == {
            "consolidate_duplicates",
            "archive_stale",
            "recompute_recency",
            "cleanup_expired",
            "prune_access_logs",
        }

    def test_jobs_use_settings_intervals(self):
        scheduler = MaintenanceScheduler()
        job_map = {j.name: j for j in scheduler._jobs}

        from app.core.config import settings

        assert (
            job_map["consolidate_duplicates"].interval_minutes
            == settings.scheduler_consolidation_interval
        )
        assert job_map["archive_stale"].interval_minutes == settings.scheduler_archive_interval
        assert job_map["recompute_recency"].interval_minutes == settings.scheduler_recency_interval
        assert job_map["cleanup_expired"].interval_minutes == settings.scheduler_cleanup_interval
        assert job_map["prune_access_logs"].interval_minutes == settings.scheduler_prune_interval

    def test_jobs_use_settings_enabled(self):
        scheduler = MaintenanceScheduler()
        job_map = {j.name: j for j in scheduler._jobs}

        from app.core.config import settings

        assert job_map["consolidate_duplicates"].enabled == settings.scheduler_enable_consolidation
        assert job_map["archive_stale"].enabled == settings.scheduler_enable_archive
        assert job_map["recompute_recency"].enabled == settings.scheduler_enable_recency
        assert job_map["cleanup_expired"].enabled == settings.scheduler_enable_cleanup
        assert job_map["prune_access_logs"].enabled == settings.scheduler_enable_prune

    @pytest.mark.asyncio
    async def test_get_status(self):
        scheduler = MaintenanceScheduler()
        status = await scheduler.get_status()

        assert status["running"] is False
        assert len(status["jobs"]) == 5
        for job_status in status["jobs"]:
            assert "name" in job_status
            assert "enabled" in job_status
            assert "interval_minutes" in job_status
            assert "run_count" in job_status

    @pytest.mark.asyncio
    async def test_run_unknown_job(self):
        scheduler = MaintenanceScheduler()
        result = await scheduler.run_job_now("nonexistent")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_job_success(self):
        scheduler = MaintenanceScheduler()

        mock_handler = AsyncMock(return_value={"ok": True})
        test_job = ScheduledJob(
            name="mock_job",
            handler=mock_handler,
            interval_minutes=60,
        )
        result = await scheduler._execute_job(test_job)

        assert result["status"] == "success"
        assert result["job"] == "mock_job"
        assert test_job.run_count == 1
        assert test_job.last_run is not None
        assert test_job.last_error is None

    @pytest.mark.asyncio
    async def test_execute_job_failure(self):
        scheduler = MaintenanceScheduler()

        async def failing_handler():
            raise RuntimeError("DB down")

        test_job = ScheduledJob(
            name="failing_job",
            handler=failing_handler,
            interval_minutes=60,
        )
        result = await scheduler._execute_job(test_job)

        assert result["status"] == "error"
        assert "DB down" in result["error"]
        assert test_job.last_error == "DB down"

    @pytest.mark.asyncio
    async def test_stop_sets_flag(self):
        scheduler = MaintenanceScheduler()
        assert scheduler._running is False
        await scheduler.stop()
        assert scheduler._running is False


@pytest.mark.unit
class TestSchedulerSingleton:
    """Test the get_scheduler singleton."""

    def test_get_scheduler_returns_instance(self):
        import app.workers.scheduler as mod

        mod._scheduler = None  # reset
        s1 = get_scheduler()
        s2 = get_scheduler()
        assert s1 is s2
        mod._scheduler = None  # cleanup


# ═══════════════════════════════════════════════════════════════════
# 5. Settings Tests
# ═══════════════════════════════════════════════════════════════════

from app.core.config import settings


@pytest.mark.unit
class TestNewSettings:
    """Test that all InsForge-inspired settings have correct defaults."""

    # ── WebSocket ─────────────────────────────────────────────
    def test_enable_websocket_default(self):
        assert settings.enable_websocket is True

    # ── MCP ───────────────────────────────────────────────────
    def test_enable_mcp_default(self):
        assert settings.enable_mcp is True

    # ── Explorer UI ──────────────────────────────────────────
    def test_enable_explorer_default(self):
        assert settings.enable_explorer is True

    # ── Scheduler ─────────────────────────────────────────────
    def test_enable_scheduler_default(self):
        assert settings.enable_scheduler is True

    def test_scheduler_intervals(self):
        assert settings.scheduler_consolidation_interval == 3600
        assert settings.scheduler_archive_interval == 7200
        assert settings.scheduler_recency_interval == 1800
        assert settings.scheduler_cleanup_interval == 3600
        assert settings.scheduler_prune_interval == 86400

    def test_scheduler_thresholds(self):
        assert settings.scheduler_stale_threshold_days == 90
        assert settings.scheduler_access_log_retention_days == 90

    def test_scheduler_job_enable_flags(self):
        assert settings.scheduler_enable_consolidation is True
        assert settings.scheduler_enable_archive is True
        assert settings.scheduler_enable_recency is True
        assert settings.scheduler_enable_cleanup is True
        assert settings.scheduler_enable_prune is True

    # ── RLS ───────────────────────────────────────────────────
    def test_enable_rls_default(self):
        assert settings.enable_rls is False

    # ── Existing settings still correct ──────────────────────
    def test_app_name(self):
        assert settings.app_name == "AgentMemoryDB"

    def test_scoring_weights_sum_to_one(self):
        total = (
            settings.score_weight_vector
            + settings.score_weight_recency
            + settings.score_weight_importance
            + settings.score_weight_authority
            + settings.score_weight_confidence
        )
        assert abs(total - 1.0) < 0.001


# ═══════════════════════════════════════════════════════════════════
# 6. WebSocket Singleton + emit_memory_event Tests
# ═══════════════════════════════════════════════════════════════════

from app.ws import emit_memory_event, get_connection_manager


@pytest.mark.unit
class TestWebSocketSingleton:
    """Test the singleton manager factory."""

    def test_get_connection_manager_returns_same_instance(self):
        import app.ws as ws_mod

        ws_mod._manager = None
        m1 = get_connection_manager()
        m2 = get_connection_manager()
        assert m1 is m2
        ws_mod._manager = None

    @pytest.mark.asyncio
    async def test_emit_memory_event_broadcasts(self):
        import app.ws as ws_mod

        mgr = ConnectionManager()
        ws_mod._manager = mgr

        ws = AsyncMock()
        await mgr.connect(ws, channels=["user:u1"])

        await emit_memory_event(
            event_type="memory.created",
            data={"memory_id": "x"},
            user_id="u1",
        )

        ws.send_text.assert_called()
        payload = json.loads(ws.send_text.call_args[0][0])
        assert payload["event"] == "memory.created"
        assert "user:u1" in payload["channels"]

        ws_mod._manager = None


# ═══════════════════════════════════════════════════════════════════
# 7. ErrorResponse Schema Tests
# ═══════════════════════════════════════════════════════════════════

from app.schemas.common import ErrorResponse


@pytest.mark.unit
class TestErrorResponse:
    """Test the ErrorResponse schema we added."""

    def test_error_response_construction(self):
        err = ErrorResponse(detail="Not found")
        assert err.detail == "Not found"

    def test_error_response_serialization(self):
        err = ErrorResponse(detail="Bad request")
        d = err.model_dump()
        assert d == {"detail": "Bad request"}
