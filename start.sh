#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8787}"
FRONTEND_PORT="${PORT:-6700}"
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
  lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

print_port_owner() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$1" -sTCP:LISTEN || true
  fi
}

stop_port_processes() {
  local port="$1"
  local pids=""
  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  fi
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

wait_for_url() {
  local url="$1"
  local label="$2"
  local attempts="${3:-30}"
  local i

  for ((i = 1; i <= attempts; i++)); do
    if http_ok "$url"; then
      return 0
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
  stop_port_processes "$BACKEND_PORT"
elif [[ "$mode" != "start" ]]; then
  echo "Usage: ./start.sh [restart]" >&2
  exit 1
fi

echo "Starting Markhub..."
echo "Backend:  $MARKHUB_BACKEND_URL"
echo "Frontend: http://127.0.0.1:${FRONTEND_PORT}"
echo

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  echo "Installing frontend dependencies..."
  (cd "$FRONTEND_DIR" && npm install)
fi

if http_ok "$MARKHUB_BACKEND_URL/api/config"; then
  echo "Backend is already running. Reusing it."
elif port_in_use "$BACKEND_PORT"; then
  echo "Backend port $BACKEND_PORT is already in use, but it does not look like Markhub backend."
  print_port_owner "$BACKEND_PORT"
  echo "Set BACKEND_PORT to another port or stop the process above." >&2
  exit 1
else
  echo "Launching backend..."
  (cd "$BACKEND_DIR" && "$PYTHON_BIN" server.py --host "$BACKEND_HOST" --port "$BACKEND_PORT") &
  backend_pid=$!
  wait_for_url "$MARKHUB_BACKEND_URL/api/config" "Backend"
fi

if http_ok "http://127.0.0.1:${FRONTEND_PORT}/"; then
  echo "Frontend is already running. Reusing it."
elif port_in_use "$FRONTEND_PORT"; then
  echo "Frontend port $FRONTEND_PORT is already in use, but it does not respond like Markhub frontend."
  print_port_owner "$FRONTEND_PORT"
  echo "Set PORT to another port or stop the process above." >&2
  exit 1
else
  echo "Launching frontend..."
  (cd "$FRONTEND_DIR" && PORT="$FRONTEND_PORT" MARKHUB_BACKEND_URL="$MARKHUB_BACKEND_URL" npm run dev) &
  frontend_pid=$!
  wait_for_url "http://127.0.0.1:${FRONTEND_PORT}/" "Frontend"
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
