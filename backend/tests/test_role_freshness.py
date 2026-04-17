"""Tests for role-freshness helpers and end-to-end emission via score_role.

Freshness is intentionally NOT folded into readiness — these tests pin
that contract so future changes can't silently start mutating the
student's match score based on how recent the role posting is.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.app.services import role_match_scoring as rms
from backend.app.services.role_match_scoring import (
    RoleRequirement,
    StudentSkill,
    freshness_age_days,
    freshness_label,
    freshness_rank_factor,
    score_role,
)


NOW = datetime(2026, 4, 17, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# freshness_label
# ---------------------------------------------------------------------------

def test_freshness_label_unknown_when_missing():
    assert freshness_label(None, NOW) == "unknown"


def test_freshness_label_active_within_14_days():
    assert freshness_label(NOW - timedelta(days=0), NOW) == "active"
    assert freshness_label(NOW - timedelta(days=7), NOW) == "active"
    assert freshness_label(NOW - timedelta(days=14), NOW) == "active"


def test_freshness_label_recent_between_14_and_60_days():
    assert freshness_label(NOW - timedelta(days=15), NOW) == "recent"
    assert freshness_label(NOW - timedelta(days=60), NOW) == "recent"


def test_freshness_label_aging_between_60_and_180_days():
    assert freshness_label(NOW - timedelta(days=61), NOW) == "aging"
    assert freshness_label(NOW - timedelta(days=180), NOW) == "aging"


def test_freshness_label_stale_beyond_180_days():
    assert freshness_label(NOW - timedelta(days=181), NOW) == "stale"
    assert freshness_label(NOW - timedelta(days=365), NOW) == "stale"


def test_freshness_label_handles_naive_timestamps():
    naive = (NOW - timedelta(days=5)).replace(tzinfo=None)
    assert freshness_label(naive, NOW) == "active"


# ---------------------------------------------------------------------------
# freshness_age_days + rank factor
# ---------------------------------------------------------------------------

def test_freshness_age_days_returns_none_for_missing():
    assert freshness_age_days(None, NOW) is None


def test_freshness_age_days_basic():
    assert freshness_age_days(NOW - timedelta(days=3, hours=4), NOW) == 3
    assert freshness_age_days(NOW - timedelta(days=200), NOW) == 200


def test_freshness_age_days_clamped_to_zero_for_future():
    assert freshness_age_days(NOW + timedelta(days=1), NOW) == 0


def test_rank_factor_active_boost_within_bounds():
    f = freshness_rank_factor("active")
    assert 1.0 < f <= 1.05


def test_rank_factor_stale_dampens_within_bounds():
    f = freshness_rank_factor("stale")
    assert 0.95 <= f < 1.0


def test_rank_factor_unknown_is_neutral():
    assert freshness_rank_factor("unknown") == 1.0
    assert freshness_rank_factor("not-a-real-label") == 1.0


# ---------------------------------------------------------------------------
# score_role end-to-end: freshness must NOT mutate readiness
# ---------------------------------------------------------------------------

def _basic_inputs():
    reqs = [
        RoleRequirement(
            skill_id="s1",
            skill_name="Python",
            target_level=2,
            required=True,
            weight=1.0,
        ),
        RoleRequirement(
            skill_id="s2",
            skill_name="SQL",
            target_level=2,
            required=True,
            weight=1.0,
        ),
    ]
    skills = [
        StudentSkill(
            skill_id="s1",
            skill_name="Python",
            decision="demonstrated",
            achieved_level=3,
            assessed_at=NOW - timedelta(days=10),
        ),
        StudentSkill(
            skill_id="s2",
            skill_name="SQL",
            decision="demonstrated",
            achieved_level=2,
            assessed_at=NOW - timedelta(days=10),
        ),
    ]
    return reqs, skills


def test_score_role_readiness_independent_of_freshness():
    reqs, skills = _basic_inputs()
    fresh = score_role(
        "r1", "Data Analyst", reqs, skills,
        now_utc=NOW, role_last_seen_at=NOW - timedelta(days=2),
    )
    stale = score_role(
        "r1", "Data Analyst", reqs, skills,
        now_utc=NOW, role_last_seen_at=NOW - timedelta(days=400),
    )
    assert fresh.readiness == stale.readiness
    assert fresh.match_class == stale.match_class
    assert fresh.match_ratio_must == stale.match_ratio_must


def test_score_role_emits_freshness_metadata():
    reqs, skills = _basic_inputs()
    res = score_role(
        "r1", "Data Analyst", reqs, skills,
        now_utc=NOW, role_last_seen_at=NOW - timedelta(days=3),
    )
    assert res.freshness_label == "active"
    assert res.freshness_age_days == 3
    # rank_score reflects the small active nudge
    assert res.rank_score > res.readiness
    assert res.rank_score <= res.readiness * 1.05 + 1e-6


def test_score_role_unknown_freshness_when_missing():
    reqs, skills = _basic_inputs()
    res = score_role("r1", "Data Analyst", reqs, skills, now_utc=NOW)
    assert res.freshness_label == "unknown"
    assert res.freshness_age_days is None
    assert res.rank_score == res.readiness


def test_score_role_stale_rank_score_is_dampened_but_not_destroyed():
    reqs, skills = _basic_inputs()
    res = score_role(
        "r1", "Data Analyst", reqs, skills,
        now_utc=NOW, role_last_seen_at=NOW - timedelta(days=400),
    )
    assert res.freshness_label == "stale"
    assert res.rank_score < res.readiness
    # Rank dampening must stay within ±5pp of readiness (≥ 0.95×).
    assert res.rank_score >= res.readiness * 0.95 - 1e-6


def test_freshness_constants_are_monotonic():
    assert rms.FRESHNESS_ACTIVE_DAYS < rms.FRESHNESS_RECENT_DAYS
    assert rms.FRESHNESS_RECENT_DAYS < rms.FRESHNESS_AGING_DAYS


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
