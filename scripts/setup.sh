#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
command -v node >/dev/null || { echo 'Install Node.js 22.12 or later first.' >&2; exit 1; }
node -e 'const [major, minor] = process.versions.node.split(".").map(Number); if (major < 22 || (major === 22 && minor < 12)) { console.error("Node.js 22.12 or later is required."); process.exit(1); }'
command -v pnpm >/dev/null || { echo 'Install pnpm 11.19.0 first (npm install -g pnpm@11.19.0).' >&2; exit 1; }
python3 -m venv .venv
.venv/bin/python -m pip install --no-cache-dir -r requirements.lock
pnpm install --frozen-lockfile
pnpm exec playwright install chromium --only-shell
pnpm prepare:web
pnpm build
.venv/bin/python scripts/verify_model.py
printf '\nReady. Run ./scripts/start.sh and open http://127.0.0.1:8765\n'
