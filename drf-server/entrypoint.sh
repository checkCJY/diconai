#!/bin/sh
set -e

# RUN_MIGRATIONS=0 으로 두면 celery-worker/beat 컨테이너에서 중복 실행 방지.
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    echo "[entrypoint] migrate --noinput"
    python manage.py migrate --noinput
fi

# COLLECT_STATIC=0 으로 두면 celery 컨테이너에서 스킵.
if [ "${COLLECT_STATIC:-1}" = "1" ]; then
    echo "[entrypoint] collectstatic --noinput --clear"
    python manage.py collectstatic --noinput --clear
fi

exec "$@"
