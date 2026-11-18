#!/usr/bin/env python3
"""Exercise built-in profile authorization through Hermes' real HTTP auth layer.

Uses temporary profiles, the native ticket issuer/redemption and request guards,
plus the host's real plugin discovery and consent policy. ASGI supplies a local
socket peer; no gateway process, external providers, or user data are involved.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from profile_scope_http_regression import _hermes_agent_source


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = "hermes-memory-ui"
BASE = f"/api/plugins/{PLUGIN}/builtin"


def _profile(home: Path, marker: str, consent: str) -> None:
    (home / "memories").mkdir(parents=True)
    (home / "memories" / "MEMORY.md").write_text(marker, encoding="utf-8")
    (home / "memories" / "USER.md").write_text(f"user-{marker}", encoding="utf-8")
    (home / "profile.yaml").write_text(f"bot_title: {marker}\n", encoding="utf-8")
    (home / "config.yaml").write_text(
        f"plugins:\n  {consent}: [{PLUGIN}]\n" if consent else "plugins: {}\n",
        encoding="utf-8",
    )


async def _main() -> None:
    source = _hermes_agent_source()
    with tempfile.TemporaryDirectory(prefix="memory-ui-auth-") as temporary:
        # Set home before importing Hermes so its cached launch home, discovery
        # roots and native authorities all belong to this disposable fixture.
        os.environ["HOME"] = temporary
        os.environ["USERPROFILE"] = temporary
        home = Path(temporary) / ".hermes"
        os.environ["HERMES_HOME"] = str(home)
        os.environ["HERMES_DASHBOARD_SESSION_TOKEN"] = "fixture-dashboard-owner"
        other = home / "profiles" / "other"
        denied = home / "profiles" / "denied"
        unconsented = home / "profiles" / "unconsented"
        _profile(home, "A-PRIVATE", "enabled")
        _profile(other, "B-PRIVATE", "enabled")
        _profile(denied, "DENIED-PRIVATE", "disabled")
        _profile(unconsented, "UNCONSENTED-PRIVATE", "")
        # Real host discovery finds the user plugin under the default root for
        # all four profiles; each target's config decides its consent.
        dashboard = home / "plugins" / PLUGIN / "dashboard"
        dashboard.mkdir(parents=True)
        (dashboard / "manifest.json").write_text(
            json.dumps({"name": PLUGIN, "api": "plugin_api.py", "entry": "index.js"}),
            encoding="utf-8",
        )
        (dashboard / "plugin_api.py").write_text(
            "from fastapi import APIRouter\nrouter = APIRouter()\n", encoding="utf-8"
        )
        sys.path.insert(0, str(source))
        from gateway.runtime_bootstrap import TicketStore
        from gateway.session_authorities import SessionAuthorities
        from hermes_cli import web_server as web
        from hermes_cli.dashboard_auth.native_http import (
            authenticate_native_http,
            native_profile_scope,
        )
        from hermes_cli.plugin_host_http_auth import with_hosted_admission
        from hermes_cli.web_server_dashboard import _plugin_api_request_refused
        from hermes_cli.web_server_profiles import _config_profile_scope

        module_name = "builtin_profile_auth_plugin_api"
        spec = importlib.util.spec_from_file_location(module_name, ROOT / "dashboard" / "plugin_api.py")
        assert spec is not None and spec.loader is not None
        plugin = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = plugin
        spec.loader.exec_module(plugin)
        instance_id = "memory-ui-auth-fixture"
        homes = [home, other, denied, unconsented]
        registry = SessionAuthorities(home, multiplexed=True)
        for path in homes:
            registry.add(path, SimpleNamespace(profile_id=str(path), instance_id=instance_id))
        tickets = TicketStore(instance_id, frozenset(str(path) for path in homes))
        runner = SimpleNamespace(
            session_authorities=registry,
            session_ticket_store=tickets,
            session_runtime_descriptor={
                "state": "ready",
                "instance_id": instance_id,
                "served_profiles": [{"profile_id": str(path), "home": str(path)} for path in homes],
            },
            _draining=False,
        )
        app = FastAPI()
        app.state.gateway_runner = runner

        @app.middleware("http")
        async def host_auth(request: Request, call_next):
            # The native seam checks the original socket peer, not proxy data.
            request.scope["hermes.gateway_socket_peer"] = ("127.0.0.1", 12345)
            rejected = await authenticate_native_http(request)
            if rejected is not None:
                return rejected
            try:
                web._require_token(request)
                with native_profile_scope(request):
                    with _config_profile_scope(request.query_params.get("profile")):
                        if await _plugin_api_request_refused(PLUGIN):
                            return JSONResponse({"detail": "Plugin not found"}, status_code=404)
                        return await call_next(request)
            except HTTPException as exc:
                return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

        app.include_router(plugin.router, prefix=f"/api/plugins/{PLUGIN}")

        def native_headers(path: Path = home) -> dict[str, str]:
            ticket = tickets.mint(profile_id=str(path), subject="uid:fixture", purpose="native-http")
            return {"X-Hermes-Gateway-Ticket": ticket}

        def entries(response):
            assert response.status_code == 200, response.text
            return response.json()["stores"][0]["entries"]

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get(BASE)).status_code == 401
            assert (await client.get(BASE, headers={"X-Hermes-Gateway-Ticket": "invalid"})).status_code == 401
            one_use = native_headers()
            assert entries(await client.get(BASE, headers=one_use)) == ["A-PRIVATE"]
            assert (await client.get(BASE, headers=one_use)).status_code == 401
            assert entries(await client.get(BASE, headers=native_headers(other))) == ["B-PRIVATE"]

            # Both selectors must honor the same principal. Before the fix,
            # memory_profile bypassed the host's check and returned B's bytes.
            for query in (
                "profile=other",
                "profile=default&memory_profile=other",
                "memory_profile=other",
                "profile=current&memory_profile=other",
            ):
                response = await client.get(f"{BASE}?{query}", headers=native_headers())
                assert response.status_code == 403, (query, response.status_code, response.text)
                assert "B-PRIVATE" not in response.text
            response = await client.get(f"{BASE}?memory_profile=default", headers=native_headers(other))
            assert response.status_code == 403, response.text
            response = await client.get(f"{BASE}/profiles", headers=native_headers())
            assert response.status_code == 200, response.text
            choices = response.json()["profiles"]
            assert "other" not in {choice["name"] for choice in choices}, choices
            assert str(other) not in response.text and "B-PRIVATE" not in response.text

            # A verified host-wide dashboard owner may inspect another bot,
            # provided that bot independently consented to the plugin.
            owner = {"X-Hermes-Session-Token": "fixture-dashboard-owner"}
            assert entries(await client.get(f"{BASE}?memory_profile=other", headers=owner)) == ["B-PRIVATE"]
            for name in ("denied", "unconsented"):
                response = await client.get(f"{BASE}?memory_profile={name}", headers=owner)
                assert response.status_code == 404, (name, response.status_code, response.text)
                assert "PRIVATE" not in response.text
            response = await client.get(f"{BASE}/profiles", headers=owner)
            assert response.status_code == 200, response.text
            names = {choice["name"] for choice in response.json()["profiles"]}
            assert "other" in names and not names.intersection({"denied", "unconsented"}), names
            for selection, status in (("missing", 404), ("..%2Fescape", 400)):
                response = await client.get(f"{BASE}?memory_profile={selection}", headers=owner)
                assert response.status_code == status, (selection, response.text)

        # A hosted plugin sees only admitted/not-admitted, without the native
        # grant's profile reach. That boolean must never authorize a sibling.
        hosted = with_hosted_admission(app, True)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=hosted), base_url="http://test") as client:
            assert entries(await client.get(BASE)) == ["A-PRIVATE"]
            response = await client.get(f"{BASE}/profiles")
            assert response.status_code == 200, response.text
            assert response.json()["switching_supported"] is False
            assert [choice["name"] for choice in response.json()["profiles"]] == ["current"]
            response = await client.get(f"{BASE}?memory_profile=other")
            assert response.status_code == 501, response.text
        print("builtin-profile auth HTTP regression: ok")


if __name__ == "__main__":
    asyncio.run(_main())
