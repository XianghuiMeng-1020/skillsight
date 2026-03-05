from __future__ import annotations

from typing import Any, Dict, Iterable, Set


def enforce_demo_output(obj: Dict[str, Any], allowed_chunk_ids: Iterable[str]) -> Dict[str, Any]:
    """
    Hard rules (Decision 2):
      - label not_enough_information => evidence_chunk_ids must be [] and refusal_reason non-null
      - label demonstrated/mentioned => evidence_chunk_ids non-empty subset of allowed and refusal_reason null
    """
    allowed: Set[str] = {str(x) for x in (allowed_chunk_ids or [])}
    label = obj.get("label")
    if label not in ("not_enough_information", "mentioned", "demonstrated"):
        raise ValueError("label must be one of: demonstrated, mentioned, not_enough_information")
    eids = obj.get("evidence_chunk_ids") or []
    if not isinstance(eids, list):
        raise ValueError("evidence_chunk_ids must be a list")
    eids = [str(x) for x in eids]

    if label == "not_enough_information":
        if len(eids) != 0:
            raise ValueError("refusal must have empty evidence_chunk_ids")
        refusal_reason = obj.get("refusal_reason")
        if refusal_reason in (None, ""):
            raise ValueError("refusal must include refusal_reason")
        if str(refusal_reason) not in ("irrelevant_evidence", "insufficient_evidence", "llm_or_schema_error"):
            raise ValueError("refusal_reason must be one of: irrelevant_evidence, insufficient_evidence, llm_or_schema_error")
    else:
        if len(eids) == 0:
            raise ValueError("non-refusal must cite >=1 evidence_chunk_ids")
        bad = [x for x in eids if x not in allowed]
        if bad:
            raise ValueError(f"evidence_chunk_ids includes unknown chunk_ids: {bad[:5]}")
        obj["refusal_reason"] = None

    obj["evidence_chunk_ids"] = eids
    return obj


def enforce_prof_output(obj: Dict[str, Any], allowed_chunk_ids: Iterable[str], rubric_ids: Iterable[str]) -> Dict[str, Any]:
    """
    Hard rules (Decision 3):
      - level==0 => evidence_chunk_ids=[] and matched_criteria=[]
      - level>0  => evidence_chunk_ids non-empty subset of allowed; matched_criteria subset of rubric_ids
    """
    allowed: Set[str] = {str(x) for x in (allowed_chunk_ids or [])}
    rub: Set[str] = {str(x) for x in (rubric_ids or [])}

    level = obj.get("level")
    eids = obj.get("evidence_chunk_ids") or []
    if not isinstance(eids, list):
        raise ValueError("evidence_chunk_ids must be a list")
    eids = [str(x) for x in eids]

    mcrit = obj.get("matched_criteria") or []
    if not isinstance(mcrit, list):
        raise ValueError("matched_criteria must be a list")
    mcrit = [str(x) for x in mcrit]

    if int(level) == 0:
        if len(eids) != 0:
            raise ValueError("level=0 must have empty evidence_chunk_ids")
        obj["matched_criteria"] = []
    else:
        if len(eids) == 0:
            raise ValueError("level>0 must cite evidence_chunk_ids")
        if len(mcrit) == 0:
            raise ValueError("level>0 must include matched_criteria")
        bad = [x for x in eids if x not in allowed]
        if bad:
            raise ValueError(f"evidence_chunk_ids includes unknown chunk_ids: {bad[:5]}")
        badc = [c for c in mcrit if c not in rub]
        if badc:
            raise ValueError(f"matched_criteria includes unknown rubric ids: {badc[:5]}")

    obj["evidence_chunk_ids"] = eids
    obj["matched_criteria"] = mcrit
    return obj


def validate_pointer(pointer: Dict[str, Any], allowed_chunk_ids: Iterable[str] | None = None) -> None:
    """
    Pointer integrity checks for MVP.
    Required fields:
      - doc_id, chunk_id, char_start, char_end, quote_hash, snippet
    """
    req = ["doc_id", "chunk_id", "char_start", "char_end", "quote_hash", "snippet"]
    for k in req:
        if k not in pointer or pointer.get(k) in (None, ""):
            raise ValueError(f"pointer missing {k}")
    if allowed_chunk_ids is not None:
        allowed: Set[str] = {str(x) for x in (allowed_chunk_ids or [])}
        cid = str(pointer.get("chunk_id"))
        if cid not in allowed:
            raise ValueError("pointer chunk_id not in allowed set")
    cs = int(pointer["char_start"])
    ce = int(pointer["char_end"])
    if cs < 0 or ce < 0 or ce <= cs:
        raise ValueError("pointer char range invalid")
    qh = str(pointer["quote_hash"])
    if len(qh) < 16:
        raise ValueError("pointer quote_hash too short")
    sn = str(pointer["snippet"])
    if len(sn) > 500:
        raise ValueError("pointer snippet too long")

