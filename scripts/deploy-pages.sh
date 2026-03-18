#!/usr/bin/env bash
# Deploy static frontend to Cloudflare Pages (https://skillsight-230.pages.dev)
# Requires: CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID (or wrangler login)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_URL="${NEXT_PUBLIC_API_URL:-https://skillsight-backend-production.up.railway.app}"
PROJECT="${CF_PAGES_PROJECT:-skillsight-230}"
cd "$ROOT/web"
echo "Building with NEXT_PUBLIC_API_URL=$API_URL"
NEXT_PUBLIC_API_URL="$API_URL" npm run build
echo "Deploying to Cloudflare Pages project: $PROJECT"
npx --yes wrangler pages deploy out --project-name="$PROJECT" --commit-dirty=true
echo "Done. Open https://${PROJECT}.pages.dev"
