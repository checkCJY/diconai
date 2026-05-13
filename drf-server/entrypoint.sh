#!/bin/sh
set -e

# prometheus_client multiprocess 모드 — drf + celery-worker가 같은 디렉토리에 쓰고
# /metrics 엔드포인트에서 합산해 노출한다. 두 컨테이너 모두 /app 볼륨을 공유하므로
# /app/prometheus_multiproc 을 공유 디렉토리로 사용.
if [ -n "${PROMETHEUS_MULTIPROC_DIR}" ]; then
    mkdir -p "${PROMETHEUS_MULTIPROC_DIR}"
fi

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
