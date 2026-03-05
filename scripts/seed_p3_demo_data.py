#!/usr/bin/env python3
"""
P3 Demo Data Seed Script
Creates demo org structure + users + review tickets via the admin BFF API.

Usage:
    python3 scripts/seed_p3_demo_data.py
    SKILLSIGHT_API=http://127.0.0.1:8001 python3 scripts/seed_p3_demo_data.py
"""
import json
import os
import sys
import time

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    import urllib.request as urllib_request
    HAS_REQUESTS = False

API = os.getenv("SKILLSIGHT_API", "http://127.0.0.1:8001")
ADMIN_ID = "admin_seed"


def _request(method, path, data=None, token=None):
    url = f"{API}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    for attempt in range(3):
        try:
            if HAS_REQUESTS:
                # Force direct localhost access; avoid corporate/system proxy causing false 502.
                r = requests.request(
                    method,
                    url,
                    json=data,
                    headers=headers,
                    timeout=15,
                    proxies={"http": None, "https": None},
                )
                r.raise_for_status()
                return r.json()
            body = json.dumps(data).encode() if data is not None else None
            req = urllib_request.Request(url, data=body, headers=headers, method=method)
            with urllib_request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read())
        except Exception as e:
            code = getattr(e, "status_code", getattr(e, "code", 0))
            body_text = ""
            if hasattr(e, "response") and e.response is not None:
                body_text = (getattr(e.response, "text", "") or "")[:200]
            elif hasattr(e, "read"):
                try:
                    body_text = e.read().decode("utf-8", errors="replace")[:200]
                except Exception:
                    body_text = str(e)[:200]
            print(f"  ERROR {method} {path} attempt {attempt + 1}: {code or type(e).__name__} {body_text}", file=sys.stderr)
            if attempt < 2:
                time.sleep(2)
            else:
                raise


def get_admin_token():
    print("[1/N] Getting admin token…")
    # Use core auth endpoint to avoid BFF proxy flakiness during pack orchestration.
    resp = _request("POST", "/auth/dev_login", {"subject_id": ADMIN_ID, "role": "admin"})
    token = resp["token"]
    print(f"  Admin token: {token[:40]}…")
    return token


def seed_faculty(token):
    print("[2/N] Creating faculty…")
    _request("POST", "/bff/admin/onboarding/faculty",
             {"faculty_id": "ENG", "name": "Faculty of Engineering"}, token)
    print("  ENG created")


def seed_programmes(token):
    print("[3/N] Creating programmes…")
    for pid, name in [("CSCI_MSC", "MSc Computer Science"), ("DSCI_MSC", "MSc Data Science")]:
        _request("POST", "/bff/admin/onboarding/programme",
                 {"programme_id": pid, "name": name, "faculty_id": "ENG"}, token)
        print(f"  {pid}: {name}")


def seed_terms(token):
    print("[4/N] Creating terms…")
    for tid, label, sd, ed in [
        ("2024-25-T1", "2024-25 Semester 1", "2024-09-01", "2024-12-31"),
        ("2025-26-T1", "2025-26 Semester 1", "2025-09-01", "2025-12-31"),
    ]:
        _request("POST", "/bff/admin/onboarding/term",
                 {"term_id": tid, "label": label, "start_date": sd, "end_date": ed}, token)
        print(f"  {tid}: {label}")


def seed_courses(token):
    print("[5/N] Creating courses…")
    courses = [
        {"course_id": "COMP3000", "course_name": "Software Engineering", "programme_id": "CSCI_MSC", "faculty_id": "ENG", "term_id": "2025-26-T1"},
        {"course_id": "COMP3100", "course_name": "Machine Learning", "programme_id": "CSCI_MSC", "faculty_id": "ENG", "term_id": "2025-26-T1"},
        {"course_id": "DSCI3000", "course_name": "Data Analysis", "programme_id": "DSCI_MSC", "faculty_id": "ENG", "term_id": "2025-26-T1"},
    ]
    for c in courses:
        _request("POST", "/bff/admin/onboarding/course", c, token)
        print(f"  {c['course_id']}: {c['course_name']}")


def seed_users(token):
    print("[6/N] Creating users (assign roles + context)…")

    # Staff user
    _request("POST", "/bff/admin/users/assign_role",
             {"user_id": "staff_demo", "role": "staff"}, token)
    _request("POST", "/bff/admin/users/assign_context", {
        "user_id": "staff_demo", "role": "staff",
        "faculty_id": "ENG", "course_id": "COMP3000", "term_id": "2025-26-T1"
    }, token)
    _request("POST", "/bff/admin/users/teaching_relation", {
        "user_id": "staff_demo", "course_id": "COMP3000", "term_id": "2025-26-T1", "role": "instructor"
    }, token)
    _request("POST", "/bff/admin/users/teaching_relation", {
        "user_id": "staff_demo", "course_id": "COMP3100", "term_id": "2025-26-T1", "role": "ta"
    }, token)
    print("  staff_demo: staff, courses [COMP3000, COMP3100]")

    # Programme leader
    _request("POST", "/bff/admin/users/assign_role",
             {"user_id": "prog_leader_demo", "role": "programme_leader"}, token)
    _request("POST", "/bff/admin/users/assign_context", {
        "user_id": "prog_leader_demo", "role": "programme_leader",
        "faculty_id": "ENG", "programme_id": "CSCI_MSC"
    }, token)
    print("  prog_leader_demo: programme_leader, programme CSCI_MSC")

    # Admin (admin_seed + admin_demo for E2E compatibility)
    _request("POST", "/bff/admin/users/assign_role",
             {"user_id": ADMIN_ID, "role": "admin"}, token)
    _request("POST", "/bff/admin/users/assign_role",
             {"user_id": "admin_demo", "role": "admin"}, token)
    print(f"  {ADMIN_ID}, admin_demo: admin")


