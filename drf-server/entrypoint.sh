#!/bin/sh
set -e
# 이성현 수정 — Pod IP를 ALLOWED_HOSTS에 런타임 주입 (* 없이 readinessProbe 통과)
POD_IP=$(hostname -i | awk '{print $1}')
export DJANGO_ALLOWED_HOSTS="${DJANGO_ALLOWED_HOSTS},${POD_IP}"


# prometheus_client multiprocess 모드 — drf + celery-worker가 같은 디렉토리에 쓰고
# /metrics 엔드포인트에서 합산해 노출한다. 두 컨테이너 모두 /app 볼륨을 공유하므로
# /app/prometheus_multiproc 을 공유 디렉토리로 사용.
if [ -n "${PROMETHEUS_MULTIPROC_DIR}" ]; then
    mkdir -p "${PROMETHEUS_MULTIPROC_DIR}"
    # 재기동 시 이전 프로세스가 남긴 stale .db 파일 제거.
    # 비정상 종료된 .db 파일이 남으면 MultiProcessCollector가 JSON 파싱 실패 → /metrics 500.
    find "${PROMETHEUS_MULTIPROC_DIR}" -name "*.db" -delete 2>/dev/null || true
fi

# RUN_MIGRATIONS=0 으로 두면 celery-worker/beat 컨테이너에서 중복 실행 방지.
# 변경 (이성현 수정) — migrate 완료 후 시퀀스 안전망
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    echo "[entrypoint] migrate --noinput"
    python manage.py migrate --noinput
    echo "[entrypoint] reset sequences"
    python manage.py sqlsequencereset \
        accounts alerts dashboard facilities geofence ml \
        monitoring notices notifications operations \
        positioning reference safety training \
        | python manage.py dbshell
fi

# COLLECT_STATIC=0 으로 두면 celery 컨테이너에서 스킵.
if [ "${COLLECT_STATIC:-1}" = "1" ]; then
    echo "[entrypoint] collectstatic --noinput --clear"
    python manage.py collectstatic --noinput --clear
fi

exec "$@"
