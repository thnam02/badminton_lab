#!/usr/bin/env bash
# Put Badminton Lab online from this Mac.
#
#   ./scripts/go-live.sh
#
# Builds the website, starts the API and the website on their own ports (the
# dev servers on 3000 / 8001 can keep running), and opens a public Cloudflare
# link (https://<random>.trycloudflare.com). The link changes every time this
# starts. The Mac must stay on; it is kept awake while this runs.
# Ctrl+C stops everything. Logs are in .live/.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_PORT="${API_PORT:-8100}"
WEB_PORT="${WEB_PORT:-3100}"
LIVE="$ROOT/.live"
mkdir -p "$LIVE"

export NEXT_PUBLIC_API_URL=/api
export BACKEND_URL="http://127.0.0.1:$API_PORT"
export NEXT_DIST_DIR=.next-live

pids=()
cleanup() {
  trap - EXIT INT TERM
  echo
  echo "Stopping…"
  for pid in "${pids[@]+"${pids[@]}"}"; do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
  rm -f "$LIVE/url.txt"
}
trap cleanup EXIT INT TERM

for port in "$API_PORT" "$WEB_PORT"; do
  if lsof -ti "tcp:$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port $port is already in use. Is go-live already running?" >&2
    exit 1
  fi
done
command -v cloudflared >/dev/null || { echo "Install cloudflared first: brew install cloudflared" >&2; exit 1; }

wait_for() {  # url, name, log
  for _ in $(seq 1 90); do
    curl -fs -o /dev/null "$1" && return 0
    sleep 1
  done
  echo "$2 did not start; see $3" >&2
  tail -20 "$3" >&2
  exit 1
}

echo "1/4 Updating the database…"
(cd "$ROOT/backend" && .venv/bin/python -m app.labelling.cli init-db)

echo "2/4 Building the website (about a minute)…"
if ! (cd "$ROOT/frontend" && node_modules/.bin/next build >"$LIVE/build.log" 2>&1); then
  tail -30 "$LIVE/build.log" >&2
  exit 1
fi

echo "3/4 Starting the API and the website…"
(cd "$ROOT/backend" && exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT") \
  >"$LIVE/api.log" 2>&1 &
pids+=($!)
(cd "$ROOT/frontend" && exec node_modules/.bin/next start -H 127.0.0.1 -p "$WEB_PORT") \
  >"$LIVE/web.log" 2>&1 &
pids+=($!)
wait_for "http://127.0.0.1:$API_PORT/health" "The API" "$LIVE/api.log"
wait_for "http://127.0.0.1:$WEB_PORT/login" "The website" "$LIVE/web.log"

echo "4/4 Opening the public link…"
cloudflared tunnel --no-autoupdate --url "http://127.0.0.1:$WEB_PORT" >"$LIVE/tunnel.log" 2>&1 &
pids+=($!)
url=""
for _ in $(seq 1 60); do
  url="$(grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' "$LIVE/tunnel.log" | head -1 || true)"
  [ -n "$url" ] && break
  sleep 1
done
if [ -z "$url" ]; then
  echo "Cloudflare did not give a link; see $LIVE/tunnel.log" >&2
  tail -20 "$LIVE/tunnel.log" >&2
  exit 1
fi
echo "$url" >"$LIVE/url.txt"

caffeinate -dimsu -w $$ &
pids+=($!)

cat <<EOF

  Badminton Lab is online:

    $url/login

  Admin signs in as "admin", the coach as "jeff" (passwords in .env).
  This link changes each time go-live starts. Keep this window open;
  Ctrl+C takes the site offline.

EOF

while true; do
  for pid in "${pids[@]}"; do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "A part of the site stopped unexpectedly; see the logs in $LIVE." >&2
      exit 1
    fi
  done
  sleep 5
done
