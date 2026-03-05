"""
Regression: courses table has title, not course_name.
- Ensures no raw SQL references c.course_name (column does not exist).
- Staff courses endpoint returns course_name (alias from title) when data exists.
"""
import pathlib

import pytest


def test_no_course_name_column_in_sql():
    """Regression: backend must not reference c.course_name in raw SQL (column does not exist)."""
    backend = pathlib.Path(__file__).resolve().parent.parent / "app"
    bad_pattern = "c.course_name"
    for f in backend.rglob("*.py"):
        content = f.read_text(encoding="utf-8", errors="replace")
        if bad_pattern in content:
            # Allow only in comments or AS alias context; the bug is SELECT c.course_name
            lines = content.splitlines()
            for i, line in enumerate(lines):
                if bad_pattern in line and "AS course_name" not in line:
                    # Exclude comment-only lines
                    code = line.split("#")[0].strip()
                    if bad_pattern in code:
                        pytest.fail(
                            f"{f.relative_to(backend.parent)}:{i+1} contains '{bad_pattern}' "
                            "(column does not exist). Use c.title AS course_name instead."
                        )


def test_staff_courses_returns_course_name_field():
    """Staff courses response must include course_name when courses exist (alias from title)."""
    from fastapi.testclient import TestClient

    client = TestClient(__import__("backend.app.main", fromlist=["app"]).app)
    # Get staff token (dev_login creates token; may return empty list if no seed)
    r = client.post(
        "/bff/staff/auth/dev_login",
        json={
            "subject_id": "staff_test",
            "role": "staff",
            "course_ids": ["COMP3000"],
            "term_id": "2025-26-T1",
        },
    )
    if r.status_code != 200:
        pytest.skip("dev_login not available")
    token = r.json().get("token")
    if not token:
        pytest.skip("No token from dev_login")

    resp = client.get(
        "/bff/staff/courses",
        headers={"Authorization": f"Bearer {token}", "X-Purpose": "teaching_support"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    courses = data.get("courses", [])
    # When courses exist, each must have course_name (alias from title)
    for c in courses:
        assert "course_name" in c, f"Each course must have course_name: {c}"
        assert c["course_name"] is not None and str(c["course_name"]).strip() != "", (
            f"course_name must not be null/empty: {c}"
        )
