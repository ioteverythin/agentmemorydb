"""LangChain integration for AgentMemoryDB.

Provides drop-in components for LangChain pipelines:

- **AgentMemoryDBChatHistory** — ``BaseChatMessageHistory`` implementation
  that persists conversation turns as typed memories.

- **AgentMemoryDBRetriever** — ``BaseRetriever`` that runs hybrid
  semantic search over memories and returns LangChain ``Document`` objects.

- **create_memory_tool** — returns a LangChain ``Tool`` that lets an
  agent store and recall memories dynamically during execution.

All classes work with **both** the embedded ``Client`` (SQLite) and
the remote ``HttpClient``.

Quick start::

    import agentmemodb
    from agentmemodb.integrations.langchain import (
        AgentMemoryDBChatHistory,
        AgentMemoryDBRetriever,
        create_memory_tool,
    )

    db = agentmemodb.Client()

    # 1. Chat history
    history = AgentMemoryDBChatHistory(client=db, user_id="user-1", session_id="s1")
    history.add_user_message("Hello!")
    history.add_ai_message("Hi there!")
    print(history.messages)

    # 2. Retriever (plug into RetrievalQA, ConversationalRetrievalChain, etc.)
    retriever = AgentMemoryDBRetriever(client=db, user_id="user-1", top_k=5)
    docs = retriever.invoke("What language does the user prefer?")

    # 3. Tool for agents
    tool = create_memory_tool(db, user_id="user-1")
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Iterator, List, Optional, Sequence

# ── LangChain imports (lazy — fail gracefully if not installed) ──

try:
    from langchain_core.chat_history import BaseChatMessageHistory
    from langchain_core.documents import Document
    from langchain_core.messages import (
        AIMessage,
        BaseMessage,
        HumanMessage,
        SystemMessage,
        messages_from_dict,
        messages_to_dict,
    )
    from langchain_core.retrievers import BaseRetriever
    from langchain_core.callbacks import CallbackManagerForRetrieverRun
    from langchain_core.tools import Tool

    _HAS_LANGCHAIN = True
except ImportError:
    _HAS_LANGCHAIN = False


def _require_langchain() -> None:
    if not _HAS_LANGCHAIN:
        raise ImportError(
            "LangChain integration requires langchain-core. "
            "Install with: pip install langchain-core"
        )


# ═══════════════════════════════════════════════════════════════════
# 1. Chat Message History
# ═══════════════════════════════════════════════════════════════════


class AgentMemoryDBChatHistory:
    """LangChain-compatible chat message history backed by AgentMemoryDB.

    Each message is stored as a separate memory with a sequential key
    like ``chat:session-123:msg:0001``.  This preserves ordering while
    leveraging AgentMemoryDB's versioning, search, and PII masking.

    Parameters
    ----------
    client
        An ``agentmemodb.Client`` or ``agentmemodb.HttpClient`` instance.
    user_id
        User who owns the conversation.
    session_id
        Unique identifier for this conversation session.
    """

    def __init__(
        self,
        client: Any,
        user_id: str,
        session_id: str | None = None,
    ) -> None:
        _require_langchain()
        self._client = client
        self._user_id = user_id
        self._session_id = session_id or str(uuid.uuid4())
        self._msg_counter = 0
        # Load existing message count
        existing = self._client.list(
            user_id,
            memory_type="episodic",
            scope="session",
            limit=10000,
        )
        session_msgs = [
            m
            for m in existing
            if m.key.startswith(f"chat:{self._session_id}:msg:")
        ]
        self._msg_counter = len(session_msgs)

    @property
    def messages(self) -> list:
        """Return all messages in chronological order."""
        all_memories = self._client.list(
            self._user_id,
            memory_type="episodic",
            scope="session",
            limit=10000,
        )
        session_msgs = sorted(
            [
                m
                for m in all_memories
                if m.key.startswith(f"chat:{self._session_id}:msg:")
            ],
            key=lambda m: m.key,
        )
        messages = []
        for mem in session_msgs:
            try:
                data = json.loads(mem.content)
                role = data.get("role", "human")
                text = data.get("content", "")
            except (json.JSONDecodeError, TypeError):
                role = "human"
                text = mem.content

            if role == "human":
                messages.append(HumanMessage(content=text))
            elif role == "ai":
                messages.append(AIMessage(content=text))
            elif role == "system":
                messages.append(SystemMessage(content=text))
            else:
                messages.append(HumanMessage(content=text))
        return messages

    def add_message(self, message: Any) -> None:
        """Add a message to the history."""
        if isinstance(message, HumanMessage):
            role = "human"
        elif isinstance(message, AIMessage):
            role = "ai"
        elif isinstance(message, SystemMessage):
            role = "system"
        else:
            role = "human"

        self._msg_counter += 1
        key = f"chat:{self._session_id}:msg:{self._msg_counter:04d}"
        content_json = json.dumps({"role": role, "content": message.content})

        self._client.upsert(
            self._user_id,
            key,
            content_json,
            memory_type="episodic",
            scope="session",
            metadata={
                "session_id": self._session_id,
                "role": role,
                "msg_index": self._msg_counter,
            },
        )

    def add_user_message(self, message: str) -> None:
        """Convenience: add a human message."""
        self.add_message(HumanMessage(content=message))

    def add_ai_message(self, message: str) -> None:
        """Convenience: add an AI message."""
        self.add_message(AIMessage(content=message))

    def clear(self) -> None:
        """Delete all messages in this session."""
        all_memories = self._client.list(
            self._user_id,
            memory_type="episodic",
            scope="session",
            limit=10000,
        )
        for mem in all_memories:
            if mem.key.startswith(f"chat:{self._session_id}:msg:"):
                self._client.delete(self._user_id, mem.key)
        self._msg_counter = 0


# ═══════════════════════════════════════════════════════════════════
# 2. Retriever
# ═══════════════════════════════════════════════════════════════════


class AgentMemoryDBRetriever:
    """LangChain-compatible retriever that searches AgentMemoryDB.

    Drop into any LangChain chain that accepts a retriever:
    ``RetrievalQA``, ``ConversationalRetrievalChain``,
    ``create_retrieval_chain``, etc.

    Parameters
    ----------
    client
        An ``agentmemodb.Client`` or ``agentmemodb.HttpClient`` instance.
    user_id
        User whose memories to search.
    top_k
        Maximum number of results to return.
    memory_types
        Optional list of memory types to filter (e.g. ``["semantic"]``).
    score_threshold
        Minimum score threshold — memories below this are excluded.
    """

    def __init__(
        self,
        client: Any,
        user_id: str,
        top_k: int = 5,
        memory_types: list[str] | None = None,
        score_threshold: float = 0.0,
    ) -> None:
        _require_langchain()
        self._client = client
        self._user_id = user_id
        self._top_k = top_k
        self._memory_types = memory_types
        self._score_threshold = score_threshold

    def invoke(
        self,
        query: str,
        **kwargs: Any,
    ) -> list:
        """Search and return LangChain Document objects."""
        results = self._client.search(
            self._user_id,
            query,
            top_k=self._top_k,
            memory_types=self._memory_types,
        )

        docs = []
        for r in results:
            if r.score < self._score_threshold:
                continue
            doc = Document(
                page_content=r.content,
                metadata={
                    "memory_id": r.id,
                    "memory_key": r.key,
                    "memory_type": r.memory.memory_type,
                    "score": r.score,
                    "importance": r.memory.importance,
                    "confidence": r.memory.confidence,
                    "version": r.memory.version,
                },
            )
            docs.append(doc)
        return docs

    # Alias for LangChain's expected interface
    def get_relevant_documents(self, query: str, **kwargs: Any) -> list:
        """Alias for ``invoke`` — matches LangChain's retriever interface."""
        return self.invoke(query, **kwargs)

    async def ainvoke(self, query: str, **kwargs: Any) -> list:
        """Async version — falls back to sync for embedded client."""
        return self.invoke(query, **kwargs)