def seed_review_tickets(token):
    """Insert sample review tickets directly via SQL through the API context."""
    print("[7/N] Creating review tickets…")
    # Use the BFF health check to verify connection, then insert via direct DB
    # Note: We insert tickets by calling the admin API indirectly
    # Since there's no POST /review endpoint, we'll use direct DB connection

    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    try:
        from backend.app.db.session import engine
        from sqlalchemy import text
        import json as _json

        tickets = [
            {
                "scope_course_id": "COMP3000",
                "scope_term_id": "2025-26-T1",
                "skill_id": "communication",
                "uncertainty_reason": "Evidence count below threshold (2 < 3 required)",
                "routed_to_role": "staff",
                "draft_json": {"draft_label": "mentioned", "draft_rationale": "AI found weak evidence"},
                "evidence_pointers": [
                    {"type": "chunk_ref", "doc_id": "doc_demo_1", "chunk_idx": 2, "section": "Introduction"},
                    {"type": "chunk_ref", "doc_id": "doc_demo_1", "chunk_idx": 5, "section": "Conclusion"},
                ],
            },
            {
                "scope_course_id": "COMP3000",
                "scope_term_id": "2025-26-T1",
                "skill_id": "problem_solving",
                "uncertainty_reason": "Conflicting evidence: some chunks support, others contradict",
                "routed_to_role": "staff",
                "draft_json": {"draft_label": "demonstrated", "draft_rationale": "Mixed evidence"},
                "evidence_pointers": [
                    {"type": "chunk_ref", "doc_id": "doc_demo_2", "chunk_idx": 3, "section": "Methods"},
                ],
            },
            {
                "scope_course_id": "COMP3100",
                "scope_term_id": "2025-26-T1",
                "skill_id": "data_analysis",
                "uncertainty_reason": "Low confidence score (0.42 < 0.7 threshold)",
                "routed_to_role": "staff",
                "draft_json": {"draft_label": "mentioned", "draft_rationale": "Marginal evidence"},
                "evidence_pointers": [],
            },
        ]

        with engine.begin() as conn:
            for t in tickets:
                conn.execute(
                    text("""
                        INSERT INTO review_tickets
                          (scope_course_id, scope_term_id, skill_id, uncertainty_reason,
                           routed_to_role, draft_json, evidence_pointers, status)
                        VALUES
                          (:cid, :tid, :sid, :reason, :role,
                           (:draft)::jsonb, (:ptrs)::jsonb, 'open')
                    """),
                    {
                        "cid": t["scope_course_id"],
                        "tid": t["scope_term_id"],
                        "sid": t["skill_id"],
                        "reason": t["uncertainty_reason"],
                        "role": t["routed_to_role"],
                        "draft": _json.dumps(t["draft_json"]),
                        "ptrs": _json.dumps(t["evidence_pointers"]),
                    },
                )
        print(f"  Created {len(tickets)} review tickets for COMP3000, COMP3100")
    except Exception as e:
        print(f"  WARNING: Could not insert review tickets via DB: {e}", file=sys.stderr)
        print("  (Tickets can be created manually via /review_tickets API)")


def seed_learning_resources(token):
    """P5: Seed demo learning resources for action recommendations."""
    print("[7b/N] Creating learning resources (P5)...")
    try:
        from backend.app.db.session import engine
        from sqlalchemy import text
        import json as _json

        resources = [
            {
                "title": "COMP3000 Privacy & Ethics Workshop",
                "resource_type": "workshop",
                "location": "HKU COMP3000 / Faculty workshop",
                "gap_type": "missing_proof",
                "skill_ids": ["HKU.SKILL.PRIVACY.v1", "HKU.SKILL.ACADEMIC_INTEGRITY.v1"],
            },
            {
                "title": "Data Analysis Lab (COMP3100)",
                "resource_type": "course",
                "location": "HKU COMP3100",
                "gap_type": "needs_strengthening",
                "skill_ids": ["HKU.SKILL.DATA_ANALYSIS.v1"],
            },
        ]
        with engine.begin() as conn:
            for r in resources:
                rid = str(__import__("uuid").uuid4())
                conn.execute(
                    text("""
                        INSERT INTO learning_resources
                        (resource_id, title, resource_type, location, gap_type)
                        VALUES (:rid, :title, :rtype, :loc, :gap)
                    """),
                    {"rid": rid, "title": r["title"], "rtype": r["resource_type"], "loc": r["location"], "gap": r["gap_type"]},
                )
                for sid in r["skill_ids"]:
                    conn.execute(
                        text("""
                            INSERT INTO resource_skill_map (resource_id, skill_id, gap_type)
                            VALUES (:rid, :sid, :gap)
                        """),
                        {"rid": rid, "sid": sid, "gap": r["gap_type"]},
                    )
        print(f"  Created {len(resources)} learning resources")
    except Exception as e:
        print(f"  WARNING: Could not seed learning resources: {e}", file=sys.stderr)


