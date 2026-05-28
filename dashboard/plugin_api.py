"""Hermes Memory UI dashboard plugin backend.

Mounted by Hermes dashboard at /api/plugins/hermes-memory-ui/.

Read-only inspection covers built-in memory files, holographic memory,
Mem0, Honcho, and Hindsight provider state. No mutation endpoints are exposed
intentionally. Memory writes should go through Hermes' memory/fact_store
tools or provider classes so validation, locking, FTS/HRR maintenance,
and provider-specific semantics are preserved.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.parse
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from fastapi import APIRouter, Query
except Exception:  # Allows local syntax/import tests outside the dashboard.
    class APIRouter:  # type: ignore
        def get(self, *_args, **_kwargs):
            return lambda fn: fn

    def Query(default=None, **_kwargs):  # type: ignore
        return default

router = APIRouter()

PLUGIN_VERSION = "0.5.0"
ENTRY_DELIMITER = "\n§\n"
DEFAULT_MEMORY_LIMIT = 2200
DEFAULT_USER_LIMIT = 1375
DEFAULT_FACT_LIMIT = 500
MAX_FACT_LIMIT = 2000
DEFAULT_MEM0_LIMIT = 500
MAX_MEM0_LIMIT = 2000
DEFAULT_HONCHO_LIMIT = 50
MAX_HONCHO_LIMIT = 100
DEFAULT_HINDSIGHT_LIMIT = 25
MAX_HINDSIGHT_LIMIT = 100
DEFAULT_MNEMOSYNE_LIMIT = 25
MAX_MNEMOSYNE_LIMIT = 100
DEFAULT_BYTEROVER_LIMIT = 10
MAX_BYTEROVER_LIMIT = 50
DEFAULT_BYTEROVER_QUERY_TIMEOUT = 60
HINDSIGHT_DEFAULT_CLOUD_URL = "https://api.hindsight.vectorize.io"
HINDSIGHT_DEFAULT_LOCAL_URL = "http://localhost:8888"
VALID_HINDSIGHT_BUDGETS = {"low", "mid", "high"}
REDACTED = "[REDACTED]"
SECRET_QUERY_KEYS = {
    "access_token",
    "apikey",
    "api_key",
    "auth",
    "authorization",
    "bearer",
    "client_secret",
    "key",
    "password",
    "secret",
    "token",
}


def _redact_url(value: str) -> str:
    """Redact URL userinfo and secret-looking query values before returning JSON."""
    try:
        parsed = urllib.parse.urlsplit(value)
    except Exception:
        return value
    if not parsed.scheme or not parsed.netloc:
        return value

    netloc = parsed.netloc
    if parsed.username is not None or parsed.password is not None:
        host = parsed.hostname or ""
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        port = f":{parsed.port}" if parsed.port is not None else ""
        netloc = f"{REDACTED}@{host}{port}"

    query_parts = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    redacted_query = urllib.parse.urlencode([
        (key, REDACTED if key.lower() in SECRET_QUERY_KEYS else value)
        for key, value in query_parts
    ]).replace("%5BREDACTED%5D", REDACTED)
    return urllib.parse.urlunsplit((parsed.scheme, netloc, parsed.path, redacted_query, parsed.fragment))


def _safe_error(exc: BaseException | str) -> str:
    """Return an error string safe for dashboard JSON responses."""
    text = str(exc)
    text = re.sub(r"https?://[^\s'\"<>]+", lambda match: _redact_url(match.group(0)), text)
    text = re.sub(r"(?i)\bBearer\s+[^\s,;]+", f"Bearer {REDACTED}", text)
    text = re.sub(
        r"(?i)\b(api[_-]?key|access[_-]?token|token|secret|password|authorization)\s*[:=]\s*[^\s,;&]+",
        lambda match: f"{match.group(1)}={REDACTED}",
        text,
    )
    return text


def _hermes_home() -> Path:
    """Return active Hermes home, respecting profiles when available."""
    try:
        from hermes_constants import get_hermes_home
        return Path(get_hermes_home()).expanduser()
    except Exception:
        return Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser()


def _read_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        import yaml
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _load_simple_env_file(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.exists():
        return values
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if not text or text.startswith("#") or "=" not in text:
                continue
            key, value = text.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    except Exception:
        return {}
    return values


def _env_value(key: str, default: str = "") -> str:
    value = os.environ.get(key)
    if value not in (None, ""):
        return str(value)
    file_env = _load_simple_env_file(_hermes_home() / ".env")
    return file_env.get(key, default)


def _truthy(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return default
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def _dig(data: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def _memory_limits(config: Dict[str, Any]) -> Dict[str, int]:
    memory_cfg = config.get("memory", {}) if isinstance(config.get("memory"), dict) else {}
    # Keep a few aliases to survive config key naming changes across Hermes versions.
    memory_limit = (
        memory_cfg.get("memory_char_limit")
        or memory_cfg.get("memory_limit")
        or memory_cfg.get("agent_memory_char_limit")
        or DEFAULT_MEMORY_LIMIT
    )
    user_limit = (
        memory_cfg.get("user_char_limit")
        or memory_cfg.get("user_profile_char_limit")
        or memory_cfg.get("profile_char_limit")
        or DEFAULT_USER_LIMIT
    )
    try:
        memory_limit = int(memory_limit)
    except Exception:
        memory_limit = DEFAULT_MEMORY_LIMIT
    try:
        user_limit = int(user_limit)
    except Exception:
        user_limit = DEFAULT_USER_LIMIT
    return {"memory": memory_limit, "user": user_limit}


def _parse_entries(raw: str) -> List[str]:
    if not raw.strip():
        return []
    return [entry.strip() for entry in raw.split(ENTRY_DELIMITER) if entry.strip()]


def _read_builtin_store(store_id: str, filename: str, label: str, limit: int) -> Dict[str, Any]:
    path = _hermes_home() / "memories" / filename
    try:
        raw = path.read_text(encoding="utf-8") if path.exists() else ""
        entries = _parse_entries(raw)
        char_count = len(ENTRY_DELIMITER.join(entries)) if entries else 0
        stat = path.stat() if path.exists() else None
        return {
            "id": store_id,
            "label": label,
            "filename": filename,
            "path": str(path),
            "exists": path.exists(),
            "entries": entries,
            "entry_count": len(entries),
            "char_count": char_count,
            "char_limit": limit,
            "usage_percent": round((char_count / limit) * 100, 1) if limit else None,
            "modified_at": stat.st_mtime if stat else None,
            "error": None,
        }
    except Exception as exc:
        return {
            "id": store_id,
            "label": label,
            "filename": filename,
            "path": str(path),
            "exists": path.exists(),
            "entries": [],
            "entry_count": 0,
            "char_count": 0,
            "char_limit": limit,
            "usage_percent": 0,
            "modified_at": None,
            "error": _safe_error(exc),
        }


def _builtin_payload(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    config = config if config is not None else _read_yaml(_hermes_home() / "config.yaml")
    limits = _memory_limits(config)
    stores = [
        _read_builtin_store("memory", "MEMORY.md", "Agent memory", limits["memory"]),
        _read_builtin_store("user", "USER.md", "User profile", limits["user"]),
    ]
    return {
        "hermes_home": str(_hermes_home()),
        "stores": stores,
        "total_entries": sum(s["entry_count"] for s in stores),
        "generated_at": time.time(),
    }


def _resolve_holographic_db(config: Dict[str, Any]) -> Path:
    home = _hermes_home()
    db_path = _dig(config, "plugins", "hermes-memory-store", "db_path", default=None)
    if not db_path:
        db_path = str(home / "memory_store.db")
    if isinstance(db_path, str):
        db_path = db_path.replace("$HERMES_HOME", str(home)).replace("${HERMES_HOME}", str(home))
        return Path(db_path).expanduser()
    return home / "memory_store.db"


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    # SQLite URI read-only mode prevents accidental writes from this dashboard plugin.
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5.0)
    conn.row_factory = sqlite3.Row
    return conn


def _safe_like(text: str) -> str:
    return f"%{text.replace('%', '').replace('_', '')}%"


def _holographic_payload(
    config: Optional[Dict[str, Any]] = None,
    *,
    limit: int = DEFAULT_FACT_LIMIT,
    category: Optional[str] = None,
    min_trust: float = 0.0,
    search: Optional[str] = None,
) -> Dict[str, Any]:
    config = config if config is not None else _read_yaml(_hermes_home() / "config.yaml")
    db_path = _resolve_holographic_db(config)
    provider = _dig(config, "memory", "provider", default=None)
    category = category if isinstance(category, str) and category.strip() else None
    search = search if isinstance(search, str) and search.strip() else None
    try:
        min_trust = float(min_trust or 0.0)
    except Exception:
        min_trust = 0.0
    try:
        limit = int(limit or DEFAULT_FACT_LIMIT)
    except Exception:
        limit = DEFAULT_FACT_LIMIT
    limit = max(1, min(limit, MAX_FACT_LIMIT))

    base: Dict[str, Any] = {
        "id": "holographic",
        "label": "Holographic memory",
        "provider_configured": provider == "holographic",
        "db_path": str(db_path),
        "exists": db_path.exists(),
        "facts": [],
        "fact_count": 0,
        "total_facts": 0,
        "categories": [],
        "entities_count": 0,
        "memory_banks_count": 0,
        "limit": limit,
        "error": None,
        "generated_at": time.time(),
    }

    if not db_path.exists():
        return base

    try:
        with _connect_readonly(db_path) as conn:
            try:
                base["total_facts"] = int(conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0])
            except Exception:
                base["total_facts"] = 0
            try:
                base["entities_count"] = int(conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0])
            except Exception:
                base["entities_count"] = 0
            try:
                base["memory_banks_count"] = int(conn.execute("SELECT COUNT(*) FROM memory_banks").fetchone()[0])
            except Exception:
                base["memory_banks_count"] = 0
            try:
                rows = conn.execute(
                    """
                    SELECT category, COUNT(*) AS count
                    FROM facts
                    GROUP BY category
                    ORDER BY count DESC, category ASC
                    """
                ).fetchall()
                base["categories"] = [{"category": r["category"] or "general", "count": r["count"]} for r in rows]
            except Exception:
                base["categories"] = []

            where = ["trust_score >= ?"]
            params: List[Any] = [float(min_trust or 0.0)]
            if category:
                where.append("category = ?")
                params.append(category)
            if search:
                where.append("(content LIKE ? OR tags LIKE ?)")
                like = _safe_like(search)
                params.extend([like, like])
            params.append(limit)
            sql = f"""
                SELECT fact_id, content, category, tags, trust_score,
                       retrieval_count, helpful_count, created_at, updated_at
                FROM facts
                WHERE {' AND '.join(where)}
                ORDER BY fact_id ASC
                LIMIT ?
            """
            facts = [dict(row) for row in conn.execute(sql, params).fetchall()]
            base["facts"] = facts
            base["fact_count"] = len(facts)
    except Exception as exc:
        base["error"] = _safe_error(exc)

    return base


def _expand_path(value: Optional[str], home: Optional[Path] = None) -> Optional[Path]:
    if not value or not isinstance(value, str):
        return None
    home = home or _hermes_home()
    expanded = value.replace("$HERMES_HOME", str(home)).replace("${HERMES_HOME}", str(home))
    return Path(expanded).expanduser()


def _load_mem0_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Load non-secret Mem0 configuration for read-only dashboard access."""
    home = _hermes_home()
    config_path = home / "mem0.json"
    file_cfg: Dict[str, Any] = {}
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8")) or {}
            file_cfg = data if isinstance(data, dict) else {}
        except Exception:
            file_cfg = {}

    def pick(key: str, env_key: str, default: Any = None) -> Any:
        value = os.environ.get(env_key, default)
        if key in file_cfg and file_cfg.get(key) not in (None, ""):
            value = file_cfg.get(key)
        return value

    api_key = pick("api_key", "MEM0_API_KEY", "")
    rerank = pick("rerank", "MEM0_RERANK", True)
    if isinstance(rerank, str):
        rerank = rerank.strip().lower() not in {"0", "false", "no", "off"}
    return {
        "config_path": str(config_path),
        "config_exists": config_path.exists(),
        "api_key_present": bool(api_key),
        "user_id": pick("user_id", "MEM0_USER_ID", "hermes-user"),
        "agent_id": pick("agent_id", "MEM0_AGENT_ID", "hermes"),
        "rerank": rerank,
        # Keep the real value private and local to the API call path.
        "_api_key": api_key,
    }


