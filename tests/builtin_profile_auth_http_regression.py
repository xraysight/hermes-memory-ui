#!/usr/bin/env python3
"""Exercise built-in profile authorization through Hermes' real HTTP auth layer.

Uses temporary profiles, the native ticket issuer/redemption and request guards,
plus the host's real plugin discovery and consent policy. ASGI supplies a local
socket peer; no gateway process, external providers, or user data are involved.
"""
from __future__ import annotations

import asyncio
import shutil
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import httpx

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
        for target in (home, other, denied, unconsented):
            shutil.copytree(ROOT / "dashboard", target / "plugins" / PLUGIN / "dashboard")
            shutil.copyfile(ROOT / "plugin.yaml", target / "plugins" / PLUGIN / "plugin.yaml")
        sys.path.insert(0, str(source))
        from gateway.runtime_bootstrap import TicketStore
        from gateway.session_authorities import SessionAuthorities
        from hermes_cli import web_server as web
        from hermes_cli.web_server_dashboard import _mount_plugin_api_routes

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
        app = web.app
        app.state.gateway_runner = runner
        _mount_plugin_api_routes()

        def native_headers(path: Path = home) -> dict[str, str]:
            ticket = tickets.mint(profile_id=str(path), subject="uid:fixture", purpose="native-http")
            return {"X-Hermes-Gateway-Ticket": ticket}

        def entries(response):
            assert response.status_code == 200, response.text
            return response.json()["stores"][0]["entries"]

        async def gateway_request(scope, receive, send):
            # The real gateway records the transport peer before HTTP middleware.
            scope["hermes.gateway_socket_peer"] = scope["client"]
            await app(scope, receive, send)

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway_request), base_url="http://localhost") as client:
            assert (await client.get(BASE)).status_code == 401
            assert (await client.get(BASE, headers={"X-Hermes-Gateway-Ticket": "invalid"})).status_code == 401
            one_use = native_headers()
            assert entries(await client.get(BASE, headers=one_use)) == ["A-PRIVATE"]
            assert (await client.get(BASE, headers=one_use)).status_code == 401
            assert entries(await client.get(BASE, headers=native_headers(other))) == ["B-PRIVATE"]

            # The host authenticates and authorizes the named request before routing it.
            response = await client.get(f"{BASE}?profile=other", headers=native_headers())
            assert response.status_code == 403, (response.status_code, response.text)
            owner = {"X-Hermes-Session-Token": web._SESSION_TOKEN}
            assert entries(await client.get(f"{BASE}?profile=other", headers=owner)) == ["B-PRIVATE"]
            for name in ("denied", "unconsented"):
                response = await client.get(f"{BASE}?profile={name}", headers=owner)
                assert response.status_code == 404, (name, response.status_code, response.text)
                assert "PRIVATE" not in response.text
            # Legacy clients must not mistake the launch profile's data for their selection.
            assert (await client.get(f"{BASE}?memory_profile=other", headers=owner)).status_code == 400
            assert entries(await client.get(BASE, headers=owner)) == ["A-PRIVATE"]
        print("builtin-profile auth HTTP regression: ok")


if __name__ == "__main__":
    asyncio.run(_main())
