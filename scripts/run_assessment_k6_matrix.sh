#!/usr/bin/env bash
set -euo pipefail

API_BASE="${API_BASE:-${1:-http://127.0.0.1:8001}}"
TOKEN="${TOKEN:-}"
USER_ID="${USER_ID:-perf_user}"
OUT_DIR="${OUT_DIR:-artifacts/perf}"
SMOKE="${SMOKE:-0}"

mkdir -p "${OUT_DIR}"

if [[ "${SMOKE}" == "1" || "${SMOKE}" == "true" ]]; then
  echo "== Smoke mode: 10 RPS, 15s =="
  docker run --rm --network host \
    -e API_BASE="${API_BASE}" \
    -e TOKEN="${TOKEN}" \
    -e USER_ID="${USER_ID}" \
    -e SMOKE=1 \
    -e ASSESSMENT_TYPE=programming \
    -v "$(pwd):/work" \
    grafana/k6:latest \
    run /work/scripts/perf/assessment_submit_stress.js \
    --summary-export "/work/${OUT_DIR}/k6-smoke.json"
  echo "Smoke completed -> ${OUT_DIR}/k6-smoke.json"
  exit 0
fi

for rps in 100 300 500; do
  echo "== Running k6 at ${rps} RPS =="
  docker run --rm --network host \
    -e API_BASE="${API_BASE}" \
    -e TOKEN="${TOKEN}" \
    -e USER_ID="${USER_ID}" \
    -e TARGET_RPS="${rps}" \
    -e STAGE_SECONDS=60 \
    -e ASSESSMENT_TYPE=programming \
    -v "$(pwd):/work" \
    grafana/k6:latest \
    run /work/scripts/perf/assessment_submit_stress.js \
    --summary-export "/work/${OUT_DIR}/k6-${rps}.json"
done

echo "k6 matrix completed. reports -> ${OUT_DIR}"
