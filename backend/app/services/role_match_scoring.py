"""
Unified role-readiness scoring + match classification.

This module is the single source of truth for converting a student's skill
profile into a per-role readiness score.  Both the heavy assessor path
(``/assess/role_readiness``) and the lightweight batch path
(``/bff/student/roles/alignment/batch``) call into here so they cannot
disagree.

Contributions over the previous in-line implementations:

* **Skill normalization with aliases**: free-text skill names from extraction
  or scraped JDs are normalized (lower-case, punctuation stripped) and
  resolved against a curated alias dictionary (``SKILL_ALIASES``) before
  matching.  This recovers cases like ``scikit-learn`` -> ``Machine
  Learning`` that the previous exact-id join silently dropped.

* **Adjacent-skill / transferable-skill credit**: a curated adjacency
  dictionary (``SKILL_ADJACENCY``) gives partial credit when a student
  demonstrates a closely related skill for which the role asks.  This is
  the "transferable skills" angle the literature recommends and
  prevents the algorithm from treating ``PyTorch`` as no evidence at all
  for a ``TensorFlow`` requirement.

* **Reliability-aware base score**: when an aggregator-derived
  ``reliability_level`` is available, it modulates the base skill score
  (high=1.0, medium=0.9, low=0.7) so multi-source corroboration shows up
  in the number, not just metadata.

* **Smooth key-skill gating**: replaces the previous step-cliff caps
  (62/75) with a continuous penalty.  No more visible "jumps" when a key
  skill nudges past 0.35 or 0.6.

* **Backend-emitted match_class**: ``confirmed`` / ``potential`` /
  ``below`` is computed here so the frontend stops re-deriving its own
  classification.

The functions are pure (no DB / network), making them trivially unit
testable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

# ---------------------------------------------------------------------------
# Constants — kept as module-level so callers (and tests) can import them.
# ---------------------------------------------------------------------------

MUST_WEIGHT_BOOST: float = 1.2
OPTIONAL_WEIGHT_FACTOR: float = 0.7
MENTIONED_FLOOR: float = 0.22
RECENCY_HALF_LIFE_DAYS: float = 180.0
RECENCY_MIN_FACTOR: float = 0.6
MET_THRESHOLD: float = 0.75
ADJACENT_CREDIT_CAP: float = 0.55  # transferable evidence never reaches "met"

# Match classification thresholds.  Centralized here so we don't sprinkle
# magic numbers across FE + BE.
CLASS_CONFIRMED_READINESS: float = 65.0
CLASS_CONFIRMED_MUST_RATIO: float = 0.6
CLASS_POTENTIAL_READINESS: float = 35.0
CLASS_POTENTIAL_MUST_RATIO: float = 0.2

# Reliability multipliers — multiplied into the per-skill base score.
RELIABILITY_FACTOR: Dict[str, float] = {
    "high": 1.0,
    "medium": 0.9,
    "low": 0.7,
}


# ---------------------------------------------------------------------------
# Skill alias dictionary (no DB migration — additive in code).
#
# Maps lower-cased free-text labels to a canonical "concept key".  The
# canonical key is matched directly against role requirement skill names
# (also lower-cased) AND against a curated set of canonical concept keys.
# This is intentionally conservative: only widely-accepted synonyms.
# ---------------------------------------------------------------------------

SKILL_ALIASES: Dict[str, str] = {
    # Programming languages / ecosystems
    "py": "python",
    "python3": "python",
    "py3": "python",
    "javascript": "javascript",
    "js": "javascript",
    "ecmascript": "javascript",
    "typescript": "typescript",
    "ts": "typescript",
    "node": "javascript",
    "node.js": "javascript",
    "nodejs": "javascript",
    "golang": "go",
    "c sharp": "c#",
    "csharp": "c#",
    "rlang": "r",
    "r language": "r",
    # Data / SQL
    "structured query language": "sql",
    "t-sql": "sql",
    "transact-sql": "sql",
    "pl/sql": "sql",
    "mysql": "sql",
    "postgresql": "sql",
    "postgres": "sql",
    "sqlite": "sql",
    "redshift": "sql",
    "bigquery": "sql",
    # ML / DL frameworks
    "scikit-learn": "machine learning",
    "scikit learn": "machine learning",
    "sklearn": "machine learning",
    "xgboost": "machine learning",
    "lightgbm": "machine learning",
    "catboost": "machine learning",
    "ml": "machine learning",
    "ml engineer": "machine learning",
    "machine-learning": "machine learning",
    "tensorflow": "deep learning",
    "tf": "deep learning",
    "keras": "deep learning",
    "pytorch": "deep learning",
    "torch": "deep learning",
    "huggingface": "deep learning",
    "hugging face": "deep learning",
    "transformers": "deep learning",
    "dl": "deep learning",
    "neural networks": "deep learning",
    "neural network": "deep learning",
    # Analytics / viz
    "data analytics": "data analysis",
    "exploratory data analysis": "data analysis",
    "eda": "data analysis",
    "tableau": "data visualization",
    "power bi": "data visualization",
    "powerbi": "data visualization",
    "matplotlib": "data visualization",
    "seaborn": "data visualization",
    "plotly": "data visualization",
    "d3.js": "data visualization",
    "looker": "data visualization",
    "data viz": "data visualization",
    "viz": "data visualization",
    # Statistics
    "stats": "statistics",
    "statistical analysis": "statistics",
    "biostatistics": "statistics",
    "statistical modeling": "statistics",
    "regression analysis": "statistics",
    # Soft skills
    "communications": "communication",
    "verbal communication": "communication",
    "written communication": "communication",
    "presentations": "presentation",
    "public speaking": "presentation",
    "presenting": "presentation",
    "team work": "teamwork",
    "team-work": "teamwork",
    "collaboration": "teamwork",
    # Cloud / data eng
    "aws": "cloud computing",
    "amazon web services": "cloud computing",
    "azure": "cloud computing",
    "gcp": "cloud computing",
    "google cloud": "cloud computing",
    "cloud": "cloud computing",
    "spark": "data engineering",
    "pyspark": "data engineering",
    "hadoop": "data engineering",
    "airflow": "data engineering",
    "dbt": "data engineering",
    "etl": "data engineering",
    "data pipeline": "data engineering",
    "data pipelines": "data engineering",
    # NLP
    "natural language processing": "nlp",
    "llm": "nlp",
    "llms": "nlp",
    "large language models": "nlp",
    # Product
    "product management": "product sense",
    "product strategy": "product sense",
    "user research": "ux research",
    "ux": "ux research",
}


# ---------------------------------------------------------------------------
# Skill adjacency / transferability graph.
#
# For each canonical skill we list adjacent skills with a transfer weight in
# (0, 1).  When a role requires X but the student only has Y where Y is
# adjacent to X, the student gets ``transfer_weight * achieved_score``
# credit, capped at ``ADJACENT_CREDIT_CAP``.  This mirrors the
# "transferable skills" recommendation from the careers literature.
# ---------------------------------------------------------------------------

SKILL_ADJACENCY: Dict[str, List[Dict[str, Any]]] = {
    "python": [
        {"to": "r", "weight": 0.5},
        {"to": "data analysis", "weight": 0.45},
    ],
    "r": [
        {"to": "python", "weight": 0.4},
        {"to": "statistics", "weight": 0.55},
    ],
    "sql": [
        {"to": "data analysis", "weight": 0.5},
        {"to": "data engineering", "weight": 0.45},
    ],
    "machine learning": [
        {"to": "deep learning", "weight": 0.6},
        {"to": "statistics", "weight": 0.45},
        {"to": "data analysis", "weight": 0.35},
    ],
    "deep learning": [
        {"to": "machine learning", "weight": 0.65},
        {"to": "nlp", "weight": 0.5},
    ],
    "nlp": [
        {"to": "deep learning", "weight": 0.55},
        {"to": "machine learning", "weight": 0.4},
    ],
    "data analysis": [
        {"to": "statistics", "weight": 0.45},
        {"to": "data visualization", "weight": 0.4},
        {"to": "sql", "weight": 0.4},
    ],
    "data visualization": [
        {"to": "data analysis", "weight": 0.35},
        {"to": "communication", "weight": 0.25},
    ],
    "statistics": [
        {"to": "data analysis", "weight": 0.4},
        {"to": "machine learning", "weight": 0.35},
    ],
    "data engineering": [
        {"to": "sql", "weight": 0.5},
        {"to": "python", "weight": 0.4},
    ],
    "cloud computing": [
        {"to": "data engineering", "weight": 0.4},
        {"to": "system design", "weight": 0.35},
    ],
    "communication": [
        {"to": "presentation", "weight": 0.6},
        {"to": "teamwork", "weight": 0.4},
    ],
    "presentation": [
        {"to": "communication", "weight": 0.65},
    ],
    "teamwork": [
        {"to": "communication", "weight": 0.45},
    ],
    "product sense": [
        {"to": "data analysis", "weight": 0.35},
        {"to": "communication", "weight": 0.3},
    ],
    "javascript": [
        {"to": "typescript", "weight": 0.7},
    ],
    "typescript": [
        {"to": "javascript", "weight": 0.85},
    ],
}


# ---------------------------------------------------------------------------
# Data-driven key-skill discovery (with the legacy hard-coded map as a
# fallback for role titles we have not yet seen enough of).
# ---------------------------------------------------------------------------

ROLE_KEY_SKILLS_FALLBACK: Dict[str, List[str]] = {
    "data scientist": ["python", "machine learning", "statistics"],
    "machine learning engineer": ["python", "machine learning", "statistics"],
    "ml engineer": ["python", "machine learning", "statistics"],
    "nlp engineer": ["python", "machine learning"],
    "ai engineer": ["python", "machine learning"],
    "ai researcher": ["python", "machine learning"],
    "data analyst": ["sql", "data analysis", "statistics"],
    "business analyst": ["data analysis", "communication"],
    "bi analyst": ["sql", "data visualization"],
    "bi developer": ["sql", "data visualization"],
    "software engineer": ["programming", "system design"],
    "software developer": ["programming", "system design"],
    "backend engineer": ["programming", "system design"],
    "frontend engineer": ["programming", "javascript"],
    "full stack": ["programming", "javascript"],
    "product manager": ["product sense", "data analysis", "communication"],
    "quant analyst": ["statistics", "python", "mathematics"],
    "quantitative analyst": ["statistics", "python", "mathematics"],
    "research assistant": ["data analysis", "statistics"],
    "ux researcher": ["data analysis", "communication"],
    "data engineer": ["sql", "python", "data analysis"],
}

_ROLE_KEY_RE: Dict[re.Pattern, List[str]] = {
    re.compile(r"\b" + re.escape(k) + r"\b"): v
    for k, v in ROLE_KEY_SKILLS_FALLBACK.items()
}


# ---------------------------------------------------------------------------
# Pure data classes consumed by the scorer.
# ---------------------------------------------------------------------------


@dataclass
class StudentSkill:
    """Represents what we know about a student's grasp of one skill."""

    skill_id: str
    skill_name: str
    decision: str = ""  # "demonstrated" | "match" | "mentioned" | ""
    achieved_level: int = 0
    assessed_at: Optional[datetime] = None
    reliability_level: Optional[str] = None  # "high" | "medium" | "low"


