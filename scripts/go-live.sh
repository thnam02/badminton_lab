#!/usr/bin/env bash
# Put Badminton Lab online from this Mac.
#
#   ./scripts/go-live.sh
#
# Builds the website, starts the API and the website on their own ports (the
# dev servers on 3000 / 8001 can keep running), and opens a stable public
# Tailscale Funnel URL (https://<machine>.<tailnet>.ts.net). Jeff only needs
# a browser — no Tailscale install on his side. The Mac must stay on; it is
# kept awake while this runs. Ctrl+C stops everything. Logs are in .live/.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_PORT="${API_PORT:-8100}"
WEB_PORT="${WEB_PORT:-3100}"
LIVE="$ROOT/.live"
mkdir -p "$LIVE"

export NEXT_PUBLIC_API_URL=/api
export BACKEND_URL="http://127.0.0.1:$API_PORT"
export NEXT_DIST_DIR=.next-live

TAILSCALE_BIN=""
for candidate in \
  tailscale \
  /Applications/Tailscale.app/Contents/MacOS/Tailscale \
  /usr/local/bin/tailscale \
  "$HOME/bin/tailscale"
do
  if command -v "$candidate" >/dev/null 2>&1; then
    TAILSCALE_BIN="$(command -v "$candidate")"
    break
  elif [ -x "$candidate" ]; then
    TAILSCALE_BIN="$candidate"
    break
  fi
done

pids=()
funnel_on=0
cleanup() {
  trap - EXIT INT TERM
  echo
  echo "Stopping…"
  if [ "$funnel_on" = 1 ] && [ -n "$TAILSCALE_BIN" ]; then
    "$TAILSCALE_BIN" funnel reset >/dev/null 2>&1 || true
  fi
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

if [ -z "$TAILSCALE_BIN" ]; then
  echo "Tailscale is not installed." >&2
  echo "Install the Standalone app from https://tailscale.com/download/mac, sign in," >&2
  echo "then run this script again." >&2
  exit 1
fi

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

echo "4/4 Opening the public Tailscale Funnel link…"
if ! "$TAILSCALE_BIN" status >/dev/null 2>&1; then
  echo "Tailscale is installed but not signed in / connected." >&2
  echo "Open the Tailscale app, sign in, turn it on, then re-run this script." >&2
  exit 1
fi

# Clear any previous Funnel route so we always publish the live web port.
"$TAILSCALE_BIN" funnel reset >/dev/null 2>&1 || true

funnel_out="$LIVE/funnel.log"
if ! "$TAILSCALE_BIN" funnel --bg --yes --https=443 "http://127.0.0.1:$WEB_PORT" \
  >"$funnel_out" 2>&1; then
  echo "Could not start Tailscale Funnel; see $funnel_out" >&2
  cat "$funnel_out" >&2
  echo >&2
  echo "First-time setup: open https://login.tailscale.com/f/funnel and enable Funnel," >&2
  echo "then confirm HTTPS certificates are on for your tailnet." >&2
  exit 1
fi
funnel_on=1

url=""
for _ in $(seq 1 60); do
  # Prefer the Funnel status JSON; fall back to parsing text status / command output.
  if status_json="$("$TAILSCALE_BIN" funnel status --json 2>/dev/null || true)"; then
    url="$(printf '%s' "$status_json" | python3 -c '
import json, sys, re
raw = sys.stdin.read().strip()
if not raw:
    raise SystemExit(0)
try:
    data = json.loads(raw)
except json.JSONDecodeError:
    m = re.search(r"https://[a-zA-Z0-9.-]+\.ts\.net", raw)
    print(m.group(0) if m else "")
    raise SystemExit(0)
# Common shapes: {"Success":{...}} or nested ServeConfig-like maps with "HTTPS"/"Funnel".
def walk(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and v.startswith("https://") and ".ts.net" in v:
                yield v.rstrip("/")
            yield from walk(v)
    elif isinstance(obj, list):
        for i in obj:
            yield from walk(i)
urls = list(walk(data))
if urls:
    print(urls[0])
' 2>/dev/null || true)"
  fi
  if [ -z "$url" ]; then
    url="$(
      { cat "$funnel_out"; "$TAILSCALE_BIN" funnel status 2>/dev/null || true; } \
        | grep -Eo 'https://[a-zA-Z0-9.-]+\.ts\.net' | head -1 || true
    )"
  fi
  if [ -z "$url" ]; then
    # Last resort: machine DNS name from status.
    dns_name="$("$TAILSCALE_BIN" status --json 2>/dev/null | python3 -c '
import json, sys
data = json.load(sys.stdin)
self = data.get("Self") or {}
dns = self.get("DNSName") or ""
print(dns.rstrip("."))
' 2>/dev/null || true)"
    if [ -n "$dns_name" ]; then
      url="https://$dns_name"
    fi
  fi
  [ -n "$url" ] && break
  sleep 1
done

if [ -z "$url" ]; then
  echo "Funnel started but no public URL was found; see $funnel_out" >&2
  "$TAILSCALE_BIN" funnel status >&2 || true
  exit 1
fi
echo "$url" >"$LIVE/url.txt"

caffeinate -dimsu -w $$ &
pids+=($!)

cat <<EOF

  Badminton Lab is online:

    $url/login

  Admin signs in as "admin", the coach as "jeff" (passwords in .env).
  This link stays the same while Tailscale Funnel is on this Mac.
  Keep this window open; Ctrl+C takes the site offline.

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