# ═══════════════════════════════════════════════════════════════════
# 3. Memory Tool (for LangChain Agents)
# ═══════════════════════════════════════════════════════════════════


def create_memory_tool(
    client: Any,
    user_id: str,
    tool_name: str = "memory_store_and_recall",
    top_k: int = 5,
) -> Any:
    """Create a LangChain Tool that can store and recall memories.

    The tool accepts a JSON string with an "action" field:

    - ``{"action": "store", "key": "...", "content": "..."}``
    - ``{"action": "recall", "query": "..."}``
    - ``{"action": "recall", "query": "...", "top_k": 3}``

    Parameters
    ----------
    client
        An ``agentmemodb.Client`` or ``agentmemodb.HttpClient``.
    user_id
        User context for memory operations.
    tool_name
        Name the agent will use to invoke this tool.
    top_k
        Default number of results for recall.
    """
    _require_langchain()

    def _run(input_str: str) -> str:
        try:
            data = json.loads(input_str)
        except json.JSONDecodeError:
            # Treat as a recall query
            data = {"action": "recall", "query": input_str}

        action = data.get("action", "recall")

        if action == "store":
            key = data.get("key", f"agent:{uuid.uuid4().hex[:8]}")
            content = data.get("content", "")
            memory_type = data.get("memory_type", "semantic")
            mem = client.upsert(
                user_id, key, content, memory_type=memory_type
            )
            return f"Stored memory '{key}' (v{mem.version}): {content[:100]}"

        elif action == "recall":
            query = data.get("query", "")
            k = data.get("top_k", top_k)
            results = client.search(user_id, query, top_k=k)
            if not results:
                return "No relevant memories found."
            lines = []
            for i, r in enumerate(results, 1):
                lines.append(
                    f"{i}. [{r.key}] (score={r.score:.3f}): {r.content}"
                )
            return "\n".join(lines)

        else:
            return f"Unknown action '{action}'. Use 'store' or 'recall'."

    return Tool(
        name=tool_name,
        func=_run,
        description=(
            "Store and recall long-term memories. "
            "Input must be a JSON string with 'action' field. "
            "For storing: {\"action\": \"store\", \"key\": \"topic:subtopic\", \"content\": \"fact to remember\"}. "
            "For recalling: {\"action\": \"recall\", \"query\": \"what do you know about X?\"}."
        ),
    )


