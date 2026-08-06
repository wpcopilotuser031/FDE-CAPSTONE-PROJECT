#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

# Configuration
SUDO="sudo"
COMPOSE_CMD=""
DOCKER_PUSH=${DOCKER_PUSH:-false}
DOCKER_REGISTRY=${DOCKER_REGISTRY:-}
IMAGE_TAG=${IMAGE_TAG:-latest}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --push)
      DOCKER_PUSH=true
      shift
      ;;
    --registry)
      DOCKER_REGISTRY="$2"
      shift 2
      ;;
    --tag)
      IMAGE_TAG="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: $0 [--push] [--registry <username>] [--tag <tag>]"
      exit 1
      ;;
  esac
done

# Validate docker-compose
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

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "✓ Services Started Successfully!"
echo "════════════════════════════════════════════════════════════════"
echo "Backend:       http://127.0.0.1:8090"
echo "Agent Runtime: http://127.0.0.1:8091"
echo "MCP Gateway:   http://127.0.0.1:8092"
echo "UI:            http://127.0.0.1:8093"
echo "════════════════════════════════════════════════════════════════"
echo ""

# Docker Hub Push (optional)
if [[ "$DOCKER_PUSH" == "true" ]]; then
  if [[ -z "$DOCKER_REGISTRY" ]]; then
    echo "❌ Error: --registry <username> is required for Docker Hub push"
    exit 1
  fi

  echo "📦 Pushing images to Docker Hub registry: $DOCKER_REGISTRY"
  echo "════════════════════════════════════════════════════════════════"

  # Get the local image IDs
  BACKEND_IMAGE=$($SUDO docker images fde-capstone-project-backend --format "{{.ID}}" | head -1)
  AGENT_IMAGE=$($SUDO docker images fde-capstone-project-agent_runtime --format "{{.ID}}" | head -1)
  MCP_IMAGE=$($SUDO docker images fde-capstone-project-mcp_gateway --format "{{.ID}}" | head -1)

  # Define remote image names
  BACKEND_REMOTE="${DOCKER_REGISTRY}/referral-platform-backend:${IMAGE_TAG}"
  AGENT_REMOTE="${DOCKER_REGISTRY}/referral-platform-agent-runtime:${IMAGE_TAG}"
  MCP_REMOTE="${DOCKER_REGISTRY}/referral-platform-mcp-gateway:${IMAGE_TAG}"

  # Tag images
  echo "Tagging images for push..."
  $SUDO docker tag fde-capstone-project-backend "$BACKEND_REMOTE" || true
  $SUDO docker tag fde-capstone-project-agent_runtime "$AGENT_REMOTE" || true
  $SUDO docker tag fde-capstone-project-mcp_gateway "$MCP_REMOTE" || true

  # Push images
  echo "Pushing Backend image: $BACKEND_REMOTE"
  $SUDO docker push "$BACKEND_REMOTE" 2>&1 | tail -5
  echo "✓ Backend pushed"

  echo ""
  echo "Pushing Agent Runtime image: $AGENT_REMOTE"
  $SUDO docker push "$AGENT_REMOTE" 2>&1 | tail -5
  echo "✓ Agent Runtime pushed"

  echo ""
  echo "Pushing MCP Gateway image: $MCP_REMOTE"
  $SUDO docker push "$MCP_REMOTE" 2>&1 | tail -5
  echo "✓ MCP Gateway pushed"

  echo ""
  echo "════════════════════════════════════════════════════════════════"
  echo "✓ Images pushed to Docker Hub!"
  echo "════════════════════════════════════════════════════════════════"
  echo ""
  echo "📥 Download and run images:"
  echo ""
  echo "1️⃣  Backend:"
  echo "    docker pull $BACKEND_REMOTE"
  echo "    docker run -p 8090:8090 --env-file .env $BACKEND_REMOTE"
  echo ""
  echo "2️⃣  Agent Runtime:"
  echo "    docker pull $AGENT_REMOTE"
  echo "    docker run -p 8091:8091 --env-file .env $AGENT_REMOTE"
  echo ""
  echo "3️⃣  MCP Gateway:"
  echo "    docker pull $MCP_REMOTE"
  echo "    docker run -p 8092:8092 --env-file .env $MCP_REMOTE"
  echo ""
  echo "Or use docker-compose with remote images:"
  echo "    services:"
  echo "      backend:"
  echo "        image: $BACKEND_REMOTE"
  echo "      agent_runtime:"
  echo "        image: $AGENT_REMOTE"
  echo "      mcp_gateway:"
  echo "        image: $MCP_REMOTE"
  echo ""
  echo "════════════════════════════════════════════════════════════════"
fi
