#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8787}"
FRONTEND_PORT="${PORT:-6700}"
FRONTEND_HMR_PORT="${HMR_PORT:-$((FRONTEND_PORT + 17978))}"
PYTHON_BIN="${PYTHON_BIN:-}"
MARKHUB_BACKEND_URL="${MARKHUB_BACKEND_URL:-http://${BACKEND_HOST}:${BACKEND_PORT}}"

backend_pid=""
frontend_pid=""
cleaned_up=0
mode="${1:-start}"

cleanup() {
  if [[ "$cleaned_up" -eq 1 ]]; then
    return
  fi
  cleaned_up=1
  echo
  echo "Stopping Markhub services..."
  if [[ -n "$frontend_pid" ]] && kill -0 "$frontend_pid" 2>/dev/null; then
    kill "$frontend_pid" 2>/dev/null || true
  fi
  if [[ -n "$backend_pid" ]] && kill -0 "$backend_pid" 2>/dev/null; then
    kill "$backend_pid" 2>/dev/null || true
  fi
  wait "$frontend_pid" "$backend_pid" 2>/dev/null || true
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

http_ok() {
  command -v curl >/dev/null 2>&1 && curl -fsS --max-time 2 "$1" >/dev/null 2>&1
}

port_in_use() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    return 0
  fi
  if command -v ss >/dev/null 2>&1; then
    ss -ltn "sport = :$port" 2>/dev/null | tail -n +2 | grep -q .
    return $?
  fi
  "$PYTHON_BIN" - "$port" <<'PY'
import socket
import sys

port = int(sys.argv[1])
for host in ("127.0.0.1", "0.0.0.0"):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except PermissionError:
        sys.exit(1)
    try:
        sock.bind((host, port))
    except OSError:
        sys.exit(0)
    finally:
        sock.close()
sys.exit(1)
PY
}

print_port_owner() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$1" -sTCP:LISTEN || true
  fi
  if command -v ss >/dev/null 2>&1; then
    ss -ltnp "sport = :$1" || true
  fi
}

port_pids() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true
  fi
  if command -v ss >/dev/null 2>&1; then
    ss -ltnp "sport = :$port" 2>/dev/null \
      | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' \
      | sort -u
  fi
}

is_markhub_process() {
  local pid="$1"
  local cmdline=""
  if [[ -r "/proc/$pid/cmdline" ]]; then
    cmdline="$(tr '\0' ' ' < "/proc/$pid/cmdline")"
  else
    cmdline="$(ps -p "$pid" -o args= 2>/dev/null || true)"
  fi
  [[ "$cmdline" == *"$ROOT_DIR"* || "$cmdline" == *"markhub-frontend"* || "$cmdline" == *"server.ts"* ]]
}

stop_port_processes() {
  local port="$1"
  local pids=""
  pids="$(port_pids "$port")"
  if [[ -z "$pids" ]]; then
    return
  fi
  echo "Stopping existing service on port $port..."
  while IFS= read -r pid; do
    if [[ -n "$pid" ]]; then
      kill "$pid" 2>/dev/null || true
    fi
  done <<< "$pids"
  sleep 1
}

stop_markhub_port_processes() {
  local port="$1"
  local pids=""
  local stopped=0
  pids="$(port_pids "$port")"
  if [[ -z "$pids" ]]; then
    return 0
  fi
  while IFS= read -r pid; do
    if [[ -n "$pid" ]] && is_markhub_process "$pid"; then
      echo "Stopping stale Markhub process on port $port (pid $pid)..."
      kill "$pid" 2>/dev/null || true
      stopped=1
    fi
  done <<< "$pids"
  if [[ "$stopped" -eq 1 ]]; then
    sleep 1
  fi
}

ensure_port_available() {
  local port="$1"
  local label="$2"
  if ! port_in_use "$port"; then
    return 0
  fi
  stop_markhub_port_processes "$port"
  if port_in_use "$port"; then
    echo "$label port $port is already in use by another process." >&2
    print_port_owner "$port"
    return 1
  fi
}

wait_for_url() {
  local url="$1"
  local label="$2"
  local attempts="${3:-30}"
  local pid="${4:-}"
  local i

  for ((i = 1; i <= attempts; i++)); do
    if http_ok "$url"; then
      return 0
    fi
    if [[ -n "$pid" ]] && ! kill -0 "$pid" 2>/dev/null; then
      echo "$label process stopped before becoming ready." >&2
      return 1
    fi
    sleep 1
  done

  echo "$label did not become ready at $url" >&2
  return 1
}

trap cleanup INT TERM EXIT

if [[ -z "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3 || command -v python || true)"
elif ! command -v "$PYTHON_BIN" >/dev/null 2>&1 && [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python not found at PYTHON_BIN=$PYTHON_BIN." >&2
  exit 1
fi

if [[ -z "$PYTHON_BIN" ]]; then
  echo "Python not found. Set PYTHON_BIN to the Python with backend dependencies installed." >&2
  exit 1
fi

require_command npm

if [[ "$mode" == "restart" ]]; then
  stop_port_processes "$FRONTEND_PORT"
  stop_port_processes "$FRONTEND_HMR_PORT"
  stop_port_processes "$BACKEND_PORT"
elif [[ "$mode" != "start" ]]; then
  echo "Usage: ./start.sh [restart]" >&2
  exit 1
fi

echo "Starting Markhub..."
echo "Backend:  $MARKHUB_BACKEND_URL"
echo "Frontend: http://127.0.0.1:${FRONTEND_PORT}"
echo "HMR:      ws://127.0.0.1:${FRONTEND_HMR_PORT}"
echo

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  echo "Installing frontend dependencies..."
  (cd "$FRONTEND_DIR" && npm install)
fi

if http_ok "$MARKHUB_BACKEND_URL/api/config"; then
  echo "Backend is already running. Reusing it."
else
  ensure_port_available "$BACKEND_PORT" "Backend"
  echo "Launching backend..."
  (cd "$BACKEND_DIR" && "$PYTHON_BIN" server.py --host "$BACKEND_HOST" --port "$BACKEND_PORT") &
  backend_pid=$!
  wait_for_url "$MARKHUB_BACKEND_URL/api/config" "Backend" 30 "$backend_pid"
fi

if http_ok "http://127.0.0.1:${FRONTEND_PORT}/"; then
  echo "Frontend is already running. Reusing it."
else
  ensure_port_available "$FRONTEND_PORT" "Frontend"
  ensure_port_available "$FRONTEND_HMR_PORT" "Frontend HMR"
  echo "Launching frontend..."
  (cd "$FRONTEND_DIR" && PORT="$FRONTEND_PORT" HMR_PORT="$FRONTEND_HMR_PORT" MARKHUB_BACKEND_URL="$MARKHUB_BACKEND_URL" npm run dev) &
  frontend_pid=$!
  wait_for_url "http://127.0.0.1:${FRONTEND_PORT}/" "Frontend" 30 "$frontend_pid"
fi

echo
echo "Markhub is ready. Open http://127.0.0.1:${FRONTEND_PORT}"
echo "Press Ctrl+C to stop both services."

if [[ -z "$backend_pid" && -z "$frontend_pid" ]]; then
  trap - INT TERM EXIT
  echo "Both services were already running, so this script will exit without stopping them."
  exit 0
fi

while true; do
  if [[ -n "$backend_pid" ]] && ! kill -0 "$backend_pid" 2>/dev/null; then
    break
  fi
  if [[ -n "$frontend_pid" ]] && ! kill -0 "$frontend_pid" 2>/dev/null; then
    break
  fi
  sleep 1
done

echo "One of the Markhub services stopped."
