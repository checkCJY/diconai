"""
Django 세션 정리 Celery 태스크.

[배경]
Django의 DB 세션 백엔드(django.contrib.sessions.backends.db)는 사용자가 로그인할 때마다
django_session 테이블에 행을 생성한다. 세션이 만료돼도 Django는 자동 삭제하지 않음.
방치하면 탈퇴한 사용자·만료된 브라우저 세션이 무기한 누적 → 테이블이 불필요하게 비대해짐.

[해결 방법]
Django 내장 management command `clearsessions`를 Celery 태스크로 래핑.
CELERY_BEAT_SCHEDULE에서 주 1회(매주 일요일 새벽) 실행.

[clearsessions 동작]
django.contrib.sessions.backends.db.SessionStore.clear_expired() 호출 →
session_key가 expire_date < now()인 모든 행 삭제. 활성 세션은 건드리지 않음.

[DataRetentionPolicy와의 관계]
세션은 "보관 기간"을 설정할 성격이 아님 — 만료 즉시 불필요.
DataRetentionPolicy 순회 대상에서 제외하고 본 태스크가 독립적으로 관리.
"""

import logging

from celery import shared_task
from django.core.management import call_command

logger = logging.getLogger(__name__)


@shared_task
def clear_expired_sessions() -> dict:
    """
    만료된 Django 세션 삭제.

    Django clearsessions 커맨드 호출 — expire_date < now() 인 세션 행 전부 삭제.
    활성 세션(아직 만료 안 된 것)은 삭제하지 않음.

    Returns:
        {"status": "ok"} — 성공 시. 실패 시 예외 전파 (Celery retry 정책 적용).
    """
    logger.info("[sessions] action=clear_start")
    try:
        # clearsessions는 stdout 출력 없음 — 삭제 건수 반환도 없음.
        # 실패 시 CommandError 예외 발생 → Celery가 태스크 실패로 기록.
        call_command("clearsessions")
        logger.info("[sessions] action=clear_done")
        return {"status": "ok"}
    except Exception:
        logger.exception("[sessions] action=clear_failed")
        raise
