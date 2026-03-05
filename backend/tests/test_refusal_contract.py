"""
Refusal contract tests: strict shape (code, message, next_step) only; no label/reason by default.
Denylist scan: no forbidden keys in refusal objects.
"""
import os
import pytest
from unittest.mock import patch

# Forbidden keys in refusal objects (default mode)
REFUSAL_LEGACY_KEYS = {"label", "reason"}

REQUIRED_REFUSAL_KEYS = {"code", "message", "next_step"}


def _refusal_has_only_strict_keys(refusal: dict) -> bool:
    """Refusal must have code, message, next_step and must NOT have label/reason in default."""
    if not isinstance(refusal, dict):
        return False
    for k in REQUIRED_REFUSAL_KEYS:
        if k not in refusal or not isinstance(refusal.get(k), str):
            return False
    for k in REFUSAL_LEGACY_KEYS:
        if k in refusal:
            return False
    return True


def _denylist_scan(obj, path: str = "") -> list:
    """
    Recursively find any refusal object that contains forbidden keys (label, reason).
    Returns list of paths where violation was found.
    """
    violations = []
    if isinstance(obj, dict):
        if "refusal" in obj:
            r = obj["refusal"]
            if isinstance(r, dict):
                for bad in REFUSAL_LEGACY_KEYS:
                    if bad in r:
                        violations.append(f"{path}.refusal.{bad}")
        for k, v in obj.items():
            violations.extend(_denylist_scan(v, f"{path}.{k}" if path else k))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            violations.extend(_denylist_scan(item, f"{path}[{i}]"))
    return violations


def test_make_refusal_returns_wrapper_shape():
    """make_refusal returns { ok: false, refusal: { code, message, next_step } }."""
    from backend.app.refusal import make_refusal
    out = make_refusal("test_code", "Test message", "Do something.")
    assert out.get("ok") is False
    assert "refusal" in out
    r = out["refusal"]
    assert r.get("code") == "test_code"
    assert r.get("message") == "Test message"
    assert r.get("next_step") == "Do something."
    assert "label" not in r
    assert "reason" not in r


def test_refusal_dict_strict_no_legacy_by_default():
    """refusal_dict returns only code, message, next_step when compat not set."""
    from backend.app.refusal import refusal_dict
    with patch.dict(os.environ, {}, clear=False):
        if "REFUSAL_COMPAT" in os.environ:
            del os.environ["REFUSAL_COMPAT"]
    out = refusal_dict("x", "y", "z", headers=None)
    assert set(out.keys()) == {"code", "message", "next_step"}
    assert "label" not in out
    assert "reason" not in out


def test_normalize_legacy_refusal_produces_strict_only():
    """normalize_legacy_refusal produces strict keys only."""
    from backend.app.refusal import normalize_legacy_refusal
    out = normalize_legacy_refusal({"label": "old", "reason": "because", "next_step": "go"})
    assert out == {"code": "old", "message": "because", "next_step": "go"}
    out2 = normalize_legacy_refusal({"code": "c", "message": "m"})
    assert set(out2.keys()) == REQUIRED_REFUSAL_KEYS
    assert "label" not in out2
    assert "reason" not in out2


def test_search_refusal_strict_fields(client, db):
    """Search endpoint refusal has only code, message, next_step (no label/reason)."""
    with patch("backend.app.routers.search.retrieve_evidence") as mock_ret:
        from backend.app.retrieval_pipeline import RetrievalResult, RetrievalMeta, ReliabilityInfo
        mock_ret.return_value = RetrievalResult(
            items=[],
            retrieval_meta=RetrievalMeta(
                vector_top_k=10,
                reranker_enabled=False,
                pre_scores=[0.10],
                post_scores=[],
                min_score_passed=False,
                refusal={"code": "evidence_below_threshold_pre", "message": "Below threshold", "next_step": "Retry"},
            ),
            reliability=ReliabilityInfo(level="low", reason_codes=["evidence_below_threshold_pre"]),
        )
        resp = client.post(
            "/search/evidence_vector",
            json={"query_text": "xyz", "k": 5},
            headers={"X-Subject-Id": "test", "X-Role": "staff"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "refusal" in data
    assert _refusal_has_only_strict_keys(data["refusal"]), "refusal must have only code, message, next_step"
    violations = _denylist_scan(data)
    assert not violations, f"denylist violations: {violations}"


def test_403_detail_has_refusal_wrapper(client):
    """403 from access control has detail.refusal with strict shape (no label/reason)."""
    # No auth / wrong purpose can yield 403 with detail = { ok, refusal }
    resp = client.get(
        "/bff/staff/courses",
        headers={"X-Purpose": "teaching_support"},  # may 403 if no valid token/identity
    )
    if resp.status_code != 403:
        pytest.skip("expected 403 without valid staff identity")
    data = resp.json()
    detail = data.get("detail")
    assert isinstance(detail, dict), "403 detail must be object"
    refusal = detail.get("refusal") or (detail if detail.get("code") else None)
    assert refusal, "403 must include refusal or code"
    # If new contract: detail.refusal
    if detail.get("refusal"):
        assert _refusal_has_only_strict_keys(detail["refusal"]), "refusal must be strict"
    violations = _denylist_scan({"detail": detail})
    assert not violations, f"denylist in 403 detail: {violations}"


def test_denylist_scan_helpers():
    """Denylist scan detects label/reason inside refusal."""
    assert _denylist_scan({"refusal": {"code": "x", "message": "y", "next_step": "z"}}) == []
    assert _denylist_scan({"refusal": {"code": "x", "label": "x", "message": "y", "next_step": "z"}}) != []
    assert _denylist_scan({"refusal": {"code": "x", "reason": "y", "message": "y", "next_step": "z"}}) != []
    assert _refusal_has_only_strict_keys({"code": "c", "message": "m", "next_step": "n"})
    assert not _refusal_has_only_strict_keys({"code": "c", "message": "m", "next_step": "n", "label": "c"})
    assert not _refusal_has_only_strict_keys({"code": "c", "message": "m"})  # missing next_step