@dataclass
class RoleRequirement:
    """One row from ``role_skill_requirements`` enriched with skill name."""

    skill_id: str
    skill_name: str
    target_level: int = 2
    required: bool = True
    weight: float = 1.0


@dataclass
class ScoredRequirement:
    """Per-requirement breakdown returned alongside the role score."""

    skill_id: str
    skill_name: str
    target_level: int
    required: bool
    weight: float
    base_score: float
    recency_factor: float
    reliability_factor: float
    score: float
    met: bool
    matched_via: str  # "direct" | "alias" | "adjacent" | "none"
    adjacent_source: Optional[str] = None


@dataclass
class RoleMatchResult:
    role_id: str
    role_title: str
    readiness: float  # 0..100
    raw_readiness: float  # before key-skill smoothing
    match_class: str  # "confirmed" | "potential" | "below"
    match_ratio_must: float  # 0..1
    skills_met: int
    skills_total: int
    skills_met_must: int
    skills_total_must: int
    skills_met_optional: int
    skills_total_optional: int
    critical_gaps: List[str] = field(default_factory=list)
    improvable_gaps: List[str] = field(default_factory=list)
    adjacent_credits: List[Dict[str, str]] = field(default_factory=list)
    items: List[ScoredRequirement] = field(default_factory=list)
    freshness_label: str = "unknown"
    freshness_age_days: Optional[int] = None
    rank_score: float = 0.0  # readiness × freshness nudge (used for sorting)


