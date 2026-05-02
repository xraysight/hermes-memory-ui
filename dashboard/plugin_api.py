"""Hermes Memory UI dashboard plugin backend.

Mounted by Hermes dashboard at /api/plugins/hermes-memory-ui/.

MVP scope: read-only inspection of:
- built-in memory files: $HERMES_HOME/memories/MEMORY.md and USER.md
- holographic memory SQLite fact store: $HERMES_HOME/memory_store.db by default

No mutation endpoints are exposed intentionally. Memory writes should go through
Hermes' memory/fact_store tools or provider classes so validation, locking,
FTS/HRR maintenance, and mirroring semantics are preserved.
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
    limit = max(1, min(int(limit or DEFAULT_FACT_LIMIT), MAX_FACT_LIMIT))

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
    limit = max(1, min(int(limit or DEFAULT_MEM0_LIMIT), MAX_MEM0_LIMIT))

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


@router.get("/status")
async def status() -> Dict[str, Any]:
    home = _hermes_home()
    config = _read_yaml(home / "config.yaml")
    db_path = _resolve_holographic_db(config)
    mem0_cfg = _load_mem0_config(config)
    return {
        "plugin": "hermes-memory-ui",
        "version": "0.2.0",
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
        "version": "0.2.0",
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
        "generated_at": time.time(),
    }
