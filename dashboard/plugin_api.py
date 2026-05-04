"""Hermes Memory UI dashboard plugin backend.

Mounted by Hermes dashboard at /api/plugins/hermes-memory-ui/.

Read-only inspection covers built-in memory files, holographic memory,
Mem0, and Honcho provider state. No mutation endpoints are exposed
intentionally. Memory writes should go through Hermes' memory/fact_store
tools or provider classes so validation, locking, FTS/HRR maintenance,
and provider-specific semantics are preserved.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from fastapi import APIRouter, Query
except Exception:  # Allows local syntax/import tests outside the dashboard.
    class APIRouter:  # type: ignore
        def get(self, *_args, **_kwargs):
            return lambda fn: fn

    def Query(default=None, **_kwargs):  # type: ignore
        return default

router = APIRouter()

ENTRY_DELIMITER = "\n§\n"
DEFAULT_MEMORY_LIMIT = 2200
DEFAULT_USER_LIMIT = 1375
DEFAULT_FACT_LIMIT = 500
MAX_FACT_LIMIT = 2000
DEFAULT_MEM0_LIMIT = 500
MAX_MEM0_LIMIT = 2000
DEFAULT_HONCHO_LIMIT = 50
MAX_HONCHO_LIMIT = 100


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
            "error": str(exc),
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
        base["error"] = str(exc)

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
        base["error"] = str(exc)

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
        base["_import_error"] = str(exc)
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


def _list_honcho_conclusions(observer_peer: Any, target_peer_id: str, limit: int) -> List[Dict[str, Any]]:
    try:
        scope = observer_peer.conclusions_of(target_peer_id)
        try:
            items = scope.list(page=1, size=limit, reverse=True)
        except TypeError:
            items = scope.list(page=1, size=limit)
        if not isinstance(items, list):
            items = list(items or [])
        return [_normalize_honcho_conclusion(item, index) for index, item in enumerate(items[:limit])]
    except Exception:
        return []


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
        "user": {"peer_id": honcho_cfg["user_peer"], "card": [], "representation": "", "conclusions": []},
        "ai": {"peer_id": honcho_cfg["ai_peer"], "card": [], "representation": "", "conclusions": []},
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
        base["user"]["conclusions"] = _list_honcho_conclusions(ai_peer_obj, user_peer_id, limit)
        base["ai"]["conclusions"] = _list_honcho_conclusions(ai_peer_obj, ai_peer_id, limit)
        base["search_results"] = _honcho_search_results(base, search, limit)
        base["search_result_count"] = len(base["search_results"])
    except Exception as exc:
        base["error"] = str(exc)
    return base


@router.get("/status")
async def status() -> Dict[str, Any]:
    home = _hermes_home()
    config = _read_yaml(home / "config.yaml")
    db_path = _resolve_holographic_db(config)
    mem0_cfg = _load_mem0_config(config)
    honcho_cfg = _honcho_config_payload(config)
    return {
        "plugin": "hermes-memory-ui",
        "version": "0.3.0",
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
        "version": "0.3.0",
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
        "generated_at": time.time(),
    }
