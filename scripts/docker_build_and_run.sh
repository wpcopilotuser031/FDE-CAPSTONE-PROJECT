#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

SUDO="sudo"
COMPOSE_CMD=""
if ! $SUDO command -v docker-compose >/dev/null 2>&1; then
  echo "docker-compose not found. Trying docker compose plugin..."
  if ! $SUDO docker compose version >/dev/null 2>&1; then
    echo "docker-compose or 'docker compose' is required to run multiple services."
    exit 1
  else
    COMPOSE_CMD="$SUDO docker compose"
  fi
else
  COMPOSE_CMD="$SUDO docker-compose"
fi

SERVICE_CONTAINERS=(referral-backend referral-agent-runtime referral-mcp-gateway referral-ui)
PUSH_IMAGES="${PUSH_IMAGES:-true}"
DOCKER_LOGIN="${DOCKER_LOGIN:-true}"
DOCKERHUB_USER="${DOCKERHUB_USER:-aviroopbasu1995}"
DOCKERHUB_REPO="${DOCKERHUB_REPO:-fde-capstone}"
DOCKERHUB_TOKEN="${DOCKERHUB_TOKEN:-}"
IMAGES=(
  "$DOCKERHUB_USER/$DOCKERHUB_REPO:backend"
  "$DOCKERHUB_USER/$DOCKERHUB_REPO:agent-runtime"
  "$DOCKERHUB_USER/$DOCKERHUB_REPO:mcp-gateway"
  "$DOCKERHUB_USER/$DOCKERHUB_REPO:ui"
)

echo "Cleaning up old containers and ports before starting services..."
for container in "${SERVICE_CONTAINERS[@]}"; do
  if $SUDO docker ps -a --format '{{.Names}}' | grep -x "$container" >/dev/null 2>&1; then
    echo "Removing existing container $container"
    $SUDO docker rm -f "$container" >/dev/null 2>&1 || true
  fi
 done

# If ports required by services are occupied, try to stop occupying processes first
PORTS=(8090 8091 8092 8093)
for port in "${PORTS[@]}"; do
  pids=$($SUDO lsof -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
  if [[ -n "$pids" ]]; then
    echo "Port $port is currently in use by pids: $pids — attempting graceful stop..."
    $SUDO kill $pids 2>/dev/null || true
    sleep 1
    remaining=$($SUDO lsof -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
    if [[ -n "$remaining" ]]; then
      echo "Port $port still in use by pids: $remaining — force killing..."
      $SUDO kill -9 $remaining 2>/dev/null || true
      sleep 0.5
    fi
    echo "Cleared port $port"
  fi
 done

# Try a compose down to remove previous stack state and orphans.
$COMPOSE_CMD down --remove-orphans || true

echo "Building and starting services with $COMPOSE_CMD ..."
$COMPOSE_CMD up --build -d &
COMPOSE_PID=$!

# Wait for compose to finish starting
wait $COMPOSE_PID || true

if [[ "$PUSH_IMAGES" == "true" ]]; then
  if [[ "$DOCKER_LOGIN" == "true" ]]; then
    if [[ -n "$DOCKERHUB_TOKEN" ]]; then
      echo "Logging into Docker Hub as '$DOCKERHUB_USER' using DOCKERHUB_TOKEN..."
      echo "$DOCKERHUB_TOKEN" | $SUDO docker login -u "$DOCKERHUB_USER" --password-stdin
    else
      echo "Docker Hub token not found in environment."
      read -rsp "Enter Docker Hub personal access token for $DOCKERHUB_USER: " DOCKERHUB_TOKEN
      echo
      if [[ -z "$DOCKERHUB_TOKEN" ]]; then
        echo "No token entered. Skipping Docker login; push may fail if not already authenticated."
      else
        echo "Logging into Docker Hub as '$DOCKERHUB_USER'..."
        echo "$DOCKERHUB_TOKEN" | $SUDO docker login -u "$DOCKERHUB_USER" --password-stdin
      fi
    fi
  fi

  echo "Pushing built images to Docker Hub repository '$DOCKERHUB_USER/$DOCKERHUB_REPO' ..."
  for image in "${IMAGES[@]}"; do
    echo "Pushing $image"
    $SUDO docker push "$image"
  done
fi

echo "Services started. Backend: http://127.0.0.1:8090 | Agent runtime: http://127.0.0.1:8091 | MCP gateway: http://127.0.0.1:8092 | UI: http://127.0.0.1:8093"