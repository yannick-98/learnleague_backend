#!/bin/bash
set -e

# DB_* vars take precedence; fall back to POSTGRES_* for compatibility
_DB_HOST="${DB_HOST:-${POSTGRES_HOST:-db}}"
_DB_PORT="${DB_PORT:-${POSTGRES_PORT:-5432}}"
_DB_NAME="${DB_NAME:-${POSTGRES_DB:-learnleague}}"
_DB_USER="${DB_USER:-${POSTGRES_USER:-learnleague}}"
_DB_PASSWORD="${DB_PASSWORD:-${POSTGRES_PASSWORD:-}}"

echo "Waiting for database at ${_DB_HOST}:${_DB_PORT}..."
while ! python -c "
import psycopg2, os, sys
try:
    psycopg2.connect(
        host='${_DB_HOST}',
        port='${_DB_PORT}',
        dbname='${_DB_NAME}',
        user='${_DB_USER}',
        password='${_DB_PASSWORD}',
    )
    print('Database ready')
except Exception as e:
    print(f'Database not ready: {e}', file=sys.stderr)
    sys.exit(1)
" 2>/dev/null; do
  echo "Database not ready, waiting 2s..."
  sleep 2
done

echo "Running migrations..."
python manage.py migrate --noinput

echo "Setting up periodic Celery Beat tasks..."
python manage.py setup_periodic_tasks

echo "Collecting static files..."
python manage.py collectstatic --noinput --clear

echo "Starting Daphne ASGI server..."
exec daphne -b 0.0.0.0 -p 8000 config.asgi:application
