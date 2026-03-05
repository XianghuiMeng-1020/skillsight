#!/usr/bin/env bash
# Pack artifact integrity gate – fail-closed
# Verifies required logs exist and are non-empty; Playwright report dir has expected files.
#
# Usage: ./scripts/verify_pack_artifact_integrity.sh ARTIFACT_DIR
#   ARTIFACT_DIR: e.g. artifacts/go_live_baseline_p5/YYYYMMDD_HHMMSS
#
# Exit 0: all checks pass
# Exit 1: missing/empty file or unexpected state; prints diagnostics
# Bash 3.2 compatible.

set -e
set -u

ART_DIR="${1:-}"
if [ -z "$ART_DIR" ] || [ ! -d "$ART_DIR" ]; then
  echo "[FAIL] ARTIFACT_DIR required and must exist: $ART_DIR"
  exit 1
fi

LOG_DIR="${ART_DIR}/LOGS"
FAIL=0

check_file() {
  local f="$1"
  local desc="${2:-$f}"
  if [ ! -f "$f" ]; then
    echo "[FAIL] Missing: $desc"
    FAIL=1
    return 1
  fi
  if [ ! -s "$f" ]; then
    echo "[FAIL] Empty: $desc"
    FAIL=1
    return 1
  fi
  return 0
}

echo "=== Pack Artifact Integrity Gate ==="
echo "ART_DIR=$ART_DIR"

# Required logs (non-empty)
check_file "$LOG_DIR/decision12_pytest.txt" "LOGS/decision12_pytest.txt" || true
check_file "$LOG_DIR/check_decision_1_2.log" "LOGS/check_decision_1_2.log" || true
check_file "$LOG_DIR/check_refusal_contract.log" "LOGS/check_refusal_contract.log" || true
check_file "$LOG_DIR/change_log_check.log" "LOGS/change_log_check.log" || true
check_file "$LOG_DIR/check_human_review.log" "LOGS/check_human_review.log" || true
check_file "$LOG_DIR/bootstrap.log" "LOGS/bootstrap.log" || true

# At least one of: backend.log, web.log, frontend_prod_build.log
if [ ! -f "$LOG_DIR/backend.log" ] && [ ! -f "$LOG_DIR/web.log" ] && [ ! -f "$LOG_DIR/frontend_prod_build.log" ]; then
  echo "[FAIL] At least one of backend.log, web.log, frontend_prod_build.log must exist"
  FAIL=1
fi

# P0/P1 verification outputs
check_file "$ART_DIR/P0_VERIFICATION_OUTPUT.txt" "P0_VERIFICATION_OUTPUT.txt" || true
[ -f "$ART_DIR/P1_VERIFICATION_OUTPUT.txt" ] && check_file "$ART_DIR/P1_VERIFICATION_OUTPUT.txt" "P1_VERIFICATION_OUTPUT.txt" || true

# SUMMARY.md
check_file "$ART_DIR/SUMMARY.md" "SUMMARY.md" || true

# Playwright: expect P5_E2E dir or P5_UI_E2E_OUTPUT.txt
if [ -f "$ART_DIR/P5_UI_E2E_OUTPUT.txt" ]; then
  check_file "$ART_DIR/P5_UI_E2E_OUTPUT.txt" "P5_UI_E2E_OUTPUT.txt" || true
fi
if [ -d "$ART_DIR/P5_E2E" ]; then
  # At least one file in E2E results (screenshots, videos, or report)
  E2E_COUNT=$(find "$ART_DIR/P5_E2E" -type f 2>/dev/null | wc -l | tr -d ' ')
  if [ "${E2E_COUNT:-0}" -eq 0 ]; then
    echo "[WARN] P5_E2E directory empty (no report files)"
  fi
fi

# Refusal contract must show [PASS]
if [ -f "$LOG_DIR/check_refusal_contract.log" ]; then
  if ! grep -q "\[PASS\]" "$LOG_DIR/check_refusal_contract.log" 2>/dev/null; then
    echo "[FAIL] LOGS/check_refusal_contract.log missing [PASS]"
    echo "  --- Last 20 lines ---"
    tail -20 "$LOG_DIR/check_refusal_contract.log" 2>/dev/null || true
    FAIL=1
  fi
fi

# Diagnostics on failure
if [ "$FAIL" -ne 0 ]; then
  echo ""
  echo "=== Diagnostics ==="
  echo "Contents of $ART_DIR:"
  ls -la "$ART_DIR" 2>/dev/null || true
  echo ""
  echo "Contents of $LOG_DIR:"
  ls -la "$LOG_DIR" 2>/dev/null || true
  if [ -f "$ART_DIR/FAILURE_REPORT.txt" ]; then
    echo ""
    echo "--- FAILURE_REPORT.txt ---"
    cat "$ART_DIR/FAILURE_REPORT.txt" 2>/dev/null || true
  fi
  exit 1
fi

echo ""
echo "[PASS] Pack artifact integrity gate complete"
exit 0