# ═══════════════════════════════════════════════════════════════════
# 4. Conversation Memory Wrapper (for legacy chains)
# ═══════════════════════════════════════════════════════════════════


class AgentMemoryDBConversationMemory:
    """Drop-in memory for LangChain ``ConversationChain`` and similar.

    Stores conversation history in AgentMemoryDB AND uses semantic
    search to inject relevant past knowledge into the prompt.

    Usage::

        from langchain.chains import ConversationChain
        from langchain_openai import ChatOpenAI

        memory = AgentMemoryDBConversationMemory(
            client=db,
            user_id="user-1",
            session_id="session-abc",
            relevant_memories_key="relevant_context",
        )

        chain = ConversationChain(
            llm=ChatOpenAI(),
            memory=memory,
        )
        chain.invoke({"input": "What's my favorite language?"})
    """

    def __init__(
        self,
        client: Any,
        user_id: str,
        session_id: str | None = None,
        memory_key: str = "history",
        relevant_memories_key: str | None = "relevant_context",
        input_key: str = "input",
        output_key: str = "output",
        top_k: int = 5,
        return_messages: bool = True,
    ) -> None:
        _require_langchain()
        self._client = client
        self._user_id = user_id
        self._chat_history = AgentMemoryDBChatHistory(
            client=client, user_id=user_id, session_id=session_id
        )
        self._retriever = AgentMemoryDBRetriever(
            client=client, user_id=user_id, top_k=top_k
        )
        self.memory_key = memory_key
        self.relevant_memories_key = relevant_memories_key
        self.input_key = input_key
        self.output_key = output_key
        self.return_messages = return_messages

    @property
    def memory_variables(self) -> list[str]:
        """Keys this memory injects into the chain."""
        keys = [self.memory_key]
        if self.relevant_memories_key:
            keys.append(self.relevant_memories_key)
        return keys

    def load_memory_variables(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Load conversation history + relevant long-term memories."""
        result: dict[str, Any] = {}

        # Chat history
        messages = self._chat_history.messages
        if self.return_messages:
            result[self.memory_key] = messages
        else:
            lines = []
            for m in messages:
                prefix = "Human" if isinstance(m, HumanMessage) else "AI"
                lines.append(f"{prefix}: {m.content}")
            result[self.memory_key] = "\n".join(lines)

        # Relevant long-term memories (semantic search)
        if self.relevant_memories_key:
            query = inputs.get(self.input_key, "")
            if query:
                docs = self._retriever.invoke(query)
                context_parts = []
                for doc in docs:
                    key = doc.metadata.get("memory_key", "")
                    score = doc.metadata.get("score", 0)
                    context_parts.append(
                        f"[{key}] (relevance={score:.2f}): {doc.page_content}"
                    )
                result[self.relevant_memories_key] = "\n".join(context_parts)
            else:
                result[self.relevant_memories_key] = ""

        return result

    def save_context(self, inputs: dict[str, Any], outputs: dict[str, str]) -> None:
        """Save the current turn to memory."""
        human_input = inputs.get(self.input_key, "")
        ai_output = outputs.get(self.output_key, "")

        if human_input:
            self._chat_history.add_user_message(human_input)
        if ai_output:
            self._chat_history.add_ai_message(ai_output)

    def clear(self) -> None:
        """Clear conversation history."""
        self._chat_history.clear()


__all__ = [
    "AgentMemoryDBChatHistory",
    "AgentMemoryDBRetriever",
    "AgentMemoryDBConversationMemory",
    "create_memory_tool",
]
