#!/bin/sh
# Default mode "web": check the deployment, migrate, then run Gunicorn.
# Any other command (run_scheduler, setup_admin, ...) is executed as given.
set -eu

if [ "${1:-web}" = "web" ]; then
    python manage.py check --deploy
    if [ "${AUTO_MIGRATE:-true}" != "false" ]; then
        python manage.py migrate --noinput
    fi
    exec gunicorn config.wsgi:application \
        --bind 0.0.0.0:8000 \
        --workers "${GUNICORN_WORKERS:-2}" \
        --timeout "${GUNICORN_TIMEOUT:-240}" \
        --access-logfile -
fi

exec "$@"
