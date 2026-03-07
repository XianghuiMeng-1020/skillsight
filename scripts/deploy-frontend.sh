#!/bin/bash
set -e

cd "$(dirname "$0")/../web"

echo "==> Building frontend with production API URL..."
NEXT_PUBLIC_API_URL=https://skillsight-api.onrender.com npm run build

echo "==> Deploying to Cloudflare Pages..."
wrangler pages deploy out --project-name=skillsight --commit-dirty=true

echo "==> Done! Frontend deployed to https://skillsight-230.pages.dev"
