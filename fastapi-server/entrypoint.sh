#!/bin/sh
set -e

# prometheus_client multiprocess 모드 대비 — 현재 uvicorn workers=1 (단일 프로세스)이라
# PROMETHEUS_MULTIPROC_DIR 미설정 상태. multi-worker 전환 시 아래 4가지 작업 필요:
#   1) docker-compose에 PROMETHEUS_MULTIPROC_DIR env 추가
#   2) app.py generate_latest() → MultiProcessCollector 패턴으로 교체
#   3) uvicorn signal handler 또는 별도 cleanup 방식 적용 (uvicorn은 child_exit 훅 없음)
#   4) 이 entrypoint의 cleanup 블록이 자동으로 활성화됨
if [ -n "${PROMETHEUS_MULTIPROC_DIR}" ]; then
    mkdir -p "${PROMETHEUS_MULTIPROC_DIR}"
    # 재기동 시 이전 프로세스가 남긴 stale .db 파일 제거.
    # 비정상 종료된 .db 파일이 남으면 MultiProcessCollector JSON 파싱 실패 → /metrics 500.
    find "${PROMETHEUS_MULTIPROC_DIR}" -name "*.db" -delete
fi

exec "$@"
