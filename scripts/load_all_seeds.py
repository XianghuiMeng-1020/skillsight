#!/usr/bin/env python3
"""
One-shot loader: import all seed data into SkillSight.
  1. Skills (18 comprehensive skills)
  2. Roles (43 enriched LinkedIn roles, split by programme)
  3. Courses (40 HKU courses from BASc(SDS) + BSc(IM))
  4. Course-skill mappings (52 mappings)

Usage:
  python3 scripts/load_all_seeds.py
  SKILLSIGHT_API=http://127.0.0.1:8001 python3 scripts/load_all_seeds.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    import urllib.request as urllib_request
    HAS_REQUESTS = False

REPO_ROOT = Path(__file__).resolve().parents[1]
API = os.getenv("SKILLSIGHT_API", "http://127.0.0.1:8001")


def _req(method: str, path: str, data=None, token: str | None = None, retries: int = 3):
    url = f"{API}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    for attempt in range(retries):
        try:
            if HAS_REQUESTS:
                r = requests.request(method, url, json=data, headers=headers, timeout=30,
                                     proxies={"http": None, "https": None})
                if r.status_code >= 400:
                    print(f"  {method} {path} -> {r.status_code}: {r.text[:200]}", file=sys.stderr)
                    if attempt < retries - 1:
                        time.sleep(2)
                        continue
                    return None
                return r.json()
            body = json.dumps(data).encode() if data is not None else None
            req = urllib_request.Request(url, data=body, headers=headers, method=method)
            with urllib_request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except Exception as e:
            print(f"  {method} {path} attempt {attempt+1} error: {e}", file=sys.stderr)
            if attempt < retries - 1:
                time.sleep(2)
    return None


def _login_admin() -> str:
    res = _req("POST", "/bff/admin/auth/dev_login", {"subject_id": "admin_loader", "role": "admin"})
    if not res:
        print("Failed to login as admin", file=sys.stderr)
        sys.exit(1)
    return res.get("token") or res.get("access_token") or ""


def main() -> None:
    # Health check
    health = _req("GET", "/health")
    if not health:
        print(f"Backend not reachable at {API}. Start it first.", file=sys.stderr)
        sys.exit(1)
    print(f"Backend OK: {API}")

    token = _login_admin()
    if not token:
        print("No token from dev_login, trying without auth...", file=sys.stderr)

    headers_with_token = {"Authorization": f"Bearer {token}"} if token else {}

    # ---- 1. Import Skills ----
    skills_file = REPO_ROOT / "backend" / "data" / "seeds" / "skills_comprehensive.json"
    if skills_file.exists():
        skills = json.loads(skills_file.read_text())
        for s in skills:
            if isinstance(s.get("aliases"), list):
                s["aliases"] = json.dumps(s["aliases"])
            if isinstance(s.get("level_rubric"), dict):
                s["level_rubric"] = json.dumps(s["level_rubric"])
        print(f"\n[1/4] Importing {len(skills)} skills...")
        res = _req("POST", "/skills/import", skills, token)
        if res:
            print(f"  Skills: {res}")
        else:
            print("  Skills import failed, trying individual...", file=sys.stderr)
            for s in skills:
                _req("POST", "/skills/import", [s], token)
    else:
        print(f"[1/4] Skills file not found: {skills_file}", file=sys.stderr)

    # ---- 2. Import Roles ----
    for prog in ["basc_sds", "bsc_im"]:
        roles_file = REPO_ROOT / f"roles_enriched_{prog}_linkedin.json"
        if not roles_file.exists():
            roles_file = REPO_ROOT / f"roles_import_{prog}_linkedin.json"
        if roles_file.exists():
            roles = json.loads(roles_file.read_text())
            print(f"\n[2/4] Importing {len(roles)} roles for {prog}...")
            res = _req("POST", "/roles/import", roles, token)
            if res:
                print(f"  Roles ({prog}): {res}")
            else:
                print(f"  Roles import failed for {prog}", file=sys.stderr)
        else:
            print(f"  No roles file for {prog}", file=sys.stderr)

    # ---- 3. Import Courses ----
    courses_file = REPO_ROOT / "backend" / "data" / "seeds" / "courses_hku.json"
    if courses_file.exists():
        courses = json.loads(courses_file.read_text())
        print(f"\n[3/4] Importing {len(courses)} courses...")
        ok = 0
        for c in courses:
            payload = {
                "course_id": c["course_id"],
                "course_name": c["course_name"],
                "description": f"{c.get('category', '')} | {c.get('programme', '')} | {c.get('assessment', '')} | {c.get('credits', 6)} credits",
                "programme_id": None,
                "faculty_id": None,
                "term_id": None,
            }
            res = _req("POST", "/bff/admin/onboarding/course", payload, token)
            if res and res.get("ok"):
                ok += 1
        print(f"  Courses imported: {ok}/{len(courses)}")
    else:
        print(f"[3/4] Courses file not found: {courses_file}", file=sys.stderr)

    # ---- 4. Import Course-Skill Map ----
    csmap_file = REPO_ROOT / "backend" / "data" / "seeds" / "course_skill_map.json"
    if csmap_file.exists():
        csmap = json.loads(csmap_file.read_text())
        print(f"\n[4/4] Importing {len(csmap)} course-skill mappings...")
        ok = 0
        for m in csmap:
            try:
                if HAS_REQUESTS:
                    r = requests.post(
                        f"{API}/course-skill-map",
                        json={"course_id": m["course_id"], "skill_id": m["skill_id"],
                              "relevance": m.get("relevance", "primary")},
                        headers={"Content-Type": "application/json",
                                 **({"Authorization": f"Bearer {token}"} if token else {})},
                        timeout=10,
                        proxies={"http": None, "https": None},
                    )
                    if r.status_code < 400:
                        ok += 1
            except Exception:
                pass
        print(f"  Course-skill mappings: {ok}/{len(csmap)}")
    else:
        print(f"[4/4] Course-skill map not found: {csmap_file}", file=sys.stderr)

    # ---- 5. Seed Resume Templates (DB + DOCX files) ----
    seed_resume = REPO_ROOT / "scripts" / "seed_resume_templates.py"
    if seed_resume.exists():
        print("\n[5/5] Seeding resume templates...")
        import subprocess
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_ROOT)
        r = subprocess.run(
            [sys.executable, str(seed_resume)],
            cwd=str(REPO_ROOT),
            env=env,
            timeout=30,
        )
        if r.returncode != 0:
            print("  Resume templates seed failed (run alembic upgrade head first?)", file=sys.stderr)
    else:
        print("\n[5/5] seed_resume_templates.py not found, skipping.")

    # ---- Summary ----
    print("\n=== Import Complete ===")
    skills_res = _req("GET", "/skills?limit=100", token=token)
    roles_res = _req("GET", "/roles?limit=100", token=token)
    courses_res = _req("GET", "/courses?limit=100", token=token)
    print(f"  Skills in DB:  {skills_res.get('count', '?') if skills_res else '?'}")
    print(f"  Roles in DB:   {roles_res.get('count', '?') if roles_res else '?'}")
    print(f"  Courses in DB: {courses_res.get('count', '?') if courses_res else '?'}")
    print("\nDone!")


if __name__ == "__main__":
    main()
