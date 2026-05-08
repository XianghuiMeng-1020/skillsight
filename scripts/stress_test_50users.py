#!/usr/bin/env python3
"""
SkillSight Concurrent Load Test — 50 Simultaneous Users
Simulates a seminar scenario: 50 users register and perform core actions concurrently.

Usage:
  python3 scripts/stress_test_50users.py [--target local|prod]
  python3 scripts/stress_test_50users.py --target prod   # test production
  python3 scripts/stress_test_50users.py --target local  # test localhost:8001
"""

import asyncio
import aiohttp
import time
import sys
import statistics
from dataclasses import dataclass, field
from typing import List, Optional

# ─── Config ───────────────────────────────────────────────────────────────────
TARGET = "prod"
for i, arg in enumerate(sys.argv):
    if arg == "--target" and i + 1 < len(sys.argv):
        TARGET = sys.argv[i + 1]

BASE_URL = {
    "local": "http://localhost:8001",
    "prod":  "https://skillsight-api.onrender.com",
}.get(TARGET, "http://localhost:8001")

NUM_USERS        = 50
CONCURRENT_LIMIT = 50   # all at once
TTL_SECONDS      = 3600

print(f"\n{'='*60}")
print(f"  SkillSight Stress Test — {NUM_USERS} Concurrent Users")
print(f"  Target : {BASE_URL}")
print(f"{'='*60}\n")

# ─── Result tracking ──────────────────────────────────────────────────────────
@dataclass
class UserResult:
    user_id: str
    login_ok: bool = False
    login_ms: float = 0.0
    profile_ok: bool = False
    profile_ms: float = 0.0
    jobs_ok: bool = False
    jobs_ms: float = 0.0
    error: Optional[str] = None


