#!/usr/bin/env python3
"""
🤖 Agentic Personal Assistant — powered by AgentMemoryDB
=========================================================

A multi-turn conversational agent that:
  1. Extracts facts/preferences from what you say → stores in AgentMemoryDB
  2. Recalls relevant memories when answering → hybrid vector search
  3. Builds a persistent profile across sessions (memories survive restarts)
  4. Shows memory operations in real-time so you can watch the DB work

Run:
    python agent_demo.py

Then open the Explorer UI to see memories appear live:
    http://localhost:8100/explorer/search
"""

from __future__ import annotations

import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone

# ── Make local package importable ──
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from agentmemodb.http_client import HttpClient

# ═══════════════════════════════════════════════════════════════════
#  Configuration
# ═══════════════════════════════════════════════════════════════════

AGENTMEMO_URL = "http://localhost:8100"
AGENT_NAME = "Atlas"

# Stable file to persist the user_id across runs
_USER_ID_FILE = os.path.join(ROOT, ".agent_demo_user_id")
USER_ID: str = ""  # Set at startup

# ═══════════════════════════════════════════════════════════════════
#  Simple rule-based fact extractor (no LLM needed)
# ═══════════════════════════════════════════════════════════════════

EXTRACTION_PATTERNS = [
    # "I like X", "I love X", "I enjoy X", "I prefer X"
    (r"(?:i|I)\s+(?:like|love|enjoy|prefer|adore)\s+(.+?)(?:\.|,|!|$)",
     "preference", "pref:{tag}", 0.8),
    # "My name is X", "I'm X", "I am X"
    (r"(?:my name is|i'm|i am)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
     "identity", "identity:name", 0.95),
    # "I work at X", "I work for X", "I'm working at X"
    (r"(?:i work (?:at|for)|i'm working (?:at|for))\s+(.+?)(?:\.|,|!|$)",
     "professional", "prof:company", 0.85),
    # "I'm a X" (role/profession)
    (r"(?:i'm a|i am a|i work as a?)\s+(.+?)(?:\.|,|!|$)",
     "professional", "prof:role", 0.85),
    # "I live in X", "I'm from X", "I'm based in X"
    (r"(?:i (?:live|reside) in|i'm (?:from|based in))\s+(.+?)(?:\.|,|!|$)",
     "identity", "identity:location", 0.9),
    # "My favorite X is Y"
    (r"my (?:fav(?:ou?rite)?)\s+(\w+)\s+is\s+(.+?)(?:\.|,|!|$)",
     "preference", "pref:{0}", 0.85),
    # "I'm learning X", "I'm studying X"
    (r"(?:i'm|i am)\s+(?:learning|studying)\s+(.+?)(?:\.|,|!|$)",
     "goal", "goal:learning", 0.7),
    # "I want to X", "I plan to X", "My goal is to X"
    (r"(?:i want to|i plan to|my goal is to|i'd like to)\s+(.+?)(?:\.|,|!|$)",
     "goal", "goal:aspiration", 0.7),
    # "I have a X" (pet, car, etc.)
    (r"(?:i have|i've got)\s+(?:a |an )?(.+?)(?:\.|,|!|$)",
     "fact", "fact:possession", 0.7),
    # "My X is Y"
    (r"my\s+(\w+)\s+is\s+(.+?)(?:\.|,|!|$)",
     "fact", "fact:{0}", 0.65),
]


def extract_facts(text: str) -> list[dict]:
    """Extract structured facts from user input using pattern matching."""
    facts = []
    text_lower = text.lower().strip()

    for pattern, mem_type, key_template, confidence in EXTRACTION_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            groups = match.groups()
            value = groups[-1].strip().rstrip(".,!?")

            if len(value) < 2 or len(value) > 100:
                continue

            # Build the memory key
            if "{0}" in key_template:
                tag = groups[0].strip().lower().replace(" ", "_")[:20]
                key = key_template.replace("{0}", tag)
            elif "{tag}" in key_template:
                tag = value.lower().replace(" ", "_")[:20]
                key = key_template.replace("{tag}", tag)
            else:
                key = key_template

            content = f"The user mentioned: {value}"
            if mem_type == "preference":
                content = f"The user likes/prefers: {value}"
            elif mem_type == "identity":
                content = f"User info — {key.split(':')[1]}: {value}"
            elif mem_type == "professional":
                content = f"Professional — {key.split(':')[1]}: {value}"
            elif mem_type == "goal":
                content = f"User goal: {value}"

            facts.append({
                "key": key,
                "content": content,
                "memory_type": "semantic" if mem_type in ("preference", "identity", "fact") else "episodic",
                "importance": confidence,
                "confidence": confidence,
            })

    return facts


