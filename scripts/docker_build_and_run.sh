#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

COMPOSE_CMD=""
if ! command -v docker-compose >/dev/null 2>&1; then
  echo "docker-compose not found. Trying docker compose plugin..."
  if ! docker compose version >/dev/null 2>&1; then
    echo "docker-compose or 'docker compose' is required to run multiple services."
    exit 1
  else
    COMPOSE_CMD="docker compose"
  fi
else
  COMPOSE_CMD="docker-compose"
fi

echo "Building and starting services with $COMPOSE_CMD ..."
$COMPOSE_CMD up --build -d

echo "Services started. Backend: http://127.0.0.1:8090 | Agent runtime: http://127.0.0.1:8091 | MCP gateway: http://127.0.0.1:8092 | UI: http://127.0.0.1:8093"
