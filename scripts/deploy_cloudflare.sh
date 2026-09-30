#!/usr/bin/env bash
#
# Deploy BLUEBAN 813 to Cloudflare Pages as a static site.
#
# The hosted build has no server: every visitor gets a private in-browser
# workspace seeded from the pipeline outputs, so the product ships as files.
#
#   1. bake outputs/ into apps/web/public/pipeline
#   2. static-export the Next.js app (output: export writes into its distDir,
#      apps/web/.next-static, so a running dev server's .next is untouched)
#   3. upload that folder to Cloudflare Pages
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
OUT="$WEB/.next-static"

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
rm -rf "$OUT"
BLUEBAN_STATIC=1 NEXT_PUBLIC_DATA_MODE=static npx next build

if [[ ! -f "$OUT/index.html" ]]; then
  echo "Export produced no index.html in $OUT; aborting." >&2
  exit 1
fi

echo
echo "==> 3/3  upload to Cloudflare Pages project '$PROJECT'"
cd "$ROOT"
npx wrangler pages deploy "$OUT" \
  --project-name "$PROJECT" \
  --branch "$BRANCH" \
  --commit-dirty=true

echo
echo "Deployed to https://$PROJECT.pages.dev"
echo "Custom domain (once, in the dashboard): Workers & Pages > $PROJECT > Custom domains >"
echo "  Set up a custom domain > blueban813.kanbanstudios.ae"