def _unwrap_mem0_results(response: Any) -> List[Any]:
    if isinstance(response, dict):
        results = response.get("results", response.get("memories", []))
        return results if isinstance(results, list) else []
    if isinstance(response, list):
        return response
    return []


def _normalize_mem0_memory(item: Any, index: int) -> Dict[str, Any]:
    if isinstance(item, str):
        return {"id": str(index + 1), "memory": item, "score": None, "created_at": None, "updated_at": None, "metadata": {}}
    if not isinstance(item, dict):
        return {"id": str(index + 1), "memory": str(item), "score": None, "created_at": None, "updated_at": None, "metadata": {}}
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    return {
        "id": item.get("id") or item.get("memory_id") or item.get("uuid") or str(index + 1),
        "memory": item.get("memory") or item.get("text") or item.get("content") or "",
        "score": item.get("score"),
        "created_at": item.get("created_at") or item.get("createdAt"),
        "updated_at": item.get("updated_at") or item.get("updatedAt"),
        "user_id": item.get("user_id") or item.get("userId"),
        "agent_id": item.get("agent_id") or item.get("agentId"),
        "metadata": metadata,
    }


def _filter_mem0_memories(memories: List[Dict[str, Any]], search: Optional[str], limit: int) -> List[Dict[str, Any]]:
    if search:
        needle = search.casefold()
        memories = [m for m in memories if needle in str(m.get("memory", "")).casefold()]
    return memories[:limit]


def _mem0_payload(
    config: Optional[Dict[str, Any]] = None,
    *,
    limit: int = DEFAULT_MEM0_LIMIT,
    search: Optional[str] = None,
) -> Dict[str, Any]:
    config = config if config is not None else _read_yaml(_hermes_home() / "config.yaml")
    provider = _dig(config, "memory", "provider", default=None)
    mem0_cfg = _load_mem0_config(config)
    search = search if isinstance(search, str) and search.strip() else None
    try:
        limit = int(limit or DEFAULT_MEM0_LIMIT)
    except Exception:
        limit = DEFAULT_MEM0_LIMIT
    limit = max(1, min(limit, MAX_MEM0_LIMIT))

    base: Dict[str, Any] = {
        "id": "mem0",
        "label": "Mem0 memory",
        "provider_configured": provider == "mem0",
        "mode": "read-only",
        "config_path": mem0_cfg["config_path"],
        "config_exists": mem0_cfg["config_exists"],
        "api_key_present": mem0_cfg["api_key_present"],
        "user_id": mem0_cfg["user_id"],
        "agent_id": mem0_cfg["agent_id"],
        "memories": [],
        "memory_count": 0,
        "total_memories": 0,
        "limit": limit,
        "search": search or "",
        "error": None,
        "generated_at": time.time(),
    }

    try:
        if not mem0_cfg["api_key_present"]:
            base["error"] = "Mem0 API key not configured. Set MEM0_API_KEY in $HERMES_HOME/.env or the process environment."
            return base

        try:
            from mem0 import MemoryClient  # type: ignore
        except ImportError:
            base["error"] = "mem0 package not installed in the dashboard environment. Install mem0ai."
            return base

        client = MemoryClient(api_key=mem0_cfg["_api_key"])
        filters = {"user_id": mem0_cfg["user_id"]}
        if search:
            response = client.search(query=search, filters=filters, rerank=mem0_cfg["rerank"], top_k=limit)
        else:
            response = client.get_all(filters=filters)
        all_memories = [_normalize_mem0_memory(item, index) for index, item in enumerate(_unwrap_mem0_results(response))]
        base["total_memories"] = len(all_memories)
        base["memories"] = _filter_mem0_memories(all_memories, None, limit)
        base["memory_count"] = len(base["memories"])
    except Exception as exc:
        base["error"] = _safe_error(exc)

    return base


def _normalize_honcho_card(card: Any) -> List[str]:
    if not card:
        return []
    if isinstance(card, (list, tuple)):
        return [str(item) for item in card if item]
    return [str(card)]


def _object_to_dict(item: Any) -> Dict[str, Any]:
    if isinstance(item, dict):
        return dict(item)
    model_dump = getattr(item, "model_dump", None)
    if callable(model_dump):
        try:
            data = model_dump()
            return data if isinstance(data, dict) else {}
        except Exception:
            pass
    as_dict = getattr(item, "dict", None)
    if callable(as_dict):
        try:
            data = as_dict()
            return data if isinstance(data, dict) else {}
        except Exception:
            pass
    result: Dict[str, Any] = {}
    for key in ("id", "content", "created_at", "updated_at", "session_id", "metadata"):
        if hasattr(item, key):
            value = getattr(item, key)
            if not callable(value):
                result[key] = value
    return result


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    iso = getattr(value, "isoformat", None)
    if callable(iso):
        try:
            return iso()
        except Exception:
            pass
    return str(value)


def _normalize_honcho_conclusion(item: Any, index: int) -> Dict[str, Any]:
    data = _object_to_dict(item)
    content = data.get("content") or data.get("text") or data.get("body") or ""
    return {
        "id": data.get("id") or data.get("conclusion_id") or data.get("uuid") or str(index + 1),
        "content": str(content),
        "created_at": _json_safe(data.get("created_at") or data.get("createdAt")),
        "updated_at": _json_safe(data.get("updated_at") or data.get("updatedAt")),
        "session_id": data.get("session_id") or data.get("sessionId"),
        "metadata": _json_safe(data.get("metadata") if isinstance(data.get("metadata"), dict) else {}),
    }


