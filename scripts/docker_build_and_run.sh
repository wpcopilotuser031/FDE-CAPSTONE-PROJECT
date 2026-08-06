#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-local}"

DOCKERHUB_USER="${DOCKERHUB_USER:-aviroopbasu1995}"
DOCKERHUB_REPO="${DOCKERHUB_REPO:-fde-capstone}"
DOCKERHUB_TOKEN="${DOCKERHUB_TOKEN:-}"
PUSH_IMAGES="${PUSH_IMAGES:-true}"
DOCKER_LOGIN="${DOCKER_LOGIN:-true}"
DOCKER_BIN=("docker")

NETWORK_NAME="${NETWORK_NAME:-referral-net}"

BACKEND_CONTAINER="${BACKEND_CONTAINER:-referral-backend}"
AGENT_CONTAINER="${AGENT_CONTAINER:-referral-agent-runtime}"
MCP_CONTAINER="${MCP_CONTAINER:-referral-mcp-gateway}"
UI_CONTAINER="${UI_CONTAINER:-referral-ui}"

BACKEND_IMAGE="${DOCKERHUB_USER}/${DOCKERHUB_REPO}:backend"
AGENT_IMAGE="${DOCKERHUB_USER}/${DOCKERHUB_REPO}:agent-runtime"
MCP_IMAGE="${DOCKERHUB_USER}/${DOCKERHUB_REPO}:mcp-gateway"
UI_IMAGE="${DOCKERHUB_USER}/${DOCKERHUB_REPO}:ui"
LAUNCHER_IMAGE="${DOCKERHUB_USER}/${DOCKERHUB_REPO}:launcher"

usage() {
  cat <<'EOF'
Usage:
  scripts/docker_build_and_run.sh [local|launch|stop|publish-launcher]

Modes:
  local   Build and run compose stack, then push backend/agent-runtime/mcp-gateway/ui and launcher image.
  launch  Pull images from Docker Hub, kill existing containers if any, and start all services.
  stop    Stop and remove launched containers and network.
  publish-launcher  Build and push only the launcher image.
EOF
}

bool_true() {
  case "${1:-}" in
    true|TRUE|1|yes|YES|on|ON) return 0 ;;
    *) return 1 ;;
  esac
}

init_docker_bin() {
  if docker info >/dev/null 2>&1; then
    DOCKER_BIN=("docker")
    return
  fi

  if command -v sudo >/dev/null 2>&1 && sudo docker info >/dev/null 2>&1; then
    DOCKER_BIN=("sudo" "docker")
    return
  fi

  DOCKER_BIN=("docker")
}

ensure_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "docker is required but not found in PATH."
    exit 1
  fi
  init_docker_bin
}

docker_compose_cmd() {
  if "${DOCKER_BIN[@]}" compose version >/dev/null 2>&1; then
    echo "DOCKER_COMPOSE_PLUGIN"
  elif command -v docker-compose >/dev/null 2>&1; then
    echo "docker-compose"
  elif command -v sudo >/dev/null 2>&1 && sudo docker-compose --version >/dev/null 2>&1; then
    echo "sudo docker-compose"
  else
    echo ""
  fi
}

docker_login_if_needed() {
  if ! bool_true "$DOCKER_LOGIN"; then
    return
  fi

  if [[ -z "$DOCKERHUB_TOKEN" ]]; then
    read -rsp "Enter Docker Hub personal access token for $DOCKERHUB_USER: " DOCKERHUB_TOKEN
    echo
  fi

  if [[ -n "$DOCKERHUB_TOKEN" ]]; then
    echo "$DOCKERHUB_TOKEN" | "${DOCKER_BIN[@]}" login -u "$DOCKERHUB_USER" --password-stdin
  else
    echo "No token provided. Skipping docker login."
  fi
}

local_build_run_push() {
  ensure_docker

  ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
  cd "$ROOT_DIR"

  local compose_cmd
  compose_cmd="$(docker_compose_cmd)"
  if [[ -z "$compose_cmd" ]]; then
    echo "docker-compose or docker compose is required."
    exit 1
  fi

  echo "Cleaning previous stack..."
  if [[ "$compose_cmd" == "DOCKER_COMPOSE_PLUGIN" ]]; then
    "${DOCKER_BIN[@]}" compose down --remove-orphans || true
  else
    eval "$compose_cmd down --remove-orphans" || true
  fi

  echo "Building and starting compose stack..."
  if [[ "$compose_cmd" == "DOCKER_COMPOSE_PLUGIN" ]]; then
    "${DOCKER_BIN[@]}" compose up --build -d
  else
    eval "$compose_cmd up --build -d"
  fi

  if bool_true "$PUSH_IMAGES"; then
    docker_login_if_needed

    echo "Pushing service images..."
    "${DOCKER_BIN[@]}" push "$BACKEND_IMAGE"
    "${DOCKER_BIN[@]}" push "$AGENT_IMAGE"
    "${DOCKER_BIN[@]}" push "$MCP_IMAGE"
    "${DOCKER_BIN[@]}" push "$UI_IMAGE"

    echo "Building and pushing launcher image..."
    "${DOCKER_BIN[@]}" build -f docker/launcher.Dockerfile -t "$LAUNCHER_IMAGE" .
    "${DOCKER_BIN[@]}" push "$LAUNCHER_IMAGE"
  fi

  echo "Done."
  echo "UI:      http://127.0.0.1:8093"
  echo "Backend: http://127.0.0.1:8090"
  echo "Agent:   http://127.0.0.1:8091"
  echo "MCP:     http://127.0.0.1:8092"
  echo "Launcher: $LAUNCHER_IMAGE"
}

