"""Adapters package — framework integration stubs."""

from app.adapters.langgraph_store import AgentMemoryDBStore

try:
    from app.adapters.langchain_history import AgentMemoryDBChatMessageHistory
except ImportError:  # langchain-core not installed
    AgentMemoryDBChatMessageHistory = None  # type: ignore[assignment,misc]

__all__ = [
    "AgentMemoryDBChatMessageHistory",
    "AgentMemoryDBStore",
]