# ═══════════════════════════════════════════════════════════════════
#  Agent Brain — recall + respond
# ═══════════════════════════════════════════════════════════════════

def recall_context(db: HttpClient, query: str) -> list[str]:
    """Search memories relevant to the current conversation turn."""
    results = db.search(USER_ID, query, top_k=5)
    return [f"[{r.memory.key}] {r.memory.content}" for r in results]


def generate_response(user_input: str, memories: list[str], turn: int) -> str:
    """Generate a response using retrieved memories (rule-based for demo).

    In production, you'd call an LLM here with the memories as context.
    """
    input_lower = user_input.lower()

    # Greeting
    if any(w in input_lower for w in ["hello", "hi", "hey", "greetings"]):
        if memories:
            # We remember something about the user!
            known_facts = "\n".join(f"    • {m.split('] ')[1]}" for m in memories if '] ' in m)
            return (
                f"Hey there! Welcome back! 👋\n"
                f"  Here's what I remember about you:\n{known_facts}\n"
                f"  What would you like to talk about?"
            )
        return f"Hello! I'm {AGENT_NAME}, your AI assistant with persistent memory. 🧠\n  Tell me about yourself — I'll remember everything!"

    # "What do you know about me?"
    if any(p in input_lower for p in ["what do you know", "what do you remember", "tell me about me"]):
        if memories:
            facts = "\n".join(f"    • {m.split('] ')[1]}" for m in memories if '] ' in m)
            return f"Here's everything I recall about you:\n{facts}"
        return "I don't know much about you yet. Tell me something!"

    # Question answering with memory
    if "?" in user_input:
        if memories:
            context = "; ".join(m.split('] ')[1] for m in memories[:3] if '] ' in m)
            return f"Based on what I know: {context}\n  (Want to know more? Just ask!)"
        return "I'm not sure — I don't have memories about that yet. Tell me more!"

    # Default: acknowledge learning
    return "Got it, I've noted that down! 📝 Keep telling me more, or ask me what I remember."


# ═══════════════════════════════════════════════════════════════════
#  Conversation Loop
# ═══════════════════════════════════════════════════════════════════

def print_header():
    print("\n" + "═" * 62)
    print(f"  🤖 {AGENT_NAME} — Personal Assistant with AgentMemoryDB")
    print("═" * 62)
    print(f"  Memory backend : {AGENTMEMO_URL}")
    if USER_ID:
        print(f"  User ID        : {USER_ID}")
    print(f"  Explorer UI    : {AGENTMEMO_URL}/explorer/search")
    print("─" * 62)
    print("  Commands:")
    print("    /memories  — list all stored memories")
    print("    /search X  — raw search for X")
    print("    /forget    — clear all memories")
    print("    /quit      — exit")
    print("═" * 62 + "\n")


def _ensure_user(db: HttpClient) -> str:
    """Create or reuse the demo user.  Returns the user_id."""
    global USER_ID

    # Try to load from a previous run
    if os.path.exists(_USER_ID_FILE):
        cached_id = open(_USER_ID_FILE).read().strip()
        resp = db._client.get(f"/api/v1/users/{cached_id}")
        if resp.status_code == 200:
            USER_ID = cached_id
            print(f"  👤 Reusing user: {USER_ID}")
            return USER_ID

    # Create a new user
    resp = db._client.post(
        "/api/v1/users",
        json={"name": "agent-demo-user"},
        timeout=60.0,
    )
    if resp.status_code < 300:
        USER_ID = resp.json()["id"]
        with open(_USER_ID_FILE, "w") as f:
            f.write(USER_ID)
        print(f"  👤 Created user: {USER_ID}")
    else:
        raise RuntimeError(f"Failed to create user: {resp.status_code} {resp.text[:200]}")
    return USER_ID


def _create_link(db: HttpClient, source_id: str, target_id: str, link_type: str, desc: str):
    """Create a memory link between two memories."""
    try:
        resp = db._client.post("/api/v1/memory-links", json={
            "source_memory_id": source_id,
            "target_memory_id": target_id,
            "link_type": link_type,
            "description": desc,
        })
        return resp.status_code < 300
    except Exception:
        return False


def _get_memory_id(db: HttpClient, key: str) -> str | None:
    """Lookup a memory's UUID by key."""
    mem = db.get(USER_ID, key)
    return mem.id if mem else None


