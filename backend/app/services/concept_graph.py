"""DB-backed concept graph loader with safe in-memory fallback.

Reads ``skill_aliases`` and ``skill_adjacency`` rows (added by migration
``u8v9w0x1y2z3_concept_graph_and_match_feedback``) and merges them on top
of the curated defaults from
``backend.app.services.role_match_scoring``.

Behaviour contract — important for safe deploys:

* If the tables don't exist (e.g. migration not yet applied on Render),
  the loader silently returns the in-code defaults.  The application
  must not crash.
* If the tables exist but are empty, same thing — pure defaults.
* If the tables have rows, DB rows take precedence over hard-coded
  defaults for the same key.

A small TTL cache keeps lookups O(1) without hitting the DB on every
request.  ``invalidate()`` lets admin endpoints (future work) bust the
cache after a manual edit.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Mapping, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.app.services.role_match_scoring import (
    SKILL_ADJACENCY as DEFAULT_ADJACENCY,
    SKILL_ALIASES as DEFAULT_ALIASES,
    normalize_skill_label,
)

_log = logging.getLogger(__name__)

# 5 minute TTL.  Concept graph changes are rare enough that this won't
# meaningfully delay edits but is short enough to recover if an admin
# bulk-imports new rows without restarting the API.
_CACHE_TTL_SECONDS = 300

_lock = threading.Lock()
_cache: Dict[str, Any] = {
    "aliases": None,
    "adjacency": None,
    "loaded_at": 0.0,
}


def _table_exists(engine: Engine, table_name: str) -> bool:
    # Broad except is intentional: this is a startup-time best-effort
    # probe.  Any failure (DB down, no permissions, missing engine, …)
    # means "fall back to defaults", never "crash the request".
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_name = :t LIMIT 1"
                ),
                {"t": table_name},
            ).first()
        return row is not None
    except Exception as exc:
        _log.warning("concept_graph: existence check for %s failed: %s", table_name, exc)
        return False


def _load_aliases_from_db(engine: Engine) -> Dict[str, str]:
    """Returns {normalized_label: canonical}.  DB rows override defaults."""
    if not _table_exists(engine, "skill_aliases"):
        return dict(DEFAULT_ALIASES)
    merged: Dict[str, str] = dict(DEFAULT_ALIASES)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT label, canonical FROM skill_aliases")
            ).mappings().all()
        for r in rows:
            label = normalize_skill_label(r.get("label"))
            canonical = normalize_skill_label(r.get("canonical"))
            if label and canonical:
                merged[label] = canonical
    except Exception as exc:
        _log.warning("concept_graph: skill_aliases query failed (%s); using defaults", exc)
        return dict(DEFAULT_ALIASES)
    return merged


def _load_adjacency_from_db(engine: Engine) -> Dict[str, List[Dict[str, Any]]]:
    """Returns {from_canonical: [{"to": ..., "weight": ...}, ...]}.

    DB rows override default edges with the same (from, to) pair; new
    edges are appended.
    """
    if not _table_exists(engine, "skill_adjacency"):
        return {k: [dict(e) for e in v] for k, v in DEFAULT_ADJACENCY.items()}

    merged: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for src, edges in DEFAULT_ADJACENCY.items():
        merged[src] = {e["to"]: dict(e) for e in edges}

    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT from_concept, to_concept, weight "
                    "FROM skill_adjacency"
                )
            ).mappings().all()
        for r in rows:
            src = normalize_skill_label(r.get("from_concept"))
            dst = normalize_skill_label(r.get("to_concept"))
            try:
                w = float(r.get("weight"))
            except (TypeError, ValueError):
                continue
            if not src or not dst or not (0 < w <= 1):
                continue
            merged.setdefault(src, {})[dst] = {"to": dst, "weight": w}
    except Exception as exc:
        _log.warning("concept_graph: skill_adjacency query failed (%s); using defaults", exc)
        return {k: [dict(e) for e in v] for k, v in DEFAULT_ADJACENCY.items()}

    return {src: list(edges.values()) for src, edges in merged.items()}


def load(engine: Engine, *, force: bool = False) -> None:
    """Populate the cache from the DB if expired or forced."""
    now = time.time()
    with _lock:
        if not force and _cache["aliases"] is not None:
            if now - _cache["loaded_at"] < _CACHE_TTL_SECONDS:
                return
        _cache["aliases"] = _load_aliases_from_db(engine)
        _cache["adjacency"] = _load_adjacency_from_db(engine)
        _cache["loaded_at"] = now


def invalidate() -> None:
    with _lock:
        _cache["aliases"] = None
        _cache["adjacency"] = None
        _cache["loaded_at"] = 0.0


def get_aliases(engine: Optional[Engine] = None) -> Mapping[str, str]:
    """Return current alias map.  Loads from DB on first call when an
    engine is supplied; otherwise returns the in-code defaults.

    Pure callers (unit tests, the scorer's pure functions) can call this
    without an engine and get deterministic defaults.
    """
    if engine is None:
        return _cache["aliases"] or DEFAULT_ALIASES
    load(engine)
    return _cache["aliases"] or DEFAULT_ALIASES


def get_adjacency(engine: Optional[Engine] = None) -> Mapping[str, List[Dict[str, Any]]]:
    if engine is None:
        return _cache["adjacency"] or DEFAULT_ADJACENCY
    load(engine)
    return _cache["adjacency"] or DEFAULT_ADJACENCY


__all__ = [
    "load",
    "invalidate",
    "get_aliases",
    "get_adjacency",
]