# ---------------------------------------------------------------------------
# Normalization helpers.
# ---------------------------------------------------------------------------

_NON_ALNUM_RE = re.compile(r"[^a-z0-9+#./\-\s]")
_WS_RE = re.compile(r"\s+")


def normalize_skill_label(value: Any) -> str:
    """Lower-case, strip punctuation, collapse whitespace.  Pure."""
    if value is None:
        return ""
    s = str(value).strip().lower().replace("_", " ")
    s = _NON_ALNUM_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    return s


def canonicalize(label: str, aliases: Optional[Mapping[str, str]] = None) -> str:
    """Resolve a free-text label to its canonical concept key.

    Falls through to the normalized label when no alias is registered, so
    exact-name matching still works as before.

    ``aliases`` lets callers inject a DB-loaded merged map without making
    this function impure.
    """
    norm = normalize_skill_label(label)
    if not norm:
        return ""
    src = aliases if aliases is not None else SKILL_ALIASES
    return src.get(norm, norm)


# ---------------------------------------------------------------------------
# Per-skill scoring primitives.
# ---------------------------------------------------------------------------


def recency_factor(
    assessed_at: Optional[datetime],
    now_utc: Optional[datetime] = None,
) -> float:
    """Half-life decay with floor.  Identical to the legacy formula but
    available as a stand-alone function so callers don't re-implement.
    """
    if not assessed_at:
        return RECENCY_MIN_FACTOR
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    assessed = (
        assessed_at
        if assessed_at.tzinfo
        else assessed_at.replace(tzinfo=timezone.utc)
    )
    age_days = max(0.0, (now_utc - assessed).total_seconds() / 86400.0)
    if age_days <= 7:
        return 1.0
    decay = 0.5 ** (age_days / RECENCY_HALF_LIFE_DAYS)
    return max(RECENCY_MIN_FACTOR, min(1.0, decay))


