#!/usr/bin/env bash
# Serve StrengthLab with a production WSGI server.
#   ./run.sh            -> http://0.0.0.0:5001
#   PORT=8080 ./run.sh  -> http://0.0.0.0:8080
set -euo pipefail

PORT="${PORT:-5001}"
WORKERS="${WEB_CONCURRENCY:-3}"

if [ -z "${SECRET_KEY:-}" ]; then
  echo "SECRET_KEY is not set; falling back to the generated .secret_key file." >&2
fi

exec gunicorn \
  --bind "0.0.0.0:${PORT}" \
  --workers "${WORKERS}" \
  --threads 2 \
  --timeout 60 \
  --access-logfile - \
  app:app
