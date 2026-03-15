#!/usr/bin/env python3
"""AgentMemoryDB × LangChain × LangGraph — Full Integration Demo.

Demonstrates how to integrate AgentMemoryDB with both LangChain and
LangGraph using the embedded SQLite client (no server needed).

Sections:
    1. LangChain — ChatMessageHistory (conversation persistence)
    2. LangChain — Retriever (semantic search → Documents)
    3. LangChain — Memory Tool (agent can store/recall)
    4. LangChain — ConversationMemory (history + relevant knowledge)
    5. LangGraph — Store (long-term agent memory)
    6. LangGraph — Saver (checkpoint persistence)
    7. LangGraph — Memory Node (recall + save in graph)
    8. LangGraph — Full StateGraph Workflow
    9. MemoryManager — Short-term + Long-term combined
   10. MemoryManager — LangGraph Integration (context window)

Usage:
    python examples/scripts/demo_langchain_langgraph.py
    python examples/scripts/demo_langchain_langgraph.py --provider huggingface
    python examples/scripts/demo_langchain_langgraph.py --provider openai
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, TypedDict

# ── Parse args first ────────────────────────────────────────────

parser = argparse.ArgumentParser(description="AgentMemoryDB LangChain/LangGraph Demo")
parser.add_argument(
    "--provider",
    choices=["huggingface", "openai", "dummy"],
    default="dummy",
    help="Embedding provider (default: dummy)",
)
parser.add_argument(
    "--model",
    default=None,
    help="Model name (e.g. all-MiniLM-L6-v2 for HuggingFace)",
)
args = parser.parse_args()

# ── Setup embedding function ────────────────────────────────────

def build_embedding(provider: str, model: str | None = None):
    """Build an embedding function based on provider."""
    if provider == "huggingface":
        from sentence_transformers import SentenceTransformer
        model_name = model or "all-MiniLM-L6-v2"
        print(f"  Loading HuggingFace model: {model_name}...")
        st_model = SentenceTransformer(model_name)

        class HFEmbed:
            @property
            def dimension(self) -> int:
                return st_model.get_sentence_embedding_dimension()
            def __call__(self, texts: list[str]) -> list[list[float]]:
                return st_model.encode(texts, normalize_embeddings=True).tolist()

        emb = HFEmbed()
        print(f"  ✓ Model loaded ({emb.dimension}-d)")
        return emb

    elif provider == "openai":
        from agentmemodb import OpenAIEmbedding
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("  ⚠ OPENAI_API_KEY not set, falling back to dummy")
            from agentmemodb import DummyEmbedding
            return DummyEmbedding()
        return OpenAIEmbedding(api_key=api_key, model=model or "text-embedding-3-small")

    else:
        from agentmemodb import DummyEmbedding
        return DummyEmbedding()


# ── Banner ──────────────────────────────────────────────────────

print("=" * 70)
print("  AgentMemoryDB × LangChain × LangGraph Integration Demo")
print("=" * 70)
print(f"  Provider: {args.provider}")
print()

embedding_fn = build_embedding(args.provider, args.model)

# ── Import everything ───────────────────────────────────────────

import agentmemodb
from agentmemodb import Client, MemoryManager
from agentmemodb.integrations.langchain import (
    AgentMemoryDBChatHistory,
    AgentMemoryDBRetriever,
    AgentMemoryDBConversationMemory,
    create_memory_tool,
)
from agentmemodb.integrations.langgraph import (
    AgentMemoryDBStore,
    AgentMemoryDBSaver,
    create_memory_node,
    create_save_memory_node,
)

passed = 0
failed = 0


def section(num: int, title: str):
    print(f"\n{'─' * 70}")
    print(f"  {num}. {title}")
    print(f"{'─' * 70}\n")


def check(label: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✓ {label}" + (f"  →  {detail}" if detail else ""))
    else:
        failed += 1
        print(f"  ✗ {label}" + (f"  →  {detail}" if detail else ""))


# ═══════════════════════════════════════════════════════════════════
#  1. LangChain — ChatMessageHistory
# ═══════════════════════════════════════════════════════════════════

section(1, "LangChain — ChatMessageHistory")

db1 = Client(path=":memory:", embedding_fn=embedding_fn)
history = AgentMemoryDBChatHistory(client=db1, user_id="user-1", session_id="session-001")

history.add_user_message("Hi! I'm working on a Python backend project.")
history.add_ai_message("That's great! Python is excellent for backends. What framework?")
history.add_user_message("I'm using FastAPI — it's amazing for async APIs.")
history.add_ai_message("FastAPI is a fantastic choice. Want help with anything specific?")

messages = history.messages
check("Messages stored", len(messages) == 4, f"{len(messages)} messages")
check("Correct types", messages[0].__class__.__name__ == "HumanMessage")
check("Content preserved", "FastAPI" in messages[2].content)

# Test clear
history.clear()
check("Clear works", len(history.messages) == 0)

# Re-add for later demos
history.add_user_message("I love Python and FastAPI")
history.add_ai_message("Noted — Python + FastAPI is your stack!")
check("Re-populated", len(history.messages) == 2)

db1.close()


# ═══════════════════════════════════════════════════════════════════
#  2. LangChain — Retriever
# ═══════════════════════════════════════════════════════════════════

section(2, "LangChain — Retriever (Semantic Search → Documents)")

db2 = Client(path=":memory:", embedding_fn=embedding_fn)

# Seed some long-term knowledge
db2.upsert("user-1", "pref:language", "User strongly prefers Python for all backend work")
db2.upsert("user-1", "pref:framework", "User uses FastAPI for building async APIs")
db2.upsert("user-1", "pref:database", "User prefers PostgreSQL with pgvector for vector search")
db2.upsert("user-1", "pref:editor", "User uses VS Code with Copilot extension")
db2.upsert("user-1", "fact:project", "Currently building an AI memory system called AgentMemoryDB")
db2.upsert("user-1", "pref:testing", "User writes pytest tests with 100% coverage goal")

retriever = AgentMemoryDBRetriever(
    client=db2, user_id="user-1", top_k=3, score_threshold=0.0
)

# Search
docs = retriever.invoke("What programming language does the user prefer?")
check("Returns Documents", len(docs) > 0, f"{len(docs)} docs returned")
check("Has page_content", hasattr(docs[0], "page_content"))
check("Has metadata", "memory_key" in docs[0].metadata)
check("Has score", "score" in docs[0].metadata, f"score={docs[0].metadata.get('score', 0):.3f}")

print(f"\n  Query: 'What programming language does the user prefer?'")
for i, doc in enumerate(docs):
    print(f"    {i+1}. [{doc.metadata['memory_key']}] {doc.page_content[:60]}... "
          f"(score={doc.metadata['score']:.3f})")

# Search for framework
docs2 = retriever.invoke("What API framework is being used?")
check("Framework search", len(docs2) > 0, f"top result: {docs2[0].metadata['memory_key']}")

# Also test get_relevant_documents (legacy alias)
docs3 = retriever.get_relevant_documents("testing approach")
check("Legacy alias works", len(docs3) > 0)

db2.close()


# ═══════════════════════════════════════════════════════════════════
#  3. LangChain — Memory Tool (for Agents)
# ═══════════════════════════════════════════════════════════════════

section(3, "LangChain — Memory Tool (Agent Store & Recall)")

db3 = Client(path=":memory:", embedding_fn=embedding_fn)

tool = create_memory_tool(db3, user_id="agent-1", tool_name="memory")

# Store a memory
store_result = tool.func(json.dumps({
    "action": "store",
    "key": "pref:color",
    "content": "User's favorite color is blue"
}))
check("Store via tool", "Stored memory" in store_result, store_result[:60])

# Store another
tool.func(json.dumps({
    "action": "store",
    "key": "pref:food",
    "content": "User loves sushi and ramen"
}))

# Recall
recall_result = tool.func(json.dumps({
    "action": "recall",
    "query": "What is the user's favorite color?"
}))
check("Recall via tool", "blue" in recall_result.lower(), recall_result.split("\n")[0])

# Plain text recall (fallback)
plain_result = tool.func("What food does the user like?")
check("Plain text recall", "sushi" in plain_result.lower() or "ramen" in plain_result.lower())

# Tool has description
check("Tool has description", len(tool.description) > 50)

db3.close()


# ═══════════════════════════════════════════════════════════════════
#  4. LangChain — ConversationMemory
# ═══════════════════════════════════════════════════════════════════

section(4, "LangChain — ConversationMemory (History + Knowledge)")

db4 = Client(path=":memory:", embedding_fn=embedding_fn)

# Pre-seed long-term knowledge
db4.upsert("user-2", "pref:lang", "User prefers TypeScript for frontend work")
db4.upsert("user-2", "pref:framework", "User uses React with Next.js")
db4.upsert("user-2", "skill:python", "User is also proficient in Python")

memory = AgentMemoryDBConversationMemory(
    client=db4,
    user_id="user-2",
    session_id="conv-001",
    top_k=3,
    return_messages=False,
)

# Save a conversation turn
memory.save_context(
    {"input": "What frontend framework should I use?"},
    {"output": "Based on your preferences, React with Next.js would be ideal."}
)

# Load memory variables (includes history + relevant knowledge)
variables = memory.load_memory_variables({"input": "What's my preferred frontend stack?"})

check("Has history", len(variables["history"]) > 0, f"{len(variables['history'])} chars")
check("Has relevant_context", len(variables.get("relevant_context", "")) > 0)
check("Context has knowledge", "TypeScript" in variables.get("relevant_context", "") or
      "React" in variables.get("relevant_context", "") or
      "Next.js" in variables.get("relevant_context", ""))

print(f"\n  History:\n    {variables['history'][:200]}")
print(f"\n  Relevant Context:\n    {variables.get('relevant_context', 'none')[:200]}")

# Clear
memory.clear()
empty_vars = memory.load_memory_variables({"input": "test"})
check("Clear works", len(empty_vars["history"]) == 0)

db4.close()


# ═══════════════════════════════════════════════════════════════════
#  5. LangGraph — Store (Long-term Memory for Nodes)
# ═══════════════════════════════════════════════════════════════════

section(5, "LangGraph — Store (Long-term Agent Memory)")

db5 = Client(path=":memory:", embedding_fn=embedding_fn)
store = AgentMemoryDBStore(client=db5, user_id="agent-1", namespace="knowledge")

# Store memories
store.put("user:name", "The user's name is Josh")
store.put("user:role", "Josh is a full-stack developer")
store.put("project:current", "Working on AgentMemoryDB — an AI memory system")
store.put("pref:tools", "Prefers Python, FastAPI, PostgreSQL, React")
store.put("pref:ide", "Uses VS Code with GitHub Copilot")

check("Stored 5 memories", store.count() == 5)

# Search
results = store.search("What is the user working on?", top_k=3)
check("Search returns results", len(results) > 0, f"top: {results[0].key}")

# Text search (for prompt injection)
context_text = store.search_as_text("developer tools and preferences")
check("Text format works", len(context_text) > 0)
print(f"\n  Context block:\n{context_text}")

# Get specific
mem = store.get("user:name")
check("Get by key", mem is not None, f"content: {mem.content}")

# Put many
store.put_many([
    {"key": "skill:python", "content": "Expert-level Python developer"},
    {"key": "skill:react", "content": "Proficient in React and TypeScript"},
])
check("Batch put", store.count() == 7)

# List
all_mems = store.list()
check("List all", len(all_mems) == 7)

# Delete
store.delete("pref:ide")
check("Delete works", store.count() == 6)

db5.close()


# ═══════════════════════════════════════════════════════════════════
#  6. LangGraph — Saver (Checkpoint Persistence)
# ═══════════════════════════════════════════════════════════════════

section(6, "LangGraph — Saver (Graph State Checkpoints)")

db6 = Client(path=":memory:", embedding_fn=embedding_fn)
saver = AgentMemoryDBSaver(client=db6, user_id="system")

config = {"configurable": {"thread_id": "thread-abc"}}

# Save checkpoint 1
state1 = {"messages": ["Hello!"], "step": 1, "context": "initial"}
result1 = saver.put(config, state1, metadata={"node": "start", "step": 1})
check("Checkpoint 1 saved", "checkpoint_id" in result1["configurable"])
cp1_id = result1["configurable"]["checkpoint_id"]

# Save checkpoint 2
state2 = {"messages": ["Hello!", "Hi there!"], "step": 2, "context": "processing"}
result2 = saver.put(config, state2, metadata={"node": "agent", "step": 2})
cp2_id = result2["configurable"]["checkpoint_id"]
check("Checkpoint 2 saved", cp2_id != cp1_id)

# Load latest checkpoint
latest = saver.get(config)
check("Load latest", latest is not None)
check("Latest is step 2", latest.get("step") == 2, f"step={latest.get('step')}")

# Load specific checkpoint
cp1_config = {"configurable": {"thread_id": "thread-abc", "checkpoint_id": cp1_id}}
old = saver.get(cp1_config)
check("Time-travel to cp1", old is not None and old.get("step") == 1)

# Get tuple
tup = saver.get_tuple(config)
check("Tuple interface", tup is not None and len(tup) == 3)
check("Tuple has config", "thread_id" in tup[0].get("configurable", {}))

# List checkpoints
checkpoints = saver.list_checkpoints("thread-abc")
check("List checkpoints", len(checkpoints) == 2, f"{len(checkpoints)} found")

# Delete thread
deleted = saver.delete_thread("thread-abc")
check("Delete thread", deleted >= 2, f"deleted {deleted} checkpoints")

db6.close()


# ═══════════════════════════════════════════════════════════════════
#  7. LangGraph — Memory Nodes (Recall + Save)
# ═══════════════════════════════════════════════════════════════════

section(7, "LangGraph — Memory Nodes (Recall + Save)")

db7 = Client(path=":memory:", embedding_fn=embedding_fn)
store7 = AgentMemoryDBStore(client=db7, user_id="user-1")

# Pre-seed knowledge
store7.put("pref:lang", "User prefers Python for backend development")
store7.put("pref:db", "User uses PostgreSQL with pgvector")
store7.put("skill:ml", "User has experience with machine learning and embeddings")

# Create recall node
recall_node = create_memory_node(store7, input_key="input", context_key="context", top_k=3)

# Simulate state
state = {"input": "What database should I use for vector search?"}
updates = recall_node(state)
check("Recall node works", "context" in updates)
check("Context has content", len(updates.get("context", "")) > 0)
print(f"\n  Recalled context:\n    {updates.get('context', '')[:200]}")

# Create save node
save_node = create_save_memory_node(store7, content_key="output", key_prefix="conv")

# Simulate saving output
save_state = {"output": "I recommend PostgreSQL with pgvector for vector search capabilities."}
save_node(save_state)
check("Save node stored", store7.count() == 4)  # 3 original + 1 new

db7.close()


# ═══════════════════════════════════════════════════════════════════
#  8. LangGraph — Full StateGraph Workflow
# ═══════════════════════════════════════════════════════════════════

section(8, "LangGraph — Full StateGraph Workflow")

try:
    from langgraph.graph import StateGraph, END

    # Define state
    class AgentState(TypedDict):
        input: str
        context: str
        output: str

    db8 = Client(path=":memory:", embedding_fn=embedding_fn)
    store8 = AgentMemoryDBStore(client=db8, user_id="user-1")

    # Seed knowledge
    store8.put("fact:product", "AgentMemoryDB is an AI memory system with hybrid search")
    store8.put("fact:features", "It supports versioning, PII masking, and graph links")
    store8.put("fact:stack", "Built with Python, FastAPI, PostgreSQL, pgvector")

    # Node: recall memory
    def recall(state: AgentState) -> dict:
        query = state["input"]
        context = store8.search_as_text(query, top_k=3)
        return {"context": context}

    # Node: generate (simulated — no LLM needed)
    def generate(state: AgentState) -> dict:
        context = state.get("context", "")
        query = state["input"]
        response = f"Based on my knowledge:\n{context}\n\nRegarding '{query}': The system is comprehensive."
        return {"output": response}

    # Node: save memory
    def save(state: AgentState) -> dict:
        output = state.get("output", "")
        if output:
            store8.put(
                f"response:{hash(output) % 10000:04d}",
                output[:200],
                memory_type="episodic",
            )
        return {}

    # Build graph
    graph = StateGraph(AgentState)
    graph.add_node("recall", recall)
    graph.add_node("generate", generate)
    graph.add_node("save", save)
    graph.add_edge("recall", "generate")
    graph.add_edge("generate", "save")
    graph.add_edge("save", END)
    graph.set_entry_point("recall")

    app = graph.compile()

    # Run the graph
    result = app.invoke({
        "input": "Tell me about AgentMemoryDB features",
        "context": "",
        "output": "",
    })

    check("Graph executed", "output" in result)
    check("Output has content", len(result["output"]) > 0)
    check("Memory saved", store8.count() == 4)  # 3 original + 1 episodic
    print(f"\n  Graph output:\n    {result['output'][:200]}")

    db8.close()

except ImportError as e:
    print(f"  ⚠ Skipping StateGraph demo: {e}")
    check("LangGraph available", False, str(e))


# ═══════════════════════════════════════════════════════════════════
#  9. MemoryManager — Short-term + Long-term Combined
# ═══════════════════════════════════════════════════════════════════

section(9, "MemoryManager — Short-term + Long-term Combined")

with MemoryManager("agent-1", path=":memory:", embedding_fn=embedding_fn) as mgr:
    # === Short-term (conversation buffer) ===
    mgr.short_term.add_system("You are a helpful coding assistant.")
    mgr.short_term.add_user("I'm building a REST API with FastAPI.")
    mgr.short_term.add_assistant("Great choice! FastAPI is excellent for async APIs.")
    mgr.short_term.add_user("How should I handle authentication?")
    mgr.short_term.add_assistant("I'd recommend JWT tokens with OAuth2 password flow.")

    check("Short-term: 5 messages", mgr.short_term.count() == 5)

    # Export as OpenAI-compatible format
    msg_list = mgr.short_term.to_list()
    check("OpenAI format", msg_list[0] == {"role": "system", "content": "You are a helpful coding assistant."})

    # Export as string
    conv_str = mgr.short_term.to_string()
    check("String format", "user:" in conv_str and "assistant:" in conv_str)

    # === Long-term (persistent knowledge) ===
    mgr.long_term.remember("pref:framework", "User prefers FastAPI for REST APIs", importance=0.9)
    mgr.long_term.remember("pref:auth", "User interested in JWT + OAuth2 authentication", importance=0.8)
    mgr.long_term.remember("skill:python", "User is building Python REST APIs", importance=0.7)

    check("Long-term: 3 memories", mgr.long_term.count() == 3)

    # Recall
    results = mgr.long_term.recall("What framework for APIs?")
    check("Recall works", len(results) > 0, f"top: {results[0].key}")

    # === Promote from conversation → long-term ===
    mgr.promote("insight:auth_approach", "Use JWT tokens with OAuth2 for FastAPI authentication", importance=0.85)
    check("Promote works", mgr.long_term.count() == 4)
    promoted = mgr.long_term.get("insight:auth_approach")
    check("Promoted has source", promoted.metadata.get("source") == "conversation")

    # === Context window for LLM ===
    ctx = mgr.get_context_window(
        "How should I set up authentication?",
        n_messages=5,
        n_memories=3,
    )
    check("Context has messages", len(ctx["messages"]) == 5)
    check("Context has memories", len(ctx["relevant_memories"]) > 0)
    check("Context has stats", ctx["stats"]["memory_count"] == 4)

    print(f"\n  Context window stats:")
    print(f"    Messages: {ctx['stats']['message_count']}")
    print(f"    Relevant memories: {len(ctx['relevant_memories'])}")
    for m in ctx["relevant_memories"]:
        print(f"      - [{m['key']}] {m['content'][:50]}... (score={m['score']:.3f})")

    # === New thread ===
    mgr.new_thread("session-2")
    mgr.short_term.add_user("Starting a new conversation about deployment.")
    check("New thread: 1 msg", mgr.short_term.count() == 1)
    check("Long-term persists", mgr.long_term.count() == 4)


# ═══════════════════════════════════════════════════════════════════
#  10. MemoryManager — LangGraph Integration
# ═══════════════════════════════════════════════════════════════════

section(10, "MemoryManager + LangGraph — Full Agent Pattern")

try:
    from langgraph.graph import StateGraph, END

    class FullAgentState(TypedDict):
        input: str
        context: str
        history: str
        output: str

    mgr10 = MemoryManager("user-1", path=":memory:", embedding_fn=embedding_fn, max_messages=20)

    # Seed long-term knowledge
    mgr10.long_term.remember("pref:lang", "User prefers Python", importance=0.9)
    mgr10.long_term.remember("pref:db", "User uses PostgreSQL + pgvector", importance=0.8)
    mgr10.long_term.remember("project:current", "Building AgentMemoryDB", importance=0.95)

    # Node: load context (conversation + knowledge)
    def load_context(state: FullAgentState) -> dict:
        query = state["input"]
        # Add user message to short-term
        mgr10.short_term.add_user(query)
        # Get combined context
        ctx = mgr10.get_context_window(query, n_messages=10, n_memories=5)
        # Format for LLM
        history = "\n".join(
            f"{m['role']}: {m['content']}" for m in ctx["messages"]
        )
        memory_ctx = "\n".join(
            f"- [{m['key']}] {m['content']}" for m in ctx["relevant_memories"]
        )
        return {"history": history, "context": memory_ctx}

    # Node: respond (simulated LLM)
    def respond(state: FullAgentState) -> dict:
        response = (
            f"Based on your context and history, here's my answer about "
            f"'{state['input'][:50]}'.\n"
            f"Knowledge used: {len(state.get('context', '').splitlines())} memories"
        )
        # Save assistant response to short-term
        mgr10.short_term.add_assistant(response)
        return {"output": response}

    # Node: learn (extract & promote insights)
    def learn(state: FullAgentState) -> dict:
        output = state.get("output", "")
        if "recommend" in output.lower() or "suggest" in output.lower():
            mgr10.promote(
                f"insight:{hash(output) % 10000:04d}",
                output[:200],
                importance=0.7,
            )
        return {}

    # Build the full agent graph
    graph = StateGraph(FullAgentState)
    graph.add_node("load_context", load_context)
    graph.add_node("respond", respond)
    graph.add_node("learn", learn)
    graph.add_edge("load_context", "respond")
    graph.add_edge("respond", "learn")
    graph.add_edge("learn", END)
    graph.set_entry_point("load_context")

    agent = graph.compile()

    # Run conversation turn 1
    result1 = agent.invoke({
        "input": "What language am I using for this project?",
        "context": "", "history": "", "output": "",
    })
    check("Turn 1 complete", len(result1["output"]) > 0)
    check("Turn 1 has context", len(result1["context"]) > 0)

    # Run conversation turn 2
    result2 = agent.invoke({
        "input": "What database should I pair with it?",
        "context": "", "history": "", "output": "",
    })
    check("Turn 2 complete", len(result2["output"]) > 0)
    check("History grows", mgr10.short_term.count() == 4)  # 2 user + 2 assistant

    # Run conversation turn 3
    result3 = agent.invoke({
        "input": "What am I currently building?",
        "context": "", "history": "", "output": "",
    })
    check("Turn 3 complete", len(result3["output"]) > 0)
    check("Conversation tracked", mgr10.short_term.count() == 6)
    check("Knowledge intact", mgr10.long_term.count() >= 3)

    print(f"\n  Final state:")
    print(f"    Short-term messages: {mgr10.short_term.count()}")
    print(f"    Long-term memories:  {mgr10.long_term.count()}")
    print(f"    Last 4 messages:")
    for m in mgr10.short_term.get_last(4):
        print(f"      {m['role']}: {m['content'][:60]}")

    mgr10.close()

except ImportError as e:
    print(f"  ⚠ Skipping MemoryManager+LangGraph demo: {e}")


# ═══════════════════════════════════════════════════════════════════
#  Summary
# ═══════════════════════════════════════════════════════════════════

print(f"\n{'═' * 70}")
print(f"  Results: {passed} passed, {failed} failed")
print(f"{'═' * 70}")

if failed > 0:
    print(f"\n  ⚠ {failed} check(s) failed!")
    sys.exit(1)
else:
    print(f"\n  ✅ All {passed} checks passed!")
    print()
    print("  Integration points demonstrated:")
    print("    • LangChain ChatMessageHistory  — conversation persistence")
    print("    • LangChain Retriever           — semantic search → Documents")
    print("    • LangChain Memory Tool          — agent store/recall")
    print("    • LangChain ConversationMemory   — history + relevant knowledge")
    print("    • LangGraph Store                — long-term node memory")
    print("    • LangGraph Saver                — state checkpoint persistence")
    print("    • LangGraph Memory Nodes          — recall + save in graph")
    print("    • LangGraph StateGraph            — full workflow with memory")
    print("    • MemoryManager                   — short-term + long-term unified")
    print("    • MemoryManager + LangGraph       — full agent pattern")
    print()

sys.exit(0)
