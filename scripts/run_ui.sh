#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f "ui/index.html" ]]; then
  echo "UI files not found in $ROOT_DIR/ui"
  exit 1
fi

PORT=8093
if lsof -t -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port $PORT is already in use. Choose a different port or stop the occupying process."
  exit 1
fi

if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  echo "Python is required to run the UI server."
  exit 1
fi

cd ui
# Use a simple static HTTP server so UI can be served independently from the backend.
exec "$PYTHON" -m http.server "$PORT"
