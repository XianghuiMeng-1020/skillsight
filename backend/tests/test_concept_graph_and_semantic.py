"""Tests for the DB-backed concept graph loader, the IDF semantic
matcher, and the soft-requirement bonus integration in score_role.

These avoid the real DB by using lightweight in-memory dicts where
possible.  The loader's DB path is exercised via SQLAlchemy errors that
trigger the fallback branch — proving production stays up even if the
migration hasn't been applied yet.
"""
from __future__ import annotations

from typing import Any

import pytest

from backend.app.services import concept_graph
from backend.app.services.role_match_scoring import (
    SKILL_ADJACENCY,
    SKILL_ALIASES,
    RoleRequirement,
    StudentSkill,
    canonicalize,
    score_role,
)
from backend.app.services.semantic_job_matcher import (
    compute_idf,
    cosine_similarity,
    match_job_skill_semantic,
    rank_jobs_for_skills,
)


# ---------------------------------------------------------------------------
# concept_graph loader: graceful fallback
# ---------------------------------------------------------------------------


class _BrokenEngine:
    """Minimal stub that raises on every connect — proves the loader
    falls back to in-code defaults when the DB is unreachable."""

    def connect(self):  # pragma: no cover - exercised via the loader
        raise RuntimeError("DB unreachable in test")


class TestConceptGraphFallback:
    def setup_method(self):
        concept_graph.invalidate()

    def test_aliases_fallback_to_defaults_when_engine_missing(self):
        out = concept_graph.get_aliases(None)
        # Spot check a known default.
        assert out["sklearn"] == "machine learning"

    def test_adjacency_fallback_to_defaults_when_engine_missing(self):
        out = concept_graph.get_adjacency(None)
        assert "machine learning" in out
        # Edges include deep learning.
        assert any(e["to"] == "deep learning" for e in out["machine learning"])

    def test_loader_handles_db_error_gracefully(self):
        # Even with a broken engine, get_aliases must return defaults
        # rather than raising.  This is the "Render hasn't run alembic
        # yet" safety net.
        eng = _BrokenEngine()
        out_aliases = concept_graph.get_aliases(eng)  # type: ignore[arg-type]
        out_adj = concept_graph.get_adjacency(eng)  # type: ignore[arg-type]
        assert out_aliases["pytorch"] == "deep learning"
        assert "deep learning" in out_adj


# ---------------------------------------------------------------------------
# scorer: aliases / adjacency overrides + soft-requirement bonus
# ---------------------------------------------------------------------------


def _student(name: str, decision: str = "demonstrated", level: int = 3) -> StudentSkill:
    from datetime import datetime, timezone
    return StudentSkill(
        skill_id=f"HKU.SKILL.{name.upper().replace(' ', '_')}.v1",
        skill_name=name,
        decision=decision,
        achieved_level=level,
        assessed_at=datetime.now(timezone.utc),
    )


def _req(name: str, target: int = 2, required: bool = True, weight: float = 1.0) -> RoleRequirement:
    return RoleRequirement(
        skill_id=f"HKU.SKILL.{name.upper().replace(' ', '_')}.v1",
        skill_name=name,
        target_level=target,
        required=required,
        weight=weight,
    )


class TestScorerInjectableConceptGraph:
    def test_db_alias_override_wins_over_default(self):
        # Custom override: claim "rust" maps to "machine learning".  This
        # is silly but proves overrides take effect end-to-end.
        custom_aliases = {**SKILL_ALIASES, "rust": "machine learning"}
        result = score_role(
            role_id="r1",
            role_title="ML Engineer",
            requirements=[_req("Machine Learning")],
            student_skills=[_student("Rust")],
            aliases=custom_aliases,
        )
        # Without the override Rust would not contribute; with it the
        # student gets credit for Machine Learning.
        assert result.skills_met_must == 1

    def test_db_adjacency_override_adds_new_edge(self):
        # Empty default for "underwater basket weaving" — add an edge
        # from "python" to it via override and verify partial credit
        # flows through.
        custom_adj = {
            **SKILL_ADJACENCY,
            "underwater basket weaving": [{"to": "python", "weight": 0.5}],
        }
        baseline = score_role(
            role_id="r2",
            role_title="Niche Researcher",
            requirements=[_req("Underwater Basket Weaving")],
            student_skills=[_student("Python")],
        )
        with_override = score_role(
            role_id="r2",
            role_title="Niche Researcher",
            requirements=[_req("Underwater Basket Weaving")],
            student_skills=[_student("Python")],
            adjacency=custom_adj,
        )
        # Default scoring: the requirement 'underwater basket weaving' has
        # no adjacency edge, so the student earns 0.  With the override,
        # readiness must be strictly greater.
        assert with_override.readiness > baseline.readiness