def base_skill_score(decision: str, achieved: int, target: int) -> float:
    """Maps (decision, level) to a [0, 1] base score.  Pure."""
    target_safe = max(1, int(target))
    achieved_safe = max(0, int(achieved))
    ratio = min(1.2, achieved_safe / target_safe)
    if decision in ("demonstrated", "match"):
        if achieved_safe >= target_safe:
            return 1.0
        return min(0.95, 0.45 + 0.5 * ratio)
    if decision == "mentioned":
        return min(0.6, max(MENTIONED_FLOOR, 0.15 + 0.35 * ratio))
    return 0.0


def reliability_factor(level: Optional[str]) -> float:
    if not level:
        return 1.0  # no penalty if we don't know
    return RELIABILITY_FACTOR.get(level, 1.0)


# ---------------------------------------------------------------------------
# Role freshness — derived purely from ``roles.last_seen_at``.
#
# The intent is honest transparency, not score manipulation: we surface a
# human-readable label ("Active" / "Recent" / "Aging" / "Stale") and a
# small ranking nudge factor for tie-breaks.  Readiness itself is NOT
# adjusted because that score is about the student's match to the
# requirements, not about the role's market freshness.
# ---------------------------------------------------------------------------

FRESHNESS_ACTIVE_DAYS: int = 14
FRESHNESS_RECENT_DAYS: int = 60
FRESHNESS_AGING_DAYS: int = 180

