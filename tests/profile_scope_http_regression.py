#!/usr/bin/env python3
"""Executable HTTP regression for Dashboard plugin profile scoping.

Run with a Hermes interpreter so the test exercises installed FastAPI plus the
real profile resolver, secret scope, and child-environment helpers. All profile
data and provider boundaries are synthetic, temporary, and offline.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import types
from pathlib import Path

import httpx
from fastapi import FastAPI


ROOT = Path(__file__).resolve().parents[1]


def _hermes_agent_source() -> Path:
    configured = os.environ.get("HERMES_AGENT_SOURCE", "").strip()
    candidates = [
        Path(configured).expanduser() if configured else None,
        Path(sys.executable).absolute().parents[2],
        Path(sys.executable).resolve().parents[2],
        Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser() / "hermes-agent",
        Path.home() / ".hermes" / "hermes-agent",
    ]
    for candidate in candidates:
        if candidate and (candidate / "hermes_cli" / "web_server_profiles.py").is_file():
            return candidate.resolve()
    checked = ", ".join(str(path) for path in candidates if path)
    raise RuntimeError(
        "Hermes Agent source was not found; set HERMES_AGENT_SOURCE to its checkout "
        f"(checked: {checked})"
    )


def _write_profile(home: Path, marker: str) -> None:
    (home / "memories").mkdir(parents=True)
    (home / "config.yaml").write_text("memory:\n  provider: mem0\n", encoding="utf-8")
    (home / "memories" / "MEMORY.md").write_text(marker, encoding="utf-8")
    (home / "memories" / "USER.md").write_text(f"user-{marker}", encoding="utf-8")
    (home / ".env").write_text(
        f"MEM0_API_KEY={marker}-key\nCHILD_ONLY_SECRET={marker}-child\n",
        encoding="utf-8",
    )


def _load_plugin_api():
    module_name = "profile_scope_http_plugin_api"
    spec = importlib.util.spec_from_file_location(module_name, ROOT / "dashboard" / "plugin_api.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


async def _main() -> None:
    agent_source = _hermes_agent_source()
    with tempfile.TemporaryDirectory(prefix="memory-ui-profile-scope-") as raw_root:
        # TMPDIR can live inside a real Hermes profile. Isolate the native
        # home as well, so the host resolver cannot select the real root.
        os.environ["HOME"] = raw_root
        os.environ["USERPROFILE"] = raw_root
        default_home = Path(raw_root) / ".hermes"
        other_home = default_home / "profiles" / "other"
        _write_profile(default_home, "profile-A")
        _write_profile(other_home, "profile-B")

        # This is the synthetic dashboard process home, never a real profile.
        os.environ["HERMES_HOME"] = str(default_home)
        os.environ["MEM0_API_KEY"] = "launch-environment-key"
        os.environ["CHILD_ONLY_SECRET"] = "launch-environment-child"
        sys.path.insert(0, str(agent_source))

        plugin_api = _load_plugin_api()
        cancel_entered = asyncio.Event()
        cancel_finished = asyncio.Event()

        @plugin_api.router.get("/cancel-probe")
        async def cancel_probe():
            from agent.secret_scope import get_secret
            from hermes_constants import get_hermes_home

            assert Path(get_hermes_home()) == other_home
            assert get_secret("MEM0_API_KEY") == "profile-B-key"
            cancel_entered.set()
            try:
                await asyncio.sleep(60)
            finally:
                cancel_finished.set()

        app = FastAPI()
        app.include_router(plugin_api.router, prefix="/api/plugins/hermes-memory-ui")

        async def get(path: str) -> httpx.Response:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                return await client.get(path)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            observed = []
            for query in ("", "?profile=other", "?profile=default", "?profile=current", "?profile="):
                response = await client.get(f"/api/plugins/hermes-memory-ui/builtin{query}")
                response.raise_for_status()
                observed.append(response.json()["stores"][0]["entries"])

            assert (await client.get(
                "/api/plugins/hermes-memory-ui/builtin?profile=missing"
            )).status_code == 404
            assert (await client.get(
                "/api/plugins/hermes-memory-ui/builtin?profile=..%2Fescape"
            )).status_code == 400

        assert observed == [
            ["profile-A"],
            ["profile-B"],
            ["profile-A"],
            ["profile-A"],
            ["profile-A"],
        ], observed

        # Cancellation must unwind both ContextVars before this task continues.
        cancelled = asyncio.create_task(get(
            "/api/plugins/hermes-memory-ui/cancel-probe?profile=other"
        ))
        await asyncio.wait_for(cancel_entered.wait(), timeout=5)
        cancelled.cancel()
        try:
            await cancelled
        except asyncio.CancelledError:
            pass
        else:  # pragma: no cover - a cancellation-resistant ASGI stack is a regression
            raise AssertionError("cancelled profile request unexpectedly completed")
        await asyncio.wait_for(cancel_finished.wait(), timeout=5)
        from agent.secret_scope import current_secret_scope
        from hermes_constants import get_hermes_home

        assert Path(get_hermes_home()) == default_home
        assert current_secret_scope() is None

        # No provider network calls: this fake reports which constructor key
        # the real request-scoped config path supplied.
        mem0_barrier: threading.Barrier | None = threading.Barrier(2)

        class FakeMemoryClient:
            def __init__(self, api_key: str):
                self.api_key = api_key

            def get_all(self, filters):
                nonlocal mem0_barrier
                if mem0_barrier is not None:
                    mem0_barrier.wait(timeout=5)
                return {"results": [{"id": self.api_key, "memory": self.api_key}]}

        fake_mem0 = types.ModuleType("mem0")
        fake_mem0.MemoryClient = FakeMemoryClient
        sys.modules["mem0"] = fake_mem0

        def threaded_mem0(profile: str) -> str:
            response = asyncio.run(get(f"/api/plugins/hermes-memory-ui/mem0?profile={profile}"))
            response.raise_for_status()
            return response.json()["memories"][0]["memory"]

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            future_a = pool.submit(threaded_mem0, "default")
            future_b = pool.submit(threaded_mem0, "other")
            concurrent_keys = {future_a.result(timeout=10), future_b.result(timeout=10)}
        assert concurrent_keys == {"profile-A-key", "profile-B-key"}, concurrent_keys

        mem0_barrier = None
        sequential_keys = []
        for profile in ("default", "other", "default"):
            response = await get(f"/api/plugins/hermes-memory-ui/mem0?profile={profile}")
            response.raise_for_status()
            sequential_keys.append(response.json()["memories"][0]["memory"])
        assert sequential_keys == ["profile-A-key", "profile-B-key", "profile-A-key"]
        assert "launch-environment-key" not in sequential_keys

        # _run_coro_blocking creates a worker thread. Replace only the provider
        # operation, then verify the real route carries both ContextVars into it.
        def thread_probe(*_args, **_kwargs):
            async def inspect_scope():
                from agent.secret_scope import get_secret
                from hermes_constants import get_hermes_home

                await asyncio.sleep(0)
                return {
                    "home": str(get_hermes_home()),
                    "key": get_secret("MEM0_API_KEY"),
                }

            return plugin_api._run_coro_blocking(inspect_scope())

        plugin_api._hindsight_payload = thread_probe
        thread_values = []
        for profile in ("default", "other", "default"):
            response = await get(f"/api/plugins/hermes-memory-ui/hindsight?profile={profile}")
            response.raise_for_status()
            thread_values.append(response.json())
        assert [item["key"] for item in thread_values] == [
            "profile-A-key", "profile-B-key", "profile-A-key"
        ]
        assert [Path(item["home"]) for item in thread_values] == [
            default_home, other_home, default_home
        ]

        # ByteRover is replaced at the process boundary only: exercise the real
        # config, route, and child-env construction but never launch a command.
        fake_brv = Path(raw_root) / "brv"
        fake_brv.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        fake_brv.chmod(0o755)
        project = Path(raw_root) / "project"
        project.mkdir()
        for home in (default_home, other_home):
            (home / "byterover.json").write_text(
                json.dumps({"brv_path": str(fake_brv), "project_root": str(project)}),
                encoding="utf-8",
            )

        child_envs = []
        real_subprocess_run = plugin_api.subprocess.run

        def fake_subprocess_run(argv, **kwargs):
            child_envs.append(dict(kwargs["env"]))
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=json.dumps({"success": True, "data": {"result": "offline"}}),
                stderr="",
            )

        plugin_api.subprocess.run = fake_subprocess_run
        try:
            for profile in ("default", "other", "default"):
                response = await get(
                    f"/api/plugins/hermes-memory-ui/byterover/query?query=offline&profile={profile}"
                )
                response.raise_for_status()
                assert response.json()["answer"] == "offline"
        finally:
            plugin_api.subprocess.run = real_subprocess_run

        child_keys = [env.get("MEM0_API_KEY") for env in child_envs]
        child_only = [env.get("CHILD_ONLY_SECRET") for env in child_envs]
        assert child_keys == [
            "profile-A-key", "profile-A-key", "profile-A-key",
            "profile-B-key", "profile-B-key", "profile-B-key",
            "profile-A-key", "profile-A-key", "profile-A-key",
        ], child_keys
        assert child_only == [
            "profile-A-child", "profile-A-child", "profile-A-child",
            "profile-B-child", "profile-B-child", "profile-B-child",
            "profile-A-child", "profile-A-child", "profile-A-child",
        ], child_only

        # Request handling never rewrites the launch process environment.
        assert os.environ["HERMES_HOME"] == str(default_home)
        assert os.environ["MEM0_API_KEY"] == "launch-environment-key"
        assert os.environ["CHILD_ONLY_SECRET"] == "launch-environment-child"


if __name__ == "__main__":
    asyncio.run(_main())
    print("profile-scope HTTP regression: ok")
