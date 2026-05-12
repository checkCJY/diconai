# apps/core/sqlite_pragmas.py — SQLite 연결당 PRAGMA 적용
#
# connection_created signal에 receiver를 걸어 매 connection마다 WAL/busy_timeout/synchronous를
# 설정한다. PostgreSQL 등 다른 DB 엔진으로 이관 시 connection.vendor != "sqlite" 가드로
# 자동 no-op이 되어 별도 정리 작업 없이 유지 가능.
#
# - journal_mode=WAL: 동시 reader/single writer 허용 → "database is locked" 빈도 급감
# - busy_timeout=5000: 잠금 충돌 시 최대 5초 재시도 → 폭주 시 즉시 OperationalError 회피
# - synchronous=NORMAL: WAL과 짝, 충분히 안전하면서 fsync 부담 감소
# - foreign_keys=ON: SQLite 기본 OFF인 FK 강제 (Django ORM이 의존)
from django.db.backends.signals import connection_created
from django.dispatch import receiver


@receiver(connection_created)
def apply_sqlite_pragmas(sender, connection, **_):
    if connection.vendor != "sqlite":
        return
    with connection.cursor() as cur:
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA busy_timeout=5000;")
        cur.execute("PRAGMA synchronous=NORMAL;")
        cur.execute("PRAGMA foreign_keys=ON;")
