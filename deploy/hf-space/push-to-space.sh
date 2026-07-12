#!/usr/bin/env bash
# Push DrugLens to a Hugging Face Space (Docker SDK) as a backup deployment.
#
# Why a script instead of just adding a git remote: this repo contains a ~48 MB
# Demo video and other large assets. The HF Hub rejects files >10 MB that are
# not tracked with git-LFS, so we push a curated tree containing only what the
# app actually needs to build and run.
#
# Prerequisites
#   1. Create the Space:  https://huggingface.co/new-space
#        SDK = Docker,  Template = Blank,  Hardware = CPU basic (free)
#   2. Add the secret:    Space -> Settings -> Variables and secrets
#        FIREWORKS_API_KEY = <your key>
#   3. Log in locally:    pip install -U huggingface_hub && hf auth login
#
# Usage
#   bash deploy/hf-space/push-to-space.sh <hf-username>/<space-name>
#   e.g. bash deploy/hf-space/push-to-space.sh navnit/druglens

set -euo pipefail

SPACE="${1:-}"
if [ -z "$SPACE" ]; then
    echo "Usage: bash $0 <hf-username>/<space-name>"
    exit 1
fi

REPO_ROOT="$(git rev-parse --show-toplevel)"
STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT

echo "==> Staging app files (excluding large assets) in $STAGING"
git -C "$REPO_ROOT" clone --quiet "https://huggingface.co/spaces/$SPACE" "$STAGING/space"
cd "$STAGING/space"

# Wipe tracked content, then copy in only what the image needs.
find . -mindepth 1 -maxdepth 1 ! -name '.git' -exec rm -rf {} +

cp    "$REPO_ROOT/Dockerfile"        .
cp    "$REPO_ROOT/requirements.txt"  .
cp    "$REPO_ROOT/api.py"            .
cp -r "$REPO_ROOT/src"               .
cp -r "$REPO_ROOT/data"              .

# Frontend source only — the Docker build runs `npm ci && npm run build` itself.
mkdir -p frontend
cp -r "$REPO_ROOT/frontend/src"            frontend/
cp -r "$REPO_ROOT/frontend/public"         frontend/
cp    "$REPO_ROOT/frontend/index.html"     frontend/
cp    "$REPO_ROOT/frontend/package.json"   frontend/
cp    "$REPO_ROOT/frontend/package-lock.json" frontend/
cp    "$REPO_ROOT/frontend/vite.config.ts" frontend/
cp    "$REPO_ROOT/frontend/tsconfig"*.json frontend/
cp    "$REPO_ROOT/frontend/tailwind.config.js" frontend/
cp    "$REPO_ROOT/frontend/postcss.config.js" frontend/

# The Space's README.md carries the HF metadata block (sdk, app_port...).
cp "$REPO_ROOT/deploy/hf-space/README.md" README.md

# Never ship secrets.
rm -f .env

echo "==> Sanity check: nothing oversized for the Hub (>10 MB needs LFS)"
if find . -path ./.git -prune -o -type f -size +10M -print | grep -q .; then
    echo "FATAL: file larger than 10 MB staged:"
    find . -path ./.git -prune -o -type f -size +10M -print
    exit 1
fi

echo "==> Pushing to https://huggingface.co/spaces/$SPACE"
git add -A
git -c user.email="deploy@druglens.local" -c user.name="DrugLens Deploy" \
    commit -q -m "Deploy DrugLens (FastAPI + React, Docker)" || {
        echo "Nothing changed — Space is already up to date."; exit 0; }
git push

cat <<EOF

--------------------------------------------------------------------
Pushed. HF is now building the Docker image (~3-5 min).

  Space:  https://huggingface.co/spaces/$SPACE
  Logs:   the "Logs" / "Building" tab on that page

If the build succeeds but the app errors, the usual cause is a missing
secret. Confirm FIREWORKS_API_KEY is set under
  Settings -> Variables and secrets
(without it the app still runs, but AI narrative/alternatives fall back
to the rule-based engine).
--------------------------------------------------------------------
EOF
