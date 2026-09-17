#!/usr/bin/env bash
#
# Deploy BLUEBAN 813 to Cloudflare Pages as a static site.
#
# The API is read-only — it serves artefacts the offline pipeline already wrote —
# so the whole product ships as files with no server to run or pay for.
#
#   1. bake outputs/ into apps/web/public/pipeline
#   2. static-export the Next.js app to apps/web/out
#   3. upload apps/web/out to Cloudflare Pages
#
# Requires: wrangler authenticated (`npx wrangler login`) and CLOUDFLARE_ACCOUNT_ID
# set, because the account has more than one entry and wrangler cannot choose
# non-interactively.
#
# Usage:
#   CLOUDFLARE_ACCOUNT_ID=<id> bash scripts/deploy_cloudflare.sh [branch]
set -euo pipefail

PROJECT="${BLUEBAN_PAGES_PROJECT:-blueban813}"
BRANCH="${1:-main}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEB="$ROOT/apps/web"

if [[ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ]]; then
  echo "CLOUDFLARE_ACCOUNT_ID is not set." >&2
  echo "Available accounts:" >&2
  npx wrangler whoami 2>&1 | sed -n '/Account Name/,/└/p' >&2 || true
  exit 1
fi

echo "==> 1/3  baking pipeline artefacts"
python "$ROOT/scripts/build_static_site.py"

echo
echo "==> 2/3  static export"
cd "$WEB"
rm -rf out .next
BLUEBAN_STATIC=1 NEXT_PUBLIC_DATA_MODE=static npx next build

if [[ ! -f "$WEB/out/index.html" ]]; then
  echo "Export produced no out/index.html; aborting." >&2
  exit 1
fi

echo
echo "==> 3/3  upload to Cloudflare Pages project '$PROJECT'"
cd "$ROOT"
npx wrangler pages deploy "$WEB/out" \
  --project-name "$PROJECT" \
  --branch "$BRANCH" \
  --commit-dirty=true

echo
echo "Deployed. To attach the custom domain the first time:"
echo "  npx wrangler pages domain add blue.kanbanstudios.ae --project-name $PROJECT"
