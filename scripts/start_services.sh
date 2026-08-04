#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUN_DIR="$ROOT_DIR/.run"
LOG_DIR="$RUN_DIR/logs"
PID_DIR="$RUN_DIR/pids"

mkdir -p "$LOG_DIR" "$PID_DIR"

if [[ -f "$ROOT_DIR/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.venv/bin/activate"
fi

if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
fi

start_service() {
  local name="$1"
  local module="$2"
  local port="$3"
  local health_url="$4"

  local pid_file="$PID_DIR/${name}.pid"
  local log_file="$LOG_DIR/${name}.log"

  if lsof -t -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port $port is already in use. Cannot start $name."
    lsof -nP -iTCP:"$port" -sTCP:LISTEN || true
    exit 1
  fi

  if [[ -f "$pid_file" ]]; then
    local existing_pid
    existing_pid="$(cat "$pid_file")"
    if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" 2>/dev/null; then
      echo "$name is already running (pid=$existing_pid, port=$port)."
      return
    fi
    rm -f "$pid_file"
  fi

  echo "Starting $name on port $port..."
  nohup uvicorn "$module" --host 0.0.0.0 --port "$port" >"$log_file" 2>&1 &
  local new_pid=$!
  echo "$new_pid" >"$pid_file"

  sleep 1
  if kill -0 "$new_pid" 2>/dev/null; then
    local ok=0
    for _ in {1..15}; do
      if curl -fsS "$health_url" 2>/dev/null | grep -q '"status":"ok"'; then
        ok=1
        break
      fi
      sleep 0.5
    done

    if [[ "$ok" -eq 1 ]]; then
      echo "$name started (pid=$new_pid, port=$port). Logs: $log_file"
    else
      echo "Failed health check for $name at $health_url. Check logs: $log_file"
      kill "$new_pid" 2>/dev/null || true
      exit 1
    fi
  else
    echo "Failed to start $name. Check logs: $log_file"
    exit 1
  fi
}

echo "Rebuilding ChromaDB RAG provider index from providers.json ..."
python "$ROOT_DIR/scripts/build_rag_index.py"

start_service "backend" "app.main:app" "8090" "http://127.0.0.1:8090/health"
start_service "agent_runtime" "app.agent_runtime:app" "8091" "http://127.0.0.1:8091/health"
start_service "mcp_gateway" "app.mcp_gateway:app" "8092" "http://127.0.0.1:8092/health"

echo "All services launched."