# Tie-break nudge applied on top of readiness when sorting.  Bounded to
# keep readiness order dominant.
FRESHNESS_RANK_NUDGE: Dict[str, float] = {
    "active": 1.03,
    "recent": 1.01,
    "aging": 1.0,
    "stale": 0.97,
    "unknown": 1.0,
}


def freshness_label(
    last_seen_at: Optional[datetime],
    now_utc: Optional[datetime] = None,
) -> str:
    """Map a last-seen timestamp to one of: active / recent / aging /
    stale / unknown.  Pure function."""
    if last_seen_at is None:
        return "unknown"
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    seen = (
        last_seen_at
        if last_seen_at.tzinfo
        else last_seen_at.replace(tzinfo=timezone.utc)
    )
    age_days = max(0.0, (now_utc - seen).total_seconds() / 86400.0)
    if age_days <= FRESHNESS_ACTIVE_DAYS:
        return "active"
    if age_days <= FRESHNESS_RECENT_DAYS:
        return "recent"
    if age_days <= FRESHNESS_AGING_DAYS:
        return "aging"
    return "stale"


def freshness_rank_factor(label: str) -> float:
    return FRESHNESS_RANK_NUDGE.get(label, 1.0)


def freshness_age_days(
    last_seen_at: Optional[datetime],
    now_utc: Optional[datetime] = None,
) -> Optional[int]:
    if last_seen_at is None:
        return None
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    seen = (
        last_seen_at
        if last_seen_at.tzinfo
        else last_seen_at.replace(tzinfo=timezone.utc)
    )
    return int(max(0.0, (now_utc - seen).total_seconds() / 86400.0))


# ---------------------------------------------------------------------------
# Skill-graph lookup.
# ---------------------------------------------------------------------------


def find_adjacent_evidence(
    target_canon: str,
    student_by_canon: Mapping[str, StudentSkill],
    now_utc: datetime,
    adjacency: Optional[Mapping[str, List[Dict[str, Any]]]] = None,
) -> Optional[Dict[str, Any]]:
    """If the student does not have ``target_canon`` directly, search for
    an adjacent skill they *do* have and return the best partial-credit
    score plus the source skill.

    Returns ``None`` if no adjacent evidence is available.
    """
    src = adjacency if adjacency is not None else SKILL_ADJACENCY
    neighbors = src.get(target_canon)
    if not neighbors:
        return None
    best: Optional[Dict[str, Any]] = None
    for n in neighbors:
        src = n["to"]
        weight = float(n["weight"])
        skill = student_by_canon.get(src)
        if not skill:
            continue
        # Consider only demonstrated / mentioned evidence — missing means
        # no transfer credit.
        if skill.decision not in ("demonstrated", "match", "mentioned"):
            continue
        bs = base_skill_score(skill.decision, skill.achieved_level, target=2)
        rf = recency_factor(skill.assessed_at, now_utc)
        rel = reliability_factor(skill.reliability_level)
        candidate = bs * rf * rel * weight
        candidate = min(candidate, ADJACENT_CREDIT_CAP)
        if best is None or candidate > best["score"]:
            best = {
                "score": candidate,
                "source_skill_name": skill.skill_name,
                "source_canon": src,
                "transfer_weight": weight,
            }
    return best


# ---------------------------------------------------------------------------
# Key-skill discovery (continuous gating).
# ---------------------------------------------------------------------------


def key_skill_canons_for_role(
    role_title: str,
    requirements: Sequence[RoleRequirement],
    discovered: Optional[Sequence[str]] = None,
    aliases: Optional[Mapping[str, str]] = None,
) -> List[str]:
    """Return the canonical key-skill set for a role.

    Resolution order:
    1. ``discovered`` — if the caller provides a data-driven list (e.g.
       computed from JD frequency analytics) we prefer it.
    2. The legacy ``ROLE_KEY_SKILLS_FALLBACK`` regex map.
    3. Top-2 must-skills by weight.
    """
    if discovered:
        return [canonicalize(s, aliases) for s in discovered if s]

    title_norm = normalize_skill_label(role_title)
    best_match: Optional[List[str]] = None
    best_len = 0
    for pattern, skill_names in _ROLE_KEY_RE.items():
        m = pattern.search(title_norm)
        if m and (m.end() - m.start()) > best_len:
            best_len = m.end() - m.start()
            best_match = skill_names
    if best_match is not None:
        return [canonicalize(s, aliases) for s in best_match]

    must_reqs = [r for r in requirements if r.required]
    must_reqs = sorted(must_reqs, key=lambda r: r.weight, reverse=True)
    return [canonicalize(r.skill_name, aliases) for r in must_reqs[:2]]


