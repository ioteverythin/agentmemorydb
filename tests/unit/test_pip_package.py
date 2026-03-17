"""Tests for the agentmemodb pip package (embedded + http client).

All embedded tests use ``:memory:`` — no files written to disk.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

import agentmemodb
from agentmemodb.client import Client
from agentmemodb.embeddings import DummyEmbedding, EmbeddingFunction
from agentmemodb.http_client import HttpClient
from agentmemodb.masking import PIIMaskingEngine
from agentmemodb.memory_manager import LongTermMemory, MemoryManager, ShortTermMemory
from agentmemodb.store import SQLiteStore
from agentmemodb.types import Memory, MemoryVersion, SearchResult

# ═══════════════════════════════════════════════════════════════════
#  1. Package top-level imports
# ═══════════════════════════════════════════════════════════════════


class TestPackageImports:
    """Verify top-level exports work."""

    def test_version(self):
        assert agentmemodb.__version__ == "0.1.0"

    def test_client_exported(self):
        assert agentmemodb.Client is Client

    def test_http_client_exported(self):
        assert agentmemodb.HttpClient is HttpClient

    def test_types_exported(self):
        assert agentmemodb.Memory is Memory
        assert agentmemodb.SearchResult is SearchResult
        assert agentmemodb.MemoryVersion is MemoryVersion

    def test_embeddings_exported(self):
        assert agentmemodb.DummyEmbedding is DummyEmbedding

    def test_memory_manager_exported(self):
        assert agentmemodb.MemoryManager is MemoryManager
        assert agentmemodb.ShortTermMemory is ShortTermMemory
        assert agentmemodb.LongTermMemory is LongTermMemory


# ═══════════════════════════════════════════════════════════════════
#  2. Types
# ═══════════════════════════════════════════════════════════════════


class TestTypes:
    def test_memory_defaults(self):
        m = Memory(id="1", user_id="u", key="k", content="c")
        assert m.memory_type == "semantic"
        assert m.scope == "user"
        assert m.status == "active"
        assert m.importance == 0.5
        assert m.version == 1

    def test_memory_to_dict(self):
        m = Memory(id="1", user_id="u", key="k", content="hello")
        d = m.to_dict()
        assert d["memory_key"] == "k"
        assert d["content"] == "hello"
        assert d["importance_score"] == 0.5

    def test_search_result_accessors(self):
        m = Memory(id="x", user_id="u", key="k", content="c")
        sr = SearchResult(memory=m, score=0.95)
        assert sr.key == "k"
        assert sr.content == "c"
        assert sr.id == "x"
        assert sr.score == 0.95

    def test_memory_version(self):
        v = MemoryVersion(id="v1", memory_id="m1", version=2, content="old")
        assert v.version == 2
        assert isinstance(v.created_at, datetime)


# ═══════════════════════════════════════════════════════════════════
#  3. Embeddings
# ═══════════════════════════════════════════════════════════════════


class TestDummyEmbedding:
    def test_default_dimension(self):
        emb = DummyEmbedding()
        assert emb.dimension == 128

    def test_custom_dimension(self):
        emb = DummyEmbedding(dimension=64)
        assert emb.dimension == 64

    def test_output_shape(self):
        emb = DummyEmbedding(dimension=32)
        vecs = emb(["hello", "world"])
        assert len(vecs) == 2
        assert len(vecs[0]) == 32

    def test_deterministic(self):
        emb = DummyEmbedding()
        v1 = emb(["test"])[0]
        v2 = emb(["test"])[0]
        assert v1 == v2

    def test_different_texts_differ(self):
        emb = DummyEmbedding()
        v1 = emb(["alpha"])[0]
        v2 = emb(["beta"])[0]
        assert v1 != v2

    def test_normalized(self):
        emb = DummyEmbedding()
        vec = emb(["normalize me"])[0]
        norm = sum(v * v for v in vec) ** 0.5
        assert abs(norm - 1.0) < 0.01

    def test_conforms_to_protocol(self):
        emb = DummyEmbedding()
        assert isinstance(emb, EmbeddingFunction)

    def test_openai_import_error(self):
        with pytest.raises(ImportError, match="openai"):
            from agentmemodb.embeddings import OpenAIEmbedding

            with patch.dict("sys.modules", {"openai": None}):
                OpenAIEmbedding()


# ═══════════════════════════════════════════════════════════════════
#  4. Masking (standalone)
# ═══════════════════════════════════════════════════════════════════


class TestMasking:
    def test_email(self):
        eng = PIIMaskingEngine()
        r = eng.mask_text("Contact josh@company.com please")
        assert "[EMAIL]" in r.masked_text
        assert "josh@company.com" not in r.masked_text
        assert r.was_masked

    def test_ssn(self):
        eng = PIIMaskingEngine()
        r = eng.mask_text("SSN: 123-45-6789")
        assert "[SSN]" in r.masked_text
        assert "123-45-6789" not in r.masked_text

    def test_no_pii(self):
        eng = PIIMaskingEngine()
        r = eng.mask_text("Just a normal sentence.")
        assert r.masked_text == "Just a normal sentence."
        assert not r.was_masked

    def test_multiple_patterns(self):
        eng = PIIMaskingEngine()
        r = eng.mask_text("Email: a@b.com SSN: 111-22-3333")
        assert "[EMAIL]" in r.masked_text
        assert "[SSN]" in r.masked_text
        assert len(r.detections) == 2


# ═══════════════════════════════════════════════════════════════════
#  5. SQLiteStore (low-level)
# ═══════════════════════════════════════════════════════════════════


class TestSQLiteStore:
    def _make_store(self) -> SQLiteStore:
        return SQLiteStore(path=":memory:", dimension=32)

    def test_create_and_close(self):
        s = self._make_store()
        s.close()

    def test_upsert_create(self):
        s = self._make_store()
        mem, action = s.upsert("u1", "k1", "Hello world")
        assert action == "created"
        assert mem.key == "k1"
        assert mem.version == 1
        s.close()

    def test_upsert_skip_identical(self):
        s = self._make_store()
        s.upsert("u1", "k1", "Hello")
        _, action = s.upsert("u1", "k1", "Hello")
        assert action == "skipped"
        s.close()

    def test_upsert_update(self):
        s = self._make_store()
        s.upsert("u1", "k1", "v1")
        mem, action = s.upsert("u1", "k1", "v2")
        assert action == "updated"
        assert mem.version == 2
        assert mem.content == "v2"
        s.close()

    def test_get(self):
        s = self._make_store()
        s.upsert("u1", "k1", "hi")
        mem = s.get("u1", "k1")
        assert mem is not None
        assert mem.content == "hi"
        assert s.get("u1", "missing") is None
        s.close()

    def test_get_by_id(self):
        s = self._make_store()
        mem, _ = s.upsert("u1", "k1", "hi")
        fetched = s.get_by_id(mem.id)
        assert fetched is not None
        assert fetched.id == mem.id
        assert s.get_by_id("nonexistent-uuid") is None
        s.close()

    def test_list(self):
        s = self._make_store()
        s.upsert("u1", "k1", "A")
        s.upsert("u1", "k2", "B")
        s.upsert("u2", "k3", "C")
        assert len(s.list("u1")) == 2
        assert len(s.list("u2")) == 1
        s.close()

    def test_list_filter_type(self):
        s = self._make_store()
        s.upsert("u1", "k1", "A", memory_type="semantic")
        s.upsert("u1", "k2", "B", memory_type="episodic")
        assert len(s.list("u1", memory_type="semantic")) == 1
        s.close()

    def test_delete(self):
        s = self._make_store()
        s.upsert("u1", "k1", "hi")
        assert s.delete("u1", "k1") is True
        assert s.get("u1", "k1") is None
        assert s.delete("u1", "k1") is False
        s.close()

    def test_count(self):
        s = self._make_store()
        s.upsert("u1", "k1", "A")
        s.upsert("u1", "k2", "B")
        assert s.count("u1") == 2
        s.close()

    def test_versions(self):
        s = self._make_store()
        _m1, _ = s.upsert("u1", "k", "v1")
        s.upsert("u1", "k", "v2")
        m3, _ = s.upsert("u1", "k", "v3")
        versions = s.get_versions(m3.id)
        assert len(versions) == 2
        assert versions[0].version == 2
        assert versions[1].version == 1
        s.close()

    def test_search_vector(self):
        emb = DummyEmbedding(dimension=32)
        s = self._make_store()
        vec_a = emb(["Python programming"])[0]
        vec_b = emb(["JavaScript frontend"])[0]
        s.upsert("u1", "k1", "Python programming", embedding=vec_a)
        s.upsert("u1", "k2", "JavaScript frontend", embedding=vec_b)
        q = emb(["Python programming"])[0]
        results = s.search("u1", query_embedding=q, top_k=5)
        assert len(results) == 2
        assert results[0].key == "k1"  # exact match should be first
        assert results[0].score > results[1].score
        s.close()

    def test_search_text_fallback(self):
        s = self._make_store()
        s.upsert("u1", "k1", "Python programming language")
        s.upsert("u1", "k2", "JavaScript is for browsers")
        results = s.search("u1", query_text="Python programming", top_k=5)
        assert len(results) == 2
        assert results[0].key == "k1"
        s.close()

    def test_search_empty_user(self):
        s = self._make_store()
        results = s.search("nobody", query_text="anything")
        assert results == []
        s.close()

    def test_reset(self):
        s = self._make_store()
        s.upsert("u1", "k1", "A")
        s.upsert("u1", "k2", "B")
        assert s.count("u1") == 2
        s.reset()
        assert s.count("u1") == 0
        s.close()

    def test_metadata_roundtrip(self):
        s = self._make_store()
        meta = {"source": "chat", "tags": ["python", "pref"]}
        mem, _ = s.upsert("u1", "k1", "test", metadata=meta)
        assert mem.metadata == meta
        s.close()


# ═══════════════════════════════════════════════════════════════════
#  6. Embedded Client
# ═══════════════════════════════════════════════════════════════════


class TestEmbeddedClient:
    def test_repr(self):
        db = Client(path=":memory:")
        assert "DummyEmbedding" in repr(db)
        assert "mask_pii=False" in repr(db)
        db.close()

    def test_context_manager(self):
        with Client(path=":memory:") as db:
            assert db is not None

    def test_upsert_and_get(self):
        with Client(path=":memory:") as db:
            mem = db.upsert("u1", "pref:lang", "Likes Python")
            assert mem.key == "pref:lang"
            assert mem.content == "Likes Python"
            fetched = db.get("u1", "pref:lang")
            assert fetched is not None
            assert fetched.content == "Likes Python"

    def test_upsert_dedup(self):
        with Client(path=":memory:") as db:
            m1 = db.upsert("u1", "k", "same")
            m2 = db.upsert("u1", "k", "same")
            assert m1.version == m2.version == 1

    def test_upsert_versioning(self):
        with Client(path=":memory:") as db:
            db.upsert("u1", "k", "v1")
            m2 = db.upsert("u1", "k", "v2")
            assert m2.version == 2
            assert m2.content == "v2"

    def test_search(self):
        with Client(path=":memory:") as db:
            db.upsert("u1", "k1", "Python is great for backends")
            db.upsert("u1", "k2", "React is great for frontends")
            results = db.search("u1", "Python backend")
            assert len(results) > 0
            # Both should appear, scores are from dummy embeddings
            keys = [r.key for r in results]
            assert "k1" in keys
            assert "k2" in keys

    def test_search_with_type_filter(self):
        with Client(path=":memory:") as db:
            db.upsert("u1", "k1", "A", memory_type="semantic")
            db.upsert("u1", "k2", "B", memory_type="episodic")
            results = db.search("u1", "test", memory_types=["semantic"])
            keys = [r.key for r in results]
            assert "k1" in keys
            assert "k2" not in keys

    def test_list(self):
        with Client(path=":memory:") as db:
            db.upsert("u1", "k1", "A")
            db.upsert("u1", "k2", "B")
            db.upsert("u2", "k3", "C")
            assert len(db.list("u1")) == 2
            assert len(db.list("u2")) == 1

    def test_delete(self):
        with Client(path=":memory:") as db:
            db.upsert("u1", "k1", "hi")
            assert db.delete("u1", "k1") is True
            assert db.get("u1", "k1") is None
            assert db.delete("u1", "k1") is False

    def test_count(self):
        with Client(path=":memory:") as db:
            db.upsert("u1", "k1", "A")
            db.upsert("u1", "k2", "B")
            assert db.count("u1") == 2

    def test_versions(self):
        with Client(path=":memory:") as db:
            db.upsert("u1", "k", "v1")
            db.upsert("u1", "k", "v2")
            m3 = db.upsert("u1", "k", "v3")
            vv = db.versions(m3.id)
            assert len(vv) == 2  # v1 and v2 are snapshots

    def test_get_by_id(self):
        with Client(path=":memory:") as db:
            mem = db.upsert("u1", "k1", "hello")
            fetched = db.get_by_id(mem.id)
            assert fetched is not None
            assert fetched.id == mem.id

    def test_pii_masking(self):
        with Client(path=":memory:", mask_pii=True) as db:
            mem = db.upsert("u1", "k", "Email josh@co.com please")
            assert "[EMAIL]" in mem.content
            assert "josh@co.com" not in mem.content

    def test_pii_masking_disabled(self):
        with Client(path=":memory:", mask_pii=False) as db:
            mem = db.upsert("u1", "k", "Email josh@co.com please")
            assert "josh@co.com" in mem.content

    def test_memory_type_filter(self):
        with Client(path=":memory:") as db:
            db.upsert("u1", "k1", "A", memory_type="semantic")
            db.upsert("u1", "k2", "B", memory_type="episodic")
            assert len(db.list("u1", memory_type="semantic")) == 1
            assert len(db.list("u1", memory_type="episodic")) == 1

    def test_metadata(self):
        with Client(path=":memory:") as db:
            mem = db.upsert(
                "u1",
                "k1",
                "test",
                metadata={"source": "chat", "lang": "en"},
            )
            assert mem.metadata == {"source": "chat", "lang": "en"}

    def test_reset(self):
        with Client(path=":memory:") as db:
            db.upsert("u1", "k1", "A")
            db.upsert("u1", "k2", "B")
            assert db.count("u1") == 2
            db.reset()
            assert db.count("u1") == 0

    def test_custom_embedding(self):
        """Verify a custom embedding function is accepted."""

        class ConstantEmb:
            dimension = 16

            def __call__(self, texts):
                return [[1.0 / 16**0.5] * 16 for _ in texts]

        with Client(path=":memory:", embedding_fn=ConstantEmb()) as db:
            db.upsert("u1", "k1", "hello")
            results = db.search("u1", "hello")
            assert len(results) == 1


# ═══════════════════════════════════════════════════════════════════
#  7. HttpClient (mocked)
# ═══════════════════════════════════════════════════════════════════


class TestHttpClient:
    """Test HttpClient with mocked HTTP responses."""

    def test_repr(self):
        client = HttpClient(url="http://test:8100")
        assert "HttpClient" in repr(client)
        client.close()

    def test_context_manager(self):
        with HttpClient(url="http://test:8100") as client:
            assert client is not None

    def test_dict_to_memory(self):
        d = {
            "id": "abc",
            "user_id": "u1",
            "memory_key": "k1",
            "content": "hello",
            "memory_type": "semantic",
            "scope": "user",
            "status": "active",
            "importance_score": 0.9,
            "confidence": 0.8,
            "authority_level": 5.0,
            "payload": {"tag": "test"},
            "version": 3,
            "content_hash": "abc123",
            "created_at": "2025-01-01T00:00:00+00:00",
            "updated_at": "2025-06-15T12:00:00+00:00",
        }
        mem = HttpClient._dict_to_memory(d)
        assert mem.key == "k1"
        assert mem.importance == 0.9
        assert mem.version == 3
        assert mem.metadata == {"tag": "test"}

    def test_dict_to_memory_defaults(self):
        """Minimal dict should use sane defaults."""
        mem = HttpClient._dict_to_memory({"content": "hello"})
        assert mem.content == "hello"
        assert mem.memory_type == "semantic"
        assert mem.importance == 0.5

    def test_raise_on_error(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 422
        mock_resp.text = "validation error"
        mock_resp.json.return_value = {"detail": "bad request"}
        client = HttpClient(url="http://test:8100")
        with pytest.raises(RuntimeError, match="422"):
            client._raise(mock_resp)
        client.close()


# ═══════════════════════════════════════════════════════════════════
#  8. Edge cases
# ═══════════════════════════════════════════════════════════════════


class TestEdgeCases:
    def test_empty_content(self):
        with Client(path=":memory:") as db:
            mem = db.upsert("u1", "k", "")
            assert mem.content == ""

    def test_unicode_content(self):
        with Client(path=":memory:") as db:
            mem = db.upsert("u1", "k", "日本語テスト 🚀")
            assert mem.content == "日本語テスト 🚀"

    def test_long_content(self):
        with Client(path=":memory:") as db:
            text = "x" * 100_000
            mem = db.upsert("u1", "k", text)
            assert len(mem.content) == 100_000

    def test_special_chars_in_key(self):
        with Client(path=":memory:") as db:
            db.upsert("u1", "pref:lang/python:3.11", "test")
            fetched = db.get("u1", "pref:lang/python:3.11")
            assert fetched is not None

    def test_many_memories(self):
        """Insert 500 memories, verify search returns top_k."""
        with Client(path=":memory:") as db:
            for i in range(500):
                db.upsert("u1", f"k{i}", f"Memory number {i}")
            assert db.count("u1") == 500
            results = db.search("u1", "Memory number 42", top_k=10)
            assert len(results) == 10

    def test_multiple_users_isolated(self):
        with Client(path=":memory:") as db:
            db.upsert("alice", "k1", "Alice data")
            db.upsert("bob", "k1", "Bob data")
            assert db.get("alice", "k1").content == "Alice data"
            assert db.get("bob", "k1").content == "Bob data"
            assert db.count("alice") == 1
            assert db.count("bob") == 1

    def test_get_nonexistent(self):
        with Client(path=":memory:") as db:
            assert db.get("u1", "nope") is None
            assert db.get_by_id("fake-uuid") is None


# ═══════════════════════════════════════════════════════════════════
#  9. ShortTermMemory (conversation buffer)
# ═══════════════════════════════════════════════════════════════════


class TestShortTermMemory:
    """Test short-term memory (conversation buffer per thread)."""

    def _make(self, **kwargs):
        client = Client(path=":memory:")
        return ShortTermMemory(client=client, user_id="u1", **kwargs)

    def test_add_and_get_messages(self):
        stm = self._make()
        stm.add_user("Hello!")
        stm.add_assistant("Hi there!")
        msgs = stm.get_messages()
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "Hello!"
        assert msgs[1]["role"] == "assistant"
        assert msgs[1]["content"] == "Hi there!"
        stm._client.close()

    def test_message_ordering(self):
        stm = self._make()
        for i in range(10):
            stm.add("user", f"Message {i}")
        msgs = stm.get_messages()
        assert len(msgs) == 10
        for i, m in enumerate(msgs):
            assert m["seq"] == i
            assert m["content"] == f"Message {i}"
        stm._client.close()

    def test_max_messages_limit(self):
        stm = self._make(max_messages=3)
        for i in range(10):
            stm.add("user", f"Msg {i}")
        msgs = stm.get_messages()
        assert len(msgs) == 3
        # Should return the LATEST 3
        assert msgs[0]["content"] == "Msg 7"
        assert msgs[2]["content"] == "Msg 9"
        stm._client.close()

    def test_get_last(self):
        stm = self._make()
        stm.add_user("First")
        stm.add_assistant("Second")
        stm.add_user("Third")
        last = stm.get_last(n=1)
        assert len(last) == 1
        assert last[0]["content"] == "Third"
        stm._client.close()

    def test_count(self):
        stm = self._make()
        assert stm.count() == 0
        stm.add_user("Hello")
        assert stm.count() == 1
        stm.add_assistant("Hi")
        assert stm.count() == 2
        stm._client.close()

    def test_clear(self):
        stm = self._make()
        stm.add_user("Hello")
        stm.add_assistant("Hi")
        deleted = stm.clear()
        assert deleted == 2
        assert stm.count() == 0
        stm._client.close()

    def test_to_list(self):
        stm = self._make()
        stm.add_system("You are helpful")
        stm.add_user("Hi")
        stm.add_assistant("Hello!")
        result = stm.to_list()
        assert result == [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
        ]
        stm._client.close()

    def test_to_string(self):
        stm = self._make()
        stm.add_user("Hello")
        stm.add_assistant("Hi there!")
        s = stm.to_string()
        assert s == "user: Hello\nassistant: Hi there!"
        stm._client.close()

    def test_role_filter(self):
        stm = self._make()
        stm.add_system("System prompt")
        stm.add_user("User msg")
        stm.add_assistant("Bot msg")
        stm.add_tool("Tool result")
        user_msgs = stm.get_messages(roles=["user"])
        assert len(user_msgs) == 1
        assert user_msgs[0]["role"] == "user"
        stm._client.close()

    def test_thread_isolation(self):
        client = Client(path=":memory:")
        t1 = ShortTermMemory(client=client, user_id="u1", thread_id="thread-1")
        t2 = ShortTermMemory(client=client, user_id="u1", thread_id="thread-2")
        t1.add_user("Thread 1 message")
        t2.add_user("Thread 2 message")
        assert t1.count() == 1
        assert t2.count() == 1
        assert t1.get_messages()[0]["content"] == "Thread 1 message"
        assert t2.get_messages()[0]["content"] == "Thread 2 message"
        client.close()

    def test_new_thread(self):
        stm = self._make(thread_id="original")
        stm.add_user("Hello")
        new = stm.new_thread("next-thread")
        assert new.thread_id == "next-thread"
        assert new.count() == 0
        # Original still has its message
        assert stm.count() == 1
        stm._client.close()

    def test_metadata_on_messages(self):
        stm = self._make()
        stm.add("tool", "Result from calculator", metadata={"tool_call_id": "tc_123"})
        msgs = stm.get_messages()
        assert msgs[0]["metadata"]["tool_call_id"] == "tc_123"
        stm._client.close()

    def test_len(self):
        stm = self._make()
        assert len(stm) == 0
        stm.add_user("Hello")
        assert len(stm) == 1
        stm._client.close()

    def test_repr(self):
        stm = self._make(thread_id="test-thread")
        r = repr(stm)
        assert "ShortTermMemory" in r
        assert "test-thread" in r
        stm._client.close()


# ═══════════════════════════════════════════════════════════════════
#  10. LongTermMemory (persistent knowledge)
# ═══════════════════════════════════════════════════════════════════


class TestLongTermMemory:
    """Test long-term memory (persistent knowledge store)."""

    def _make(self):
        client = Client(path=":memory:")
        return LongTermMemory(client=client, user_id="u1")

    def test_remember_and_get(self):
        ltm = self._make()
        mem = ltm.remember("pref:lang", "User prefers Python")
        assert mem.content == "User prefers Python"
        assert mem.key == "pref:lang"
        retrieved = ltm.get("pref:lang")
        assert retrieved is not None
        assert retrieved.content == "User prefers Python"
        ltm._client.close()

    def test_recall_semantic_search(self):
        ltm = self._make()
        ltm.remember("pref:lang", "User prefers Python for backend")
        ltm.remember("pref:editor", "User uses VS Code")
        ltm.remember("fact:name", "User's name is Josh")
        results = ltm.recall("programming language")
        assert len(results) > 0
        ltm._client.close()

    def test_forget(self):
        ltm = self._make()
        ltm.remember("temp", "Temporary fact")
        assert ltm.count() == 1
        deleted = ltm.forget("temp")
        assert deleted is True
        assert ltm.count() == 0
        ltm._client.close()

    def test_list_all(self):
        ltm = self._make()
        ltm.remember("k1", "Memory 1")
        ltm.remember("k2", "Memory 2")
        ltm.remember("k3", "Memory 3")
        all_mems = ltm.list_all()
        assert len(all_mems) == 3
        ltm._client.close()

    def test_default_type(self):
        client = Client(path=":memory:")
        ltm = LongTermMemory(client=client, user_id="u1", default_type="episodic")
        mem = ltm.remember("event:1", "Had a great meeting")
        assert mem.memory_type == "episodic"
        client.close()

    def test_importance_and_confidence(self):
        ltm = self._make()
        mem = ltm.remember("critical", "Very important fact", importance=0.95, confidence=0.99)
        assert mem.importance == 0.95
        assert mem.confidence == 0.99
        ltm._client.close()

    def test_metadata(self):
        ltm = self._make()
        mem = ltm.remember("k", "Content", metadata={"source": "user_input", "tags": ["pref"]})
        assert mem.metadata["source"] == "user_input"
        ltm._client.close()

    def test_versioning(self):
        ltm = self._make()
        ltm.remember("pref:lang", "User likes JavaScript")
        ltm.remember("pref:lang", "User likes TypeScript")
        ltm.remember("pref:lang", "User prefers Python")
        mem = ltm.get("pref:lang")
        assert mem.version == 3
        assert mem.content == "User prefers Python"
        ltm._client.close()

    def test_repr(self):
        ltm = self._make()
        r = repr(ltm)
        assert "LongTermMemory" in r
        ltm._client.close()


# ═══════════════════════════════════════════════════════════════════
#  11. MemoryManager (unified interface)
# ═══════════════════════════════════════════════════════════════════


class TestMemoryManager:
    """Test the unified MemoryManager."""

    def test_basic_creation(self):
        with MemoryManager("u1", path=":memory:") as mgr:
            assert mgr.user_id == "u1"
            assert mgr.short_term.count() == 0
            assert mgr.long_term.count() == 0

    def test_short_term_through_manager(self):
        with MemoryManager("u1", path=":memory:") as mgr:
            mgr.short_term.add_user("Hello!")
            mgr.short_term.add_assistant("Hi!")
            assert mgr.short_term.count() == 2
            msgs = mgr.short_term.to_list()
            assert msgs[0] == {"role": "user", "content": "Hello!"}

    def test_long_term_through_manager(self):
        with MemoryManager("u1", path=":memory:") as mgr:
            mgr.long_term.remember("pref:lang", "User likes Python")
            assert mgr.long_term.count() == 1
            mem = mgr.long_term.get("pref:lang")
            assert mem.content == "User likes Python"

    def test_promote(self):
        with MemoryManager("u1", path=":memory:", thread_id="t1") as mgr:
            mgr.short_term.add_user("I really love Python")
            mem = mgr.promote("pref:lang", "User loves Python", importance=0.9)
            assert mem.content == "User loves Python"
            assert mem.importance == 0.9
            assert mem.metadata["source"] == "conversation"
            assert mem.metadata["thread_id"] == "t1"
            assert "promoted_at" in mem.metadata

    def test_new_thread(self):
        with MemoryManager("u1", path=":memory:") as mgr:
            mgr.short_term.add_user("Old thread message")
            mgr.new_thread("new-session")
            assert mgr.short_term.thread_id == "new-session"
            assert mgr.short_term.count() == 0

    def test_get_context_window(self):
        with MemoryManager("u1", path=":memory:") as mgr:
            # Add conversation
            mgr.short_term.add_user("I prefer Python")
            mgr.short_term.add_assistant("Noted!")
            # Add long-term knowledge
            mgr.long_term.remember("pref:lang", "User prefers Python")
            mgr.long_term.remember("pref:editor", "User uses VS Code")

            ctx = mgr.get_context_window("programming language?", n_messages=5, n_memories=3)
            assert len(ctx["messages"]) == 2
            assert len(ctx["relevant_memories"]) > 0
            assert ctx["stats"]["message_count"] == 2
            assert ctx["stats"]["memory_count"] == 2

    def test_get_context_window_no_query(self):
        with MemoryManager("u1", path=":memory:") as mgr:
            mgr.short_term.add_user("Hello")
            ctx = mgr.get_context_window(None)
            assert len(ctx["messages"]) == 1
            assert ctx["relevant_memories"] == []

    def test_reset(self):
        with MemoryManager("u1", path=":memory:") as mgr:
            mgr.short_term.add_user("Hello")
            mgr.long_term.remember("k", "Content")
            mgr.reset()
            assert mgr.short_term.count() == 0
            assert mgr.long_term.count() == 0

    def test_context_manager(self):
        with MemoryManager("u1", path=":memory:") as mgr:
            mgr.long_term.remember("k", "Value")
        # Should not raise after __exit__

    def test_repr(self):
        with MemoryManager("u1", path=":memory:") as mgr:
            r = repr(mgr)
            assert "MemoryManager" in r

    def test_combined_workflow(self):
        """End-to-end: conversation → insight → promote → recall."""
        with MemoryManager("agent-1", path=":memory:") as mgr:
            # Simulate a conversation
            mgr.short_term.add_system("You are a helpful assistant.")
            mgr.short_term.add_user("I'm working on a Python backend project.")
            mgr.short_term.add_assistant("Great! I can help with that.")
            mgr.short_term.add_user("I always use FastAPI for APIs.")
            mgr.short_term.add_assistant("FastAPI is excellent for async APIs.")

            assert mgr.short_term.count() == 5

            # Agent identifies insights and promotes to long-term
            mgr.promote("pref:language", "User works with Python backend")
            mgr.promote("pref:framework", "User uses FastAPI for APIs")

            assert mgr.long_term.count() == 2

            # Later, in a new thread, recall relevant knowledge
            mgr.new_thread("session-2")
            mgr.short_term.add_user("What framework should I use for a new API?")

            results = mgr.long_term.recall("API framework preference")
            assert len(results) > 0

            # Build context for LLM
            ctx = mgr.get_context_window("API framework preference")
            assert len(ctx["messages"]) == 1  # only session-2 messages
            assert len(ctx["relevant_memories"]) > 0

    def test_max_messages_propagation(self):
        """Verify max_messages config flows through to ShortTermMemory."""
        with MemoryManager("u1", path=":memory:", max_messages=5) as mgr:
            for i in range(20):
                mgr.short_term.add_user(f"Message {i}")
            msgs = mgr.short_term.get_messages()
            assert len(msgs) == 5

    def test_pii_masking_in_long_term(self):
        """Long-term memories get PII masked when mask_pii=True."""
        with MemoryManager("u1", path=":memory:", mask_pii=True) as mgr:
            mgr.long_term.remember("contact", "Email josh@company.com, SSN 123-45-6789")
            mem = mgr.long_term.get("contact")
            assert "[EMAIL]" in mem.content
            assert "[SSN]" in mem.content
            assert "josh@company.com" not in mem.content


# ═══════════════════════════════════════════════════════════════════
#  12. SQLiteStore thread_messages operations
# ═══════════════════════════════════════════════════════════════════


class TestSQLiteStoreMessages:
    """Test thread_messages table operations in SQLiteStore."""

    def test_add_and_get_messages(self):
        store = SQLiteStore(":memory:")
        store.add_message("t1", "user", "Hello")
        store.add_message("t1", "assistant", "Hi")
        msgs = store.get_messages("t1")
        assert len(msgs) == 2
        assert msgs[0]["seq"] == 0
        assert msgs[1]["seq"] == 1
        store.close()

    def test_list_threads(self):
        store = SQLiteStore(":memory:")
        store.add_message("t1", "user", "Hello")
        store.add_message("t2", "user", "Hi")
        store.add_message("t1", "assistant", "World")
        threads = store.list_threads()
        assert len(threads) == 2
        # t1 has 2 messages
        t1 = next(t for t in threads if t["thread_id"] == "t1")
        assert t1["message_count"] == 2
        store.close()

    def test_clear_thread(self):
        store = SQLiteStore(":memory:")
        store.add_message("t1", "user", "Hello")
        store.add_message("t1", "user", "World")
        deleted = store.clear_thread("t1")
        assert deleted == 2
        assert store.count_messages("t1") == 0
        store.close()

    def test_count_messages(self):
        store = SQLiteStore(":memory:")
        assert store.count_messages("t1") == 0
        store.add_message("t1", "user", "Hello")
        assert store.count_messages("t1") == 1
        store.close()

    def test_messages_with_metadata(self):
        store = SQLiteStore(":memory:")
        store.add_message("t1", "tool", "Result", metadata={"tool_id": "calc"})
        msgs = store.get_messages("t1")
        assert msgs[0]["metadata"] == {"tool_id": "calc"}
        store.close()

    def test_get_messages_limit(self):
        store = SQLiteStore(":memory:")
        for i in range(10):
            store.add_message("t1", "user", f"Msg {i}")
        msgs = store.get_messages("t1", limit=3)
        assert len(msgs) == 3
        # Should be the latest 3 in order
        assert msgs[0]["content"] == "Msg 7"
        assert msgs[2]["content"] == "Msg 9"
        store.close()

    def test_reset_clears_messages(self):
        store = SQLiteStore(":memory:")
        store.add_message("t1", "user", "Hello")
        store.reset()
        assert store.count_messages("t1") == 0
        store.close()