class TestSoftRequirementBonus:
    def test_jd_mentions_extra_skill_grants_bonus(self):
        baseline = score_role(
            role_id="r3",
            role_title="Data Engineer",
            requirements=[_req("SQL")],
            student_skills=[_student("SQL"), _student("Spark")],
        )
        with_jd = score_role(
            role_id="r3",
            role_title="Data Engineer",
            requirements=[_req("SQL")],
            student_skills=[_student("SQL"), _student("Spark")],
            role_description="We use SQL and Spark heavily for ETL.",
        )
        assert with_jd.readiness >= baseline.readiness
        # The bonus surfaces as an adjacent_credits entry tagged as soft.
        assert any(c.get("transfer_weight") == "soft" for c in with_jd.adjacent_credits)

    def test_bonus_capped(self):
        # Pile up many JD-only skills, ensure cap works.
        student_skills = [_student(f"Tool{i}") for i in range(20)]
        # Description mentions all of them.
        desc = " ".join(f"tool{i}" for i in range(20))
        result = score_role(
            role_id="r4",
            role_title="Generic",
            requirements=[_req("Communication", required=True)],
            student_skills=student_skills,
            role_description=desc,
            semantic_bonus_cap=5.0,
        )
        # Bonus must not lift readiness above baseline + 5.0pp.
        baseline = score_role(
            role_id="r4",
            role_title="Generic",
            requirements=[_req("Communication", required=True)],
            student_skills=student_skills,
        )
        assert result.readiness - baseline.readiness <= 5.0 + 1e-6


# ---------------------------------------------------------------------------
# semantic_job_matcher: TF-IDF & ranking
# ---------------------------------------------------------------------------


class TestIdfAndCosine:
    def test_idf_downweights_common_tokens(self):
        corpus = [
            "python data analysis report",
            "python machine learning project",
            "python statistics report data",
        ]
        idf = compute_idf(corpus)
        # 'python' appears in every doc → low IDF; 'machine' in only one.
        assert idf["machine"] > idf["python"]

    def test_cosine_self_similarity_is_one(self):
        v = {"a": 1.0, "b": 2.0, "c": 3.0}
        assert cosine_similarity(v, v) == pytest.approx(1.0)

    def test_match_job_skill_semantic_returns_shape(self):
        out = match_job_skill_semantic(
            "Looking for python and SQL skills",
            ["I have done python projects", "SQL queries written daily"],
        )
        assert "semantic_score" in out
        assert "best_similarity" in out
        assert 0.0 <= out["semantic_score"] <= 1.0


class TestRankJobsForSkills:
    def test_ranking_picks_most_relevant(self):
        skills = ["python", "machine learning"]
        jobs = [
            "Senior ML engineer doing python and machine learning",
            "Front-end developer using react and typescript",
            "Data analyst writing SQL queries",
        ]
        ranked = rank_jobs_for_skills(skills, jobs, top_k=3)
        assert ranked[0]["index"] == 0
        assert ranked[0]["score"] >= ranked[1]["score"]
        assert ranked[0]["score"] >= ranked[2]["score"]

    def test_returns_empty_for_empty_inputs(self):
        assert rank_jobs_for_skills([], ["job"]) == []
        assert rank_jobs_for_skills(["python"], []) == []