def _honcho_config_payload(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    config = config if config is not None else _read_yaml(_hermes_home() / "config.yaml")
    provider = _dig(config, "memory", "provider", default=None)
    fallback_path = _hermes_home() / "honcho.json"
    base: Dict[str, Any] = {
        "provider_configured": provider == "honcho",
        "config_path": str(fallback_path),
        "config_exists": fallback_path.exists(),
        "api_key_present": bool(os.environ.get("HONCHO_API_KEY")),
        "base_url_present": bool(os.environ.get("HONCHO_BASE_URL")),
        "enabled": False,
        "host": os.environ.get("HERMES_HONCHO_HOST", "hermes"),
        "workspace": "hermes",
        "user_peer": "user",
        "ai_peer": "hermes",
        "environment": os.environ.get("HONCHO_ENVIRONMENT", "production"),
        "recall_mode": "hybrid",
        "session_strategy": "per-directory",
        "save_messages": None,
        "write_frequency": None,
        "context_tokens": None,
        "dialectic_depth": None,
        "dialectic_reasoning_level": None,
        "dialectic_dynamic": None,
        "dialectic_max_chars": None,
        "observation_mode": None,
        "user_observe_me": None,
        "user_observe_others": None,
        "ai_observe_me": None,
        "ai_observe_others": None,
        "explicitly_configured": False,
        "_client_config": None,
        "_import_error": None,
    }
    try:
        from plugins.memory.honcho.client import HonchoClientConfig, resolve_config_path  # type: ignore

        cfg = HonchoClientConfig.from_global_config()
        path = resolve_config_path()
        base.update({
            "config_path": str(path),
            "config_exists": Path(path).exists(),
            "api_key_present": bool(getattr(cfg, "api_key", None)),
            "base_url_present": bool(getattr(cfg, "base_url", None)),
            "enabled": bool(getattr(cfg, "enabled", False)),
            "host": getattr(cfg, "host", None) or "hermes",
            "workspace": getattr(cfg, "workspace_id", None) or "hermes",
            "user_peer": getattr(cfg, "peer_name", None) or "user",
            "ai_peer": getattr(cfg, "ai_peer", None) or getattr(cfg, "host", None) or "hermes",
            "environment": getattr(cfg, "environment", None) or "production",
            "recall_mode": getattr(cfg, "recall_mode", None) or "hybrid",
            "session_strategy": getattr(cfg, "session_strategy", None) or "per-directory",
            "save_messages": getattr(cfg, "save_messages", None),
            "write_frequency": getattr(cfg, "write_frequency", None),
            "context_tokens": getattr(cfg, "context_tokens", None),
            "dialectic_depth": getattr(cfg, "dialectic_depth", None),
            "dialectic_reasoning_level": getattr(cfg, "dialectic_reasoning_level", None),
            "dialectic_dynamic": getattr(cfg, "dialectic_dynamic", None),
            "dialectic_max_chars": getattr(cfg, "dialectic_max_chars", None),
            "observation_mode": getattr(cfg, "observation_mode", None),
            "user_observe_me": getattr(cfg, "user_observe_me", None),
            "user_observe_others": getattr(cfg, "user_observe_others", None),
            "ai_observe_me": getattr(cfg, "ai_observe_me", None),
            "ai_observe_others": getattr(cfg, "ai_observe_others", None),
            "explicitly_configured": getattr(cfg, "explicitly_configured", False),
            "_client_config": cfg,
        })
    except Exception as exc:
        base["_import_error"] = f"Honcho provider helpers unavailable: {_safe_error(exc)}"
    return base


def _call_peer_context(peer_obj: Any, *, target: str, search: Optional[str], limit: int) -> Dict[str, Any]:
    representation = ""
    card: List[str] = []
    try:
        kwargs: Dict[str, Any] = {"target": target}
        if search:
            kwargs["search_query"] = search
            kwargs["search_top_k"] = limit
        try:
            ctx = peer_obj.context(**kwargs)
        except TypeError:
            kwargs.pop("search_top_k", None)
            ctx = peer_obj.context(**kwargs)
        representation = getattr(ctx, "representation", None) or getattr(ctx, "peer_representation", None) or ""
        card = _normalize_honcho_card(getattr(ctx, "peer_card", None))
    except Exception:
        pass
    if not representation:
        try:
            representation = peer_obj.representation(target=target) or ""
        except Exception:
            representation = ""
    if not card:
        try:
            getter = getattr(peer_obj, "get_card", None) or getattr(peer_obj, "card", None)
            if callable(getter):
                card = _normalize_honcho_card(getter(target=target))
        except Exception:
            card = []
    return {"representation": str(representation or ""), "card": card}


def _list_honcho_conclusions(
    observer_peer: Any, target_peer_id: str, limit: int
) -> Tuple[List[Dict[str, Any]], int]:
    """Return ``(newest-first conclusions, total count)``.

    Honcho's Python SDK returns a ``SyncPage`` from
    ``ConclusionScope.list(page, size)`` whose ``.total`` attribute reflects
    the full population in the database, not just the current page. Surfacing
    that total lets the dashboard show the real population (e.g. 2076)
    instead of ``len(items)`` (which is bounded by ``MAX_HONCHO_LIMIT``).

    Items are sorted newest-first defensively so the "showing N latest" hint
    in the UI stays correct even if the SDK ever changes its default order.
    """
    try:
        scope = observer_peer.conclusions_of(target_peer_id)
        try:
            page = scope.list(page=1, size=limit, reverse=True)
        except TypeError:
            page = scope.list(page=1, size=limit)
        if hasattr(page, "items") and hasattr(page, "total"):
            raw_items = list(page.items or [])
            total = int(getattr(page, "total", 0) or 0)
        else:
            raw_items = list(page or [])
            total = len(raw_items)
        normalized = [
            _normalize_honcho_conclusion(item, index)
            for index, item in enumerate(raw_items[:limit])
        ]
        try:
            normalized.sort(key=lambda c: c.get("created_at") or "", reverse=True)
        except Exception:
            pass
        return normalized, total
    except Exception:
        return [], 0


def _honcho_search_results(base: Dict[str, Any], search: Optional[str], limit: int) -> List[Dict[str, Any]]:
    """Return visible, deterministic text matches for the dashboard search box.

    Honcho's `peer.context(search_query=...)` may still return the same peer card
    shape, especially with local/self-hosted demo data or missing embeddings. The
    dashboard should nevertheless show that Apply/Refresh used the submitted
    query, so expose lightweight read-only matches from the already returned card
    and conclusion text.
    """
    if not search:
        return []
    needle = search.casefold()
    results: List[Dict[str, Any]] = []
    for scope_key, label in (("user", "User peer"), ("ai", "AI peer")):
        peer = base.get(scope_key, {}) if isinstance(base.get(scope_key), dict) else {}
        peer_id = peer.get("peer_id") or scope_key
        for index, item in enumerate(peer.get("card") or []):
            text = str(item)
            if needle in text.casefold():
                results.append({"source": f"{label} card", "peer_id": peer_id, "id": str(index + 1), "content": text})
        representation = str(peer.get("representation") or "")
        if representation and needle in representation.casefold():
            results.append({"source": f"{label} representation", "peer_id": peer_id, "id": "representation", "content": representation})
        for conclusion in peer.get("conclusions") or []:
            text = str(conclusion.get("content", "")) if isinstance(conclusion, dict) else str(conclusion)
            if needle in text.casefold():
                results.append({
                    "source": f"{label} conclusion",
                    "peer_id": peer_id,
                    "id": str(conclusion.get("id", len(results) + 1)) if isinstance(conclusion, dict) else str(len(results) + 1),
                    "content": text,
                })
    return results[:limit]


def _honcho_payload(
    config: Optional[Dict[str, Any]] = None,
    *,
    limit: int = DEFAULT_HONCHO_LIMIT,
    search: Optional[str] = None,
) -> Dict[str, Any]:
    config = config if config is not None else _read_yaml(_hermes_home() / "config.yaml")
    honcho_cfg = _honcho_config_payload(config)
    search = search if isinstance(search, str) and search.strip() else None
    try:
        limit = int(limit or DEFAULT_HONCHO_LIMIT)
    except Exception:
        limit = DEFAULT_HONCHO_LIMIT
    limit = max(1, min(limit, MAX_HONCHO_LIMIT))
    base: Dict[str, Any] = {
        "id": "honcho",
        "label": "Honcho memory",
        "provider_configured": honcho_cfg["provider_configured"],
        "mode": "read-only",
        "config_path": honcho_cfg["config_path"],
        "config_exists": honcho_cfg["config_exists"],
        "api_key_present": honcho_cfg["api_key_present"],
        "base_url_present": honcho_cfg["base_url_present"],
        "enabled": honcho_cfg["enabled"],
        "host": honcho_cfg["host"],
        "workspace": honcho_cfg["workspace"],
        "user_peer": honcho_cfg["user_peer"],
        "ai_peer": honcho_cfg["ai_peer"],
        "environment": honcho_cfg["environment"],
        "recall_mode": honcho_cfg["recall_mode"],
        "session_strategy": honcho_cfg["session_strategy"],
        "save_messages": honcho_cfg["save_messages"],
        "write_frequency": honcho_cfg["write_frequency"],
        "context_tokens": honcho_cfg["context_tokens"],
        "dialectic_depth": honcho_cfg["dialectic_depth"],
        "dialectic_reasoning_level": honcho_cfg["dialectic_reasoning_level"],
        "dialectic_dynamic": honcho_cfg["dialectic_dynamic"],
        "dialectic_max_chars": honcho_cfg["dialectic_max_chars"],
        "observation_mode": honcho_cfg["observation_mode"],
        "user_observe_me": honcho_cfg["user_observe_me"],
        "user_observe_others": honcho_cfg["user_observe_others"],
        "ai_observe_me": honcho_cfg["ai_observe_me"],
        "ai_observe_others": honcho_cfg["ai_observe_others"],
        "explicitly_configured": honcho_cfg["explicitly_configured"],
        "user": {"peer_id": honcho_cfg["user_peer"], "card": [], "representation": "", "conclusions": [], "total_conclusions": 0, "total_card_facts": 0},
        "ai": {"peer_id": honcho_cfg["ai_peer"], "card": [], "representation": "", "conclusions": [], "total_conclusions": 0, "total_card_facts": 0},
        "search_results": [],
        "search_result_count": 0,
        "limit": limit,
        "search": search or "",
        "error": None,
        "generated_at": time.time(),
    }
    cfg = honcho_cfg.get("_client_config")
    if cfg is None:
        base["error"] = honcho_cfg.get("_import_error") or "Honcho provider helpers are not available in the dashboard environment."
        return base
    if not (honcho_cfg["api_key_present"] or honcho_cfg["base_url_present"]):
        base["error"] = "Honcho API key or base URL is not configured. Run 'hermes honcho setup' or set HONCHO_API_KEY / HONCHO_BASE_URL."
        return base
    try:
        from plugins.memory.honcho.client import get_honcho_client  # type: ignore

        client = get_honcho_client(cfg)
        user_peer_id = str(honcho_cfg["user_peer"] or "user")
        ai_peer_id = str(honcho_cfg["ai_peer"] or honcho_cfg["host"] or "hermes")
        user_peer_obj = client.peer(user_peer_id)
        ai_peer_obj = client.peer(ai_peer_id)
        base["user"].update(_call_peer_context(user_peer_obj, target=user_peer_id, search=search, limit=limit))
        base["ai"].update(_call_peer_context(ai_peer_obj, target=ai_peer_id, search=search, limit=limit))
        user_concs, user_total = _list_honcho_conclusions(ai_peer_obj, user_peer_id, limit)
        ai_concs, ai_total = _list_honcho_conclusions(ai_peer_obj, ai_peer_id, limit)
        base["user"]["conclusions"] = user_concs
        base["user"]["total_conclusions"] = user_total
        base["user"]["total_card_facts"] = len(base["user"].get("card") or [])
        base["ai"]["conclusions"] = ai_concs
        base["ai"]["total_conclusions"] = ai_total
        base["ai"]["total_card_facts"] = len(base["ai"].get("card") or [])
        base["search_results"] = _honcho_search_results(base, search, limit)
        base["search_result_count"] = len(base["search_results"])
    except Exception as exc:
        base["error"] = _safe_error(exc)
    return base


def _resolve_mnemosyne_data_dir(config: Dict[str, Any]) -> Path:
    memory_cfg = config.get("memory", {}) if isinstance(config.get("memory"), dict) else {}
    mnemosyne_cfg = memory_cfg.get("mnemosyne", {}) if isinstance(memory_cfg.get("mnemosyne"), dict) else {}
    configured = (
        mnemosyne_cfg.get("data_dir")
        or mnemosyne_cfg.get("path")
        or _env_value("MNEMOSYNE_DATA_DIR", "")
        or str(_hermes_home() / "mnemosyne" / "data")
    )
    return _expand_path(str(configured), _hermes_home()) or (_hermes_home() / "mnemosyne" / "data")


def _resolve_mnemosyne_db_path(config: Dict[str, Any]) -> Path:
    memory_cfg = config.get("memory", {}) if isinstance(config.get("memory"), dict) else {}
    mnemosyne_cfg = memory_cfg.get("mnemosyne", {}) if isinstance(memory_cfg.get("mnemosyne"), dict) else {}
    configured = mnemosyne_cfg.get("db_path") or _env_value("MNEMOSYNE_DB_PATH", "")
    if configured:
        path = _expand_path(str(configured), _hermes_home())
        if path:
            return path
    return _resolve_mnemosyne_data_dir(config) / "mnemosyne.db"


def _load_mnemosyne_config(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    config = config if config is not None else _read_yaml(_hermes_home() / "config.yaml")
    data_dir = _resolve_mnemosyne_data_dir(config)
    db_path = _resolve_mnemosyne_db_path(config)
    prefetch_chars = _env_value("MNEMOSYNE_PREFETCH_CONTENT_CHARS", "")
    return {
        "provider_configured": _dig(config, "memory", "provider", default=None) == "mnemosyne",
        "config_path": str(_hermes_home() / "config.yaml"),
        "data_dir": str(data_dir),
        "db_path": str(db_path),
        "db_exists": db_path.exists(),
        "prefetch_content_chars": prefetch_chars,
        "auto_sleep_enabled": _truthy(_env_value("MNEMOSYNE_AUTO_SLEEP_ENABLED", "true"), True),
    }


def _mnemosyne_table_exists(conn: sqlite3.Connection, table: str) -> bool:
    try:
        return conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ? LIMIT 1",
            (table,),
        ).fetchone() is not None
    except Exception:
        return False


def _mnemosyne_table_count(conn: sqlite3.Connection, table: str) -> int:
    if not _mnemosyne_table_exists(conn, table):
        return 0
    try:
        quoted = table.replace('"', '""')
        return int(conn.execute(f'SELECT COUNT(*) FROM "{quoted}"').fetchone()[0])
    except Exception:
        return 0


def _mnemosyne_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    try:
        quoted = table.replace('"', '""')
        return [str(row["name"]) for row in conn.execute(f'PRAGMA table_info("{quoted}")').fetchall()]
    except Exception:
        return []


def _json_object(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _mnemosyne_order_clause(columns: List[str], preferred: List[str]) -> str:
    for column in preferred:
        if column in columns:
            quoted = column.replace('"', '""')
            return f'ORDER BY "{quoted}" DESC'
    return ""


def _mnemosyne_where(search: Optional[str], columns: List[str], candidates: List[str]) -> tuple[str, List[Any]]:
    if not search:
        return "", []
    available = [column for column in candidates if column in columns]
    if not available:
        return "", []
    where = "WHERE " + " OR ".join([f'"{column.replace(chr(34), chr(34) + chr(34))}" LIKE ?' for column in available])
    return where, [_safe_like(search)] * len(available)


def _normalize_mnemosyne_memory(row: Dict[str, Any], index: int) -> Dict[str, Any]:
    metadata = _json_object(row.get("metadata_json"))
    text = row.get("content") or row.get("text") or row.get("memory") or ""
    return {
        "id": row.get("id") or row.get("rowid") or str(index + 1),
        "text": str(text),
        "score": row.get("score"),
        "type": row.get("memory_type") or row.get("source") or "memory",
        "source": row.get("source") or "",
        "timestamp": row.get("timestamp"),
        "created_at": row.get("created_at"),
        "session_id": row.get("session_id"),
        "importance": row.get("importance"),
        "tier": row.get("tier"),
        "recall_count": row.get("recall_count"),
        "last_recalled": row.get("last_recalled"),
        "scope": row.get("scope"),
        "channel_id": row.get("channel_id"),
        "trust_tier": row.get("trust_tier"),
        "metadata": _json_safe(metadata),
    }


def _mnemosyne_fact_text(table: str, row: Dict[str, Any]) -> str:
    if table == "memoria_facts":
        key = str(row.get("key") or "").strip()
        value = str(row.get("value") or "").strip()
        if key and value:
            return f"{key}: {value}"
        return value or key or str(row.get("context_snippet") or "")
    if table == "memoria_instructions":
        return str(row.get("instruction") or "")
    if table == "memoria_preferences":
        return str(row.get("preference") or "")
    if table == "memoria_timelines":
        return str(row.get("description") or "")
    if table == "memoria_kg":
        return " ".join(str(row.get(key) or "") for key in ("subject", "predicate", "object")).strip()
    if table == "triples":
        return " ".join(str(row.get(key) or "") for key in ("subject", "predicate", "object")).strip()
    if table == "gists":
        return str(row.get("text") or "")
    if table == "consolidated_facts":
        return " ".join(str(row.get(key) or "") for key in ("subject", "predicate", "object")).strip()
    if table == "facts":
        return " ".join(str(row.get(key) or "") for key in ("subject", "predicate", "object")).strip()
    return str(row.get("content") or row.get("value") or row.get("text") or "")


def _normalize_mnemosyne_fact(table: str, row: Dict[str, Any], index: int) -> Dict[str, Any]:
    row_id = row.get("id") or row.get("fact_id") or row.get("event_id") or str(index + 1)
    timestamp = row.get("timestamp") or row.get("date") or row.get("created_at")
    metadata = {
        key: value
        for key, value in row.items()
        if key not in {"id", "fact_id", "event_id", "content", "text", "value"}
    }
    return {
        "id": row_id,
        "text": _mnemosyne_fact_text(table, row),
        "score": row.get("importance") or row.get("confidence"),
        "type": table,
        "source": row.get("source") or row.get("session_id") or "",
        "timestamp": timestamp,
        "created_at": row.get("created_at"),
        "metadata": _json_safe(metadata),
    }


def _mnemosyne_fetch_memories(
    conn: sqlite3.Connection,
    *,
    limit: int,
    search: Optional[str],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for table in ("episodic_memory", "working_memory", "memories"):
        if len(rows) >= limit or not _mnemosyne_table_exists(conn, table):
            continue
        columns = _mnemosyne_columns(conn, table)
        selected = [
            column
            for column in (
                "rowid",
                "id",
                "content",
                "source",
                "timestamp",
                "session_id",
                "importance",
                "metadata_json",
                "created_at",
                "tier",
                "memory_type",
                "recall_count",
                "last_recalled",
                "scope",
                "channel_id",
                "trust_tier",
            )
            if column in columns
        ]
        if not selected:
            continue
        where, params = _mnemosyne_where(search, columns, ["content", "source", "session_id", "metadata_json"])
        order = _mnemosyne_order_clause(columns, ["timestamp", "created_at", "rowid", "id"])
        quoted_table = table.replace('"', '""')
        quoted_columns = ", ".join(f'"{column.replace(chr(34), chr(34) + chr(34))}"' for column in selected)
        sql = f'SELECT {quoted_columns} FROM "{quoted_table}" {where} {order} LIMIT ?'
        try:
            fetched = [dict(row) for row in conn.execute(sql, params + [limit - len(rows)]).fetchall()]
        except Exception:
            fetched = []
        rows.extend(fetched)
    return [_normalize_mnemosyne_memory(row, index) for index, row in enumerate(rows[:limit])]


def _mnemosyne_fetch_facts(
    conn: sqlite3.Connection,
    *,
    limit: int,
    search: Optional[str],
) -> List[Dict[str, Any]]:
    specs = [
        ("memoria_facts", ["id", "session_id", "fact_type", "key", "value", "context_snippet", "importance", "timestamp"], ["key", "value", "context_snippet"]),
        ("memoria_instructions", ["id", "session_id", "instruction", "active", "topic", "context_snippet"], ["instruction", "topic", "context_snippet"]),
        ("memoria_preferences", ["id", "session_id", "preference", "topic", "evolution", "context_snippet"], ["preference", "topic", "context_snippet"]),
        ("memoria_timelines", ["event_id", "session_id", "date", "description", "source"], ["description", "source", "date"]),
        ("memoria_kg", ["id", "session_id", "subject", "predicate", "object", "confidence"], ["subject", "predicate", "object"]),
        ("triples", ["id", "subject", "predicate", "object", "valid_from", "source", "confidence", "created_at"], ["subject", "predicate", "object", "source"]),
        ("gists", ["id", "text", "timestamp", "participants_json", "location", "emotion", "time_scope", "memory_id", "created_at"], ["text", "participants_json", "location", "emotion"]),
        ("consolidated_facts", ["id", "subject", "predicate", "object", "confidence", "mention_count", "first_seen", "last_seen", "veracity"], ["subject", "predicate", "object"]),
        ("facts", ["fact_id", "session_id", "subject", "predicate", "object", "timestamp", "confidence", "created_at"], ["subject", "predicate", "object"]),
    ]
    rows: List[tuple[str, Dict[str, Any]]] = []
    for table, desired, search_columns in specs:
        if len(rows) >= limit or not _mnemosyne_table_exists(conn, table):
            continue
        columns = _mnemosyne_columns(conn, table)
        selected = [column for column in desired if column in columns]
        if not selected:
            continue
        where, params = _mnemosyne_where(search, columns, search_columns)
        order = _mnemosyne_order_clause(columns, ["timestamp", "date", "created_at", "id", "event_id", "fact_id"])
        quoted_table = table.replace('"', '""')
        quoted_columns = ", ".join(f'"{column.replace(chr(34), chr(34) + chr(34))}"' for column in selected)
        sql = f'SELECT {quoted_columns} FROM "{quoted_table}" {where} {order} LIMIT ?'
        try:
            fetched = [dict(row) for row in conn.execute(sql, params + [limit - len(rows)]).fetchall()]
        except Exception:
            fetched = []
        rows.extend((table, row) for row in fetched)
    return [_normalize_mnemosyne_fact(table, row, index) for index, (table, row) in enumerate(rows[:limit])]


def _mnemosyne_config_payload(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = _load_mnemosyne_config(config)
    cfg.update({
        "id": "mnemosyne",
        "label": "Mnemosyne memory",
        "mode": "read-only/query-only",
        "error": None,
        "generated_at": time.time(),
    })
    return cfg


def _mnemosyne_contents_payload(
    config: Optional[Dict[str, Any]] = None,
    *,
    limit: int = DEFAULT_MNEMOSYNE_LIMIT,
    search: Optional[str] = None,
) -> Dict[str, Any]:
    config = config if config is not None else _read_yaml(_hermes_home() / "config.yaml")
    try:
        limit = int(limit or DEFAULT_MNEMOSYNE_LIMIT)
    except Exception:
        limit = DEFAULT_MNEMOSYNE_LIMIT
    limit = max(1, min(limit, MAX_MNEMOSYNE_LIMIT))
    search = search if isinstance(search, str) and search.strip() else None
    base = _mnemosyne_config_payload(config)
    base.update({
        "operation": "contents",
        "limit": limit,
        "search": search or "",
        "table_counts": {},
        "memories": [],
        "memory_count": 0,
        "total_memories": 0,
        "facts": [],
        "fact_count": 0,
        "total_facts": 0,
        "vector_rows": 0,
    })
    db_path = Path(str(base["db_path"]))
    if not db_path.exists():
        return base
    try:
        with _connect_readonly(db_path) as conn:
            count_tables = [
                "episodic_memory",
                "working_memory",
                "memories",
                "memoria_facts",
                "memoria_instructions",
                "memoria_preferences",
                "memoria_timelines",
                "memoria_kg",
                "gists",
                "triples",
                "consolidated_facts",
                "facts",
                "scratchpad",
                "vec_episodes_rowids",
                "vec_facts_rowids",
            ]
            counts = {table: _mnemosyne_table_count(conn, table) for table in count_tables}
            base["table_counts"] = counts
            base["total_memories"] = counts.get("episodic_memory", 0) + counts.get("working_memory", 0) + counts.get("memories", 0)
            base["total_facts"] = (
                counts.get("memoria_facts", 0)
                + counts.get("memoria_instructions", 0)
                + counts.get("memoria_preferences", 0)
                + counts.get("memoria_timelines", 0)
                + counts.get("memoria_kg", 0)
                + counts.get("gists", 0)
                + counts.get("triples", 0)
                + counts.get("consolidated_facts", 0)
                + counts.get("facts", 0)
            )
            base["vector_rows"] = counts.get("vec_episodes_rowids", 0) + counts.get("vec_facts_rowids", 0)
            base["memories"] = _mnemosyne_fetch_memories(conn, limit=limit, search=search)
            base["memory_count"] = len(base["memories"])
            base["facts"] = _mnemosyne_fetch_facts(conn, limit=limit, search=search)
            base["fact_count"] = len(base["facts"])
    except Exception as exc:
        base["error"] = _safe_error(exc)
    return base


def _load_mnemosyne_provider_class() -> Any:
    errors: List[str] = []
    try:
        from plugins.memory.mnemosyne import MnemosyneMemoryProvider  # type: ignore

        return MnemosyneMemoryProvider
    except Exception as exc:
        errors.append(f"plugins.memory.mnemosyne: {_safe_error(exc)}")

    plugin_file = _hermes_home() / "plugins" / "mnemosyne" / "__init__.py"
    if plugin_file.exists():
        try:
            spec = importlib.util.spec_from_file_location("hermes_memory_ui_mnemosyne_plugin", plugin_file)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                provider_cls = getattr(module, "MnemosyneMemoryProvider", None)
                if provider_cls is not None:
                    return provider_cls
        except Exception as exc:
            errors.append(f"{plugin_file}: {_safe_error(exc)}")

    try:
        from hermes_memory_provider import MnemosyneMemoryProvider  # type: ignore

        return MnemosyneMemoryProvider
    except Exception as exc:
        errors.append(f"hermes_memory_provider: {_safe_error(exc)}")

    raise RuntimeError("Mnemosyne provider is not available in the dashboard environment: " + "; ".join(errors))


def _make_mnemosyne_provider() -> Any:
    provider_cls = _load_mnemosyne_provider_class()
    provider = provider_cls()
    provider.initialize(session_id="dashboard", hermes_home=str(_hermes_home()), platform="dashboard")
    return provider


def _decode_mnemosyne_response(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, list):
                return {"results": parsed}
        except Exception:
            return {"context": value}
    return {"result": _json_safe(value)}


def _normalize_mnemosyne_result(item: Any, index: int) -> Dict[str, Any]:
    data = _object_to_dict(item)
    if not data and isinstance(item, str):
        data = {"content": item}
    text = data.get("content") or data.get("text") or data.get("memory") or data.get("summary") or ""
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else data.get("metadata_json")
    return {
        "id": data.get("id") or data.get("memory_id") or data.get("uuid") or str(index + 1),
        "text": str(text),
        "score": data.get("score") or data.get("similarity") or data.get("importance"),
        "type": data.get("memory_type") or data.get("type") or data.get("source") or "memory",
        "source": data.get("source") or "",
        "timestamp": data.get("timestamp") or data.get("created_at"),
        "metadata": _json_safe(_json_object(metadata) if isinstance(metadata, str) else (metadata if isinstance(metadata, dict) else {})),
    }


def _mnemosyne_payload(
    config: Optional[Dict[str, Any]] = None,
    *,
    query: Optional[str] = None,
    limit: int = DEFAULT_MNEMOSYNE_LIMIT,
    temporal_weight: float = 0.2,
    mode: str = "status",
) -> Dict[str, Any]:
    config = config if config is not None else _read_yaml(_hermes_home() / "config.yaml")
    query = query if isinstance(query, str) and query.strip() else None
    try:
        limit = int(limit or DEFAULT_MNEMOSYNE_LIMIT)
    except Exception:
        limit = DEFAULT_MNEMOSYNE_LIMIT
    limit = max(1, min(limit, MAX_MNEMOSYNE_LIMIT))
    try:
        temporal_weight = float(temporal_weight)
    except Exception:
        temporal_weight = 0.2
    temporal_weight = max(0.0, min(1.0, temporal_weight))
    base = _mnemosyne_config_payload(config)
    base.update({
        "operation": mode,
        "query": query or "",
        "limit": limit,
        "temporal_weight": temporal_weight,
        "results": [],
        "result_count": 0,
        "context": "",
        "context_char_count": 0,
        "result_source": "",
    })
    if mode == "status":
        return base
    if mode not in {"recall", "prefetch"}:
        base["error"] = f"Unsupported Mnemosyne operation: {mode}"
        return base
    if not query:
        base["error"] = "Query is required for Mnemosyne recall/prefetch."
        return base
    provider = None
    try:
        provider = _make_mnemosyne_provider()
        if mode == "prefetch":
            try:
                context = provider.prefetch(query, session_id="dashboard")
            except TypeError:
                context = provider.prefetch(query)
            base["context"] = str(context or "")
            base["context_char_count"] = len(base["context"])
            base["result_source"] = "mnemosyne_prefetch"
            return base
        response = provider.handle_tool_call(
            "mnemosyne_recall",
            {"query": query, "limit": limit, "temporal_weight": temporal_weight},
        )
        decoded = _decode_mnemosyne_response(response)
        if decoded.get("error"):
            base["error"] = _safe_error(decoded.get("error"))
        raw_results = decoded.get("results") or decoded.get("memories") or decoded.get("matches") or []
        if isinstance(raw_results, dict):
            raw_results = list(raw_results.values())
        if not isinstance(raw_results, list):
            raw_results = []
        base["results"] = [_normalize_mnemosyne_result(item, index) for index, item in enumerate(raw_results[:limit])]
        base["result_count"] = len(base["results"])
        base["result_source"] = "mnemosyne_recall"
    except Exception as exc:
        base["error"] = _safe_error(exc)
    finally:
        shutdown = getattr(provider, "shutdown", None) if provider is not None else None
        if callable(shutdown):
            try:
                import contextlib
                import io
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    shutdown()
            except Exception:
                pass
    return base


def _load_hindsight_config(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Load non-secret Hindsight configuration for dashboard inspection."""
    config = config if config is not None else _read_yaml(_hermes_home() / "config.yaml")
    home = _hermes_home()
    profile_path = home / "hindsight" / "config.json"
    legacy_path = Path.home() / ".hindsight" / "config.json"
    file_cfg: Dict[str, Any] = {}
    config_path = profile_path
    config_exists = profile_path.exists()
    if config_exists:
        file_cfg = _read_json(profile_path)
    elif legacy_path.exists():
        config_path = legacy_path
        config_exists = True
        file_cfg = _read_json(legacy_path)

    mode = str(file_cfg.get("mode") or _env_value("HINDSIGHT_MODE", "cloud") or "cloud")
    if mode == "local":
        mode = "local_embedded"
    api_key = file_cfg.get("apiKey") or file_cfg.get("api_key") or _env_value("HINDSIGHT_API_KEY", "")
    llm_key = file_cfg.get("llmApiKey") or file_cfg.get("llm_api_key") or _env_value("HINDSIGHT_LLM_API_KEY", "")
    default_url = HINDSIGHT_DEFAULT_LOCAL_URL if mode in {"local_embedded", "local_external"} else HINDSIGHT_DEFAULT_CLOUD_URL
    api_url = (
        file_cfg.get("api_url")
        or _env_value("HINDSIGHT_API_URL", "")
        or _env_value("HINDSIGHT_DAEMON_URL", "")
        or default_url
    )
    banks = file_cfg.get("banks") if isinstance(file_cfg.get("banks"), dict) else {}
    hermes_bank = banks.get("hermes") if isinstance(banks.get("hermes"), dict) else {}
    bank_id = file_cfg.get("bank_id") or hermes_bank.get("bankId") or _env_value("HINDSIGHT_BANK_ID", "hermes")
    bank_template = file_cfg.get("bank_id_template", "") or ""
    budget = file_cfg.get("recall_budget") or file_cfg.get("budget") or hermes_bank.get("budget") or _env_value("HINDSIGHT_BUDGET", "mid")
    if budget not in VALID_HINDSIGHT_BUDGETS:
        budget = "mid"
    return {
        "provider_configured": _dig(config, "memory", "provider", default=None) == "hindsight",
        "config_path": str(config_path),
        "config_exists": bool(config_exists),
        "mode": mode,
        "api_url": _redact_url(str(api_url)),
        "api_key_present": bool(api_key),
        "llm_key_present": bool(llm_key),
        "llm_provider": file_cfg.get("llm_provider") or "",
        "llm_model": file_cfg.get("llm_model") or "",
        "llm_base_url_present": bool(file_cfg.get("llm_base_url") or _env_value("HINDSIGHT_API_LLM_BASE_URL", "")),
        "bank_id": str(bank_id or "hermes"),
        "bank_id_template": str(bank_template),
        "bank_mission": file_cfg.get("bank_mission", ""),
        "bank_retain_mission": file_cfg.get("bank_retain_mission") or "",
        "recall_budget": budget,
        "recall_prefetch_method": file_cfg.get("recall_prefetch_method") or file_cfg.get("prefetch_method") or "recall",
        "recall_max_tokens": file_cfg.get("recall_max_tokens", 4096),
        "recall_max_input_chars": file_cfg.get("recall_max_input_chars", 800),
        "recall_tags": file_cfg.get("recall_tags") or None,
        "recall_tags_match": file_cfg.get("recall_tags_match", "any"),
        "memory_mode": file_cfg.get("memory_mode", "hybrid"),
        "auto_retain": _truthy(file_cfg.get("auto_retain"), True),
        "auto_recall": _truthy(file_cfg.get("auto_recall"), True),
        "retain_async": _truthy(file_cfg.get("retain_async"), True),
        "retain_every_n_turns": file_cfg.get("retain_every_n_turns", 1),
        "timeout": file_cfg.get("timeout") if file_cfg.get("timeout") is not None else _env_value("HINDSIGHT_TIMEOUT", "120"),
        "idle_timeout": file_cfg.get("idle_timeout") if file_cfg.get("idle_timeout") is not None else _env_value("HINDSIGHT_IDLE_TIMEOUT", "300"),
        "profile": file_cfg.get("profile", "hermes"),
        "_api_url": str(api_url),
        "_api_key": api_key,
        "_file_config": file_cfg,
    }


def _normalize_hindsight_result(item: Any, index: int) -> Dict[str, Any]:
    data = _object_to_dict(item)

    def attr(name: str, default: Any = None) -> Any:
        if name in data:
            return data.get(name)
        value = getattr(item, name, default)
        return default if callable(value) else value

    text = attr("text") or attr("content") or attr("memory") or attr("document") or ""
    metadata = attr("metadata", {})
    return {
        "id": attr("id") or attr("document_id") or attr("uuid") or str(index + 1),
        "text": str(text),
        "score": attr("score") or attr("relevance") or attr("similarity"),
        "type": attr("type") or attr("kind"),
        "metadata": _json_safe(metadata if isinstance(metadata, dict) else {}),
    }


def _hindsight_should_manage_local_daemon(cfg: Dict[str, Any]) -> bool:
    if cfg.get("mode") != "local_embedded":
        return False
    parsed = urllib.parse.urlparse(str(cfg.get("_api_url") or HINDSIGHT_DEFAULT_LOCAL_URL))
    return parsed.hostname in {"127.0.0.1", "localhost", "::1"}


def _hindsight_embed_candidates() -> List[Path]:
    candidates: List[Path] = []
    which = shutil.which("hindsight-embed")
    if which:
        candidates.append(Path(which))
    try:
        candidates.append(Path(sys.executable).with_name("hindsight-embed"))
    except Exception:
        pass
    candidates.extend([
        _hermes_home() / "hermes-agent" / "venv" / "bin" / "hindsight-embed",
        Path.home() / ".hermes" / "hermes-agent" / "venv" / "bin" / "hindsight-embed",
        Path.home() / ".local" / "bin" / "hindsight-embed",
    ])

    seen = set()
    unique: List[Path] = []
    for candidate in candidates:
        text = str(candidate)
        if text and text not in seen:
            unique.append(candidate)
            seen.add(text)
    return unique


def _resolve_hindsight_embed() -> tuple[Optional[str], Dict[str, Any]]:
    candidates = _hindsight_embed_candidates()
    checked = [str(path) for path in candidates]
    resolved = None
    for path in candidates:
        if path.exists() and os.access(path, os.X_OK):
            resolved = str(path)
            break
    diagnostics = {
        "PATH": os.environ.get("PATH", ""),
        "sys_executable": sys.executable,
        "checked_paths": checked,
        "resolved_path": resolved,
    }
    return resolved, diagnostics


def _ensure_hindsight_local_daemon(cfg: Dict[str, Any]) -> Optional[str]:
    """Best-effort start for local_embedded Hindsight before client calls."""
    if not _hindsight_should_manage_local_daemon(cfg):
        return None
    profile = str(cfg.get("profile") or "hermes")
    binary, diagnostics = _resolve_hindsight_embed()
    diagnostics.update({"profile": profile, "mode": cfg.get("mode")})
    if not binary:
        safe_diagnostics = _safe_error(json.dumps(diagnostics, sort_keys=True))
        return f"hindsight-embed command not found in dashboard environment; diagnostics={safe_diagnostics}"
    cmd = [binary, "-p", profile, "daemon", "start"]
    env = os.environ.copy()
    env.setdefault("HERMES_HOME", str(_hermes_home()))
    try:
        result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        safe_diagnostics = _safe_error(json.dumps(diagnostics, sort_keys=True))
        return f"hindsight-embed command not found in dashboard environment; diagnostics={safe_diagnostics}"
    except Exception as exc:
        return f"Could not start local Hindsight daemon: {_safe_error(exc)}"
    if result.returncode not in (0,):
        output = (result.stderr or result.stdout or "").strip()
        return _safe_error(output) or f"hindsight-embed daemon start exited with {result.returncode}"
    return None


def _run_coro_blocking(coro: Any) -> Any:
    """Run a coroutine from sync dashboard helper code, even inside FastAPI's event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: Dict[str, Any] = {}

    def runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # pragma: no cover - re-raised in caller thread
            result["error"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    if "error" in result:
        raise result["error"]
    return result.get("value")


def _hindsight_timeout_seconds(cfg: Dict[str, Any]) -> float:
    try:
        return float(cfg.get("timeout") or 120)
    except Exception:
        return 120.0


def _hindsight_connection_failed(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "connection refused" in text or "cannot connect" in text or "connect call failed" in text


def _hindsight_client_call(cfg: Dict[str, Any], fn: Callable[[Any], Any]) -> Any:
    """Call the official Hindsight client for read-only inspection operations."""

    async def invoke() -> Any:
        from hindsight_client import Hindsight  # type: ignore

        client = Hindsight(
            base_url=str(cfg.get("_api_url") or HINDSIGHT_DEFAULT_LOCAL_URL).rstrip("/"),
            api_key=cfg.get("_api_key") or None,
            timeout=_hindsight_timeout_seconds(cfg),
            user_agent=f"hermes-memory-ui-dashboard/{PLUGIN_VERSION}",
        )
        try:
            return await fn(client)
        finally:
            await client.aclose()

    try:
        return _run_coro_blocking(invoke())
    except Exception as exc:
        if _hindsight_connection_failed(exc):
            start_error = _ensure_hindsight_local_daemon(cfg)
            if start_error:
                raise RuntimeError(start_error) from exc
            return _run_coro_blocking(invoke())
        raise


def _normalize_hindsight_document(item: Any, index: int) -> Dict[str, Any]:
    data = item if isinstance(item, dict) else _object_to_dict(item)

    def attr(name: str, default: Any = None) -> Any:
        if isinstance(data, dict) and name in data:
            return data.get(name)
        value = getattr(item, name, default)
        return default if callable(value) else value

    text = attr("original_text") or attr("text") or attr("content") or ""
    doc_metadata = attr("document_metadata", {}) or attr("metadata", {}) or {}
    return {
        "id": attr("id") or attr("document_id") or str(index + 1),
        "text": str(text),
        "type": "document",
        "score": None,
        "metadata": {
            "source": "hindsight_client_documents",
            "memory_unit_count": attr("memory_unit_count"),
            "text_length": attr("text_length") or len(str(text)),
            "created_at": _json_safe(attr("created_at")),
            "updated_at": _json_safe(attr("updated_at")),
            "tags": attr("tags", []) or [],
            "retain_params": _json_safe(attr("retain_params")),
            "document_metadata": _json_safe(doc_metadata if isinstance(doc_metadata, dict) else {}),
        },
    }


def _hindsight_contents_payload(
    config: Optional[Dict[str, Any]] = None,
    *,
    limit: int = DEFAULT_HINDSIGHT_LIMIT,
    search: Optional[str] = None,
) -> Dict[str, Any]:
    """List visible Hindsight memory units and source documents via hindsight_client."""
    config = config if config is not None else _read_yaml(_hermes_home() / "config.yaml")
    cfg = _load_hindsight_config(config)
    try:
        limit = int(limit or DEFAULT_HINDSIGHT_LIMIT)
    except Exception:
        limit = DEFAULT_HINDSIGHT_LIMIT
    limit = max(1, min(limit, MAX_HINDSIGHT_LIMIT))
    search = search if isinstance(search, str) and search.strip() else None
    bank_id = str(cfg.get("bank_id") or "hermes")
    base = _hindsight_config_payload(config)
    base.update({
        "operation": "contents",
        "search": search or "",
        "limit": limit,
        "memories": [],
        "memory_count": 0,
        "total_memories": 0,
        "documents": [],
        "document_count": 0,
        "total_documents": 0,
        "stats": {},
    })
    try:
        async def fetch_contents(client: Any) -> Dict[str, Any]:
            stats_resp = await client.banks.get_agent_stats(
                bank_id=bank_id,
                _request_timeout=_hindsight_timeout_seconds(cfg),
            )
            memories_resp = await client.memory.list_memories(
                bank_id=bank_id,
                q=search,
                limit=limit,
                offset=0,
                _request_timeout=_hindsight_timeout_seconds(cfg),
            )
            docs_resp = await client.documents.list_documents(
                bank_id=bank_id,
                q=None,
                limit=max(limit, 100),
                offset=0,
                _request_timeout=_hindsight_timeout_seconds(cfg),
            )
            docs_items = list(getattr(docs_resp, "items", None) or [])
            detailed_docs: List[Dict[str, Any]] = []
            for item in docs_items[: max(limit, 100)]:
                doc_id = getattr(item, "id", None) or (_object_to_dict(item).get("id") if item is not None else None)
                doc_data = item
                if doc_id:
                    try:
                        doc_data = await client.documents.get_document(
                            bank_id=bank_id,
                            document_id=str(doc_id),
                            _request_timeout=_hindsight_timeout_seconds(cfg),
                        )
                    except Exception:
                        doc_data = item
                normalized = _normalize_hindsight_document(doc_data, len(detailed_docs))
                if search:
                    haystack = (normalized.get("text", "") + " " + normalized.get("id", "") + " " + json.dumps(normalized.get("metadata", {}))).casefold()
                    if search.casefold() not in haystack:
                        continue
                detailed_docs.append(normalized)
                if len(detailed_docs) >= limit:
                    break
            memories_items = list(getattr(memories_resp, "items", None) or [])
            return {
                "stats": _json_safe(_object_to_dict(stats_resp)),
                "memories": [_normalize_hindsight_result(item, index) for index, item in enumerate(memories_items[:limit])],
                "total_memories": getattr(memories_resp, "total", len(memories_items)) or len(memories_items),
                "documents": detailed_docs,
                "total_documents": getattr(docs_resp, "total", len(docs_items)) or len(docs_items),
            }

        content = _hindsight_client_call(cfg, fetch_contents)
        base["stats"] = content.get("stats", {})
        base["memories"] = content.get("memories", [])
        base["memory_count"] = len(base["memories"])
        base["total_memories"] = content.get("total_memories", base["memory_count"])
        base["documents"] = content.get("documents", [])
        base["document_count"] = len(base["documents"])
        base["total_documents"] = content.get("total_documents", base["document_count"])
    except Exception as exc:
        base["error"] = _safe_error(exc)
    return base


def _make_hindsight_provider() -> Any:
    from plugins.memory.hindsight import HindsightMemoryProvider  # type: ignore

    provider = HindsightMemoryProvider()
    provider.initialize(session_id="dashboard", hermes_home=str(_hermes_home()), platform="dashboard")
    return provider


def _hindsight_config_payload(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = _load_hindsight_config(config)
    public = {k: v for k, v in cfg.items() if not k.startswith("_")}
    public.update({
        "id": "hindsight",
        "label": "Hindsight memory",
        "mode_label": "query-only",
        "generated_at": time.time(),
        "error": None,
    })
    return public


def _hindsight_payload(
    config: Optional[Dict[str, Any]] = None,
    *,
    query: Optional[str] = None,
    limit: int = DEFAULT_HINDSIGHT_LIMIT,
    mode: str = "status",
) -> Dict[str, Any]:
    config = config if config is not None else _read_yaml(_hermes_home() / "config.yaml")
    query = query if isinstance(query, str) and query.strip() else None
    try:
        limit = int(limit or DEFAULT_HINDSIGHT_LIMIT)
    except Exception:
        limit = DEFAULT_HINDSIGHT_LIMIT
    limit = max(1, min(limit, MAX_HINDSIGHT_LIMIT))
    base = _hindsight_config_payload(config)
    base.update({
        "operation": mode,
        "query": query or "",
        "limit": limit,
        "results": [],
        "result_count": 0,
        "reflection": "",
    })
    if mode == "status":
        return base
    if mode not in {"recall", "reflect"}:
        base["error"] = f"Unsupported Hindsight operation: {mode}"
        return base
    if not query:
        base["error"] = "Query is required for Hindsight recall/reflect."
        return base
    provider = None
    try:
        provider = _make_hindsight_provider()
        if mode == "reflect":
            response = provider._run_hindsight_operation(
                lambda client: client.areflect(bank_id=provider._bank_id, query=query, budget=provider._budget)
            )
            base["reflection_source"] = "hindsight_reflect"
            base["reflection"] = str(getattr(response, "text", "") or "")
            return base
        recall_kwargs: Dict[str, Any] = {
            "bank_id": provider._bank_id,
            "query": query,
            "budget": provider._budget,
            "max_tokens": provider._recall_max_tokens,
        }
        if getattr(provider, "_recall_tags", None):
            recall_kwargs["tags"] = provider._recall_tags
            recall_kwargs["tags_match"] = provider._recall_tags_match
        if getattr(provider, "_recall_types", None):
            recall_kwargs["types"] = provider._recall_types
        response = provider._run_hindsight_operation(lambda client: client.arecall(**recall_kwargs))
        raw_results = list(getattr(response, "results", None) or [])[:limit]
        base["results"] = [_normalize_hindsight_result(item, index) for index, item in enumerate(raw_results)]
        base["result_source"] = "hindsight_recall"
        base["result_count"] = len(base["results"])
    except Exception as exc:
        base["error"] = _safe_error(exc)
    finally:
        shutdown = getattr(provider, "shutdown", None) if provider is not None else None
        if callable(shutdown):
            try:
                import contextlib
                import io
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    shutdown()
            except Exception:
                pass
    return base


def _load_byterover_config(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Load non-secret ByteRover CLI configuration for read-only dashboard access."""
    config = config if config is not None else _read_yaml(_hermes_home() / "config.yaml")
    home = _hermes_home()
    config_path = home / "byterover.json"
    file_cfg = _read_json(config_path)
    plugin_cfg = _dig(config, "plugins", "hermes-memory-ui", "byterover", default={})
    if not isinstance(plugin_cfg, dict):
        plugin_cfg = {}

    def pick(key: str, env_key: str, default: Any = "") -> Any:
        value = os.environ.get(env_key, default)
        if key in plugin_cfg and plugin_cfg.get(key) not in (None, ""):
            value = plugin_cfg.get(key)
        if key in file_cfg and file_cfg.get(key) not in (None, ""):
            value = file_cfg.get(key)
        return value

    brv_path = str(pick("brv_path", "BRV_PATH", "brv"))
    if os.path.basename(brv_path) == brv_path:
        resolved_brv = shutil.which(brv_path)
    else:
        expanded_brv = _expand_path(brv_path, home)
        resolved_brv = str(expanded_brv) if expanded_brv and expanded_brv.exists() else None
    project_root = str(pick("project_root", "BYTEROVER_PROJECT_ROOT", "") or "")
    if project_root:
        expanded = _expand_path(project_root, home)
        project_root = str(expanded) if expanded else project_root
    search_scope = str(pick("search_scope", "BYTEROVER_SEARCH_SCOPE", "") or "")
    try:
        query_timeout = int(pick("query_timeout", "BYTEROVER_QUERY_TIMEOUT", DEFAULT_BYTEROVER_QUERY_TIMEOUT))
    except Exception:
        query_timeout = DEFAULT_BYTEROVER_QUERY_TIMEOUT
    return {
        "config_path": str(config_path),
        "config_exists": config_path.exists(),
        "brv_path": brv_path,
        "resolved_brv_path": resolved_brv or "",
        "brv_available": bool(resolved_brv),
        "project_root": project_root,
        "project_exists": bool(project_root and Path(project_root).exists()),
        "search_scope": search_scope,
        "query_timeout": max(1, min(query_timeout, 300)),
    }


def _parse_byterover_json_output(raw: str) -> Any:
    """Parse ByteRover JSON output, accepting both single JSON and JSON-lines events."""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        pass

    events: List[Any] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except Exception:
            return {"raw": raw}
    if not events:
        return {"raw": raw}

    completed = None
    for event in events:
        if not isinstance(event, dict):
            continue
        marker = str(event.get("event") or event.get("status") or "").lower()
        if marker == "completed":
            completed = event
    if isinstance(completed, dict):
        data = completed.get("data") if isinstance(completed.get("data"), dict) else completed
        return {"success": True, "data": data, "events": events}
    return {"success": True, "data": events[-1] if isinstance(events[-1], dict) else {"events": events}, "events": events}


def _run_byterover_command(cfg: Dict[str, Any], args: List[str], *, timeout: int = 30) -> Dict[str, Any]:
    brv = cfg.get("resolved_brv_path") or cfg.get("brv_path") or "brv"
    if not cfg.get("brv_available"):
        return {"ok": False, "error": "brv command not found. Install ByteRover CLI or set BRV_PATH.", "data": None}
    cwd = cfg.get("project_root") or "/tmp"
    try:
        result = subprocess.run(
            [str(brv), *args],
            cwd=cwd if Path(cwd).exists() else "/tmp",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except Exception as exc:
        return {"ok": False, "error": _safe_error(exc), "data": None}

    raw = (result.stdout or result.stderr or "").strip()
    parsed: Any = _parse_byterover_json_output(raw) if raw else None
    if result.returncode != 0:
        return {"ok": False, "error": _safe_error(raw or f"brv exited with {result.returncode}"), "data": parsed}
    if isinstance(parsed, dict) and parsed.get("success") is False:
        err = _dig(parsed, "data", "error", default=None) or parsed.get("error") or raw
        return {"ok": False, "error": _safe_error(err), "data": parsed}
    return {"ok": True, "error": None, "data": parsed}


def _unwrap_byterover_data(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload if isinstance(payload, dict) else {}


def _compact_byterover_excerpt(text: str, query: Optional[str], *, radius: int = 180) -> str:
    """Return a short search snippet around the first query keyword hit."""
    text = re.sub(r"\n{3,}", "\n\n", str(text or "")).strip()
    if not text:
        return ""
    terms = []
    if query:
        terms = [term for term in re.findall(r"[\w-]{3,}", query, flags=re.UNICODE) if term.lower() not in {"what", "which", "where", "when", "does", "with", "from", "about", "project"}]
    lowered = text.lower()
    facts_match = re.search(r"## Facts\s*(.*?)(?:\n## |\n---\n|\Z)", text, flags=re.IGNORECASE | re.DOTALL)
    if facts_match and terms:
        matching_facts = []
        for line in facts_match.group(1).splitlines():
            stripped = line.strip()
            if (
                stripped.startswith("- ")
                and any(term.lower() in stripped.lower() for term in terms)
                and "preferred search" not in stripped.lower()
            ):
                matching_facts.append(stripped[2:].strip().rstrip(".") + ".")
        if matching_facts:
            return " ".join(matching_facts[:3])

    hit = -1
    for term in sorted(terms, key=len, reverse=True):
        hit = lowered.find(term.lower())
        if hit >= 0:
            break
    if hit < 0:
        if len(text) <= radius * 2:
            return text
        return text[: radius * 2].rstrip() + "…"

    start = max(0, hit - radius)
    end = min(len(text), hit + radius)
    # Prefer line/sentence boundaries when close enough, so snippets don't start mid-word.
    boundary_start = max(text.rfind("\n", 0, start + 1), text.rfind(". ", 0, start + 1))
    if boundary_start >= 0 and hit - boundary_start <= radius + 80:
        start = boundary_start + (2 if text[boundary_start:boundary_start + 2] == ". " else 1)
    boundary_end_candidates = [pos for pos in (text.find("\n", end), text.find(". ", end)) if pos >= 0]
    if boundary_end_candidates:
        boundary_end = min(boundary_end_candidates)
        if boundary_end - hit <= radius + 120:
            end = boundary_end + (1 if text[boundary_end:boundary_end + 2] == ". " else 0)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet.rstrip() + "…"
    return snippet


def _normalize_byterover_result(item: Any, index: int, query: Optional[str] = None, project_root: Optional[str] = None) -> Dict[str, Any]:
    if not isinstance(item, dict):
        return {"id": str(index + 1), "path": "", "score": None, "excerpt": _compact_byterover_excerpt(str(item), query), "raw_excerpt": str(item), "metadata": {}}
    text = item.get("excerpt") or item.get("snippet") or item.get("content") or item.get("text") or item.get("summary") or ""
    path = item.get("path") or item.get("file") or item.get("source") or ""
    raw_text = str(text)
    full_text = ""
    if project_root and path:
        try:
            candidate = Path(project_root) / ".brv" / "context-tree" / str(path)
            resolved = candidate.resolve()
            root = (Path(project_root) / ".brv" / "context-tree").resolve()
            if resolved.exists() and resolved.is_file():
                try:
                    resolved.relative_to(root)
                except ValueError:
                    full_text = ""
                else:
                    full_text = resolved.read_text(encoding="utf-8", errors="replace")
        except Exception:
            full_text = ""
    compact = _compact_byterover_excerpt(full_text or raw_text, query)
    return {
        "id": str(item.get("id") or path or index + 1),
        "path": path,
        "title": item.get("title") or item.get("name") or "",
        "score": item.get("score") or item.get("rank") or item.get("similarity"),
        "excerpt": compact,
        "raw_excerpt": raw_text if raw_text != compact else "",
        "metadata": _json_safe({k: v for k, v in item.items() if k not in {"id", "path", "file", "source", "title", "name", "score", "rank", "similarity", "excerpt", "snippet", "content", "text", "summary"}}),
    }


def _compact_byterover_answer(query: str, answer: str) -> str:
    """Derive a short display answer from ByteRover's often-verbose query output."""
    if not answer:
        return ""
    query_l = query.lower()

    facts_match = re.search(r"## Facts\s*(.*?)(?:\n## |\n---\n|\Z)", answer, flags=re.IGNORECASE | re.DOTALL)
    facts: List[str] = []
    if facts_match:
        for line in facts_match.group(1).splitlines():
            stripped = line.strip()
            if stripped.startswith("- "):
                facts.append(stripped[2:].strip())

    if facts:
        if "codename" in query_l:
            codename_fact = next((fact for fact in facts if "codename" in fact.lower()), "")
            if codename_fact:
                codename_match = re.search(r"codename\s+is\s+([^.;`]+)", codename_fact, flags=re.IGNORECASE)
                codename = codename_match.group(1).strip() if codename_match else ""
                if codename and codename.lower() not in query_l:
                    return f"No. The project codename is {codename}."
                return codename_fact.rstrip(".") + "."
        if "owner" in query_l or "owns" in query_l or "who" in query_l:
            owner_fact = next((fact for fact in facts if "owner" in fact.lower()), "")
            if owner_fact:
                return owner_fact.rstrip(".") + "."
        if "retention" in query_l or "expire" in query_l or "sync" in query_l:
            retention = [
                fact.rstrip(".") + "."
                for fact in facts
                if any(term in fact.lower() for term in ("retention", "expire", "sync"))
                and "preferred search" not in fact.lower()
            ]
            if retention:
                return " ".join(retention[:3])

        query_terms = {term for term in re.findall(r"[a-z0-9][a-z0-9_-]{2,}", query_l) if term not in {"what", "which", "where", "when", "does", "with", "from", "about", "project"}}
        ranked = []
        for fact in facts:
            fact_l = fact.lower()
            score = sum(1 for term in query_terms if term in fact_l)
            if score:
                ranked.append((score, fact))
        if ranked:
            ranked.sort(key=lambda item: item[0], reverse=True)
            return " ".join(fact.rstrip(".") + "." for _score, fact in ranked[:2])
        return facts[0].rstrip(".") + "."

    summary_match = re.search(r"\*\*Summary\*\*:\s*(.*?)(?:\n\n|\Z)", answer, flags=re.IGNORECASE | re.DOTALL)
    if summary_match:
        return summary_match.group(1).strip()
    return answer.strip().splitlines()[0][:500]


def _byterover_payload(
    config: Optional[Dict[str, Any]] = None,
    *,
    limit: int = DEFAULT_BYTEROVER_LIMIT,
    search: Optional[str] = None,
) -> Dict[str, Any]:
    config = config if config is not None else _read_yaml(_hermes_home() / "config.yaml")
    provider = _dig(config, "memory", "provider", default=None)
    cfg = _load_byterover_config(config)
    search = search if isinstance(search, str) and search.strip() else None
    try:
        limit = int(limit or DEFAULT_BYTEROVER_LIMIT)
    except Exception:
        limit = DEFAULT_BYTEROVER_LIMIT
    limit = max(1, min(limit, MAX_BYTEROVER_LIMIT))

    base: Dict[str, Any] = {
        "id": "byterover",
        "label": "ByteRover memory",
        "provider_configured": provider == "byterover",
        "mode": "read-only",
        "config_path": cfg["config_path"],
        "config_exists": cfg["config_exists"],
        "brv_available": cfg["brv_available"],
        "brv_path": cfg["resolved_brv_path"] or cfg["brv_path"],
        "project_root": cfg["project_root"],
        "project_exists": cfg["project_exists"],
        "search_scope": cfg["search_scope"],
        "locations": [],
        "location_count": 0,
        "status": {},
        "results": [],
        "result_count": 0,
        "total_found": 0,
        "search": search or "",
        "limit": limit,
        "error": None,
        "generated_at": time.time(),
    }

    if not cfg["brv_available"]:
        base["error"] = "brv command not found. Install ByteRover CLI or set BRV_PATH."
        return base

    locations = _run_byterover_command(cfg, ["locations", "--format", "json"], timeout=20)
    if locations["ok"]:
        data = _unwrap_byterover_data(locations["data"])
        locs = data.get("locations", []) if isinstance(data, dict) else []
        base["locations"] = [_json_safe(item) for item in (locs if isinstance(locs, list) else [])]
        base["location_count"] = len(base["locations"])
    elif locations["error"]:
        base["error"] = locations["error"]

    status_args = ["status", "--format", "json"]
    if cfg.get("project_root"):
        status = _run_byterover_command(cfg, status_args, timeout=20)
        if status["ok"]:
            base["status"] = _json_safe(_unwrap_byterover_data(status["data"]))
        elif status["error"] and not base["error"]:
            base["error"] = status["error"]
    elif search:
        base["error"] = "ByteRover project_root is not configured. Set project_root in $HERMES_HOME/byterover.json or BYTEROVER_PROJECT_ROOT before running search."

    if search and cfg.get("project_root"):
        search_args = ["search", search, "--format", "json", "--limit", str(limit)]
        if cfg.get("search_scope"):
            search_args.extend(["--scope", str(cfg["search_scope"])])
        found = _run_byterover_command(cfg, search_args, timeout=30)
        if found["ok"]:
            data = _unwrap_byterover_data(found["data"])
            results = data.get("results", []) if isinstance(data, dict) else []
            results = results if isinstance(results, list) else []
            base["results"] = [_normalize_byterover_result(item, index, search, cfg.get("project_root")) for index, item in enumerate(results[:limit])]
            base["result_count"] = len(base["results"])
            base["total_found"] = data.get("totalFound", base["result_count"]) if isinstance(data, dict) else base["result_count"]
        elif found["error"]:
            base["error"] = found["error"]

    return base


def _byterover_query_payload(
    query: str,
    config: Optional[Dict[str, Any]] = None,
    *,
    timeout: Optional[int] = None,
) -> Dict[str, Any]:
    config = config if config is not None else _read_yaml(_hermes_home() / "config.yaml")
    cfg = _load_byterover_config(config)
    base = _byterover_payload(config, limit=DEFAULT_BYTEROVER_LIMIT, search=None)
    base.update({"operation": "query", "query": query, "answer": "", "answer_summary": "", "matched_docs": [], "task_id": None})
    if not query.strip():
        base["error"] = "Query is required."
        return base
    if not cfg.get("project_root"):
        base["error"] = "ByteRover project_root is not configured. Set project_root in $HERMES_HOME/byterover.json or BYTEROVER_PROJECT_ROOT before running query."
        return base
    command_timeout = int(timeout or cfg.get("query_timeout") or DEFAULT_BYTEROVER_QUERY_TIMEOUT)
    result = _run_byterover_command(
        cfg,
        ["query", query, "--format", "json"],
        timeout=command_timeout + 5,
    )
    if not result["ok"]:
        base["error"] = result["error"]
        return base
    data = _unwrap_byterover_data(result["data"])
    base["answer"] = str(data.get("result") or data.get("answer") or "") if isinstance(data, dict) else ""
    base["answer_summary"] = _compact_byterover_answer(query, base["answer"])
    base["matched_docs"] = _json_safe(data.get("matchedDocs", [])) if isinstance(data, dict) else []
    base["task_id"] = data.get("taskId") if isinstance(data, dict) else None
    base["top_score"] = data.get("topScore") if isinstance(data, dict) else None
    return base


@router.get("/status")
async def status() -> Dict[str, Any]:
    home = _hermes_home()
    config = _read_yaml(home / "config.yaml")
    db_path = _resolve_holographic_db(config)
    mem0_cfg = _load_mem0_config(config)
    honcho_cfg = _honcho_config_payload(config)
    mnemosyne_cfg = _load_mnemosyne_config(config)
    hindsight_cfg = _load_hindsight_config(config)
    byterover_cfg = _load_byterover_config(config)
    return {
        "plugin": "hermes-memory-ui",
        "version": PLUGIN_VERSION,
        "mode": "read-only",
        "hermes_home": str(home),
        "config_path": str(home / "config.yaml"),
        "memory_provider": _dig(config, "memory", "provider", default=None),
        "builtin": {
            "memory_path": str(home / "memories" / "MEMORY.md"),
            "memory_exists": (home / "memories" / "MEMORY.md").exists(),
            "user_path": str(home / "memories" / "USER.md"),
            "user_exists": (home / "memories" / "USER.md").exists(),
        },
        "holographic": {
            "db_path": str(db_path),
            "db_exists": db_path.exists(),
            "provider_configured": _dig(config, "memory", "provider", default=None) == "holographic",
        },
        "mem0": {
            "config_path": mem0_cfg["config_path"],
            "config_exists": mem0_cfg["config_exists"],
            "api_key_present": mem0_cfg["api_key_present"],
            "user_id": mem0_cfg["user_id"],
            "agent_id": mem0_cfg["agent_id"],
            "provider_configured": _dig(config, "memory", "provider", default=None) == "mem0",
        },
        "honcho": {
            "config_path": honcho_cfg["config_path"],
            "config_exists": honcho_cfg["config_exists"],
            "api_key_present": honcho_cfg["api_key_present"],
            "base_url_present": honcho_cfg["base_url_present"],
            "enabled": honcho_cfg["enabled"],
            "host": honcho_cfg["host"],
            "workspace": honcho_cfg["workspace"],
            "user_peer": honcho_cfg["user_peer"],
            "ai_peer": honcho_cfg["ai_peer"],
            "recall_mode": honcho_cfg["recall_mode"],
            "session_strategy": honcho_cfg["session_strategy"],
            "provider_configured": _dig(config, "memory", "provider", default=None) == "honcho",
        },
        "mnemosyne": {
            "config_path": mnemosyne_cfg["config_path"],
            "data_dir": mnemosyne_cfg["data_dir"],
            "db_path": mnemosyne_cfg["db_path"],
            "db_exists": mnemosyne_cfg["db_exists"],
            "prefetch_content_chars": mnemosyne_cfg["prefetch_content_chars"],
            "auto_sleep_enabled": mnemosyne_cfg["auto_sleep_enabled"],
            "provider_configured": mnemosyne_cfg["provider_configured"],
        },
        "byterover": {
            "config_path": byterover_cfg["config_path"],
            "config_exists": byterover_cfg["config_exists"],
            "brv_available": byterover_cfg["brv_available"],
            "brv_path": byterover_cfg["resolved_brv_path"] or byterover_cfg["brv_path"],
            "project_root": byterover_cfg["project_root"],
            "project_exists": byterover_cfg["project_exists"],
            "search_scope": byterover_cfg["search_scope"],
            "provider_configured": _dig(config, "memory", "provider", default=None) == "byterover",
        },
        "hindsight": {
            "config_path": hindsight_cfg["config_path"],
            "config_exists": hindsight_cfg["config_exists"],
            "mode": hindsight_cfg["mode"],
            "api_url": hindsight_cfg["api_url"],
            "api_key_present": hindsight_cfg["api_key_present"],
            "llm_key_present": hindsight_cfg["llm_key_present"],
            "llm_provider": hindsight_cfg["llm_provider"],
            "llm_model": hindsight_cfg["llm_model"],
            "bank_id": hindsight_cfg["bank_id"],
            "bank_id_template": hindsight_cfg["bank_id_template"],
            "recall_budget": hindsight_cfg["recall_budget"],
            "memory_mode": hindsight_cfg["memory_mode"],
            "auto_retain": hindsight_cfg["auto_retain"],
            "auto_recall": hindsight_cfg["auto_recall"],
            "provider_configured": hindsight_cfg["provider_configured"],
        },
        "generated_at": time.time(),
    }


@router.get("/builtin")
async def builtin() -> Dict[str, Any]:
    return _builtin_payload()


@router.get("/holographic")
async def holographic(
    limit: int = Query(DEFAULT_FACT_LIMIT, ge=1, le=MAX_FACT_LIMIT),
    category: Optional[str] = Query(None),
    min_trust: float = Query(0.0, ge=0.0, le=1.0),
    search: Optional[str] = Query(None),
) -> Dict[str, Any]:
    return _holographic_payload(limit=limit, category=category or None, min_trust=min_trust, search=search or None)


@router.get("/mem0")
async def mem0(
    limit: int = Query(DEFAULT_MEM0_LIMIT, ge=1, le=MAX_MEM0_LIMIT),
    search: Optional[str] = Query(None),
) -> Dict[str, Any]:
    return _mem0_payload(limit=limit, search=search or None)


@router.get("/honcho")
async def honcho(
    limit: int = Query(DEFAULT_HONCHO_LIMIT, ge=1, le=MAX_HONCHO_LIMIT),
    search: Optional[str] = Query(None),
) -> Dict[str, Any]:
    return _honcho_payload(limit=limit, search=search or None)


@router.get("/byterover")
async def byterover(
    limit: int = Query(DEFAULT_BYTEROVER_LIMIT, ge=1, le=MAX_BYTEROVER_LIMIT),
    search: Optional[str] = Query(None),
) -> Dict[str, Any]:
    return _byterover_payload(limit=limit, search=search or None)


@router.get("/byterover/query")
async def byterover_query(
    query: str = Query(...),
    timeout: int = Query(DEFAULT_BYTEROVER_QUERY_TIMEOUT, ge=1, le=300),
) -> Dict[str, Any]:
    return _byterover_query_payload(query=query, timeout=timeout)


@router.get("/hindsight")
async def hindsight() -> Dict[str, Any]:
    return _hindsight_payload(mode="status")


@router.get("/hindsight/contents")
async def hindsight_contents(
    limit: int = Query(DEFAULT_HINDSIGHT_LIMIT, ge=1, le=MAX_HINDSIGHT_LIMIT),
    search: Optional[str] = Query(None),
) -> Dict[str, Any]:
    return _hindsight_contents_payload(limit=limit, search=search or None)


@router.get("/hindsight/recall")
async def hindsight_recall(
    query: str = Query(...),
    limit: int = Query(DEFAULT_HINDSIGHT_LIMIT, ge=1, le=MAX_HINDSIGHT_LIMIT),
) -> Dict[str, Any]:
    return _hindsight_payload(query=query, limit=limit, mode="recall")


@router.get("/hindsight/reflect")
async def hindsight_reflect(
    query: str = Query(...),
) -> Dict[str, Any]:
    return _hindsight_payload(query=query, limit=1, mode="reflect")


@router.get("/mnemosyne")
async def mnemosyne() -> Dict[str, Any]:
    return _mnemosyne_contents_payload()


@router.get("/mnemosyne/contents")
async def mnemosyne_contents(
    limit: int = Query(DEFAULT_MNEMOSYNE_LIMIT, ge=1, le=MAX_MNEMOSYNE_LIMIT),
    search: Optional[str] = Query(None),
) -> Dict[str, Any]:
    return _mnemosyne_contents_payload(limit=limit, search=search or None)


@router.get("/mnemosyne/recall")
async def mnemosyne_recall(
    query: str = Query(...),
    limit: int = Query(DEFAULT_MNEMOSYNE_LIMIT, ge=1, le=MAX_MNEMOSYNE_LIMIT),
    temporal_weight: float = Query(0.2, ge=0.0, le=1.0),
) -> Dict[str, Any]:
    return _mnemosyne_payload(query=query, limit=limit, temporal_weight=temporal_weight, mode="recall")


@router.get("/mnemosyne/prefetch")
async def mnemosyne_prefetch(
    query: str = Query(...),
) -> Dict[str, Any]:
    return _mnemosyne_payload(query=query, mode="prefetch")


@router.get("/snapshot")
async def snapshot(
    limit: int = Query(DEFAULT_FACT_LIMIT, ge=1, le=MAX_FACT_LIMIT),
    category: Optional[str] = Query(None),
    min_trust: float = Query(0.0, ge=0.0, le=1.0),
    search: Optional[str] = Query(None),
) -> Dict[str, Any]:
    config = _read_yaml(_hermes_home() / "config.yaml")
    return {
        "plugin": "hermes-memory-ui",
        "version": PLUGIN_VERSION,
        "mode": "read-only",
        "builtin": _builtin_payload(config),
        "holographic": _holographic_payload(
            config,
            limit=limit,
            category=category or None,
            min_trust=min_trust,
            search=search or None,
        ),
        "mem0": _mem0_payload(config, limit=limit, search=search or None),
        "honcho": _honcho_payload(config, limit=limit, search=search or None),
        "mnemosyne": _mnemosyne_contents_payload(config, limit=limit, search=search or None),
        "byterover": _byterover_payload(config, limit=limit, search=search or None),
        "hindsight": _hindsight_payload(config, mode="status"),
        "generated_at": time.time(),
    }
