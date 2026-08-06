#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

# Configuration - ALWAYS PUSH is now the default behavior
SUDO="sudo"
COMPOSE_CMD=""
DOCKER_REGISTRY=${DOCKER_REGISTRY:-}
IMAGE_TAG=${IMAGE_TAG:-latest}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --registry)
      DOCKER_REGISTRY="$2"
      shift 2
      ;;
    --tag)
      IMAGE_TAG="$2"
      shift 2
      ;;
    --no-push)
      # Optional flag to skip push if user doesn't want it
      NO_PUSH=true
      shift
      ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: $0 [--registry <username>] [--tag <tag>] [--no-push]"
      exit 1
      ;;
  esac
done

# Validate docker-compose - try both docker-compose and docker compose
if docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD="docker compose"
elif docker-compose --version >/dev/null 2>&1; then
  COMPOSE_CMD="docker-compose"
elif $SUDO docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD="$SUDO docker compose"
elif $SUDO docker-compose --version >/dev/null 2>&1; then
  COMPOSE_CMD="$SUDO docker-compose"
else
  echo "❌ docker-compose or 'docker compose' is required to run multiple services."
  exit 1
<<<<<<< HEAD
fi

# Auto-detect Docker Hub username from docker config if registry not provided
if [[ -z "$DOCKER_REGISTRY" ]]; then
  if [[ -f ~/.docker/config.json ]]; then
    DOCKER_REGISTRY=$(grep -o '"Username":"[^"]*"' ~/.docker/config.json | head -1 | cut -d'"' -f4)
  fi

  if [[ -z "$DOCKER_REGISTRY" ]]; then
    echo "❌ Error: Docker Hub username not found"
    echo "Please provide registry with: --registry <username>"
    echo "Or log in to Docker Hub first: docker login"
    exit 1
  fi
=======
>>>>>>> fb62957 (fix: Improve docker-compose detection without sudo prefix issues)
fi

# Auto-detect Docker Hub username from docker config if registry not provided
if [[ -z "$DOCKER_REGISTRY" ]]; then
  if [[ -f ~/.docker/config.json ]]; then
    DOCKER_REGISTRY=$(grep -o '"Username":"[^"]*"' ~/.docker/config.json | head -1 | cut -d'"' -f4)
  fi

  if [[ -z "$DOCKER_REGISTRY" ]]; then
    echo "❌ Error: Docker Hub username not found"
    echo "Please provide registry with: --registry <username>"
    echo "Or log in to Docker Hub first: docker login"
    exit 1
  fi
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

<<<<<<< HEAD
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

# Docker Hub Push - ALWAYS HAPPENS (unless --no-push is specified)
if [[ "${NO_PUSH:-false}" != "true" ]]; then
  echo "📦 Pushing images to Docker Hub: $DOCKER_REGISTRY"
  echo "════════════════════════════════════════════════════════════════"

  # Define remote image names
  BACKEND_REMOTE="${DOCKER_REGISTRY}/referral-platform-backend:${IMAGE_TAG}"
  AGENT_REMOTE="${DOCKER_REGISTRY}/referral-platform-agent-runtime:${IMAGE_TAG}"
  MCP_REMOTE="${DOCKER_REGISTRY}/referral-platform-mcp-gateway:${IMAGE_TAG}"

  # Tag images
  echo "Tagging images..."
  $SUDO docker tag fde-capstone-project-backend "$BACKEND_REMOTE" 2>/dev/null || true
  $SUDO docker tag fde-capstone-project-agent_runtime "$AGENT_REMOTE" 2>/dev/null || true
  $SUDO docker tag fde-capstone-project-mcp_gateway "$MCP_REMOTE" 2>/dev/null || true

  # Push images with error handling
  echo ""
  echo "Pushing images to Docker Hub..."
  echo ""

  push_image() {
    local local_image=$1
    local remote_image=$2
    local service_name=$3

    if $SUDO docker push "$remote_image" 2>/dev/null; then
      echo "✓ $service_name pushed successfully"
    else
      echo "⚠ Failed to push $service_name"
      echo "  Make sure you're logged in: docker login -u $DOCKER_REGISTRY"
      return 1
    fi
  }

  push_image "fde-capstone-project-backend" "$BACKEND_REMOTE" "Backend"
  push_image "fde-capstone-project-agent_runtime" "$AGENT_REMOTE" "Agent Runtime"
  push_image "fde-capstone-project-mcp_gateway" "$MCP_REMOTE" "MCP Gateway"

  echo ""
  echo "════════════════════════════════════════════════════════════════"
  echo "✓ All images pushed to Docker Hub!"
  echo "════════════════════════════════════════════════════════════════"
  echo ""
  echo "🌐 Public Registry URLs - Share these to download:"
  echo ""
  echo "📥 BACKEND IMAGE:"
  echo "   🔗 https://hub.docker.com/r/$DOCKER_REGISTRY/referral-platform-backend"
  echo "   📦 docker pull $BACKEND_REMOTE"
  echo ""
  echo "📥 AGENT RUNTIME IMAGE:"
  echo "   🔗 https://hub.docker.com/r/$DOCKER_REGISTRY/referral-platform-agent-runtime"
  echo "   📦 docker pull $AGENT_REMOTE"
  echo ""
  echo "📥 MCP GATEWAY IMAGE:"
  echo "   🔗 https://hub.docker.com/r/$DOCKER_REGISTRY/referral-platform-mcp-gateway"
  echo "   📦 docker pull $MCP_REMOTE"
  echo ""
  echo "════════════════════════════════════════════════════════════════"
  echo ""
  echo "🚀 Run containers locally:"
  echo ""
  echo "   docker run -p 8090:8090 --env-file .env $BACKEND_REMOTE"
  echo "   docker run -p 8091:8091 --env-file .env $AGENT_REMOTE"
  echo "   docker run -p 8092:8092 --env-file .env $MCP_REMOTE"
  echo ""
  echo "════════════════════════════════════════════════════════════════"
else
  echo "⏭️  Skipped Docker Hub push (--no-push flag used)"
  echo "════════════════════════════════════════════════════════════════"
fi
=======
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
>>>>>>> c77223950aa5b95b9eb4211e8a8d5990e356e0d7
