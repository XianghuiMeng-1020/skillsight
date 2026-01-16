#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../backend"
source .venv/bin/activate
exec python3 worker.py
