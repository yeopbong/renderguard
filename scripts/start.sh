#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
  echo 'Run ./scripts/setup.sh first.' >&2
  exit 1
fi
if [ ! -f dist/index.html ]; then
  echo 'Build the frontend with pnpm build first.' >&2
  exit 1
fi
exec .venv/bin/python -m server.app "$@"
