#!/usr/bin/env python3
"""EngramDB — a 60-second, zero-setup tour of agent memory.

Runs entirely on the embeddable SQLite package (``pip install engramdb``) with
an in-memory store and a tiny local bag-of-words embedder, so there is nothing
to configure and no API key required::

    python examples/demo.py

It walks through the full memory lifecycle an agent actually uses:

1. Short-term (working) memory — the live conversation buffer.
2. Promotion — distilling durable facts into long-term memory.
3. Recall — semantic search over what was remembered.
4. Versioning — facts change over time; old versions are preserved.
5. Context assembly — the budget-shaped block you inject into the next turn.
"""

from __future__ import annotations

import hashlib
import math
import re
import sys
import time

from engramdb import MemoryManager

# ── A tiny, dependency-free embedder ────────────────────────────────
# Real deployments use OpenAI / Cohere / sentence-transformers or the
# server's pgvector path. This bag-of-words embedder keeps the demo
# self-contained while still giving *meaningful* (lexical) recall.


class BagOfWordsEmbedding:
    dimension = 256

    def __call__(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dimension
        for tok in re.findall(r"[a-z0-9]+", text.lower()):
            tok = tok[:-1] if tok.endswith("s") and len(tok) > 3 else tok  # crude stem
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            vec[h % self.dimension] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


# ── Pretty printing ─────────────────────────────────────────────────

PAUSE = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0


def rule(title: str) -> None:
    print(f"\n\033[1;36m┌─ {title} " + "─" * max(0, 58 - len(title)) + "┐\033[0m")


def say(who: str, text: str) -> None:
    color = {"user": "\033[1;33m", "assistant": "\033[1;32m"}.get(who, "\033[0m")
    print(f"  {color}{who:>9}\033[0m │ {text}")
    time.sleep(PAUSE)


def note(text: str) -> None:
    print(f"  \033[2m{text}\033[0m")
    time.sleep(PAUSE)


def main() -> None:
    print("\033[1;35m")
    print("   ███████╗███╗   ██╗ ██████╗ ██████╗  █████╗ ███╗   ███╗██████╗ ██████╗ ")
    print("   ██╔════╝████╗  ██║██╔════╝ ██╔══██╗██╔══██╗████╗ ████║██╔══██╗██╔══██╗")
    print("   █████╗  ██╔██╗ ██║██║  ███╗██████╔╝███████║██╔████╔██║██║  ██║██████╔╝")
    print("   ██╔══╝  ██║╚██╗██║██║   ██║██╔══██╗██╔══██║██║╚██╔╝██║██║  ██║██╔══██╗")
    print("   ███████╗██║ ╚████║╚██████╔╝██║  ██║██║  ██║██║ ╚═╝ ██║██████╔╝██████╔╝")
    print("   ╚══════╝╚═╝  ╚═══╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝╚═════╝ ╚═════╝ ")
    print("\033[0m   \033[2mSQL-native, auditable memory for agentic AI\033[0m")

    mem = MemoryManager("alice", path=":memory:", embedding_fn=BagOfWordsEmbedding())

    # 1 ── Short-term conversation ----------------------------------
    rule("1. Short-term memory  (the live conversation)")
    turns = [
        ("user", "Hi! I'm Alice. I mostly write Python, and I hate tabs — spaces only."),
        ("assistant", "Noted, Alice — Python, and spaces over tabs. Anything else?"),
        ("user", "Yeah, I'm a staff backend engineer. Keep answers short."),
        ("assistant", "Got it. Short answers, backend context. 👍"),
    ]
    for who, text in turns:
        (mem.short_term.add_user if who == "user" else mem.short_term.add_assistant)(text)
        say(who, text)
    note(f"→ {mem.short_term.count()} messages buffered in thread '{mem.short_term.thread_id}'")

    # 2 ── Promote durable facts to long-term -----------------------
    rule("2. Promotion  (distil durable facts → long-term memory)")
    facts = [
        ("pref:language", "Alice codes primarily in Python.", 0.9),
        ("pref:style", "Alice prefers spaces over tabs (4-space indent).", 0.8),
        ("pref:verbosity", "Alice wants short, terse answers.", 0.7),
        ("fact:role", "Alice is a staff backend engineer.", 0.85),
    ]
    for key, content, importance in facts:
        mem.promote(key, content, importance=importance)
        note(f"remember  {key:<16} → “{content}”  (importance={importance})")
    note(f"→ {mem.long_term.count()} long-term memories stored")

    # 3 ── Recall (semantic search) ---------------------------------
    rule("3. Recall  (semantic search over long-term memory)")
    for query in ["spaces or tabs?", "what language does Alice code in?"]:
        results = mem.long_term.recall(query, top_k=2)
        print(f"  \033[1;37mquery\033[0m │ {query}")
        for r in results:
            bar = "█" * round(r.score * 20)
            print(f"        │   \033[36m{bar:<20}\033[0m {r.score:.3f}  {r.key} — {r.content}")
        time.sleep(PAUSE)

    # 4 ── Versioning -----------------------------------------------
    rule("4. Versioning  (facts evolve; history is preserved)")
    say("user", "Update me — I picked up Rust too.")
    updated = mem.promote("pref:language", "Alice codes in Python and Rust.", importance=0.9)
    versions = mem.client.versions(updated.id)
    note(f"'pref:language' is now v{updated.version}: “{updated.content}”")
    for v in versions:
        note(f"   ↳ v{v.version} (superseded): “{v.content}”")

    # 5 ── Context assembly -----------------------------------------
    rule("5. Context window  (what you inject into the next LLM turn)")
    ctx = mem.get_context_window(query="Alice coding preferences", n_messages=3, n_memories=3)
    print("  \033[1;37mrecent conversation\033[0m")
    for m in ctx["messages"]:
        say(m["role"], m["content"])
    print("  \033[1;37mrelevant long-term memory\033[0m")
    for rm in ctx["relevant_memories"]:
        note(f"   • [{rm['type']}] {rm['key']}: {rm['content']}  (score={rm['score']})")
    s = ctx["stats"]
    note(f"→ assembled from {s['message_count']} messages + {s['memory_count']} memories")

    print(
        "\n  \033[1;32m✓ The next agent starts where this one left off — no re-introductions.\033[0m"
    )
    mem.close()


if __name__ == "__main__":
    main()
