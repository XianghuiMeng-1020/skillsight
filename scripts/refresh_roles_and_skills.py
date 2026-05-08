#!/usr/bin/env python3
"""
Refresh roles and skills from existing seed JSON (Gap 2).
Re-imports skills from backend/data/seeds/skills_comprehensive.json and
roles from roles_enriched_*_linkedin.json (or roles_import_*_linkedin.json).
Can be run on a schedule (e.g. monthly) to update job-market data.

Usage:
  python3 scripts/refresh_roles_and_skills.py
  SKILLSIGHT_API=http://127.0.0.1:8001 python3 scripts/refresh_roles_and_skills.py
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
                    if attempt < retries - 1:
                        time.sleep(2)
                        continue
                    return None
                return r.json()
            body = json.dumps(data).encode() if data is not None else None
            req = urllib_request.Request(url, data=body, headers=headers, method=method)
            with urllib_request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except Exception:
            if attempt < retries - 1:
                time.sleep(2)
    return None


def main() -> None:
    health = _req("GET", "/health")
    if not health:
        print(f"Backend not reachable at {API}. Start it first.", file=sys.stderr)
        sys.exit(1)
    print(f"Backend OK: {API}")

    token = None
    res = _req("POST", "/bff/admin/auth/dev_login", {"subject_id": "admin_loader", "role": "admin"})
    if res:
        token = res.get("token") or res.get("access_token") or ""

    # ---- 1. Skills ----
    skills_file = REPO_ROOT / "backend" / "data" / "seeds" / "skills_comprehensive.json"
    if skills_file.exists():
        skills = json.loads(skills_file.read_text())
        for s in skills:
            if isinstance(s.get("aliases"), list):
                s["aliases"] = json.dumps(s["aliases"])
            if isinstance(s.get("level_rubric"), dict):
                s["level_rubric"] = json.dumps(s["level_rubric"])
        print(f"\n[1/2] Importing {len(skills)} skills...")
        res = _req("POST", "/skills/import", skills, token)
        if res:
            print(f"  Skills: {res}")
        else:
            for s in skills:
                _req("POST", "/skills/import", [s], token)
            print("  Skills: imported individually")
    else:
        print(f"[1/2] Skills file not found: {skills_file}", file=sys.stderr)

    # ---- 2. Roles ----
    for prog in ["basc_sds", "bsc_im"]:
        roles_file = REPO_ROOT / f"roles_enriched_{prog}_linkedin.json"
        if not roles_file.exists():
            roles_file = REPO_ROOT / f"roles_import_{prog}_linkedin.json"
        if roles_file.exists():
            roles = json.loads(roles_file.read_text())
            print(f"\n[2/2] Importing {len(roles)} roles for {prog}...")
            res = _req("POST", "/roles/import", roles, token)
            if res:
                print(f"  Roles ({prog}): {res}")
            else:
                print(f"  Roles import failed for {prog}", file=sys.stderr)
        else:
            print(f"  No roles file for {prog}", file=sys.stderr)

    print("\n=== Refresh complete ===")


if __name__ == "__main__":
    main()
