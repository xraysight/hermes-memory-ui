import asyncio
import contextlib
import contextvars
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_API = ROOT / "dashboard" / "plugin_api.py"


def load_plugin_api(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    fake_constants = types.ModuleType("hermes_constants")
    fake_constants.get_hermes_home = lambda: str(tmp_path)
    monkeypatch.setitem(sys.modules, "hermes_constants", fake_constants)
    module_name = f"profile_scope_plugin_api_{id(tmp_path)}"
    spec = importlib.util.spec_from_file_location(module_name, PLUGIN_API)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def install_module(monkeypatch, name, module):
    parent_name, _, child_name = name.rpartition(".")
    if parent_name:
        parent = sys.modules.get(parent_name)
        if parent is None:
            parent = types.ModuleType(parent_name)
            parent.__path__ = []
            install_module(monkeypatch, parent_name, parent)
        setattr(parent, child_name, module)
    monkeypatch.setitem(sys.modules, name, module)


async def enter_and_close(scope):
    await scope.__anext__()
    await scope.aclose()


@pytest.mark.parametrize("profile", [None, "", "current", " CURRENT "])
def test_old_host_keeps_current_profile_compatible(monkeypatch, tmp_path, profile):
    module = load_plugin_api(monkeypatch, tmp_path)
    unavailable = types.ModuleType("hermes_cli.web_server_profiles")
    install_module(monkeypatch, "hermes_cli.web_server_profiles", unavailable)

    asyncio.run(enter_and_close(module._profile_request_scope(profile)))


@pytest.mark.parametrize("profile", ["default", "other"])
def test_old_host_rejects_explicit_profile_fail_closed(monkeypatch, tmp_path, profile):
    module = load_plugin_api(monkeypatch, tmp_path)
    unavailable = types.ModuleType("hermes_cli.web_server_profiles")
    install_module(monkeypatch, "hermes_cli.web_server_profiles", unavailable)

    async def enter():
        scope = module._profile_request_scope(profile)
        try:
            await scope.__anext__()
        finally:
            await scope.aclose()

    with pytest.raises(module.HTTPException) as caught:
        asyncio.run(enter())
    assert caught.value.status_code == 501
    assert "cannot safely scope" in caught.value.detail


def test_profile_dependency_unwinds_context_on_cancellation(monkeypatch, tmp_path):
    module = load_plugin_api(monkeypatch, tmp_path)
    active_profile = contextvars.ContextVar("active_profile", default=None)
    events = []

    @contextlib.contextmanager
    def profile_scope(profile):
        token = active_profile.set(profile)
        events.append(("enter", profile))
        try:
            yield
        finally:
            events.append(("exit", active_profile.get()))
            active_profile.reset(token)

    host_profiles = types.ModuleType("hermes_cli.web_server_profiles")
    host_profiles._config_profile_scope = profile_scope
    install_module(monkeypatch, "hermes_cli.web_server_profiles", host_profiles)

    async def cancel_inside_scope():
        scope = module._profile_request_scope("other")
        await scope.__anext__()
        assert active_profile.get() == "other"
        with pytest.raises(asyncio.CancelledError):
            await scope.athrow(asyncio.CancelledError())

    asyncio.run(cancel_inside_scope())
    assert active_profile.get() is None
    assert events == [("enter", "other"), ("exit", "other")]


def test_secret_resolution_is_scoped_and_fails_closed(monkeypatch, tmp_path):
    module = load_plugin_api(monkeypatch, tmp_path)
    monkeypatch.setenv("MEM0_API_KEY", "launch-key")
    calls = []
    secret_scope = types.ModuleType("agent.secret_scope")

    def get_secret(name, default=None):
        calls.append((name, default))
        return "scoped-key"

    secret_scope.get_secret = get_secret
    install_module(monkeypatch, "agent.secret_scope", secret_scope)
    assert module._env_value("MEM0_API_KEY") == "scoped-key"
    assert calls == [("MEM0_API_KEY", None)]

    def unavailable_secret(_name, _default=None):
        raise RuntimeError("scope is missing")

    secret_scope.get_secret = unavailable_secret
    with pytest.raises(RuntimeError, match="scope is missing"):
        module._env_value("MEM0_API_KEY")


def test_old_host_env_fallback_preserves_single_profile_precedence(monkeypatch, tmp_path):
    module = load_plugin_api(monkeypatch, tmp_path)
    (tmp_path / ".env").write_text("MEM0_API_KEY=file-key\n", encoding="utf-8")
    monkeypatch.setenv("MEM0_API_KEY", "launch-key")
    unavailable = types.ModuleType("agent.secret_scope")
    install_module(monkeypatch, "agent.secret_scope", unavailable)

    assert module._env_value("MEM0_API_KEY") == "launch-key"


def test_profile_child_env_delegates_to_host_boundary(monkeypatch, tmp_path):
    module = load_plugin_api(monkeypatch, tmp_path)
    calls = []
    local_env = types.ModuleType("tools.environments.local")

    def served_profile_child_env(**kwargs):
        calls.append(kwargs)
        return {"HERMES_HOME": str(kwargs["target_home"]), "ONLY": "scoped"}

    local_env.served_profile_child_env = served_profile_child_env
    install_module(monkeypatch, "tools.environments.local", local_env)

    assert module._profile_child_env() == {"HERMES_HOME": str(tmp_path), "ONLY": "scoped"}
    assert calls == [{"target_home": tmp_path, "inherit_credentials": True}]


def test_worker_thread_copies_request_context(monkeypatch, tmp_path):
    module = load_plugin_api(monkeypatch, tmp_path)
    marker = contextvars.ContextVar("profile_marker", default="missing")

    async def exercise():
        token = marker.set("selected-profile")
        try:
            async def read_marker():
                await asyncio.sleep(0)
                return marker.get()

            return module._run_coro_blocking(read_marker())
        finally:
            marker.reset(token)

    assert asyncio.run(exercise()) == "selected-profile"


def discover_host_runtime():
    configured_python = os.environ.get("HERMES_HOST_PYTHON", "").strip()
    configured_source = os.environ.get("HERMES_AGENT_SOURCE", "").strip()
    home = Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser()
    python_candidates = [
        Path(configured_python).expanduser() if configured_python else None,
        Path(configured_source).expanduser() / "venv" / "bin" / "python" if configured_source else None,
        home / "hermes-agent" / "venv" / "bin" / "python",
        Path.home() / ".hermes" / "hermes-agent" / "venv" / "bin" / "python",
    ]
    reasons = []
    for python in python_candidates:
        if python is None or not python.is_file():
            if python is not None:
                reasons.append(f"missing {python}")
            continue
        source_candidates = [
            Path(configured_source).expanduser() if configured_source else None,
            python.absolute().parents[2],
            python.resolve().parents[2],
        ]
        source = next(
            (path for path in source_candidates
             if path and (path / "hermes_cli" / "web_server_profiles.py").is_file()),
            None,
        )
        if source is None:
            reasons.append(f"Hermes source not found beside {python}")
            continue
        probe = subprocess.run(
            [str(python), "-c", "import fastapi, httpx"],
            capture_output=True,
            text=True,
            check=False,
        )
        if probe.returncode != 0:
            reasons.append(f"FastAPI/HTTPX unavailable in {python}: {probe.stderr.strip()}")
            continue
        # Keep the venv launcher path: resolving its symlink can bypass the
        # venv and lose host-only packages such as FastAPI and HTTPX.
        return python.absolute(), source.resolve(), reasons
    return None, None, reasons


def test_real_fastapi_profile_scope_regression():
    host_python, agent_source, reasons = discover_host_runtime()
    if host_python is None or agent_source is None:
        pytest.skip(
            "Hermes host integration prerequisites unavailable; set HERMES_HOST_PYTHON and "
            f"HERMES_AGENT_SOURCE ({'; '.join(reasons) or 'no candidates'})"
        )
    env = os.environ.copy()
    env["HERMES_AGENT_SOURCE"] = str(agent_source)
    result = subprocess.run(
        [str(host_python), str(ROOT / "tests" / "profile_scope_http_regression.py")],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "profile-scope HTTP regression: ok" in result.stdout


def test_dashboard_forwards_profile_and_suppresses_stale_responses():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the Dashboard profile-scope smoke test")
    result = subprocess.run(
        [
            node,
            str(ROOT / "tests" / "dashboard_profile_scope_smoke.mjs"),
            str(ROOT / "dashboard" / "dist" / "index.js"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload == {
        "exercisedRequestPaths": [
            "/api/plugins/hermes-memory-ui/byterover/query",
            "/api/plugins/hermes-memory-ui/hindsight/contents",
            "/api/plugins/hermes-memory-ui/hindsight/recall",
            "/api/plugins/hermes-memory-ui/hindsight/reflect",
            "/api/plugins/hermes-memory-ui/mnemosyne/contents",
            "/api/plugins/hermes-memory-ui/mnemosyne/prefetch",
            "/api/plugins/hermes-memory-ui/mnemosyne/recall",
            "/api/plugins/hermes-memory-ui/session-search",
            "/api/plugins/hermes-memory-ui/snapshot",
        ],
        "firstEntryProfile": "beta",
        "legacyProfileOmitted": True,
        "reentryProfile": "beta",
        "staleResponseSuppressed": True,
    }
