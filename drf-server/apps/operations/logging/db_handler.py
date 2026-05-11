import logging
from threading import local

from django.conf import settings


class DBLogHandler(logging.Handler):
    """
    Python logging → AppLog 영속화 핸들러

    [재귀 가드]
    DB INSERT 실패 또는 핸들러 자체 예외가 logger.error()를 다시 호출하는 무한 루프 회피.
    thread-local 플래그로 emit 진입 1회만 허용.

    [실패 정책]
    예외 발생 시 silent fail — stdout 핸들러가 백업으로 동작 (settings.LOGGING).

    [PR-D 비동기 처리 — 2026-05-09]
    Celery worker로 fire-and-forget delay() — web pod의 응답 latency 영향 0.
    Docker/K8s 배포 시 Celery worker pod 분리로 격리. broker(Redis) 다운 시
    `applog_create_task.delay()` 자체가 OperationalError를 발생 → graceful fallback으로
    동기 ORM INSERT 시도 (학습 환경 broker 미가동도 허용).

    [강제 동기 모드]
    `settings.APPLOG_FORCE_SYNC = True` 시 비동기 우회 (테스트 환경에서 즉각 검증용).
    """

    _guard = local()

    def emit(self, record):
        if getattr(self._guard, "active", False):
            return
        self._guard.active = True
        try:
            payload = {
                "log_category": self._infer_category(record),
                "service_module": record.name,
                "level": record.levelname,
                "message": self.format(record),
            }
            if getattr(settings, "APPLOG_FORCE_SYNC", False):
                self._sync_insert(payload)
                return
            try:
                from apps.operations.tasks.applog_task import applog_create_task

                applog_create_task.delay(**payload)
            except Exception:
                # broker 다운 / 미가동 — 동기 fallback
                self._sync_insert(payload)
        except Exception:
            # silent fail — stdout 핸들러가 백업
            pass
        finally:
            self._guard.active = False

    @staticmethod
    def _sync_insert(payload: dict) -> None:
        """broker fallback — Celery 미가용 시 동기 ORM INSERT."""
        try:
            from apps.operations.models import AppLog

            AppLog.objects.create(**payload)
        except Exception:
            pass

    @staticmethod
    def _infer_category(record):
        name = record.name.lower()
        if "celery" in name or "batch" in name or "task" in name:
            return "batch"
        if record.levelno >= logging.ERROR:
            return "error"
        return "service"