stop_launched_stack() {
  ensure_docker
  "${DOCKER_BIN[@]}" rm -f "$BACKEND_CONTAINER" "$AGENT_CONTAINER" "$MCP_CONTAINER" "$UI_CONTAINER" >/dev/null 2>&1 || true
  "${DOCKER_BIN[@]}" network rm "$NETWORK_NAME" >/dev/null 2>&1 || true
  echo "Stopped containers and removed network (if present)."
}

launch_from_hub() {
  ensure_docker

  if ! "${DOCKER_BIN[@]}" info >/dev/null 2>&1; then
    echo "Docker daemon is not reachable."
    exit 1
  fi

  stop_launched_stack

  if ! "${DOCKER_BIN[@]}" network inspect "$NETWORK_NAME" >/dev/null 2>&1; then
    "${DOCKER_BIN[@]}" network create "$NETWORK_NAME" >/dev/null
  fi

  echo "Pulling images from Docker Hub..."
  "${DOCKER_BIN[@]}" pull "$BACKEND_IMAGE"
  "${DOCKER_BIN[@]}" pull "$AGENT_IMAGE"
  "${DOCKER_BIN[@]}" pull "$MCP_IMAGE"
  "${DOCKER_BIN[@]}" pull "$UI_IMAGE"

  # Forward core runtime env vars from current environment to child containers.
  ENV_ARGS=()
  for key in \
    LLM_MODEL \
    LLM_API_KEY \
    LLM_BASE_URL \
    ANTHROPIC_MODEL \
    ANTHROPIC_API_KEY \
    ANTHROPIC_BASE_URL \
    MCP_INTERNAL_KEY \
    USE_MCP_TOOLS \
    AGENT_CALL_TRANSPORT \
    MCP_TRANSPORT; do
    if [[ -n "${!key:-}" ]]; then
      ENV_ARGS+=("-e" "$key=${!key}")
    fi
  done

  echo "Starting MCP gateway..."
  "${DOCKER_BIN[@]}" run -d \
    --name "$MCP_CONTAINER" \
    --network "$NETWORK_NAME" \
    "${ENV_ARGS[@]}" \
    -p 8092:8092 \
    "$MCP_IMAGE" \
    sh -c "python scripts/build_rag_index.py && uvicorn app.mcp_gateway:app --host 0.0.0.0 --port 8092"

  echo "Starting agent runtime..."
  "${DOCKER_BIN[@]}" run -d \
    --name "$AGENT_CONTAINER" \
    --network "$NETWORK_NAME" \
    "${ENV_ARGS[@]}" \
    -p 8091:8091 \
    "$AGENT_IMAGE" \
    sh -c "python scripts/build_rag_index.py && uvicorn app.agent_runtime:app --host 0.0.0.0 --port 8091"

  echo "Starting backend..."
  "${DOCKER_BIN[@]}" run -d \
    --name "$BACKEND_CONTAINER" \
    --network "$NETWORK_NAME" \
    "${ENV_ARGS[@]}" \
    -e "AGENT_RUNTIME_BASE_URL=http://$AGENT_CONTAINER:8091" \
    -e "MCP_HTTP_BASE_URL=http://$MCP_CONTAINER:8092" \
    -p 8090:8090 \
    "$BACKEND_IMAGE" \
    uvicorn app.main:app --host 0.0.0.0 --port 8090

  echo "Starting UI..."
  "${DOCKER_BIN[@]}" run -d \
    --name "$UI_CONTAINER" \
    --network "$NETWORK_NAME" \
    -p 8093:80 \
    "$UI_IMAGE"

  echo "All services started from Docker Hub images."
  echo "UI:      http://127.0.0.1:8093"
  echo "Backend: http://127.0.0.1:8090"
  echo "Agent:   http://127.0.0.1:8091"
  echo "MCP:     http://127.0.0.1:8092"
}

publish_launcher_only() {
  ensure_docker

  ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
  cd "$ROOT_DIR"

  docker_login_if_needed

  echo "Building launcher image..."
  docker build -f docker/launcher.Dockerfile -t "$LAUNCHER_IMAGE" .

  echo "Pushing launcher image..."
  docker push "$LAUNCHER_IMAGE"

  echo "Launcher published: $LAUNCHER_IMAGE"
}

case "$MODE" in
  local)
    local_build_run_push
    ;;
  launch)
    launch_from_hub
    ;;
  stop)
    stop_launched_stack
    ;;
  publish-launcher)
    publish_launcher_only
    ;;
  *)
    usage
    exit 1
    ;;
esac
