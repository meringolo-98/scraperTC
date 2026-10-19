#!/usr/bin/env bash
set -euo pipefail

if curl -sf -o /dev/null --max-time 2 http://127.0.0.1:8787/api/status; then
  echo "CardHunt already listening on :8787"
  exit 0
fi

exec cardhunt serve --host 0.0.0.0 --port 8787
