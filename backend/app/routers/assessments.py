import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from backend.app.db.deps import get_db
from backend.app.db.session import engine
from backend.app.deps import check_doc_access
from backend.app.security import Identity, require_auth
from backend.app.services.bloom_classifier import compute_bloom_score
from backend.app.services.assessment_rubric import DEFAULT_BLOOM_RUBRIC

router = APIRouter(prefix="/assessments", tags=["assessments"])


def _now_utc():
    return datetime.now(timezone.utc)


@router.get("")
def list_assessments(
    doc_id: str = Query(default=None, description="Filter by doc_id"),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
) -> Dict[str, Any]:
    """List skill assessments, optionally filtered by doc_id. Requires auth."""
    try:
        insp = inspect(engine)
        tables = set(insp.get_table_names(schema="public"))
        if "skill_assessments" not in tables:
            return {"count": 0, "items": [], "message": "skill_assessments table not found"}
        
        cols = _table_cols("skill_assessments")
        want = []
        for c in ["assessment_id", "doc_id", "skill_id", "decision", "evidence", "decision_meta", "created_at"]:
            if c in cols:
                want.append(c)
        if not want:
            want = cols[:min(8, len(cols))]
        
        if doc_id:
            sql = text(f"SELECT {', '.join(want)} FROM skill_assessments WHERE doc_id = :doc_id ORDER BY created_at DESC LIMIT :limit")
            rows = db.execute(sql, {"doc_id": doc_id, "limit": limit}).mappings().all()
        elif ident.role == "admin":
            sql = text(f"SELECT {', '.join(want)} FROM skill_assessments ORDER BY created_at DESC LIMIT :limit")
            rows = db.execute(sql, {"limit": limit}).mappings().all()
        else:
            raise HTTPException(status_code=400, detail="doc_id is required for non-admin users")
        
        items = []
        for r in rows:
            d = dict(r)
            for k in ["evidence", "decision_meta"]:
                if k in d:
                    d[k] = _loads_maybe(d.get(k)) or {}
            items.append(d)
        
        return {"count": len(items), "items": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/assessments failed: {type(e).__name__}: {e}")




def _table_cols(table: str) -> List[str]:
    insp = inspect(engine)
    return [c["name"] for c in insp.get_columns(table, schema="public")]


def _col_udt_map(db: Session, table: str) -> Dict[str, str]:
    sql = text(
        """
        SELECT column_name, udt_name
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=:t
        """
    )
    rows = db.execute(sql, {"t": table}).mappings().all()
    return {r["column_name"]: r["udt_name"] for r in rows}


def _loads_maybe(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return v
    if isinstance(v, str):
        s = v.strip()
        if s == "":
            return v
        try:
            return json.loads(s)
        except Exception:
            return v
    return v


def _tokenize(s: str) -> List[str]:
    if not s:
        return []
    s = s.lower()
    s = re.sub(r"[^a-z0-9_+\- ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s.split(" ") if s else []


def _build_keyword_bank(canonical_name: str, aliases: Any) -> List[str]:
    bank = []
    bank.extend(_tokenize(canonical_name or ""))
    a = _loads_maybe(aliases) or []
    if isinstance(a, str):
        a = [a]
    if isinstance(a, list):
        for x in a:
            bank.extend(_tokenize(str(x)))
    bank = [w for w in bank if w and len(w) >= 2]
    return sorted(set(bank))


def _count_hits(text_l: str, keywords: List[str]) -> Tuple[int, List[str]]:
    hits = []
    cnt = 0
    for kw in keywords:
        n = len(re.findall(rf"\b{re.escape(kw)}\b", text_l))
        if n > 0:
            hits.append(kw)
            cnt += n
    return cnt, sorted(set(hits))


def _level_from_hits(hit_count: int, hits: List[str]) -> Tuple[int, str]:
    strong = {"fastapi","uvicorn","sqlalchemy","postgres","psql","consent","pii","anonymize","de","identify","deidentify","de-identify","gdpr","sha256","hash","citation","plagiarism","honesty"}
    strong_hits = [h for h in hits if h in strong]

    if hit_count <= 0:
        return 0, "no_match"
    if hit_count <= 2:
        return 1, "weak_match"
    if hit_count <= 5:
        return 2, "match"
    if hit_count >= 6 or len(strong_hits) >= 2:
        return 3, "strong_match"
    return 2, "match"


def _make_pointer(ch: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "doc_id": ch.get("doc_id"),
        "chunk_id": ch.get("chunk_id"),
        "char_start": int(ch.get("char_start")),
        "char_end": int(ch.get("char_end")),
        "quote_hash": ch.get("quote_hash"),
        "snippet": ch.get("snippet"),
    }


def _insert_one(db: Session, table: str, data: Dict[str, Any]) -> None:
    cols = set(_table_cols(table))
    use = {k: v for k, v in data.items() if k in cols}
    if not use:
        raise RuntimeError(f"no usable columns to insert into {table}")

    udt = _col_udt_map(db, table)
    keys = list(use.keys())
    placeholders = []
    for k in keys:
        tname = (udt.get(k) or "").lower()
        if tname in ("jsonb", "json"):
            v = use.get(k)
            if v is None:
                use[k] = "null"
            elif isinstance(v, str):
                use[k] = v
            else:
                use[k] = json.dumps(v, ensure_ascii=False)
        if tname == "jsonb":
            placeholders.append(f"CAST(:{k} AS JSONB)")
        elif tname == "json":
            placeholders.append(f"CAST(:{k} AS JSON)")
        else:
            placeholders.append(f":{k}")

    sql = text(f"INSERT INTO {table} ({', '.join(keys)}) VALUES ({', '.join(placeholders)})")
    db.execute(sql, use)


def _delete_existing(db: Session, doc_id: str) -> Dict[str, int]:
    out = {"skill_assessments": 0, "skill_proficiency": 0}
    out["skill_assessments"] = int(
        db.execute(text("DELETE FROM skill_assessments WHERE doc_id=:doc_id"), {"doc_id": doc_id}).rowcount or 0
    )
    out["skill_proficiency"] = int(
        db.execute(text("DELETE FROM skill_proficiency WHERE doc_id=:doc_id"), {"doc_id": doc_id}).rowcount or 0
    )
    return out


def _select_chunks(db: Session, doc_id: str, limit: int) -> List[Dict[str, Any]]:
    cols = set(_table_cols("chunks"))
    required = ["chunk_id","doc_id","idx","char_start","char_end","snippet","quote_hash","created_at","chunk_text"]
    missing = [c for c in required if c not in cols]
    if missing:
        raise RuntimeError(f"chunks missing required columns: {missing}")
    sql = text(
        f"""
        SELECT {", ".join(required)}
        FROM chunks
        WHERE doc_id=:doc_id
        ORDER BY idx ASC
        LIMIT :limit
        """
    )
    rows = db.execute(sql, {"doc_id": doc_id, "limit": limit}).mappings().all()
    return [dict(r) for r in rows]


def _select_skills(db: Session, limit: int) -> List[Dict[str, Any]]:
    """Return skills with active aliases aggregated from skill_aliases.

    Contract:
      - Always returns: skill_id, canonical_name, definition, evidence_rules, level_rubric_json, version, source, aliases
      - aliases is a JSON list (possibly empty)
    """
    want = [
        "s.skill_id",
        "s.canonical_name",
        "s.definition",
        "s.evidence_rules",
        "s.level_rubric_json",
        "s.version",
        "s.source",
    ]

    sql = text(
        f"""
        SELECT
          {', '.join(want)},
          COALESCE(a.aliases, '[]'::jsonb) AS aliases
        FROM skills s
        LEFT JOIN (
          SELECT skill_id, jsonb_agg(alias ORDER BY alias) AS aliases
          FROM skill_aliases
          WHERE status='active'
          GROUP BY skill_id
        ) a ON a.skill_id = s.skill_id
        ORDER BY s.skill_id ASC
        LIMIT :limit
        """
    )
    rows = db.execute(sql, {"limit": limit}).mappings().all()
    return [dict(r) for r in rows]

@router.get("/run")
def run_assessments(
    doc_id: str = Query(...),
    limit_skills: int = Query(default=2000, ge=1, le=5000),
    limit_chunks: int = Query(default=5000, ge=1, le=20000),
    db_write: bool = Query(default=True),
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
) -> Dict[str, Any]:
    check_doc_access(ident, doc_id, db)
    started = _now_utc()
    run_id = str(uuid.uuid4())
    rule_version = "rule_v2_scored_keyword_match"

    try:
        chunks = _select_chunks(db, doc_id, limit_chunks)
        skills = _select_skills(db, limit_skills)

        results = []
        for sk in skills:
            sid = sk.get("skill_id")
            name = sk.get("canonical_name") or ""
            kw = _build_keyword_bank(name, sk.get("aliases"))

            matched = []
            all_hits = []
            total_hit = 0

            for ch in chunks:
                txt = ch.get("chunk_text") or ""
                cnt, hits = _count_hits(txt.lower(), kw)
                if cnt > 0:
                    matched.append((cnt, hits, ch))
                    total_hit += cnt
                    all_hits.extend(hits)

            all_hits = sorted(set(all_hits))
            bloom = compute_bloom_score([m[2].get("snippet", "") for m in matched[:8]])
            level, label = _level_from_hits(total_hit, all_hits)
            bloom_score = float(bloom.get("score", 0.0))
            if bloom_score >= 0.8:
                level = max(level, 3)
            elif bloom_score >= 0.55:
                level = max(level, 2)
            elif bloom_score >= 0.3:
                level = max(level, 1)
            decision = "no_match" if level == 0 else "match"

            matched.sort(key=lambda x: x[0], reverse=True)
            evidence = [_make_pointer(m[2]) for m in matched[:3]]

            rubric = DEFAULT_BLOOM_RUBRIC.get(str(level), {})
            rationale = (
                f"Rule={rule_version}. Skill='{name}'. Matched_chunks={len(matched)}. "
                f"Hit_count={total_hit}. Bloom={bloom.get('dominant_level')}({bloom_score}). "
                f"Keywords_hit={all_hits}. Rubric={rubric.get('descriptor','')}."
            )

            results.append(
                {
                    "skill_id": sid,
                    "decision": decision,
                    "level": int(level),
                    "label": label,
                    "rationale": rationale,
                    "evidence": evidence,
                    "bloom": bloom,
                    "rubric": rubric,
                }
            )

        deleted = {"skill_assessments": 0, "skill_proficiency": 0}
        inserted = {"skill_assessments": 0, "skill_proficiency": 0}

        if db_write:
            deleted = _delete_existing(db, doc_id)
            now = _now_utc()

            for r in results:
                _insert_one(
                    db,
                    "skill_assessments",
                    {
                        "assessment_id": str(uuid.uuid4()),
                        "doc_id": doc_id,
                        "skill_id": r["skill_id"],
                        "decision": r["decision"],
                        "evidence": r["evidence"],
                        "decision_meta": {
                            "run_id": run_id,
                            "rule_version": rule_version,
                            "bloom": r.get("bloom", {}),
                            "rubric": r.get("rubric", {}),
                        },
                        "created_at": now,
                    },
                )
                inserted["skill_assessments"] += 1

                _insert_one(
                    db,
                    "skill_proficiency",
                    {
                        "prof_id": str(uuid.uuid4()),
                        "doc_id": doc_id,
                        "skill_id": r["skill_id"],
                        "level": int(r["level"]),
                        "label": r["label"],
                        "rationale": r["rationale"],
                        "best_evidence": (r["evidence"][0] if r["evidence"] else {}),
                        "signals": {"hit_count": int(re.search(r"Hit_count=(\d+)", r["rationale"]).group(1)) if re.search(r"Hit_count=(\d+)", r["rationale"]) else 0,
                                    "keywords_hit": r.get("evidence", [])},
                        "meta": {
                            "run_id": run_id,
                            "rule_version": rule_version,
                            "bloom": r.get("bloom", {}),
                            "rubric": r.get("rubric", {}),
                        },
                        "created_at": now,
                    },
                )
                inserted["skill_proficiency"] += 1

            db.commit()

        finished = _now_utc()
        return {
            "run_id": run_id,
            "rule_version": rule_version,
            "doc_id": doc_id,
            "skills_evaluated": len(results),
            "chunks_scanned": len(chunks),
            "db_write": bool(db_write),
            "db_deleted": deleted,
            "db_inserted": inserted,
            "timing": {"started_at": started.isoformat(), "finished_at": finished.isoformat()},
            "results": results,
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"/assessments/run failed: {type(e).__name__}: {e}")
