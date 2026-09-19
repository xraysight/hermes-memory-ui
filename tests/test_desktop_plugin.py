import json
import re
import subprocess
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


ROOT = Path(__file__).resolve().parents[1]
DESKTOP_PLUGIN = ROOT / "desktop" / "plugin.js"
SMOKE_HARNESS = Path(__file__).with_name("desktop_plugin_smoke.mjs")
ALLOWED_DESKTOP_IMPORTS = {
    "@hermes/plugin-sdk",
    "react",
    "react/jsx-runtime",
}


def test_desktop_plugin_source_obeys_disk_plugin_constraints():
    assert DESKTOP_PLUGIN.exists(), "desktop/plugin.js must provide the Hermes Desktop UI"
    source = DESKTOP_PLUGIN.read_text(encoding="utf-8")
    imports = set(re.findall(r"from\s+['\"]([^'\"]+)['\"]", source))

    assert imports
    assert imports <= ALLOWED_DESKTOP_IMPORTS
    assert "@hermes/plugin-sdk" in imports
    assert "react/jsx-runtime" in imports
    assert "window.__HERMES_PLUGIN_SDK__" not in source
    assert "window.__HERMES_PLUGINS__" not in source
    assert "/api/plugins/" not in source
    assert "JSON.stringify" not in source
    assert not re.search(r"jsx\(\s*['\"]pre['\"]", source)
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|\brgba?\s*\(", source)


def test_desktop_plugin_registers_native_surfaces_and_scoped_api_calls():
    completed = subprocess.run(
        [
            "node",
            "--experimental-vm-modules",
            str(SMOKE_HARNESS),
            str(DESKTOP_PLUGIN),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    result = json.loads(completed.stdout)
    assert result["plugin"] == {"id": "hermes-memory-ui", "name": "Hermes Memory UI"}
    assert result["route"] == "/memory"
    assert result["sidebar"] == {"path": "/memory", "label": "Memory"}
    assert result["translatedKeys"] == ["title", "openMemory"]
    assert result["paletteDataId"] == "hermes-memory-ui.open"
    assert result["paletteNavigation"] == "/memory"
    assert result["i18nLocales"] == ["en", "pl"]
    assert result["normalizedFilters"] == {
        "category": "project",
        "limit": 2000,
        "minTrust": 0,
        "search": "hello world",
    }
    assert result["defaultFilters"] == {
        "category": "",
        "limit": 500,
        "minTrust": 0,
        "search": "",
    }
    assert result["queryControlConfig"] == {
        "snapshot": {
            "defaultLimit": 500,
            "limitOptions": [10, 25, 50, 100, 500, 1000, 2000],
        },
        "hindsight": {
            "defaultLimit": 25,
            "limitOptions": [10, 25, 50, 100],
        },
        "mnemosyne": {
            "defaultLimit": 25,
            "defaultTemporalWeight": 0.2,
            "limitOptions": [10, 25, 50, 100],
            "temporalWeightOptions": [0, 0.2, 0.5, 0.8, 1],
        },
        "byterover": {"queryTimeout": 60},
        "session": {
            "defaultLimit": 3,
            "defaultSort": "newest",
            "sortOptions": ["newest", "oldest"],
        },
    }
    assert result["operationOptions"] == {
        "hindsightContents": {"limit": 50, "search": "release plan"},
        "hindsightRecall": {"limit": 50, "query": "release plan"},
        "hindsightReflect": {"query": "release plan"},
        "mnemosyneContents": {"limit": 100, "search": "release plan"},
        "mnemosyneRecall": {
            "limit": 100,
            "query": "release plan",
            "temporalWeight": 0.8,
        },
        "mnemosynePrefetch": {"query": "release plan"},
    }
    assert result["visibleProviders"] == ["holographic", "honcho", "hindsight"]

    paths = result["restPaths"]
    assert len(paths) == 10
    assert all(path.startswith("/") for path in paths)
    assert all(not path.startswith("/api/") for path in paths)
    assert [path.split("?", 1)[0] for path in paths] == [
        "/snapshot",
        "/snapshot",
        "/session-search",
        "/byterover/query",
        "/hindsight/contents",
        "/hindsight/recall",
        "/hindsight/reflect",
        "/mnemosyne/contents",
        "/mnemosyne/recall",
        "/mnemosyne/prefetch",
    ]
    queries = [parse_qs(urlsplit(path).query) for path in paths]
    assert queries[0] == {
        "limit": ["500"],
        "min_trust": ["0"],
    }
    assert queries[1] == {
        "category": ["project"],
        "limit": ["25"],
        "min_trust": ["0.3"],
        "search": ["hello world"],
    }
    assert queries[2] == {
        "limit": ["3"],
        "query": ["memory search"],
        "sort": ["newest"],
        "source": ["telegram"],
    }
    assert queries[3] == {"query": ["what changed?"], "timeout": ["60"]}
    assert queries[4] == {"limit": ["50"], "search": ["dashboard"]}
    assert queries[5] == {"limit": ["50"], "query": ["remember dashboard"]}
    assert queries[6] == {"query": ["summarize dashboard"]}
    assert queries[7] == {"limit": ["100"], "search": ["dashboard"]}
    assert queries[8] == {
        "limit": ["100"],
        "query": ["remember dashboard"],
        "temporal_weight": ["0.8"],
    }
    assert queries[9] == {"query": ["inject dashboard"]}
    assert result["restTimeouts"] == [
        120_000,
        120_000,
        60_000,
        70_000,
        120_000,
        120_000,
        180_000,
        120_000,
        120_000,
        120_000,
    ]


def test_desktop_release_version_and_documentation_are_consistent():
    source = DESKTOP_PLUGIN.read_text(encoding="utf-8")
    plugin_yaml = (ROOT / "plugin.yaml").read_text(encoding="utf-8")
    manifest = json.loads((ROOT / "dashboard" / "manifest.json").read_text(encoding="utf-8"))
    plugin_api = (ROOT / "dashboard" / "plugin_api.py").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert re.search(r"^version:\s*0\.6\.2\s*$", plugin_yaml, re.MULTILINE)
    assert manifest["version"] == "0.6.2"
    assert 'PLUGIN_VERSION = "0.6.2"' in plugin_api
    assert "const VERSION = '0.6.2'" in source
    assert "Hermes Desktop" in readme
    assert "$HERMES_HOME/desktop-plugins/hermes-memory-ui/plugin.js" in readme
    assert "Settings" in readme and "Plugins" in readme
    assert "legacy `~/.hindsight/config.json`" not in readme
