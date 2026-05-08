#!/usr/bin/env bash
# SkillSight Seminar Deployment Script
# Usage: ./scripts/deploy_seminar.sh [RENDER_API_URL]
# 
# Steps:
#   1. Rebuild frontend with the correct NEXT_PUBLIC_API_URL
#   2. Deploy to Cloudflare Pages via Wrangler
#   3. Trigger Render backend redeploy (requires `render` CLI login)
#
# Prerequisites:
#   brew install wrangler   (for Cloudflare Pages deployment)
#   render login            (for Render CLI)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RENDER_API_URL="${1:-${RENDER_API_URL:-}}"
CF_PROJECT="${CF_PROJECT:-skillsight-230}"

echo "=== SkillSight Seminar Deploy ==="

# ── 1. Validate Render URL ──────────────────────────────────────────────────
if [ -z "$RENDER_API_URL" ]; then
  echo ""
  echo "No RENDER_API_URL provided. Trying to detect from Render CLI..."
  if command -v render &>/dev/null; then
    RENDER_API_URL=$(render services --output json 2>/dev/null \
      | python3 -c "import sys,json; svcs=json.load(sys.stdin); \
        [print('https://'+s['service']['serviceDetails']['url'].replace('https://','')) \
        for s in svcs if s['service']['name']=='skillsight-api']" 2>/dev/null || true)
  fi
  if [ -z "$RENDER_API_URL" ]; then
    echo ""
    echo "Could not auto-detect Render API URL."
    echo "Please run:  ./scripts/deploy_seminar.sh https://YOUR-RENDER-URL.onrender.com"
    exit 1
  fi
fi

echo "Render API URL: $RENDER_API_URL"

# ── 2. Rebuild frontend with production API URL ─────────────────────────────
echo ""
echo "== Building frontend (NEXT_PUBLIC_API_URL=$RENDER_API_URL) =="
cd "$REPO_ROOT/web"
NEXT_PUBLIC_API_URL="$RENDER_API_URL" npm run build
echo "Frontend built → web/out/"

# ── 3. Deploy frontend to Cloudflare Pages ──────────────────────────────────
if command -v wrangler &>/dev/null; then
  echo ""
  echo "== Deploying to Cloudflare Pages ($CF_PROJECT) =="
  wrangler pages deploy out --project-name "$CF_PROJECT" --commit-dirty=true
  echo "Frontend deployed."
else
  echo ""
  echo "Wrangler not found. To deploy to Cloudflare Pages manually:"
  echo "  cd web && npx wrangler pages deploy out --project-name skillsight-230"
  echo ""
  echo "Or drag-and-drop web/out/ at: https://dash.cloudflare.com → Pages → $CF_PROJECT → Deployments"
fi

# ── 4. Trigger Render backend redeploy ──────────────────────────────────────
if command -v render &>/dev/null; then
  echo ""
  echo "== Triggering Render backend redeploy =="
  render services | grep skillsight-api || true
  echo "To redeploy, run: render deploys create <service-id>"
  echo "Or push to GitHub — Render auto-deploys on push."
else
  echo ""
  echo "Render CLI not found. To redeploy backend:"
  echo "  1. Go to https://dashboard.render.com"
  echo "  2. Find 'skillsight-api' → Manual Deploy → Deploy latest commit"
fi

echo ""
echo "=== Deploy complete ==="
echo "Frontend: https://39785649.skillsight-230-97u.pages.dev"
echo "Backend:  $RENDER_API_URL"
echo ""
echo "Share the Cloudflare Pages URL with seminar attendees."
echo "They can log in with any email address — no pre-registration needed."