async def simulate_user(session: aiohttp.ClientSession, user_num: int) -> UserResult:
    """Simulate one user: register → get profile → browse jobs."""
    uid = f"seminar_stress_{user_num:03d}@hku.hk"
    result = UserResult(user_id=uid)

    # ── Step 1: Register / Login ──────────────────────────────────────────────
    t0 = time.perf_counter()
    try:
        async with session.post(
            f"{BASE_URL}/bff/student/auth/dev_login",
            json={"subject_id": uid, "role": "student", "ttl_s": TTL_SECONDS},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            result.login_ms = (time.perf_counter() - t0) * 1000
            if resp.status == 200:
                data = await resp.json()
                token = data.get("token", "")
                result.login_ok = bool(token)
            else:
                body = await resp.text()
                result.error = f"login HTTP {resp.status}: {body[:120]}"
                return result
    except Exception as e:
        result.login_ms = (time.perf_counter() - t0) * 1000
        result.error = f"login exception: {e}"
        return result

    headers = {"Authorization": f"Bearer {token}"}

    # ── Step 2: Get skill profile ─────────────────────────────────────────────
    t1 = time.perf_counter()
    try:
        async with session.get(
            f"{BASE_URL}/bff/student/profile",
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            result.profile_ms = (time.perf_counter() - t1) * 1000
            result.profile_ok = resp.status in (200, 404)  # 404 = new user, still valid
    except Exception as e:
        result.profile_ms = (time.perf_counter() - t1) * 1000
        result.error = (result.error or "") + f" | profile exception: {e}"

    # ── Step 3: Browse job matches ────────────────────────────────────────────
    t2 = time.perf_counter()
    try:
        async with session.get(
            f"{BASE_URL}/bff/student/jobs/matches?limit=5",
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            result.jobs_ms = (time.perf_counter() - t2) * 1000
            result.jobs_ok = resp.status in (200, 404)
    except Exception as e:
        result.jobs_ms = (time.perf_counter() - t2) * 1000
        result.error = (result.error or "") + f" | jobs exception: {e}"

    return result


def percentile(data: List[float], p: float) -> float:
    if not data:
        return 0.0
    return statistics.quantiles(data, n=100)[int(p) - 1] if len(data) > 1 else data[0]


async def run_test():
    connector = aiohttp.TCPConnector(limit=NUM_USERS, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:

        # ── Warm-up: single health check ─────────────────────────────────────
        print("Checking backend health...")
        try:
            async with session.get(f"{BASE_URL}/health", timeout=aiohttp.ClientTimeout(total=10)) as r:
                health = await r.json()
                print(f"  Health: {health.get('status','?')} ✓\n")
        except Exception as e:
            print(f"  WARNING: health check failed ({e}). Proceeding anyway.\n")

        # ── Launch all 50 users simultaneously ────────────────────────────────
        print(f"Launching {NUM_USERS} users simultaneously...")
        wall_start = time.perf_counter()

        tasks = [simulate_user(session, i + 1) for i in range(NUM_USERS)]
        results: List[UserResult] = await asyncio.gather(*tasks)

        wall_elapsed = (time.perf_counter() - wall_start) * 1000

    # ─── Analysis ─────────────────────────────────────────────────────────────
    login_ok   = [r for r in results if r.login_ok]
    login_fail = [r for r in results if not r.login_ok]
    prof_ok    = [r for r in results if r.profile_ok]
    jobs_ok    = [r for r in results if r.jobs_ok]
    errors     = [r for r in results if r.error]

    login_times   = [r.login_ms for r in login_ok]
    profile_times = [r.profile_ms for r in prof_ok]
    jobs_times    = [r.jobs_ms for r in jobs_ok]

    print(f"\n{'='*60}")
    print(f"  RESULTS  (wall clock: {wall_elapsed/1000:.2f}s total)")
    print(f"{'='*60}")

    def stats_line(label: str, times: List[float], ok: int) -> None:
        if times:
            avg  = statistics.mean(times)
            med  = statistics.median(times)
            p95  = percentile(times, 95)
            p99  = percentile(times, 99)
            mn   = min(times)
            mx   = max(times)
            print(f"\n  {label}")
            print(f"    Success : {ok}/{NUM_USERS} ({ok/NUM_USERS*100:.0f}%)")
            print(f"    Min     : {mn:.0f} ms")
            print(f"    Median  : {med:.0f} ms")
            print(f"    Avg     : {avg:.0f} ms")
            print(f"    P95     : {p95:.0f} ms")
            print(f"    P99     : {p99:.0f} ms")
            print(f"    Max     : {mx:.0f} ms")
        else:
            print(f"\n  {label}")
            print(f"    Success : 0/{NUM_USERS} (0%)")

    stats_line("Step 1 — Register/Login (POST /bff/student/auth/dev_login)", login_times, len(login_ok))
    stats_line("Step 2 — Get Profile   (GET  /bff/student/profile)",         profile_times, len(prof_ok))
    stats_line("Step 3 — Browse Jobs   (GET  /bff/student/jobs/matches)",    jobs_times,    len(jobs_ok))

    # ── Error details ─────────────────────────────────────────────────────────
    if errors:
        print(f"\n  ERRORS ({len(errors)} users):")
        for r in errors[:10]:
            print(f"    {r.user_id}: {r.error}")
        if len(errors) > 10:
            print(f"    ... and {len(errors)-10} more")
    else:
        print(f"\n  ERRORS: none ✓")

    # ── Seminar readiness verdict ─────────────────────────────────────────────
    login_rate = len(login_ok) / NUM_USERS
    p95_login  = percentile(login_times, 95) if login_times else 9999

    print(f"\n{'='*60}")
    print(f"  SEMINAR READINESS VERDICT")
    print(f"{'='*60}")
    if login_rate >= 0.95 and p95_login <= 3000:
        print(f"  ✅  READY  — {login_rate*100:.0f}% login success, P95={p95_login:.0f}ms")
        print(f"      System can comfortably handle 50 concurrent attendees.")
    elif login_rate >= 0.80:
        print(f"  ⚠️  MARGINAL — {login_rate*100:.0f}% success, P95={p95_login:.0f}ms")
        print(f"      Acceptable but recommend staggered logins.")
    else:
        print(f"  ❌  NOT READY — {login_rate*100:.0f}% success, P95={p95_login:.0f}ms")
        print(f"      Investigate errors above before the seminar.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(run_test())
