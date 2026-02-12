#!/usr/bin/env sh
set -e

mkdir -p /app/instance

# Ensure DB tables/default accounts exist before serving traffic.
python -c "from app import init_db; init_db()"

exec gunicorn \
  --bind "0.0.0.0:${PORT:-5000}" \
  --workers "${GUNICORN_WORKERS:-1}" \
  --threads "${GUNICORN_THREADS:-4}" \
  --timeout "${GUNICORN_TIMEOUT:-120}" \
  app:app
