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


@router.get("/status")
async def status() -> Dict[str, Any]:
    home = _hermes_home()
    config = _read_yaml(home / "config.yaml")
    db_path = _resolve_holographic_db(config)
    return {
        "plugin": "hermes-memory-ui",
        "version": "0.1.0",
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
        "version": "0.1.0",
        "mode": "read-only",
        "builtin": _builtin_payload(config),
        "holographic": _holographic_payload(
            config,
            limit=limit,
            category=category or None,
            min_trust=min_trust,
            search=search or None,
        ),
        "generated_at": time.time(),
    }
