import logging
from threading import local


class DBLogHandler(logging.Handler):
    """
    Python logging → AppLog 영속화 핸들러

    [재귀 가드]
    DB INSERT 실패 또는 핸들러 자체 예외가 logger.error()를 다시 호출하는 무한 루프 회피.
    thread-local 플래그로 emit 진입 1회만 허용.

    [실패 정책]
    예외 발생 시 silent fail — stdout 핸들러가 백업으로 동작 (settings.LOGGING).

    [Phase 2 시점]
    동기 INSERT. 운영 부하 측정 후 Phase 4에서 Celery 큐 또는 thread-pool 도입 검토.
    """

    _guard = local()

    def emit(self, record):
        if getattr(self._guard, "active", False):
            return
        self._guard.active = True
        try:
            from apps.operations.models import AppLog

            AppLog.objects.create(
                log_category=self._infer_category(record),
                service_module=record.name,
                level=record.levelname,
                message=self.format(record),
            )
        except Exception:
            # silent fail — stdout 핸들러가 백업
            pass
        finally:
            self._guard.active = False

    @staticmethod
    def _infer_category(record):
        name = record.name.lower()
        if "celery" in name or "batch" in name or "task" in name:
            return "batch"
        if record.levelno >= logging.ERROR:
            return "error"
        return "service"