def cmd_list_memories(db: HttpClient):
    """Show all memories for this user."""
    memories = db.list(USER_ID, limit=50)
    if not memories:
        print("  📭 No memories stored yet.")
        return
    print(f"\n  🧠 {len(memories)} memories stored:")
    print("  " + "─" * 56)
    for m in memories:
        age = (datetime.now(timezone.utc) - m.updated_at).total_seconds()
        age_str = f"{int(age)}s ago" if age < 60 else f"{int(age/60)}m ago"
        print(f"    [{m.memory_type:9}] {m.key:25} │ {m.content[:40]:40} │ v{m.version} {age_str}")
    print("  " + "─" * 56)


def cmd_search(db: HttpClient, query: str):
    """Raw search command."""
    results = db.search(USER_ID, query, top_k=10)
    if not results:
        print(f"  🔍 No results for '{query}'")
        return
    print(f"\n  🔍 Search results for '{query}' ({len(results)} hits):")
    for i, r in enumerate(results, 1):
        score_str = f"{r.score:.4f}" if isinstance(r.score, (int, float)) else "n/a"
        print(f"    {i}. [{score_str}] {r.memory.key} → {r.memory.content[:60]}")


def run_agent():
    """Main conversation loop."""
    print_header()

    # Connect to AgentMemoryDB
    print(f"  Connecting to {AGENTMEMO_URL} ...")
    db = HttpClient(AGENTMEMO_URL, timeout=60.0)

    # Quick health check
    try:
        resp = db._client.get("/api/v1/health")
        health = resp.json()
        print(f"  ✅ Connected! Server status: {health.get('status', '?')}")
    except Exception as e:
        print(f"  ❌ Cannot connect to AgentMemoryDB: {e}")
        print(f"     Make sure the server is running: docker compose up -d")
        return

    # Ensure user exists
    _ensure_user(db)

    # Check existing memories
    existing = len(db.list(USER_ID, limit=1000))
    if existing > 0:
        print(f"  📦 Found {existing} existing memories for this user")
    else:
        print(f"  🆕 New user — no memories yet")
    print()

    turn = 0
    while True:
        try:
            user_input = input(f"  You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Goodbye! Your memories are safely stored. 👋")
            break

        if not user_input:
            continue

        # ── Commands ──
        if user_input.startswith("/"):
            cmd = user_input.lower()
            if cmd == "/quit" or cmd == "/exit":
                print("  Goodbye! Your memories are safely stored. 👋")
                break
            elif cmd == "/memories":
                cmd_list_memories(db)
                continue
            elif cmd.startswith("/search "):
                cmd_search(db, user_input[8:].strip())
                continue
            elif cmd == "/forget":
                memories = db.list(USER_ID, limit=500)
                for m in memories:
                    db.delete(USER_ID, m.key)
                print(f"  🗑️  Cleared {len(memories)} memories.")
                continue
            else:
                print(f"  Unknown command: {cmd}")
                continue

        turn += 1

        # ── Step 1: Extract facts from user input ──
        facts = extract_facts(user_input)
        if facts:
            print(f"\n  💡 Extracted {len(facts)} fact(s):")
            for f in facts:
                print(f"     → [{f['key']}] {f['content']}")

        # ── Step 2: Store extracted facts ──
        stored = 0
        for fact in facts:
            try:
                mem = db.upsert(
                    USER_ID,
                    fact["key"],
                    fact["content"],
                    memory_type=fact["memory_type"],
                    importance=fact["importance"],
                    confidence=fact["confidence"],
                    authority=1,
                )
                stored += 1
                print(f"     ✅ Stored: {fact['key']} (v{mem.version})")
            except Exception as e:
                print(f"     ⚠️  Failed to store {fact['key']}: {e}")

        if stored:
            print(f"  📝 Saved {stored} memory(ies) to AgentMemoryDB")

        # ── Step 3: Recall relevant memories ──
        memories = recall_context(db, user_input)
        if memories:
            print(f"\n  🔍 Recalled {len(memories)} relevant memory(ies):")
            for m in memories:
                print(f"     ← {m}")

        # ── Step 4: Generate response ──
        response = generate_response(user_input, memories, turn)
        print(f"\n  🤖 {AGENT_NAME}: {response}\n")

    db.close()


# ═══════════════════════════════════════════════════════════════════
#  Auto-demo mode (non-interactive)
# ═══════════════════════════════════════════════════════════════════

