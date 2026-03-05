#!/usr/bin/env python3
"""
Stress test: 30 concurrent users hitting different features simultaneously.
"""
import concurrent.futures
import json
import sys
import time

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False
    import urllib.request
    import urllib.error

API = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8001"
NUM_USERS = 30


def api_httpx(client, method, path, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        if method == "GET":
            resp = client.get(f"{API}{path}", headers=headers, timeout=15)
        else:
            resp = client.post(f"{API}{path}", headers=headers, json=body, timeout=15)
        return resp.status_code, resp.json() if resp.status_code < 500 else {"error": resp.text[:200]}
    except Exception as e:
        return 0, {"error": str(e)[:200]}


def api_urllib(method, path, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(f"{API}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_text = ""
        try:
            body_text = e.read().decode()[:200]
        except Exception:
            pass
        return e.code, {"error": f"HTTP {e.code}: {body_text}"}
    except Exception as e:
        return 0, {"error": str(e)[:200]}


def user_session(user_id: int):
    session_start = time.time()
    steps = []
    roles = ["student", "staff", "admin", "programme_leader"]
    role = roles[user_id % len(roles)]
    prefix_map = {
        "student": "/bff/student",
        "staff": "/bff/staff",
        "admin": "/bff/admin",
        "programme_leader": "/bff/programme",
    }
    prefix = prefix_map[role]

    if HAS_HTTPX:
        client = httpx.Client(http2=False)
        do = lambda m, p, b=None, token=None: api_httpx(client, m, p, b, token)
    else:
        do = lambda m, p, b=None, token=None: api_urllib(m, p, b, token)

    # Step 1: Dev login
    t0 = time.time()
    status, data = do("POST", f"{prefix}/auth/dev_login", {
        "subject_id": f"stress_user_{user_id}",
        "role": role,
    })
    token = data.get("token", "") if isinstance(data, dict) else ""
    steps.append(("login", status, time.time() - t0))

    # Step 2: Health
    t0 = time.time()
    status, _ = do("GET", "/health")
    steps.append(("health", status, time.time() - t0))

    # Step 3: Skills
    t0 = time.time()
    status, _ = do("GET", "/skills?limit=10", token=token)
    steps.append(("skills", status, time.time() - t0))

    # Step 4: Roles
    t0 = time.time()
    status, _ = do("GET", "/roles?limit=10", token=token)
    steps.append(("roles", status, time.time() - t0))

    # Step 5: Documents
    t0 = time.time()
    status, _ = do("GET", "/documents?limit=5", token=token)
    steps.append(("documents", status, time.time() - t0))

    # Step 6: Stats
    t0 = time.time()
    status, _ = do("GET", "/stats")
    steps.append(("stats", status, time.time() - t0))

    # Step 7: Overview
    t0 = time.time()
    status, _ = do("GET", "/api/overview")
    steps.append(("overview", status, time.time() - t0))

    # Step 8: BFF health
    t0 = time.time()
    status, _ = do("GET", f"{prefix}/health", token=token)
    steps.append(("bff_health", status, time.time() - t0))

    if HAS_HTTPX:
        client.close()

    total_time = time.time() - session_start
    ok_count = sum(1 for _, s, _ in steps if 200 <= s < 500)
    return {
        "user_id": user_id,
        "role": role,
        "total_time_s": round(total_time, 3),
        "steps_ok": ok_count,
        "steps_total": len(steps),
        "steps": [(name, status, round(t, 3)) for name, status, t in steps],
    }


def main():
    print(f"=== SkillSight Stress Test: {NUM_USERS} concurrent users ===")
    print(f"API: {API}")
    print(f"HTTP client: {'httpx' if HAS_HTTPX else 'urllib'}\n")

    # Warm up
    if HAS_HTTPX:
        c = httpx.Client()
        r = c.get(f"{API}/health", timeout=10)
        print(f"Warmup: {r.status_code}")
        c.close()
    else:
        api_urllib("GET", "/health")
        print("Warmup: done")

    start = time.time()
    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=NUM_USERS) as pool:
        futures = {pool.submit(user_session, i): i for i in range(NUM_USERS)}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            results.append(result)

    elapsed = time.time() - start

    total_steps = sum(r["steps_total"] for r in results)
    ok_steps = sum(r["steps_ok"] for r in results)
    avg_session = sum(r["total_time_s"] for r in results) / len(results)
    max_session = max(r["total_time_s"] for r in results)
    min_session = min(r["total_time_s"] for r in results)

    step_times = {}
    for r in results:
        for name, status, t in r["steps"]:
            step_times.setdefault(name, []).append((t, status))

    print(f"\n{'='*60}")
    print(f"  Total wall time:    {elapsed:.2f}s")
    print(f"  Users:              {NUM_USERS}")
    print(f"  Total requests:     {total_steps}")
    print(f"  Successful:         {ok_steps}/{total_steps} ({100*ok_steps/total_steps:.1f}%)")
    print(f"  Avg session time:   {avg_session:.3f}s")
    print(f"  Min/Max session:    {min_session:.3f}s / {max_session:.3f}s")
    print(f"  Throughput:         {total_steps/elapsed:.1f} req/s")
    print(f"{'='*60}")

    print(f"\n{'Endpoint':<15} {'OK':<5} {'Fail':<5} {'Avg(ms)':<10} {'p95(ms)':<10} {'Max(ms)':<10}")
    print("-" * 60)
    for name in ["login", "health", "skills", "roles", "documents", "stats", "overview", "bff_health"]:
        times_statuses = step_times.get(name, [])
        if not times_statuses:
            continue
        times = [t for t, _ in times_statuses]
        ok = sum(1 for _, s in times_statuses if 200 <= s < 500)
        fail = len(times_statuses) - ok
        times_sorted = sorted(times)
        avg_ms = sum(times) / len(times) * 1000
        p95_idx = min(int(len(times_sorted) * 0.95), len(times_sorted) - 1)
        p95_ms = times_sorted[p95_idx] * 1000
        max_ms = max(times) * 1000
        print(f"{name:<15} {ok:<5} {fail:<5} {avg_ms:<10.1f} {p95_ms:<10.1f} {max_ms:<10.1f}")

    failed_users = [r for r in results if r["steps_ok"] < r["steps_total"]]
    if failed_users:
        print(f"\n{len(failed_users)} users had failures:")
        for r in failed_users[:5]:
            failed_names = [(n, s) for n, s, _ in r["steps"] if not (200 <= s < 500)]
            print(f"  User {r['user_id']} ({r['role']}): {failed_names}")
    else:
        print(f"\nAll {NUM_USERS} users completed all steps successfully!")

    success_rate = ok_steps / total_steps * 100
    if success_rate >= 95 and max_session < 30:
        print(f"\nPASS: {success_rate:.1f}% success rate, max session {max_session:.1f}s")
        return 0
    else:
        print(f"\nFAIL: {success_rate:.1f}% success rate, max session {max_session:.1f}s")
        return 1


if __name__ == "__main__":
    sys.exit(main())
