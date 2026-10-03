#!/bin/sh
set -eu

uvicorn app.main:app --host 127.0.0.1 --port 8000 &
API_PID=$!

HOSTNAME=127.0.0.1 PORT=3000 node /app/ui/server.js &
UI_PID=$!

cleanup() {
  kill "$API_PID" "$UI_PID" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
