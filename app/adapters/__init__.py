"""Adapters package — framework integration stubs."""

from app.adapters.langgraph_store import EngramDBStore

try:
    from app.adapters.langchain_history import EngramDBChatMessageHistory
except ImportError:  # langchain-core not installed
    EngramDBChatMessageHistory = None  # type: ignore[assignment,misc]

__all__ = [
    "EngramDBChatMessageHistory",
    "EngramDBStore",
]
