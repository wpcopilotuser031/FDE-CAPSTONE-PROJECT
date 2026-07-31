#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUN_DIR="$ROOT_DIR/.run"
PID_DIR="$RUN_DIR/pids"

mkdir -p "$PID_DIR"

stop_by_pid_file() {
  local name="$1"
  local pid_file="$PID_DIR/${name}.pid"

  if [[ ! -f "$pid_file" ]]; then
    echo "$name: no pid file found."
    return
  fi

  local pid
  pid="$(cat "$pid_file")"

  if [[ -z "$pid" ]]; then
    rm -f "$pid_file"
    echo "$name: empty pid file removed."
    return
  fi

  if kill -0 "$pid" 2>/dev/null; then
    echo "Stopping $name (pid=$pid)..."
    kill "$pid" 2>/dev/null || true

    for _ in {1..10}; do
      if kill -0 "$pid" 2>/dev/null; then
        sleep 0.5
      else
        break
      fi
    done

    if kill -0 "$pid" 2>/dev/null; then
      echo "$name did not stop gracefully; forcing kill -9 (pid=$pid)."
      kill -9 "$pid" 2>/dev/null || true
    fi
    echo "$name stopped."
  else
    echo "$name: process not running (stale pid=$pid)."
  fi

  rm -f "$pid_file"
}

stop_by_port() {
  local name="$1"
  local port="$2"

  local pids
  pids="$(lsof -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -z "$pids" ]]; then
    echo "$name: no listener on port $port."
    return
  fi

  echo "$name: stopping processes on port $port ($pids)..."
  kill $pids 2>/dev/null || true

  sleep 1
  local remaining
  remaining="$(lsof -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "$remaining" ]]; then
    echo "$name: force-stopping remaining pids on port $port ($remaining)."
    kill -9 $remaining 2>/dev/null || true
  fi
}

stop_by_pid_file "backend"
stop_by_pid_file "agent_runtime"
stop_by_pid_file "mcp_gateway"

# Safety fallback if services were started outside start_services.sh.
stop_by_port "backend" "8090"
stop_by_port "agent_runtime" "8091"
stop_by_port "mcp_gateway" "8092"

echo "Stop routine completed."
