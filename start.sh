#!/usr/bin/env bash
# Start everything for local use. Ctrl+C stops it all.
set -euo pipefail

cd "$(dirname "$0")"
BACKEND_PORT=8000
FRONTEND_PORT=3000
PGBIN="$(brew --prefix 2>/dev/null)/opt/postgresql@16/bin"

say() { printf "\033[36m%s\033[0m\n" "$*"; }
die() { printf "\033[31m%s\033[0m\n" "$*" >&2; exit 1; }

[ -x backend/.venv/bin/uvicorn ] || die "backend/.venv missing. See README.md for setup."
[ -d frontend/node_modules ] || die "frontend/node_modules missing. Run: cd frontend && npm install"

# ---- database ----
if ! "$PGBIN/pg_isready" -h localhost -q 2>/dev/null; then
  say "Starting PostgreSQL…"
  brew services start postgresql@16 >/dev/null
  for _ in $(seq 1 30); do
    "$PGBIN/pg_isready" -h localhost -q 2>/dev/null && break
    sleep 1
  done
  "$PGBIN/pg_isready" -h localhost -q 2>/dev/null || die "PostgreSQL did not start."
fi

say "Applying migrations…"
(cd backend && .venv/bin/alembic upgrade head >/dev/null)

# ---- processes ----
pids=()
stop_tree() {
  # npm spawns next-server as a child, so killing npm alone leaves the port
  # held. Take the descendants first, then the process itself.
  local pid=$1
  [ -n "$pid" ] || return 0
  pkill -TERM -P "$pid" 2>/dev/null || true
  kill -TERM "$pid" 2>/dev/null || true
}

cleanup() {
  trap - INT TERM
  printf "\n"
  say "Stopping…"
  for pid in "${pids[@]:-}"; do
    stop_tree "$pid"
  done

  for _ in $(seq 1 10); do
    still_running=0
    for pid in "${pids[@]:-}"; do
      kill -0 "$pid" 2>/dev/null && still_running=1
    done
    [ "$still_running" = "0" ] && break
    sleep 1
  done

  # Anything that ignored SIGTERM gets SIGKILL rather than being left holding
  # a port.
  for pid in "${pids[@]:-}"; do
    pkill -KILL -P "$pid" 2>/dev/null || true
    kill -KILL "$pid" 2>/dev/null || true
  done
  exit 0
}
trap cleanup INT TERM

say "Starting backend on :$BACKEND_PORT…"
(cd backend && exec .venv/bin/uvicorn app.main:app --port "$BACKEND_PORT") &
pids+=($!)

# Loading the speech model takes a few seconds; wait rather than opening a
# browser onto an API that is not up yet.
for _ in $(seq 1 120); do
  curl -sf "http://127.0.0.1:$BACKEND_PORT/api/v1/health" >/dev/null 2>&1 && break
  sleep 1
done
curl -sf "http://127.0.0.1:$BACKEND_PORT/api/v1/health" >/dev/null 2>&1 \
  || die "Backend did not come up."

say "Starting frontend on :$FRONTEND_PORT…"
(cd frontend && exec npm run dev --silent) &
pids+=($!)

for _ in $(seq 1 60); do
  curl -sf "http://localhost:$FRONTEND_PORT/" >/dev/null 2>&1 && break
  sleep 1
done

URL="http://localhost:$FRONTEND_PORT/create"
say ""
say "  Listening Studio is ready:  $URL"
say "  Ctrl+C to stop."
say ""
command -v open >/dev/null && open "$URL" || true

wait
