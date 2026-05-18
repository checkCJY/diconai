import logging
import os

from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(name="apps.operations.tasks.db_health_task.record_db_health")
def record_db_health():
    """
    SQLite DB 파일 크기를 읽어 SQLITE_DB_SIZE Gauge에 기록한다.

    Beat가 60초마다 실행 — Prometheus scrape 주기(15초)보다 길지만
    파일 크기는 급격히 변하지 않으므로 1분 단위로 충분하다.

    판단 기준:
      > 5GB : 경고 — 데이터 보관 정책 점검
      > 10GB: 경보 — 즉시 cleanup 또는 truncate 필요 (어제 사고 기준)
    """
    from apps.core.metrics import SQLITE_DB_SIZE

    db_url = settings.DATABASES.get("default", {}).get("NAME", "")
    if not db_url or not str(db_url).endswith(".sqlite3"):
        # PostgreSQL 등 SQLite가 아닌 경우 스킵 — PG 전환 후 자동 비활성화.
        return

    db_path = str(db_url)
    try:
        size = os.path.getsize(db_path)
        SQLITE_DB_SIZE.set(size)

        size_gb = size / (1024 ** 3)
        if size_gb > 10:
            logger.error(
                "[db_health] SQLite DB 크기 %.1fGB — 즉시 cleanup 필요 (임계: 10GB)",
                size_gb,
            )
        elif size_gb > 5:
            logger.warning(
                "[db_health] SQLite DB 크기 %.1fGB — 데이터 보관 정책 점검 (임계: 5GB)",
                size_gb,
            )
    except OSError as e:
        logger.error("[db_health] DB 파일 크기 읽기 실패: %s", e)