def smooth_key_skill_penalty(key_scores: Sequence[float]) -> float:
    """Returns a multiplier in [0.55, 1.0] applied to the raw readiness.

    Replaces the old 62/75 step caps with a continuous penalty.  Worst
    key skill drives the result, with the average providing a small
    cushion so a single weakness doesn't completely tank an otherwise
    strong profile.
    """
    if not key_scores:
        return 1.0
    min_key = min(key_scores)
    avg_key = sum(key_scores) / len(key_scores)
    # Both halves are in (0, 1] given any score in [0, 1].
    min_factor = 0.55 + 0.45 * min(1.0, min_key / 0.7)
    avg_factor = 0.7 + 0.3 * min(1.0, avg_key / 0.85)
    return max(0.55, min(1.0, min_factor * avg_factor))


# ---------------------------------------------------------------------------
# Match classification.
# ---------------------------------------------------------------------------


def classify_match(readiness_pct: float, must_ratio: float) -> str:
    """Returns ``"confirmed" | "potential" | "below"``.

    Confirmed: readiness AND must-ratio are both healthy.
    Potential: room to grow but must-ratio not catastrophic.
    Below: not worth surfacing as a recommendation.
    """
    if (
        readiness_pct >= CLASS_CONFIRMED_READINESS
        and must_ratio >= CLASS_CONFIRMED_MUST_RATIO
    ):
        return "confirmed"
    if (
        readiness_pct >= CLASS_POTENTIAL_READINESS
        and must_ratio >= CLASS_POTENTIAL_MUST_RATIO
    ):
        return "potential"
    return "below"


# ---------------------------------------------------------------------------
# Top-level scorer.
# ---------------------------------------------------------------------------


def _index_student_skills(
    skills: Iterable[StudentSkill],
    aliases: Optional[Mapping[str, str]] = None,
) -> Dict[str, StudentSkill]:
    """Index by canonical concept key.  Last write wins; when callers
    pre-sort by recency the most recent assessment dominates."""
    out: Dict[str, StudentSkill] = {}
    for s in skills:
        canon = canonicalize(s.skill_name, aliases) or canonicalize(s.skill_id, aliases)
        if not canon:
            continue
        prev = out.get(canon)
        # Prefer demonstrated > mentioned > none; tie-broken by recency.
        if prev is None:
            out[canon] = s
            continue
        rank = {"demonstrated": 0, "match": 0, "mentioned": 1}
        prev_rank = rank.get(prev.decision, 2)
        new_rank = rank.get(s.decision, 2)
        if new_rank < prev_rank:
            out[canon] = s
        elif new_rank == prev_rank:
            if (s.assessed_at or datetime.min.replace(tzinfo=timezone.utc)) > (
                prev.assessed_at or datetime.min.replace(tzinfo=timezone.utc)
            ):
                out[canon] = s
    return out


