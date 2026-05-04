import importlib.util
import json
import sys
import types
from pathlib import Path


PLUGIN_API = Path(__file__).resolve().parents[1] / "dashboard" / "plugin_api.py"


def load_plugin_api(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    spec = importlib.util.spec_from_file_location("plugin_api_under_test", PLUGIN_API)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


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
