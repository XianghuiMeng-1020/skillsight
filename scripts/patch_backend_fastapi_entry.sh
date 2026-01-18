#!/usr/bin/env bash
set -euo pipefail

ROOT="$(pwd)"
mkdir -p scripts

# Ensure package markers
mkdir -p backend/app schemas
touch backend/__init__.py backend/app/__init__.py schemas/__init__.py

TARGET="backend/app/main.py"

# If main exists, back it up once per run
if [[ -f "$TARGET" ]]; then
  cp "$TARGET" "${TARGET}.bak.$(date -u +%Y%m%d%H%M%S)"
fi

cat > "$TARGET" <<'PY'
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# SkillSight schemas (Week1 Day3)
# NOTE: repo-root/ is expected to be on PYTHONPATH when running uvicorn from repo root.
from schemas.skillsight_models import Skill, Role, EvidencePointer, AuditLog, ConsentRecord  # noqa: F401

app = FastAPI(title="SkillSight API", version="0.1.0")

# Local dev CORS (tighten later)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/schemas/summary")
def schemas_summary():
    """
    Returns the JSONSchema filenames generated under packages/schemas/.
    This is a simple discoverability endpoint for the MVP.
    """
    return {
        "Skill": "packages/schemas/Skill.schema.json",
        "Role": "packages/schemas/Role.schema.json",
        "EvidencePointer": "packages/schemas/EvidencePointer.schema.json",
        "AuditLog": "packages/schemas/AuditLog.schema.json",
        "ConsentRecord": "packages/schemas/ConsentRecord.schema.json",
    }
PY

echo "✅ Patched $TARGET"

echo ""
echo "Run backend (from repo root):"
echo "  source backend/.venv/bin/activate"
echo "  uvicorn backend.app.main:app --reload --port 8000"
echo ""
echo "Then open:"
echo "  http://localhost:8000/health"
echo "  http://localhost:8000/docs"
