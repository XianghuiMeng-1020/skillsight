"""
Shared test utilities: denylist recursive scan, assert_no_forbidden_keys.
Used by parameterized access control tests and Decision 2 denylist checks.
"""
from typing import Any, List, Set, Tuple


def assert_no_forbidden_keys(
    obj: Any,
    forbidden_keys: Set[str],
    path: str = "",
) -> List[Tuple[str, str]]:
    """
    Recursively scan obj (dict/list) for forbidden keys.
    Returns list of (path, key) violations. Empty list = no violations.
    """
    violations: List[Tuple[str, str]] = []

    def _scan(o: Any, p: str) -> None:
        if isinstance(o, dict):
            for k, v in o.items():
                if k in forbidden_keys:
                    violations.append((p or "root", k))
                _scan(v, f"{p}.{k}" if p else k)
        elif isinstance(o, list):
            for i, item in enumerate(o):
                _scan(item, f"{p}[{i}]")

    _scan(obj, path)
    return violations


# ACCESS_CONTROL_MATRIX.md denylist for staff/programme responses
DENYLIST_STAFF_PROGRAMME = {
    "subject_id",
    "user_id",
    "student_id",
    "chunk_text",
    "snippet",
    "stored_path",
    "storage_uri",
    "embedding",
}


def assert_response_no_forbidden_keys(
    data: dict,
    forbidden_keys: Set[str] | None = None,
    role: str = "staff",
) -> None:
    """
    Assert API response contains no forbidden keys (denylist).
    Raises AssertionError with path and key on violation.
    """
    keys = forbidden_keys or DENYLIST_STAFF_PROGRAMME
    violations = assert_no_forbidden_keys(data, keys)
    if violations:
        msg = "; ".join(f"{path}.{k}" for path, k in violations)
        raise AssertionError(
            f"Response for role={role} must not contain denylist keys: {msg}"
        )