def run_auto_demo():
    """Run a scripted conversation to show how the agent works."""
    print_header()
    print("  🎬 Running auto-demo (scripted conversation)...\n")

    db = HttpClient(AGENTMEMO_URL, timeout=60.0)

    # Health check
    try:
        resp = db._client.get("/api/v1/health")
        print(f"  ✅ Connected to AgentMemoryDB\n")
    except Exception as e:
        print(f"  ❌ Cannot connect: {e}")
        return

    # Ensure user exists
    _ensure_user(db)

    # Clear previous demo data
    old = db.list(USER_ID, limit=500)
    for m in old:
        db.delete(USER_ID, m.key)
    if old:
        print(f"  🗑️  Cleared {len(old)} old demo memories\n")

    # Scripted conversation turns
    conversation = [
        "Hi there!",
        "My name is Joshua",
        "I live in San Francisco",
        "I work at a tech startup as a software engineer",
        "I love Python and TypeScript for programming",
        "My favorite food is sushi",
        "I'm learning Rust and machine learning",
        "I want to build an AI startup someday",
        "I have a golden retriever named Max",
        "What do you know about me?",
        "What's my favorite programming language?",
        "Where do I live?",
    ]

    for i, user_input in enumerate(conversation, 1):
        print(f"  {'─' * 56}")
        print(f"  Turn {i}")
        print(f"  You: {user_input}")

        # Extract facts
        facts = extract_facts(user_input)
        stored = 0
        for fact in facts:
            try:
                mem = db.upsert(
                    USER_ID,
                    fact["key"],
                    fact["content"],
                    memory_type=fact["memory_type"],
                    importance=fact["importance"],
                    confidence=fact["confidence"],
                    authority=1,
                )
                stored += 1
                print(f"    💾 Stored: {fact['key']} → {fact['content'][:50]}")
            except Exception as e:
                print(f"    ⚠️  Error: {e}")

        # Recall
        memories = recall_context(db, user_input)
        if memories:
            print(f"    🔍 Recalled {len(memories)} memory(ies)")

        # Respond
        response = generate_response(user_input, memories, i)
        print(f"  🤖 {AGENT_NAME}: {response}\n")

    # Final summary
    print("═" * 62)
    print("  📊 Final Memory Summary")
    print("═" * 62)
    cmd_list_memories(db)

    # ── Create memory links so the Graph page shows connections ──
    print("\n  🔗 Creating memory links for graph visualization...")
    link_pairs = [
        ("identity:name",              "identity:location",       "relates_to",  "Person lives in location"),
        ("identity:name",              "prof:company",            "relates_to",  "Person works at company"),
        ("identity:name",              "pref:python_and_typescrip","relates_to", "Person has coding preferences"),
        ("prof:company",               "goal:aspiration",         "relates_to",  "Job relates to startup goal"),
        ("pref:python_and_typescrip",  "goal:learning",           "relates_to",  "Coding prefs relate to learning goals"),
        ("pref:food",                  "fact:possession",         "relates_to",  "Personal facts"),
        ("goal:aspiration",            "goal:learning",           "relates_to",  "Goals are connected"),
    ]
    links_created = 0
    for src_key, tgt_key, link_type, desc in link_pairs:
        src_id = _get_memory_id(db, src_key)
        tgt_id = _get_memory_id(db, tgt_key)
        if src_id and tgt_id:
            ok = _create_link(db, src_id, tgt_id, link_type, desc)
            if ok:
                links_created += 1
                print(f"    🔗 {src_key}  ──{link_type}──►  {tgt_key}")
    print(f"  ✅ Created {links_created} links\n")

    total = len(db.list(USER_ID, limit=1000))
    print(f"  ✅ Agent profile: {total} memories, {links_created} links")

    # ── Step-by-step guide ──────────────────────────────────────
    seed_id = _get_memory_id(db, "identity:name") or ""
    print(f"""
{'═' * 62}
  🗺️  How to explore in the UI
{'═' * 62}

  1️⃣  SEARCH  →  {AGENTMEMO_URL}/explorer/search
       • Connect (top bar)
       • Paste User ID: {USER_ID}
       • Type any query, e.g. "What does the user like?"
       • Hit Search → see ranked memories with scores

  2️⃣  GRAPH   →  {AGENTMEMO_URL}/explorer/graph
       • Connect (top bar)
       • Paste this Memory ID (seed): {seed_id}
       • Select 2 hops → click Explore
       • Nodes = memories, edges = links between them
       • Click any node to re-center the graph on it

  3️⃣  EVENTS  →  {AGENTMEMO_URL}/explorer/events
       • Connect (top bar) → click Connect on Events page
       • Re-run this script in another terminal:
           python agent_demo.py --auto
       • Watch events stream in real-time as memories are saved
{'═' * 62}
""")

    db.close()



# ═══════════════════════════════════════════════════════════════════
#  Entry point
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if "--auto" in sys.argv:
        run_auto_demo()
    else:
        run_auto_demo()  # Run auto-demo first to seed data
        print("\n" + "═" * 62)
        print("  💬 Now entering interactive mode — chat with the agent!")
        print("═" * 62 + "\n")
        run_agent()
