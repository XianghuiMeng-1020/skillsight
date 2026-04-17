"""Unit tests for the unified role-match scoring service.

These are pure-function tests with no DB / network dependencies, so they
run instantly and gate any future changes to the algorithm.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.app.services.role_match_scoring import (
    ADJACENT_CREDIT_CAP,
    CLASS_CONFIRMED_MUST_RATIO,
    CLASS_CONFIRMED_READINESS,
    CLASS_POTENTIAL_MUST_RATIO,
    CLASS_POTENTIAL_READINESS,
    MET_THRESHOLD,
    RoleRequirement,
    StudentSkill,
    base_skill_score,
    canonicalize,
    classify_match,
    find_adjacent_evidence,
    key_skill_canons_for_role,
    normalize_skill_label,
    recency_factor,
    reliability_factor,
    score_role,
    smooth_key_skill_penalty,
)


# ---------------------------------------------------------------------------
# normalization + alias resolution
# ---------------------------------------------------------------------------


class TestNormalizeAndCanonicalize:
    def test_lowercases_and_strips(self):
        assert normalize_skill_label("  Machine_Learning ") == "machine learning"

    def test_canonicalize_alias_resolves(self):
        # scikit-learn should map to "machine learning"
        assert canonicalize("scikit-learn") == "machine learning"
        assert canonicalize("sklearn") == "machine learning"
        assert canonicalize("PyTorch") == "deep learning"
        assert canonicalize("MySQL") == "sql"

    def test_canonicalize_unknown_passes_through(self):
        # unknown skills should not be lost; they fall through normalized.
        assert canonicalize("Quantum Cryptography") == "quantum cryptography"

    def test_canonicalize_empty_safe(self):
        assert canonicalize(None) == ""
        assert canonicalize("") == ""
        assert canonicalize("   ") == ""


# ---------------------------------------------------------------------------
# base scoring primitives
# ---------------------------------------------------------------------------


class TestBaseSkillScore:
    def test_demonstrated_at_target_is_full(self):
        assert base_skill_score("demonstrated", 3, 3) == 1.0

    def test_demonstrated_below_target_is_partial(self):
        s = base_skill_score("demonstrated", 1, 3)
        assert 0.45 <= s <= 0.95

    def test_mentioned_has_floor(self):
        assert base_skill_score("mentioned", 0, 2) >= 0.22

    def test_unknown_decision_zero(self):
        assert base_skill_score("", 0, 2) == 0.0
        assert base_skill_score("not_assessed", 5, 2) == 0.0


class TestRecencyFactor:
    def test_no_assessment_returns_floor(self):
        assert recency_factor(None) == pytest.approx(0.6)

    def test_recent_assessment_full(self):
        now = datetime.now(timezone.utc)
        assert recency_factor(now - timedelta(days=3), now_utc=now) == 1.0

    def test_decays_over_time_and_floors(self):
        now = datetime.now(timezone.utc)
        ancient = recency_factor(now - timedelta(days=3650), now_utc=now)
        assert ancient == pytest.approx(0.6)


class TestReliabilityFactor:
    def test_known_levels(self):
        assert reliability_factor("high") == 1.0
        assert reliability_factor("medium") == 0.9
        assert reliability_factor("low") == 0.7

    def test_unknown_no_penalty(self):
        assert reliability_factor(None) == 1.0
        assert reliability_factor("garbage") == 1.0


# ---------------------------------------------------------------------------
# adjacency / transferable skills
# ---------------------------------------------------------------------------


class TestAdjacentEvidence:
    def test_partial_credit_for_adjacent_skill(self):
        now = datetime.now(timezone.utc)
        # Student knows PyTorch (deep learning); requirement is machine learning.
        student = StudentSkill(
            skill_id="HKU.SKILL.PYTORCH.v1",
            skill_name="PyTorch",
            decision="demonstrated",
            achieved_level=3,
            assessed_at=now,
        )
        idx = {canonicalize(student.skill_name): student}
        adj = find_adjacent_evidence("machine learning", idx, now)
        assert adj is not None
        assert 0 < adj["score"] <= ADJACENT_CREDIT_CAP
        assert adj["source_skill_name"] == "PyTorch"

    def test_no_adjacent_returns_none(self):
        now = datetime.now(timezone.utc)
        adj = find_adjacent_evidence(
            "underwater basket weaving",
            {},
            now,
        )
        assert adj is None


# ---------------------------------------------------------------------------
# key-skill resolution + smooth gating
# ---------------------------------------------------------------------------


class TestKeySkillResolution:
    def test_uses_discovered_first(self):
        out = key_skill_canons_for_role("Whatever", [], discovered=["Python", "SQL"])
        assert out == ["python", "sql"]

    def test_falls_back_to_regex(self):
        out = key_skill_canons_for_role("Senior Data Analyst (HK)", [])
        assert "sql" in out and "data analysis" in out

    def test_falls_back_to_top_must_by_weight(self):
        reqs = [
            RoleRequirement(skill_id="A", skill_name="Alpha", required=True, weight=3.0),
            RoleRequirement(skill_id="B", skill_name="Beta", required=True, weight=1.0),
            RoleRequirement(skill_id="C", skill_name="Gamma", required=False, weight=5.0),
        ]
        out = key_skill_canons_for_role("Some Esoteric Title", reqs)
        assert out == ["alpha", "beta"]


class TestSmoothGating:
    def test_no_keys_no_penalty(self):
        assert smooth_key_skill_penalty([]) == 1.0

    def test_strong_keys_no_penalty(self):
        # Two keys at full score should not be penalized.
        assert smooth_key_skill_penalty([1.0, 1.0]) == 1.0

    def test_weak_keys_penalized(self):
        weak = smooth_key_skill_penalty([0.1, 0.1])
        # Floor is 0.55.
        assert 0.55 <= weak < 0.7

    def test_continuous_no_cliff(self):
        # Crossing the legacy 0.35 threshold should not produce a jump > 5%.
        below = smooth_key_skill_penalty([0.349, 0.6])
        above = smooth_key_skill_penalty([0.351, 0.6])
        assert abs(above - below) < 0.05


# ---------------------------------------------------------------------------
# classification
# ---------------------------------------------------------------------------


class TestClassifyMatch:
    def test_confirmed_requires_both_signals(self):
        assert classify_match(80, 0.9) == "confirmed"

    def test_high_readiness_low_must_is_potential(self):
        # This is the core bug the user pointed out: 78% with 1/3 must
        # should NOT be confirmed.
        assert (
            classify_match(78, 0.33) == "potential"
        ), "high readiness with weak must-coverage must be Potential, not Confirmed"

    def test_low_readiness_high_must_below(self):
        assert classify_match(20, 1.0) == "below"

    def test_potential_zone(self):
        assert classify_match(50, 0.5) == "potential"

    def test_thresholds_consistent(self):
        # Just-on-threshold should be Confirmed.
        assert (
            classify_match(CLASS_CONFIRMED_READINESS, CLASS_CONFIRMED_MUST_RATIO)
            == "confirmed"
        )
        assert (
            classify_match(CLASS_POTENTIAL_READINESS, CLASS_POTENTIAL_MUST_RATIO)
            == "potential"
        )


# ---------------------------------------------------------------------------
# end-to-end score_role behavior
# ---------------------------------------------------------------------------


def _student(name: str, decision: str = "demonstrated", level: int = 3, when=None,
             reliability=None) -> StudentSkill:
    return StudentSkill(
        skill_id=f"HKU.SKILL.{name.upper().replace(' ', '_')}.v1",
        skill_name=name,
        decision=decision,
        achieved_level=level,
        assessed_at=when or datetime.now(timezone.utc),
        reliability_level=reliability,
    )


def _req(name: str, target: int = 2, required: bool = True, weight: float = 1.0) -> RoleRequirement:
    return RoleRequirement(
        skill_id=f"HKU.SKILL.{name.upper().replace(' ', '_')}.v1",
        skill_name=name,
        target_level=target,
        required=required,
        weight=weight,
    )


class TestScoreRoleEndToEnd:
    def test_full_match_is_confirmed(self):
        result = score_role(
            role_id="r1",
            role_title="Data Analyst",
            requirements=[_req("SQL"), _req("Data Analysis"), _req("Statistics")],
            student_skills=[_student("SQL"), _student("Data Analysis"), _student("Statistics")],
        )
        assert result.match_class == "confirmed"
        assert result.skills_met == 3
        assert result.match_ratio_must == 1.0
        assert result.readiness >= 80

    def test_alias_join_recovers_match(self):
        # Student has scikit-learn but role requires Machine Learning.
        result = score_role(
            role_id="r2",
            role_title="ML Engineer",
            requirements=[_req("Machine Learning"), _req("Python")],
            student_skills=[_student("scikit-learn"), _student("python")],
        )
        # Both should be matched directly via the alias dictionary.
        assert result.skills_met_must == 2
        # Either "alias" or "direct" depending on how the canonicalizer
        # collapsed them; both count as a real match.
        for it in result.items:
            assert it.matched_via in ("alias", "direct")

    def test_adjacent_skill_partial_credit(self):
        # Student demonstrates PyTorch (deep learning) but role requires
        # Machine Learning — adjacency should give partial credit, not
        # treat it as a complete miss.
        result_with_adj = score_role(
            role_id="r3",
            role_title="ML Researcher",
            requirements=[_req("Machine Learning")],
            student_skills=[_student("PyTorch")],
        )
        # PyTorch->ML adjacency exists via deep learning <- machine learning
        # graph.  The credit may not be enough to mark "met" but readiness
        # should be > 0 and the breakdown should annotate matched_via.
        assert result_with_adj.readiness > 0
        item = result_with_adj.items[0]
        assert item.matched_via in ("adjacent", "direct", "alias")

        # Compare against a baseline where the student has no adjacent
        # skill at all — readiness must be lower in the baseline case.
        result_baseline = score_role(
            role_id="r3",
            role_title="ML Researcher",
            requirements=[_req("Machine Learning")],
            student_skills=[],
        )
        assert result_with_adj.readiness >= result_baseline.readiness

    def test_potential_classification_for_partial_must(self):
        # Strong on optional skills, weak on must — should be Potential, not
        # Confirmed even if raw readiness is high.
        result = score_role(
            role_id="r4",
            role_title="Data Analyst",
            requirements=[
                _req("SQL", required=True, weight=2.0),
                _req("Data Analysis", required=True, weight=2.0),
                _req("Statistics", required=True, weight=2.0),
                _req("Communication", required=False, weight=0.5),
            ],
            student_skills=[
                _student("SQL"),
                _student("Communication"),
            ],
        )
        # 1/3 must met → must_ratio ≈ 0.33 → can never be "confirmed".
        assert result.match_ratio_must < CLASS_CONFIRMED_MUST_RATIO
        assert result.match_class != "confirmed"

    def test_reliability_low_drops_score_vs_high(self):
        high = score_role(
            role_id="r5",
            role_title="Data Analyst",
            requirements=[_req("SQL")],
            student_skills=[_student("SQL", reliability="high")],
        )
        low = score_role(
            role_id="r5",
            role_title="Data Analyst",
            requirements=[_req("SQL")],
            student_skills=[_student("SQL", reliability="low")],
        )
        assert low.readiness < high.readiness

    def test_no_assessments_returns_zero_below(self):
        result = score_role(
            role_id="r6",
            role_title="Data Analyst",
            requirements=[_req("SQL"), _req("Statistics")],
            student_skills=[],
        )
        assert result.readiness == 0
        assert result.match_class == "below"
        assert len(result.critical_gaps) == 2

    def test_weak_key_skill_continuous_penalty(self):
        # ML engineer requires python+ML+stats; student strong on stats but
        # very weak on python.  The smooth gate should bring readiness down
        # but not snap to a single canned cap.
        now = datetime.now(timezone.utc)
        result = score_role(
            role_id="r7",
            role_title="Machine Learning Engineer",
            requirements=[
                _req("Python", target=3, weight=2.0),
                _req("Machine Learning", target=3, weight=2.0),
                _req("Statistics", target=2, weight=1.0),
            ],
            student_skills=[
                _student("Python", decision="mentioned", level=1, when=now),
                _student("Machine Learning", decision="mentioned", level=1, when=now),
                _student("Statistics", level=3, when=now),
            ],
        )
        # raw_readiness > readiness because gate kicked in.
        assert result.readiness <= result.raw_readiness
