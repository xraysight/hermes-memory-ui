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


def test_mem0_fixture_payload_is_read_only_and_searchable(monkeypatch, tmp_path):
    fixture = tmp_path / "mem0-fixture.json"
    fixture.write_text(
        json.dumps(
            {
                "results": [
                    {"id": "m1", "memory": "User prefers Polish replies", "user_id": "demo-user"},
                    {"id": "m2", "memory": "Project uses FastAPI dashboard plugins", "user_id": "demo-user"},
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "config.yaml").write_text(
        """
memory:
  provider: mem0
plugins:
  hermes-memory-ui:
    mem0_fixture_path: $HERMES_HOME/mem0-fixture.json
""".strip(),
        encoding="utf-8",
    )

    module = load_plugin_api(monkeypatch, tmp_path)
    payload = module._mem0_payload(search="polish", limit=10)

    assert payload["provider_configured"] is True
    assert payload["fixture_mode"] is True
    assert payload["api_key_present"] is False
    assert payload["total_memories"] == 2
    assert payload["memory_count"] == 1
    assert payload["memories"][0]["id"] == "m1"
    assert payload["memories"][0]["memory"] == "User prefers Polish replies"
    assert "_api_key" not in payload


def test_mem0_config_hides_api_key_and_uses_memory_client(monkeypatch, tmp_path):
    (tmp_path / "config.yaml").write_text("memory:\n  provider: mem0\n", encoding="utf-8")
    (tmp_path / "mem0.json").write_text(
        json.dumps({"api_key": "secret-token", "user_id": "piotr-test", "agent_id": "hermes-test"}),
        encoding="utf-8",
    )

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
    assert payload["user_id"] == "piotr-test"
    assert payload["agent_id"] == "hermes-test"
    assert payload["memory_count"] == 1
    assert payload["memories"][0]["memory"] == "Mem0 dashboard integration works"
    assert "secret-token" not in json.dumps(payload)
    assert calls == [("init", "secret-token"), ("get_all", {"user_id": "piotr-test"})]


def test_mem0_search_uses_search_endpoint(monkeypatch, tmp_path):
    (tmp_path / "config.yaml").write_text("memory:\n  provider: mem0\n", encoding="utf-8")
    (tmp_path / "mem0.json").write_text(json.dumps({"api_key": "secret-token", "user_id": "u1"}), encoding="utf-8")

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
