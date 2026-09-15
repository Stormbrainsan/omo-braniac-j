#!/bin/sh
set -e

echo "Waiting for postgres..."
until python - <<'PYCODE'
import os, sys, socket
host = os.environ.get("POSTGRES_HOST", "db")
port = int(os.environ.get("POSTGRES_PORT", 5432))
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(1)
try:
    s.connect((host, port))
    s.close()
    sys.exit(0)
except Exception:
    sys.exit(1)
PYCODE
do
  sleep 1
done
echo "Postgres is up."

python manage.py migrate --noinput
python manage.py collectstatic --noinput || true

exec "$@"
