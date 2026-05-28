import importlib.util
import json
import sqlite3
import sys
import types
from pathlib import Path


PLUGIN_API = Path(__file__).resolve().parents[1] / "dashboard" / "plugin_api.py"


def load_plugin_api(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    fake_constants = types.ModuleType("hermes_constants")
    fake_constants.get_hermes_home = lambda: str(tmp_path)
    monkeypatch.setitem(sys.modules, "hermes_constants", fake_constants)
    spec = importlib.util.spec_from_file_location("plugin_api_under_test", PLUGIN_API)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_session_search_payload_uses_hermes_session_search_tool_without_source(monkeypatch, tmp_path):
    calls = []

    fake_tools = types.ModuleType("tools")
    fake_session_search_tool = types.ModuleType("tools.session_search_tool")

    def fake_session_search(**kwargs):
        calls.append(kwargs)
        return json.dumps({
            "success": True,
            "mode": "discover",
            "query": kwargs["query"],
            "count": 2,
            "results": [{
                "session_id": "s1",
                "title": "Memory UI work",
                "when": "now",
                "source": "cli",
                "match_message_id": 42,
                "snippet": "session search result",
                "messages": [{"id": 42, "role": "user", "content": "find memory"}],
            }, {
                "session_id": "s2",
                "title": "Telegram memory UI work",
                "when": "now",
                "source": "telegram",
                "match_message_id": 43,
                "snippet": "telegram result",
                "messages": [{"id": 43, "role": "user", "content": "find memory from telegram"}],
            }],
        })

    setattr(fake_session_search_tool, "session_search", fake_session_search)
    monkeypatch.setitem(sys.modules, "tools", fake_tools)
    monkeypatch.setitem(sys.modules, "tools.session_search_tool", fake_session_search_tool)

    module = load_plugin_api(monkeypatch, tmp_path)
    payload = module._session_search_payload(query="memory", limit=99, sort="newest")

    assert payload["error"] is None
    assert payload["count"] == 2
    assert payload["source"] == ""
    assert [item["session_id"] for item in payload["results"]] == ["s1", "s2"]
    assert calls == [{"query": "memory", "limit": 10, "sort": "newest", "role_filter": "user,assistant"}]


def test_session_search_payload_uses_source_aware_db_search(monkeypatch, tmp_path):
    db_calls = []

    class FakeSessionDB:
        def search_messages(self, **kwargs):
            db_calls.append(("search_messages", kwargs))
            return [{
                "id": 43,
                "session_id": "s2",
                "role": "user",
                "source": "telegram",
                "model": "test-model",
                "session_started": 123,
                "snippet": "telegram result",
            }]

        def get_anchored_view(self, session_id, msg_id, window=5, bookend=3):
            db_calls.append(("get_anchored_view", session_id, msg_id, window, bookend))
            return {
                "bookend_start": [],
                "window": [{"id": msg_id, "role": "user", "content": "find memory from telegram"}],
                "bookend_end": [],
                "messages_before": 0,
                "messages_after": 0,
            }

        def get_session(self, session_id):
            db_calls.append(("get_session", session_id))
            return {"source": "telegram", "title": "Telegram memory UI work", "started_at": 123, "model": "test-model"}

    fake_hermes_state = types.ModuleType("hermes_state")
    fake_hermes_state.SessionDB = FakeSessionDB
    monkeypatch.setitem(sys.modules, "hermes_state", fake_hermes_state)

    fake_tools = types.ModuleType("tools")
    fake_session_search_tool = types.ModuleType("tools.session_search_tool")
    fake_session_search_tool._resolve_to_parent = lambda _db, session_id: session_id
    fake_session_search_tool._format_timestamp = lambda value: f"ts:{value}"
    monkeypatch.setitem(sys.modules, "tools", fake_tools)
    monkeypatch.setitem(sys.modules, "tools.session_search_tool", fake_session_search_tool)

    module = load_plugin_api(monkeypatch, tmp_path)
    payload = module._session_search_payload(query="memory", limit=3, sort="newest", source="telegram")

    assert payload["error"] is None
    assert payload["source"] == "telegram"
    assert payload["count"] == 1
    assert payload["results"][0]["session_id"] == "s2"
    assert payload["results"][0]["source"] == "telegram"
    assert payload["results"][0]["messages"][0]["anchor"] is True
    search_call = db_calls[0]
    assert search_call[0] == "search_messages"
    assert search_call[1]["source_filter"] == ["telegram"]
    assert search_call[1]["limit"] == module.SESSION_SEARCH_SCAN_LIMIT


def test_session_search_payload_maps_api_source_to_api_server(monkeypatch, tmp_path):
    db_calls = []

    class FakeSessionDB:
        def search_messages(self, **kwargs):
            db_calls.append(kwargs)
            return []

    fake_hermes_state = types.ModuleType("hermes_state")
    fake_hermes_state.SessionDB = FakeSessionDB
    monkeypatch.setitem(sys.modules, "hermes_state", fake_hermes_state)

    module = load_plugin_api(monkeypatch, tmp_path)
    payload = module._session_search_payload(query="memory", source="api")

    assert payload["error"] is None
    assert payload["source"] == "api-server"
    assert db_calls[0]["source_filter"] == ["api-server"]


def test_session_search_payload_preserves_custom_source_casing(monkeypatch, tmp_path):
    db_calls = []

    class FakeSessionDB:
        def search_messages(self, **kwargs):
            db_calls.append(kwargs)
            return []

    fake_hermes_state = types.ModuleType("hermes_state")
    fake_hermes_state.SessionDB = FakeSessionDB
    monkeypatch.setitem(sys.modules, "hermes_state", fake_hermes_state)

    module = load_plugin_api(monkeypatch, tmp_path)
    payload = module._session_search_payload(query="memory", source="Paperclip")

    assert payload["error"] is None
    assert payload["source"] == "Paperclip"
    assert db_calls[0]["source_filter"] == ["Paperclip"]


def test_mem0_config_hides_api_key_and_uses_memory_client(monkeypatch, tmp_path):
    (tmp_path / "config.yaml").write_text("memory:\n  provider: mem0\n", encoding="utf-8")
    (tmp_path / "mem0.json").write_text(
        json.dumps({"user_id": "xraysight-test", "agent_id": "hermes-test"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("MEM0_API_KEY", "secret-token")

    calls = []

    class FakeMemoryClient:
        def __init__(self, api_key):
            calls.append(("init", api_key))

        def get_all(self, filters):
            calls.append(("get_all", filters))
            return {"results": [{"id": "1", "memory": "Mem0 dashboard integration works"}]}

    fake_mem0 = types.ModuleType("mem0")
    fake_mem0.MemoryClient = FakeMemoryClient
    monkeypatch.setitem(sys.modules, "mem0", fake_mem0)

    module = load_plugin_api(monkeypatch, tmp_path)
    payload = module._mem0_payload(limit=5)

    assert payload["provider_configured"] is True
    assert payload["api_key_present"] is True
    assert payload["user_id"] == "xraysight-test"
    assert payload["agent_id"] == "hermes-test"
    assert payload["memory_count"] == 1
    assert payload["memories"][0]["memory"] == "Mem0 dashboard integration works"
    assert "secret-token" not in json.dumps(payload)
    assert calls == [("init", "secret-token"), ("get_all", {"user_id": "xraysight-test"})]


def test_mem0_search_uses_search_endpoint(monkeypatch, tmp_path):
    (tmp_path / "config.yaml").write_text("memory:\n  provider: mem0\n", encoding="utf-8")
    (tmp_path / "mem0.json").write_text(json.dumps({"user_id": "u1"}), encoding="utf-8")
    monkeypatch.setenv("MEM0_API_KEY", "secret-token")

    calls = []

    class FakeMemoryClient:
        def __init__(self, api_key):
            calls.append(("init", api_key))

        def search(self, query, filters, rerank, top_k):
            calls.append(("search", query, filters, rerank, top_k))
            return [{"id": "s1", "memory": "searched memory", "score": 0.91}]

    fake_mem0 = types.ModuleType("mem0")
    fake_mem0.MemoryClient = FakeMemoryClient
    monkeypatch.setitem(sys.modules, "mem0", fake_mem0)

    module = load_plugin_api(monkeypatch, tmp_path)
    payload = module._mem0_payload(search="dashboard", limit=7)

    assert payload["memory_count"] == 1
    assert payload["memories"][0]["score"] == 0.91
    assert calls == [("init", "secret-token"), ("search", "dashboard", {"user_id": "u1"}, True, 7)]


def test_provider_error_messages_are_redacted(monkeypatch, tmp_path):
    (tmp_path / "config.yaml").write_text("memory:\n  provider: mem0\n", encoding="utf-8")
    (tmp_path / "mem0.json").write_text(json.dumps({"user_id": "u1"}), encoding="utf-8")
    monkeypatch.setenv("MEM0_API_KEY", "secret-token")

    class FakeMemoryClient:
        def __init__(self, api_key):
            pass

        def get_all(self, filters):
            raise RuntimeError(
                "request failed: Bearer secret-token "
                "https://user:pass@example.test/v1?api_key=secret-token&token=abc123"
            )

    fake_mem0 = types.ModuleType("mem0")
    fake_mem0.MemoryClient = FakeMemoryClient
    monkeypatch.setitem(sys.modules, "mem0", fake_mem0)

    module = load_plugin_api(monkeypatch, tmp_path)
    payload = module._mem0_payload(limit=5)

    assert payload["error"]
    dumped = json.dumps(payload)
    assert "secret-token" not in dumped
    assert "user:pass" not in dumped
    assert "abc123" not in dumped
    assert "[REDACTED]" in payload["error"]


def install_fake_honcho_client(monkeypatch, tmp_path, calls):
    fake_plugins = types.ModuleType("plugins")
    fake_memory = types.ModuleType("plugins.memory")
    fake_honcho = types.ModuleType("plugins.memory.honcho")
    fake_client = types.ModuleType("plugins.memory.honcho.client")

    class FakeConfig:
        host = "hermes.test"
        workspace_id = "workspace-test"
        api_key = "honcho-secret"
        base_url = "https://honcho.local"
        environment = "production"
        peer_name = "xraysight"
        ai_peer = "hermes"
        enabled = True
        recall_mode = "hybrid"
        session_strategy = "per-directory"
        save_messages = True
        write_frequency = "async"
        context_tokens = 2048
        dialectic_depth = 2
        dialectic_reasoning_level = "low"
        dialectic_dynamic = True
        dialectic_max_chars = 600
        observation_mode = "directional"
        user_observe_me = True
        user_observe_others = True
        ai_observe_me = True
        ai_observe_others = True
        explicitly_configured = True

        @classmethod
        def from_global_config(cls):
            calls.append(("from_global_config",))
            return cls()

    class FakeConclusionScope:
        def __init__(self, observer, target):
            self.observer = observer
            self.target = target

        def list(self, page=1, size=50, reverse=False, **kwargs):
            calls.append(("conclusions", self.observer, self.target, page, size, reverse))
            return [types.SimpleNamespace(id=f"{self.target}-c1", content=f"Conclusion about {self.target}", created_at="2026-01-01T00:00:00Z")]

    class FakePeer:
        def __init__(self, peer_id):
            self.peer_id = peer_id

        def context(self, **kwargs):
            calls.append(("context", self.peer_id, kwargs))
            return types.SimpleNamespace(
                representation=f"Representation for {self.peer_id}",
                peer_card=[f"Card fact for {self.peer_id}"],
            )

        def conclusions_of(self, target):
            calls.append(("conclusions_of", self.peer_id, target))
            return FakeConclusionScope(self.peer_id, target)

    class FakeHonchoClient:
        def peer(self, peer_id):
            calls.append(("peer", peer_id))
            return FakePeer(peer_id)

    def get_honcho_client(config):
        calls.append(("get_honcho_client", config.host, config.workspace_id, config.api_key))
        return FakeHonchoClient()

    def resolve_config_path():
        return tmp_path / "honcho.json"

    fake_client.HonchoClientConfig = FakeConfig
    fake_client.get_honcho_client = get_honcho_client
    fake_client.resolve_config_path = resolve_config_path
    monkeypatch.setitem(sys.modules, "plugins", fake_plugins)
    monkeypatch.setitem(sys.modules, "plugins.memory", fake_memory)
    monkeypatch.setitem(sys.modules, "plugins.memory.honcho", fake_honcho)
    monkeypatch.setitem(sys.modules, "plugins.memory.honcho.client", fake_client)


# --- Regression tests for _list_honcho_conclusions -------------------------
#
# The dashboard used to render `len(conclusions)` as if it were the database
# total. These tests pin the contract that:
#   1. SyncPage-like objects with `.items` and `.total` surface `.total`.
#   2. Plain-list fallback paths report `len(items)`.
#   3. The function uses the page's items as-is and does not iterate or
#      fetch additional pages (no surprise N+1 calls against the SDK).


class _FakeSyncPage:
    """Minimal stand-in for honcho.pagination.SyncPage."""

    def __init__(self, items, total):
        self.items = items
        self.total = total


def _make_observer_peer(returned_page, calls):
    """Build a fake observer peer whose `conclusions_of(...).list(...)`
    returns ``returned_page`` and records every call into ``calls``."""

    class _Scope:
        def __init__(self, target):
            self.target = target

        def list(self, page=1, size=50, reverse=False, **kwargs):
            calls.append(("list", self.target, page, size, reverse))
            return returned_page

    class _Observer:
        def conclusions_of(self, target):
            calls.append(("conclusions_of", target))
            return _Scope(target)

    return _Observer()


def _conclusion(idx, created_at="2026-01-01T00:00:00Z"):
    return types.SimpleNamespace(
        id=f"c-{idx}",
        content=f"conclusion {idx}",
        created_at=created_at,
    )


def test_list_honcho_conclusions_uses_syncpage_total(monkeypatch, tmp_path):
    module = load_plugin_api(monkeypatch, tmp_path)
    page = _FakeSyncPage(items=[_conclusion(1), _conclusion(2)], total=2076)
    calls = []
    observer = _make_observer_peer(page, calls)

    items, total = module._list_honcho_conclusions(observer, "xraysight", limit=50)

    assert total == 2076
    assert len(items) == 2
    assert [c["content"] for c in items] == ["conclusion 1", "conclusion 2"]
    # Only one page request — no accidental pagination loop.
    list_calls = [c for c in calls if c[0] == "list"]
    assert len(list_calls) == 1


def test_list_honcho_conclusions_falls_back_to_len_items(monkeypatch, tmp_path):
    module = load_plugin_api(monkeypatch, tmp_path)
    # Plain list — no `.items` / `.total` attributes; older SDK shape.
    plain = [_conclusion(1), _conclusion(2), _conclusion(3)]
    calls = []
    observer = _make_observer_peer(plain, calls)

    items, total = module._list_honcho_conclusions(observer, "xraysight", limit=50)

    assert total == 3
    assert len(items) == 3
    list_calls = [c for c in calls if c[0] == "list"]
    assert len(list_calls) == 1


def test_list_honcho_conclusions_falls_back_when_total_is_none(monkeypatch, tmp_path):
    module = load_plugin_api(monkeypatch, tmp_path)
    # SyncPage with `total=None` despite non-empty items — guard against
    # backends that omit pagination metadata.
    page = _FakeSyncPage(items=[_conclusion(1), _conclusion(2)], total=None)
    calls = []
    observer = _make_observer_peer(page, calls)

    items, total = module._list_honcho_conclusions(observer, "xraysight", limit=50)

    assert total == 2  # not 0
    assert len(items) == 2


def test_list_honcho_conclusions_does_not_fetch_extra_pages(monkeypatch, tmp_path):
    module = load_plugin_api(monkeypatch, tmp_path)
    # Even when total >> page size, the function must use only the page
    # items it was given, not call .list() repeatedly.
    page = _FakeSyncPage(items=[_conclusion(i) for i in range(50)], total=2076)
    calls = []
    observer = _make_observer_peer(page, calls)

    items, total = module._list_honcho_conclusions(observer, "xraysight", limit=50)

    assert total == 2076
    assert len(items) == 50
    list_calls = [c for c in calls if c[0] == "list"]
    assert len(list_calls) == 1, f"expected single page fetch, got {list_calls}"


def test_honcho_payload_hides_api_key_and_fetches_peer_context(monkeypatch, tmp_path):
    (tmp_path / "config.yaml").write_text("memory:\n  provider: honcho\n", encoding="utf-8")
    (tmp_path / "honcho.json").write_text(json.dumps({"apiKey": "honcho-secret"}), encoding="utf-8")
    calls = []
    install_fake_honcho_client(monkeypatch, tmp_path, calls)

    module = load_plugin_api(monkeypatch, tmp_path)
    payload = module._honcho_payload(limit=5, search="xraysight")

    assert payload["provider_configured"] is True
    assert payload["api_key_present"] is True
    assert payload["base_url_present"] is True
    assert payload["workspace"] == "workspace-test"
    assert payload["host"] == "hermes.test"
    assert payload["user_peer"] == "xraysight"
    assert payload["ai_peer"] == "hermes"
    assert payload["user"]["card"] == ["Card fact for xraysight"]
    assert payload["ai"]["representation"] == "Representation for hermes"
    assert payload["user"]["conclusions"][0]["content"] == "Conclusion about xraysight"
    assert payload["search_result_count"] == 3
    assert [result["source"] for result in payload["search_results"]] == ["User peer card", "User peer representation", "User peer conclusion"]
    assert "honcho-secret" not in json.dumps(payload)
    assert ("context", "xraysight", {"target": "xraysight", "search_query": "xraysight", "search_top_k": 5}) in calls
    assert ("context", "hermes", {"target": "hermes", "search_query": "xraysight", "search_top_k": 5}) in calls


def test_honcho_snapshot_and_status_include_provider_without_secrets(monkeypatch, tmp_path):
    (tmp_path / "config.yaml").write_text("memory:\n  provider: honcho\n", encoding="utf-8")
    (tmp_path / "honcho.json").write_text(json.dumps({"apiKey": "honcho-secret"}), encoding="utf-8")
    calls = []
    install_fake_honcho_client(monkeypatch, tmp_path, calls)

    module = load_plugin_api(monkeypatch, tmp_path)
    import asyncio

    snapshot = asyncio.run(module.snapshot(limit=5))
    status = asyncio.run(module.status())

    assert snapshot["honcho"]["provider_configured"] is True
    assert status["honcho"]["provider_configured"] is True
    assert status["honcho"]["api_key_present"] is True
    assert "honcho-secret" not in json.dumps(snapshot)
    assert "honcho-secret" not in json.dumps(status)


def test_honcho_missing_sdk_returns_error(monkeypatch, tmp_path):
    (tmp_path / "config.yaml").write_text("memory:\n  provider: honcho\n", encoding="utf-8")
    for name in list(sys.modules):
        if name == "plugins" or name.startswith("plugins.memory.honcho"):
            monkeypatch.delitem(sys.modules, name, raising=False)

    module = load_plugin_api(monkeypatch, tmp_path)
    payload = module._honcho_payload(limit=5)

    assert payload["provider_configured"] is True
    assert payload["api_key_present"] is False
    assert payload["error"]
    assert "Honcho" in payload["error"]



def install_fake_hindsight_provider(monkeypatch, calls):
    fake_plugins = types.ModuleType("plugins")
    fake_memory = types.ModuleType("plugins.memory")
    fake_hindsight = types.ModuleType("plugins.memory.hindsight")

    class FakeProvider:
        def initialize(self, **kwargs):
            calls.append(("initialize", kwargs))
            self._bank_id = "test-bank"
            self._budget = "high"
            self._recall_max_tokens = 1234
            self._recall_tags = ["dashboard"]
            self._recall_tags_match = "all"
            self._recall_types = None

        def _run_hindsight_operation(self, fn):
            calls.append(("run",))
            return fn(self)

        def arecall(self, **kwargs):
            calls.append(("arecall", kwargs))
            return types.SimpleNamespace(results=[
                types.SimpleNamespace(id="r1", text="Hindsight memory result", score=0.87, metadata={"source": "test"}),
                types.SimpleNamespace(id="r2", text="Second result", score=0.42, metadata={}),
            ])

        def areflect(self, **kwargs):
            calls.append(("areflect", kwargs))
            return types.SimpleNamespace(text="Hindsight reflection")

    fake_hindsight.HindsightMemoryProvider = FakeProvider
    monkeypatch.setitem(sys.modules, "plugins", fake_plugins)
    monkeypatch.setitem(sys.modules, "plugins.memory", fake_memory)
    monkeypatch.setitem(sys.modules, "plugins.memory.hindsight", fake_hindsight)


def test_hindsight_config_status_hides_keys_and_reads_local_config(monkeypatch, tmp_path):
    (tmp_path / "config.yaml").write_text("memory:\n  provider: hindsight\n", encoding="utf-8")
    cfg_path = tmp_path / "hindsight" / "config.json"
    cfg_path.parent.mkdir()
    cfg_path.write_text(json.dumps({
        "mode": "local_embedded",
        "apiKey": "hindsight-secret",
        "llm_api_key": "llm-secret",
        "llm_provider": "ollama",
        "llm_model": "nemotron-3-super:cloud",
        "bank_id": "dashboard-bank",
        "recall_budget": "high",
        "memory_mode": "hybrid",
        "auto_retain": False,
        "auto_recall": False,
    }), encoding="utf-8")

    module = load_plugin_api(monkeypatch, tmp_path)
    payload = module._hindsight_payload(mode="status")

    assert payload["provider_configured"] is True
    assert payload["config_exists"] is True
    assert payload["mode"] == "local_embedded"
    assert payload["api_url"] == "http://localhost:8888"
    assert payload["api_key_present"] is True
    assert payload["llm_key_present"] is True
    assert payload["bank_id"] == "dashboard-bank"
    assert payload["recall_budget"] == "high"
    assert payload["auto_retain"] is False
    assert payload["auto_recall"] is False
    dumped = json.dumps(payload)
    assert "hindsight-secret" not in dumped
    assert "llm-secret" not in dumped


def test_hindsight_uses_daemon_url_for_split_host_without_managing_local_daemon(monkeypatch, tmp_path):
    (tmp_path / "config.yaml").write_text("memory:\n  provider: hindsight\n", encoding="utf-8")
    cfg_path = tmp_path / "hindsight" / "config.json"
    cfg_path.parent.mkdir()
    cfg_path.write_text(json.dumps({"mode": "local_embedded"}), encoding="utf-8")
    monkeypatch.setenv("HINDSIGHT_DAEMON_URL", "http://192.168.42.20:8888")

    module = load_plugin_api(monkeypatch, tmp_path)
    cfg = module._load_hindsight_config()

    assert cfg["_api_url"] == "http://192.168.42.20:8888"
    assert cfg["api_url"] == "http://192.168.42.20:8888"
    assert module._hindsight_should_manage_local_daemon(cfg) is False
    assert module._ensure_hindsight_local_daemon(cfg) is None


def test_hindsight_endpoint_precedence_prefers_file_then_api_env_then_daemon_env(monkeypatch, tmp_path):
    (tmp_path / "config.yaml").write_text("memory:\n  provider: hindsight\n", encoding="utf-8")
    cfg_path = tmp_path / "hindsight" / "config.json"
    cfg_path.parent.mkdir()
    cfg_path.write_text(json.dumps({"mode": "local_embedded"}), encoding="utf-8")
    monkeypatch.setenv("HINDSIGHT_DAEMON_URL", "http://192.168.42.20:8888")

    module = load_plugin_api(monkeypatch, tmp_path)
    assert module._load_hindsight_config()["_api_url"] == "http://192.168.42.20:8888"

    monkeypatch.setenv("HINDSIGHT_API_URL", "http://192.168.42.30:8888")
    assert module._load_hindsight_config()["_api_url"] == "http://192.168.42.30:8888"

    cfg_path.write_text(json.dumps({"mode": "local_embedded", "api_url": "http://192.168.42.40:8888"}), encoding="utf-8")
    assert module._load_hindsight_config()["_api_url"] == "http://192.168.42.40:8888"


def test_hindsight_local_daemon_uses_resolved_binary_when_path_is_constrained(monkeypatch, tmp_path):
    (tmp_path / "config.yaml").write_text("memory:\n  provider: hindsight\n", encoding="utf-8")
    cfg_path = tmp_path / "hindsight" / "config.json"
    cfg_path.parent.mkdir()
    cfg_path.write_text(json.dumps({"mode": "local_embedded", "profile": "test-profile"}), encoding="utf-8")
    fake_bin = tmp_path / "venv" / "bin"
    fake_bin.mkdir(parents=True)
    fake_executable = fake_bin / "python"
    fake_executable.write_text("", encoding="utf-8")
    fake_hindsight_embed = fake_bin / "hindsight-embed"
    fake_hindsight_embed.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_hindsight_embed.chmod(0o755)
    calls = []

    module = load_plugin_api(monkeypatch, tmp_path)
    monkeypatch.setattr(module.sys, "executable", str(fake_executable))
    monkeypatch.setenv("PATH", "/nonexistent")

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    cfg = module._load_hindsight_config()

    assert module._ensure_hindsight_local_daemon(cfg) is None
    assert calls[0][0] == [str(fake_hindsight_embed), "-p", "test-profile", "daemon", "start"]


def test_hindsight_local_daemon_reports_safe_diagnostics_when_binary_missing(monkeypatch, tmp_path):
    (tmp_path / "config.yaml").write_text("memory:\n  provider: hindsight\n", encoding="utf-8")
    cfg_path = tmp_path / "hindsight" / "config.json"
    cfg_path.parent.mkdir()
    cfg_path.write_text(json.dumps({"mode": "local_embedded"}), encoding="utf-8")

    module = load_plugin_api(monkeypatch, tmp_path)
    monkeypatch.setenv("PATH", "/nonexistent")
    missing_python = tmp_path / "missing" / "python"
    missing_binary = tmp_path / "missing" / "hindsight-embed"
    monkeypatch.setattr(module.sys, "executable", str(missing_python))
    monkeypatch.setattr(module, "_hindsight_embed_candidates", lambda: [missing_binary])
    cfg = module._load_hindsight_config()

    error = module._ensure_hindsight_local_daemon(cfg)

    assert "hindsight-embed command not found" in error
    assert "checked_paths" in error
    assert str(missing_binary) in error
    assert "api_key" not in error.lower()
    assert "secret" not in error.lower()


def test_hindsight_api_url_is_redacted_in_public_payloads(monkeypatch, tmp_path):
    (tmp_path / "config.yaml").write_text("memory:\n  provider: hindsight\n", encoding="utf-8")
    cfg_path = tmp_path / "hindsight" / "config.json"
    cfg_path.parent.mkdir()
    cfg_path.write_text(json.dumps({
        "mode": "cloud",
        "api_url": "https://user:pass@example.test/v1?api_key=url-secret&token=tok-secret&debug=true",
        "apiKey": "hindsight-secret",
        "bank_id": "dashboard-bank",
    }), encoding="utf-8")

    module = load_plugin_api(monkeypatch, tmp_path)
    payload = module._hindsight_payload(mode="status")

    assert payload["api_url"] == "https://[REDACTED]@example.test/v1?api_key=[REDACTED]&token=[REDACTED]&debug=true"
    dumped = json.dumps(payload)
    assert "user:pass" not in dumped
    assert "url-secret" not in dumped
    assert "tok-secret" not in dumped
    assert "hindsight-secret" not in dumped


def test_hindsight_recall_and_reflect_use_provider_without_retain(monkeypatch, tmp_path):
    (tmp_path / "config.yaml").write_text("memory:\n  provider: hindsight\n", encoding="utf-8")
    cfg_path = tmp_path / "hindsight" / "config.json"
    cfg_path.parent.mkdir()
    cfg_path.write_text(json.dumps({"mode": "cloud", "apiKey": "secret", "bank_id": "test-bank", "recall_budget": "high"}), encoding="utf-8")
    calls = []
    install_fake_hindsight_provider(monkeypatch, calls)

    module = load_plugin_api(monkeypatch, tmp_path)
    recall = module._hindsight_payload(query="dashboard", limit=1, mode="recall")
    reflect = module._hindsight_payload(query="dashboard", mode="reflect")

    assert recall["result_count"] == 1
    assert recall["results"][0]["text"] == "Hindsight memory result"
    assert recall["results"][0]["score"] == 0.87
    assert reflect["reflection"] == "Hindsight reflection"
    assert ("arecall", {"bank_id": "test-bank", "query": "dashboard", "budget": "high", "max_tokens": 1234, "tags": ["dashboard"], "tags_match": "all"}) in calls
    assert ("areflect", {"bank_id": "test-bank", "query": "dashboard", "budget": "high"}) in calls
    assert "secret" not in json.dumps(recall)
    assert not any(call and call[0] == "aretain" for call in calls)


def test_hindsight_snapshot_and_status_include_config_without_querying(monkeypatch, tmp_path):
    (tmp_path / "config.yaml").write_text("memory:\n  provider: hindsight\n", encoding="utf-8")
    cfg_path = tmp_path / "hindsight" / "config.json"
    cfg_path.parent.mkdir()
    cfg_path.write_text(json.dumps({"mode": "local_external", "api_key": "secret", "api_url": "http://127.0.0.1:8888", "bank_id": "snap-bank"}), encoding="utf-8")

    module = load_plugin_api(monkeypatch, tmp_path)
    import asyncio

    snapshot = asyncio.run(module.snapshot(limit=5))
    status = asyncio.run(module.status())

    assert snapshot["hindsight"]["provider_configured"] is True
    assert snapshot["hindsight"]["operation"] == "status"
    assert snapshot["hindsight"]["results"] == []
    assert status["hindsight"]["provider_configured"] is True
    assert status["hindsight"]["mode"] == "local_external"
    assert status["hindsight"]["bank_id"] == "snap-bank"
    assert "secret" not in json.dumps(snapshot)
    assert "secret" not in json.dumps(status)



def test_hindsight_contents_lists_client_memories_and_documents(monkeypatch, tmp_path):
    (tmp_path / "config.yaml").write_text("memory:\n  provider: hindsight\n", encoding="utf-8")
    cfg_path = tmp_path / "hindsight" / "config.json"
    cfg_path.parent.mkdir()
    cfg_path.write_text(json.dumps({"mode": "local_external", "api_url": "http://127.0.0.1:8888", "bank_id": "demo-bank"}), encoding="utf-8")
    calls = []

    class FakeApi:
        def __init__(self, name):
            self.name = name

        async def get_agent_stats(self, **kwargs):
            calls.append(("stats", kwargs))
            return types.SimpleNamespace(total_nodes=1, total_documents=1)

        async def list_memories(self, **kwargs):
            calls.append(("list_memories", kwargs))
            return types.SimpleNamespace(items=[types.SimpleNamespace(id="m1", text="Hindsight dashboard memory", type="world")], total=1)

        async def list_documents(self, **kwargs):
            calls.append(("list_documents", kwargs))
            return types.SimpleNamespace(items=[types.SimpleNamespace(id="d1", text_length=32, memory_unit_count=0)], total=1)

        async def get_document(self, **kwargs):
            calls.append(("get_document", kwargs))
            return types.SimpleNamespace(id="d1", original_text="Dashboard source document", memory_unit_count=0, tags=["demo"])

    class FakeHindsight:
        def __init__(self, base_url, api_key=None, timeout=300.0, user_agent=None):
            calls.append(("init", base_url, api_key, timeout, user_agent))
            self.banks = FakeApi("banks")
            self.memory = FakeApi("memory")
            self.documents = FakeApi("documents")

        async def aclose(self):
            calls.append(("close",))

    fake_client = types.ModuleType("hindsight_client")
    fake_client.Hindsight = FakeHindsight
    monkeypatch.setitem(sys.modules, "hindsight_client", fake_client)
    module = load_plugin_api(monkeypatch, tmp_path)

    payload = module._hindsight_contents_payload(limit=10, search="dashboard")

    assert payload["memory_count"] == 1
    assert payload["document_count"] == 1
    assert payload["memories"][0]["text"] == "Hindsight dashboard memory"
    assert payload["documents"][0]["text"] == "Dashboard source document"
    assert any(call[0] == "list_memories" for call in calls)
    assert any(call[0] == "list_documents" for call in calls)
    assert not any("/v1/default" in str(call) for call in calls)


def test_hindsight_recall_does_not_fall_back_to_documents(monkeypatch, tmp_path):
    (tmp_path / "config.yaml").write_text("memory:\n  provider: hindsight\n", encoding="utf-8")
    cfg_path = tmp_path / "hindsight" / "config.json"
    cfg_path.parent.mkdir()
    cfg_path.write_text(json.dumps({"mode": "cloud", "apiKey": "secret", "bank_id": "test-bank", "recall_budget": "high"}), encoding="utf-8")
    install_fake_hindsight_provider(monkeypatch, [])
    module = load_plugin_api(monkeypatch, tmp_path)

    class EmptyRecallProvider:
        _bank_id = "test-bank"
        _budget = "high"
        _recall_max_tokens = 1234
        _recall_tags = None
        _recall_tags_match = "any"
        _recall_types = None

        def _run_hindsight_operation(self, fn):
            return fn(self)

        def arecall(self, **kwargs):
            return types.SimpleNamespace(results=[])

    monkeypatch.setattr(module, "_make_hindsight_provider", lambda: EmptyRecallProvider())

    def fake_contents(*_args, **_kwargs):
        raise AssertionError("recall should not query source documents as fallback")

    monkeypatch.setattr(module, "_hindsight_contents_payload", fake_contents)
    payload = module._hindsight_payload(query="dashboard", limit=5, mode="recall")

    assert payload["result_source"] == "hindsight_recall"
    assert payload["result_count"] == 0
    assert payload["results"] == []
    assert "secret" not in json.dumps(payload)

def create_mnemosyne_db(tmp_path):
    db_dir = tmp_path / "mnemosyne" / "data"
    db_dir.mkdir(parents=True)
    db_path = db_dir / "mnemosyne.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE episodic_memory (
            rowid INTEGER,
            id TEXT,
            content TEXT,
            source TEXT,
            timestamp TEXT,
            session_id TEXT,
            importance REAL,
            metadata_json TEXT,
            created_at TEXT,
            tier INTEGER,
            memory_type TEXT,
            recall_count INTEGER,
            trust_tier TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO episodic_memory
        VALUES (1, 'm1', 'Mnemosyne dashboard memory about recall quality', 'test', '2026-05-20T10:00:00Z',
                's1', 0.9, '{"topic":"dashboard"}', '2026-05-20T10:00:00Z', 1, 'experience', 2, 'STATED')
        """
    )
    conn.execute(
        """
        CREATE TABLE memoria_facts (
            id INTEGER,
            session_id TEXT,
            fact_type TEXT,
            key TEXT,
            value TEXT,
            context_snippet TEXT,
            importance REAL,
            timestamp TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO memoria_facts
        VALUES (1, 's1', 'preference', 'memory_provider', 'mnemosyne',
                'dashboard should show Mnemosyne facts', 0.8, '2026-05-20T10:00:01Z')
        """
    )
    conn.execute("CREATE TABLE vec_episodes_rowids (rowid INTEGER, id TEXT, chunk_id INTEGER, chunk_offset INTEGER)")
    conn.execute("INSERT INTO vec_episodes_rowids VALUES (1, 'm1', 1, 0)")
    conn.commit()
    conn.close()
    return db_path


def install_fake_mnemosyne_provider(monkeypatch, calls):
    fake_plugins = types.ModuleType("plugins")
    fake_memory = types.ModuleType("plugins.memory")
    fake_mnemosyne = types.ModuleType("plugins.memory.mnemosyne")

    class FakeProvider:
        def initialize(self, session_id, **kwargs):
            calls.append(("initialize", session_id, kwargs))

        def handle_tool_call(self, tool_name, args, **kwargs):
            calls.append(("handle_tool_call", tool_name, args, kwargs))
            return json.dumps({
                "query": args["query"],
                "count": 1,
                "results": [{
                    "id": "r1",
                    "content": "Mnemosyne recall result",
                    "score": 0.93,
                    "source": "episodic_memory",
                    "metadata": {"scope": "dashboard"},
                }],
            })

        def prefetch(self, query, session_id=""):
            calls.append(("prefetch", query, session_id))
            return "Injected Mnemosyne context for " + query

        def shutdown(self):
            calls.append(("shutdown",))

    fake_mnemosyne.MnemosyneMemoryProvider = FakeProvider
    monkeypatch.setitem(sys.modules, "plugins", fake_plugins)
    monkeypatch.setitem(sys.modules, "plugins.memory", fake_memory)
    monkeypatch.setitem(sys.modules, "plugins.memory.mnemosyne", fake_mnemosyne)


def test_mnemosyne_contents_reads_local_db_without_writes(monkeypatch, tmp_path):
    (tmp_path / "config.yaml").write_text("memory:\n  provider: mnemosyne\n", encoding="utf-8")
    db_path = create_mnemosyne_db(tmp_path)

    module = load_plugin_api(monkeypatch, tmp_path)
    payload = module._mnemosyne_contents_payload(limit=5, search="dashboard")

    assert payload["provider_configured"] is True
    assert payload["db_path"] == str(db_path)
    assert payload["db_exists"] is True
    assert payload["table_counts"]["episodic_memory"] == 1
    assert payload["total_memories"] == 1
    assert payload["vector_rows"] == 1
    assert payload["memory_count"] == 1
    assert payload["memories"][0]["text"] == "Mnemosyne dashboard memory about recall quality"
    assert payload["fact_count"] == 1
    assert payload["facts"][0]["type"] == "memoria_facts"
    assert payload["facts"][0]["text"] == "memory_provider: mnemosyne"


def test_mnemosyne_recall_and_prefetch_use_provider_without_remember(monkeypatch, tmp_path):
    (tmp_path / "config.yaml").write_text("memory:\n  provider: mnemosyne\n", encoding="utf-8")
    calls = []
    install_fake_mnemosyne_provider(monkeypatch, calls)

    module = load_plugin_api(monkeypatch, tmp_path)
    recall = module._mnemosyne_payload(query="dashboard", limit=2, temporal_weight=0.5, mode="recall")
    prefetch = module._mnemosyne_payload(query="dashboard", mode="prefetch")

    assert recall["result_source"] == "mnemosyne_recall"
    assert recall["result_count"] == 1
    assert recall["results"][0]["text"] == "Mnemosyne recall result"
    assert recall["results"][0]["score"] == 0.93
    assert prefetch["result_source"] == "mnemosyne_prefetch"
    assert prefetch["context"] == "Injected Mnemosyne context for dashboard"
    assert ("handle_tool_call", "mnemosyne_recall", {"query": "dashboard", "limit": 2, "temporal_weight": 0.5}, {}) in calls
    assert ("prefetch", "dashboard", "dashboard") in calls
    assert not any(call and call[0] == "mnemosyne_remember" for call in calls)


def test_mnemosyne_snapshot_and_status_include_provider(monkeypatch, tmp_path):
    (tmp_path / "config.yaml").write_text("memory:\n  provider: mnemosyne\n", encoding="utf-8")
    create_mnemosyne_db(tmp_path)

    module = load_plugin_api(monkeypatch, tmp_path)
    import asyncio

    snapshot = asyncio.run(module.snapshot(limit=5))
    status = asyncio.run(module.status())

    assert snapshot["mnemosyne"]["provider_configured"] is True
    assert snapshot["mnemosyne"]["memory_count"] == 1
    assert status["mnemosyne"]["provider_configured"] is True
    assert status["mnemosyne"]["db_exists"] is True

def write_fake_brv(tmp_path):
    script = tmp_path / "fake-brv"
    log_path = tmp_path / "brv-calls.jsonl"
    script.write_text(
        """#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
log = Path(os.environ.get('FAKE_BRV_LOG', ''))
if log:
    with log.open('a', encoding='utf-8') as fh:
        fh.write(json.dumps({'argv': sys.argv[1:], 'cwd': os.getcwd()}) + '\\n')
cmd = sys.argv[1] if len(sys.argv) > 1 else ''
if cmd == 'locations':
    print(json.dumps({'success': True, 'command': 'locations', 'data': {'locations': [{'projectPath': '/workspace/demo', 'contextTreePath': '/workspace/demo/.brv/context-tree', 'isInitialized': True}]}}))
elif cmd == 'status':
    project = ''
    if '--project-root' in sys.argv:
        project = sys.argv[sys.argv.index('--project-root') + 1]
    print(json.dumps({'success': True, 'command': 'status', 'data': {'projectPath': project or os.getcwd(), 'isInitialized': True, 'contextTreePath': (project or os.getcwd()) + '/.brv/context-tree'}}))
elif cmd == 'search':
    query = sys.argv[2]
    print(json.dumps({'success': True, 'command': 'search', 'data': {'status': 'completed', 'totalFound': 1, 'results': [{'path': 'docs/memory.md', 'score': 0.91, 'excerpt': 'Hermes Memory UI supports ByteRover search for ' + query}]}}))
elif cmd == 'query':
    query = sys.argv[2]
    print(json.dumps({'success': True, 'command': 'query', 'data': {'status': 'completed', 'result': 'Answer about ' + query, 'matchedDocs': [{'path': 'docs/memory.md'}], 'taskId': 'task-1', 'topScore': 0.88}}))
else:
    print(json.dumps({'success': False, 'data': {'error': 'unknown command ' + cmd}}))
    sys.exit(1)
""",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script, log_path


def test_byterover_payload_uses_brv_status_locations_and_search(monkeypatch, tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    brv, log_path = write_fake_brv(tmp_path)
    monkeypatch.setenv("FAKE_BRV_LOG", str(log_path))
    (tmp_path / "config.yaml").write_text("memory:\n  provider: byterover\n", encoding="utf-8")
    (tmp_path / "byterover.json").write_text(json.dumps({"brv_path": str(brv), "project_root": str(project), "search_scope": "docs/"}), encoding="utf-8")

    module = load_plugin_api(monkeypatch, tmp_path)
    payload = module._byterover_payload(limit=3, search="dashboard")

    assert payload["provider_configured"] is True
    assert payload["brv_available"] is True
    assert payload["project_root"] == str(project)
    assert payload["location_count"] == 1
    assert payload["status"]["projectPath"] == str(project)
    assert payload["result_count"] == 1
    assert payload["total_found"] == 1
    assert payload["results"][0]["path"] == "docs/memory.md"
    assert payload["results"][0]["score"] == 0.91
    calls = [json.loads(line)["argv"] for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert ["locations", "--format", "json"] in calls
    assert ["status", "--format", "json"] in calls
    assert not any(call[:1] == ["status"] and "--project-root" in call for call in calls)
    assert ["search", "dashboard", "--format", "json", "--limit", "3", "--scope", "docs/"] in calls


def test_byterover_query_is_explicit_and_status_includes_provider(monkeypatch, tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    brv, log_path = write_fake_brv(tmp_path)
    monkeypatch.setenv("FAKE_BRV_LOG", str(log_path))
    (tmp_path / "config.yaml").write_text("memory:\n  provider: byterover\n", encoding="utf-8")
    (tmp_path / "byterover.json").write_text(json.dumps({"brv_path": str(brv), "project_root": str(project)}), encoding="utf-8")

    module = load_plugin_api(monkeypatch, tmp_path)
    import asyncio

    snapshot = asyncio.run(module.snapshot(limit=5))
    status = asyncio.run(module.status())
    query = module._byterover_query_payload("What is memory UI?")

    assert snapshot["byterover"]["provider_configured"] is True
    assert snapshot["byterover"]["results"] == []
    assert status["byterover"]["provider_configured"] is True
    assert status["byterover"]["brv_available"] is True
    assert query["answer"] == "Answer about What is memory UI?"
    assert query["matched_docs"] == [{"path": "docs/memory.md"}]
    calls = [json.loads(line)["argv"] for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert ["query", "What is memory UI?", "--format", "json"] in calls



def test_byterover_query_parses_json_lines_completed_event(monkeypatch, tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    script = tmp_path / "fake-brv-jsonl"
    log_path = tmp_path / "brv-jsonl-calls.jsonl"
    script.write_text(
        """#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
log = Path(os.environ.get('FAKE_BRV_LOG', ''))
if log:
    with log.open('a', encoding='utf-8') as fh:
        fh.write(json.dumps({'argv': sys.argv[1:], 'cwd': os.getcwd()}) + '\\n')
cmd = sys.argv[1] if len(sys.argv) > 1 else ''
if cmd == 'locations':
    print(json.dumps({'success': True, 'command': 'locations', 'data': {'locations': []}}))
elif cmd == 'status':
    print(json.dumps({'success': True, 'command': 'status', 'data': {'projectPath': os.getcwd(), 'isInitialized': True}}))
elif cmd == 'query':
    query = sys.argv[2]
    print(json.dumps({'event': 'thinking', 'message': 'working'}))
    print(json.dumps({'event': 'response', 'delta': 'partial'}))
    print(json.dumps({'event': 'completed', 'result': 'JSONL answer about ' + query, 'matchedDocs': [{'path': 'docs/jsonl.md'}], 'taskId': 'jsonl-task', 'topScore': 0.77}))
else:
    print(json.dumps({'success': True, 'data': {}}))
""",
        encoding="utf-8",
    )
    script.chmod(0o755)
    monkeypatch.setenv("FAKE_BRV_LOG", str(log_path))
    (tmp_path / "config.yaml").write_text("memory:\n  provider: byterover\n", encoding="utf-8")
    (tmp_path / "byterover.json").write_text(json.dumps({"brv_path": str(script), "project_root": str(project)}), encoding="utf-8")

    module = load_plugin_api(monkeypatch, tmp_path)
    payload = module._byterover_query_payload("How does JSONL work?")

    assert payload["error"] is None
    assert payload["answer"] == "JSONL answer about How does JSONL work?"
    assert payload["answer_summary"] == "JSONL answer about How does JSONL work?"
    assert payload["matched_docs"] == [{"path": "docs/jsonl.md"}]
    assert payload["task_id"] == "jsonl-task"
    assert payload["top_score"] == 0.77


def test_byterover_context_tree_excerpt_rejects_sibling_prefix_paths(monkeypatch, tmp_path):
    project = tmp_path / "project"
    context_root = project / ".brv" / "context-tree"
    sibling_root = project / ".brv" / "context-tree2"
    context_root.mkdir(parents=True)
    sibling_root.mkdir(parents=True)
    secret_file = sibling_root / "secret.md"
    secret_file.write_text("SECRET outside context tree", encoding="utf-8")

    module = load_plugin_api(monkeypatch, tmp_path)
    result = module._normalize_byterover_result(
        {"path": "../context-tree2/secret.md", "excerpt": "safe fallback excerpt"},
        0,
        "secret",
        str(project),
    )

    dumped = json.dumps(result)
    assert "SECRET outside context tree" not in dumped
    assert result["excerpt"] == "safe fallback excerpt"


def test_byterover_search_requires_project_root_to_avoid_creating_context(monkeypatch, tmp_path):
    brv, log_path = write_fake_brv(tmp_path)
    monkeypatch.setenv("FAKE_BRV_LOG", str(log_path))
    (tmp_path / "config.yaml").write_text("memory:\n  provider: byterover\n", encoding="utf-8")
    (tmp_path / "byterover.json").write_text(json.dumps({"brv_path": str(brv)}), encoding="utf-8")

    module = load_plugin_api(monkeypatch, tmp_path)
    payload = module._byterover_payload(limit=3, search="dashboard")
    query = module._byterover_query_payload("What is memory UI?")

    assert payload["provider_configured"] is True
    assert payload["locations"]
    assert payload["results"] == []
    assert "project_root is not configured" in payload["error"]
    assert "project_root is not configured" in query["error"]
    calls = [json.loads(line)["argv"] for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert ["locations", "--format", "json"] in calls
    assert not any(call and call[0] in {"search", "query", "status"} for call in calls)