def score_role(
    role_id: str,
    role_title: str,
    requirements: Sequence[RoleRequirement],
    student_skills: Sequence[StudentSkill],
    *,
    now_utc: Optional[datetime] = None,
    discovered_key_skills: Optional[Sequence[str]] = None,
    demand_index: Optional[Mapping[str, float]] = None,
    aliases: Optional[Mapping[str, str]] = None,
    adjacency: Optional[Mapping[str, List[Dict[str, Any]]]] = None,
    role_description: Optional[str] = None,
    semantic_bonus_cap: float = 5.0,
    role_last_seen_at: Optional[datetime] = None,
) -> RoleMatchResult:
    """Compute the unified role-match result.

    All inputs are pure data structures so this function can be unit
    tested without any DB.

    ``aliases`` / ``adjacency`` accept DB-loaded overrides (see
    ``backend.app.services.concept_graph``); when omitted the curated
    in-code defaults are used.

    ``role_description`` enables a small **soft-requirement** bonus: any
    student skill that's NOT in the explicit requirements but does
    appear in the role's job description gets a tiny readiness boost
    (capped by ``semantic_bonus_cap`` percentage points).  This addresses
    the long-tail "JD mentions Spark, role doesn't list it as a
    requirement, but the student knows it" case.
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    student_by_canon = _index_student_skills(student_skills, aliases)

    items: List[ScoredRequirement] = []
    critical_gaps: List[str] = []
    improvable_gaps: List[str] = []
    adjacent_credits: List[Dict[str, str]] = []
    key_canons = key_skill_canons_for_role(
        role_title, requirements, discovered_key_skills, aliases
    )
    key_canon_set = set(key_canons)
    key_scores: List[float] = []

    must_total = 0
    must_met = 0
    optional_total = 0
    optional_met = 0
    meet_count = 0

    total_weight = 0.0
    weighted_score = 0.0

    for req in requirements:
        canon = canonicalize(req.skill_name, aliases) or canonicalize(req.skill_id, aliases)
        student = student_by_canon.get(canon)

        matched_via = "none"
        adjacent_source: Optional[str] = None
        rel_factor = 1.0

        if student is not None:
            base = base_skill_score(student.decision, student.achieved_level, req.target_level)
            rec = recency_factor(student.assessed_at, now_utc)
            rel_factor = reliability_factor(student.reliability_level)
            score = base * rec * rel_factor
            matched_via = "alias" if normalize_skill_label(student.skill_name) != canon else "direct"
        else:
            base = 0.0
            rec = 1.0
            adj = find_adjacent_evidence(canon, student_by_canon, now_utc, adjacency)
            if adj is not None:
                base = adj["score"]  # already includes recency × reliability × transfer weight
                rec = 1.0  # baked-in
                score = adj["score"]
                matched_via = "adjacent"
                adjacent_source = adj["source_skill_name"]
                adjacent_credits.append(
                    {
                        "required_skill": req.skill_name,
                        "via_skill": adj["source_skill_name"],
                        "transfer_weight": f"{adj['transfer_weight']:.2f}",
                    }
                )
            else:
                score = 0.0

        # Demand-index mild boost on weight (kept compatible with previous heavy path).
        demand_boost = 1.0
        if demand_index:
            demand_boost = 1.0 + 0.25 * float(demand_index.get(req.skill_id, 0.0))

        effective_weight = max(
            0.1,
            req.weight
            * demand_boost
            * (MUST_WEIGHT_BOOST if req.required else OPTIONAL_WEIGHT_FACTOR),
        )

        met = score >= MET_THRESHOLD
        if req.required:
            must_total += 1
            if met:
                must_met += 1
                meet_count += 1
            else:
                critical_gaps.append(req.skill_name)
        else:
            optional_total += 1
            if met:
                optional_met += 1
                meet_count += 1
            else:
                improvable_gaps.append(req.skill_name)

        if req.required and canon in key_canon_set:
            key_scores.append(score)

        weighted_score += score * effective_weight
        total_weight += effective_weight

        items.append(
            ScoredRequirement(
                skill_id=req.skill_id,
                skill_name=req.skill_name,
                target_level=req.target_level,
                required=req.required,
                weight=req.weight,
                base_score=round(base, 4),
                recency_factor=round(rec, 4),
                reliability_factor=round(rel_factor, 4),
                score=round(score, 4),
                met=met,
                matched_via=matched_via,
                adjacent_source=adjacent_source,
            )
        )

    raw_readiness = (
        round((weighted_score / total_weight) * 100, 2) if total_weight > 0 else 0.0
    )

    # Smooth gating instead of step caps.
    penalty = smooth_key_skill_penalty(key_scores)
    readiness = round(raw_readiness * penalty, 2)

    # Soft-requirement bonus: student skills that are NOT in the explicit
    # role requirements but DO appear in the role's JD text get a small
    # bonus.  This catches the common "JD mentions Spark, role schema
    # doesn't list it but student knows it" case without resorting to
    # full-blown embeddings.
    soft_bonus = 0.0
    soft_matches: List[str] = []
    if role_description:
        jd_norm = normalize_skill_label(role_description)
        if jd_norm:
            req_canons = {
                canonicalize(r.skill_name, aliases) or canonicalize(r.skill_id, aliases)
                for r in requirements
            }
            for canon, sk in student_by_canon.items():
                if canon in req_canons:
                    continue
                if sk.decision not in ("demonstrated", "match"):
                    continue
                # word-boundary check on canonical AND original label.
                names_to_try = {canon, normalize_skill_label(sk.skill_name)}
                hit = False
                for name in names_to_try:
                    if not name:
                        continue
                    pat = re.compile(rf"(?<!\w){re.escape(name)}(?!\w)")
                    if pat.search(jd_norm):
                        hit = True
                        break
                if hit:
                    soft_bonus += 1.5  # percentage points per soft match
                    soft_matches.append(sk.skill_name)
            soft_bonus = min(soft_bonus, max(0.0, semantic_bonus_cap))
            if soft_bonus > 0:
                readiness = round(min(100.0, readiness + soft_bonus), 2)

    must_ratio = round(must_met / must_total, 4) if must_total else 0.0
    match_class = classify_match(readiness, must_ratio)

    # Freshness — pure metadata + tiny ranking nudge.  Does NOT
    # influence readiness because that score is about the student's fit,
    # not about the role's market activity.
    f_label = freshness_label(role_last_seen_at, now_utc)
    f_age = freshness_age_days(role_last_seen_at, now_utc)
    rank = round(readiness * freshness_rank_factor(f_label), 2)

    if soft_matches:
        # Surface soft matches via adjacent_credits with a special
        # transfer_weight marker so the FE renders them in the same row.
        for name in soft_matches:
            adjacent_credits.append(
                {
                    "required_skill": "(JD bonus)",
                    "via_skill": name,
                    "transfer_weight": "soft",
                }
            )

    return RoleMatchResult(
        role_id=role_id,
        role_title=role_title,
        readiness=readiness,
        raw_readiness=raw_readiness,
        match_class=match_class,
        match_ratio_must=must_ratio,
        skills_met=meet_count,
        skills_total=len(items),
        skills_met_must=must_met,
        skills_total_must=must_total,
        skills_met_optional=optional_met,
        skills_total_optional=optional_total,
        critical_gaps=critical_gaps,
        improvable_gaps=improvable_gaps,
        adjacent_credits=adjacent_credits,
        items=items,
        freshness_label=f_label,
        freshness_age_days=f_age,
        rank_score=rank,
    )


__all__ = [
    "MUST_WEIGHT_BOOST",
    "OPTIONAL_WEIGHT_FACTOR",
    "MENTIONED_FLOOR",
    "RECENCY_HALF_LIFE_DAYS",
    "RECENCY_MIN_FACTOR",
    "MET_THRESHOLD",
    "ADJACENT_CREDIT_CAP",
    "CLASS_CONFIRMED_READINESS",
    "CLASS_CONFIRMED_MUST_RATIO",
    "CLASS_POTENTIAL_READINESS",
    "CLASS_POTENTIAL_MUST_RATIO",
    "RELIABILITY_FACTOR",
    "SKILL_ALIASES",
    "SKILL_ADJACENCY",
    "ROLE_KEY_SKILLS_FALLBACK",
    "StudentSkill",
    "RoleRequirement",
    "ScoredRequirement",
    "RoleMatchResult",
    "normalize_skill_label",
    "canonicalize",
    "recency_factor",
    "base_skill_score",
    "reliability_factor",
    "find_adjacent_evidence",
    "key_skill_canons_for_role",
    "smooth_key_skill_penalty",
    "classify_match",
    "score_role",
]