def seed_learning_resources(token):
    """P5: Seed demo learning resources for action recommendations."""
    print("[7b/N] Seeding learning resources…")
    try:
        from backend.app.db.session import engine
        from sqlalchemy import text
        import json as _json

        resources = [
            {
                "title": "COMP3000 Privacy Workshop",
                "resource_type": "workshop",
                "location": "HKU COMP3000 / Privacy module",
                "gap_type": "missing_proof",
                "skill_ids": ["HKU.SKILL.PRIVACY.v1"],
            },
            {
                "title": "Data Analysis Lab",
                "resource_type": "course",
                "location": "HKU DSCI / approved external MOOC",
                "gap_type": "needs_strengthening",
                "skill_ids": ["HKU.SKILL.DATA_ANALYSIS.v1"],
            },
        ]
        with engine.begin() as conn:
            for r in resources:
                rid = str(__import__("uuid").uuid4())
                conn.execute(
                    text("""
                        INSERT INTO learning_resources
                        (resource_id, title, resource_type, location, gap_type)
                        VALUES (:rid, :title, :rtype, :loc, :gap)
                    """),
                    {"rid": rid, "title": r["title"], "rtype": r["resource_type"], "loc": r["location"], "gap": r["gap_type"]},
                )
                for sid in r["skill_ids"]:
                    conn.execute(
                        text("INSERT INTO resource_skill_map (resource_id, skill_id, gap_type) VALUES (:rid, :sid, :gap)"),
                        {"rid": rid, "sid": sid, "gap": r["gap_type"]},
                    )
        print(f"  Created {len(resources)} learning resources")
    except Exception as e:
        if "learning_resources" in str(e).lower() or "does not exist" in str(e).lower():
            print("  (learning_resources table not yet migrated, skipping)")
        else:
            print(f"  WARNING: Could not seed learning resources: {e}", file=__import__("sys").stderr)


def verify(token):
    print("[8/N] Verifying setup…")
    # Staff courses
    try:
        staff_token_resp = _request("POST", "/bff/staff/auth/dev_login", {
            "subject_id": "staff_demo", "role": "staff",
            "course_ids": ["COMP3000", "COMP3100"], "term_id": "2025-26-T1"
        })
        staff_token = staff_token_resp["token"]
        courses = _request("GET", "/bff/staff/courses", token=staff_token)
        print(f"  Staff sees {courses.get('count', 0)} courses via BFF")
    except Exception as e:
        print(f"  WARNING: Staff verification failed: {e}", file=sys.stderr)

    # Programme coverage
    try:
        prog_token_resp = _request("POST", "/bff/programme/auth/dev_login", {
            "subject_id": "prog_leader_demo", "role": "programme_leader", "programme_id": "CSCI_MSC"
        })
        prog_token = prog_token_resp["token"]
        programmes = _request("GET", "/bff/programme/programmes", token=prog_token)
        print(f"  Programme leader sees {len(programmes.get('programmes', []))} programmes")
    except Exception as e:
        print(f"  WARNING: Programme verification failed: {e}", file=sys.stderr)

    # Admin health
    health = _request("GET", "/bff/admin/health", token=token)
    print(f"  Admin health: {health.get('status')} | stats: {health.get('stats', {})}")


def main():
    print("=" * 60)
    print("SkillSight P3 Demo Data Seed")
    print(f"API: {API}")
    print("=" * 60)

    token = get_admin_token()
    seed_faculty(token)
    seed_programmes(token)
    seed_terms(token)
    seed_courses(token)
    seed_users(token)
    seed_review_tickets(token)
    seed_learning_resources(token)
    verify(token)

    print("\n" + "=" * 60)
    print("SEED COMPLETE")
    print("  1 faculty (ENG)")
    print("  2 programmes (CSCI_MSC, DSCI_MSC)")
    print("  2 terms (2024-25-T1, 2025-26-T1)")
    print("  3 courses (COMP3000, COMP3100, DSCI3000)")
    print("  1 staff (staff_demo) with teaching relations")
    print("  1 programme_leader (prog_leader_demo)")
    print("  1 admin (admin_seed)")
    print("  ~3 review tickets (COMP3000, COMP3100)")
    print("=" * 60)


if __name__ == "__main__":
    main()
