# apps/core/management/commands/reset_pg_sequences.py
# 이성현 추가 — PG sequence reset management command
# loaddata 또는 수동 대량 INSERT 후 PK 충돌이 발생할 때 실행하는 유틸리티 커맨드

from django.core.management.base import BaseCommand
from django.db import connection

# PG 전체 테이블의 id sequence 를 현재 max(id) 값으로 재설정하는 SQL
# EXCEPTION WHEN OTHERS THEN NULL:
#   django_session 처럼 PK 가 문자열인 테이블은 pg_get_serial_sequence 가 에러를 던짐
#   에러가 나면 그냥 건너뛰고 다음 테이블로 이동 (전체 SQL 이 멈추지 않도록)
_RESET_SQL = """
DO $$
DECLARE
    r   RECORD;
    seq TEXT;
BEGIN
    -- public 스키마의 모든 테이블을 순회
    FOR r IN
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public'
    LOOP
        BEGIN
            -- 해당 테이블의 id 컬럼 sequence 이름 조회
            seq := pg_get_serial_sequence(
                format('public.%%I', r.tablename), 'id'
            );
            IF seq IS NOT NULL THEN
                -- sequence 를 현재 max(id) 값으로 재설정
                EXECUTE format(
                    'SELECT setval(%%L,
                        COALESCE((SELECT MAX(id) FROM %%I), 1),
                        (SELECT MAX(id) IS NOT NULL FROM %%I))',
                    seq, r.tablename, r.tablename
                );
            END IF;
        EXCEPTION WHEN OTHERS THEN
            -- string PK 테이블 등 에러 발생 시 해당 테이블만 건너뜀
            NULL;
        END;
    END LOOP;
END $$;
"""


class Command(BaseCommand):
    help = "PostgreSQL PK sequence 를 현재 max(id) 로 재설정한다 (loaddata 후 실행)"

    def handle(self, *args, **options):
        self.stdout.write("sequence reset 시작...")
        with connection.cursor() as cursor:
            cursor.execute(_RESET_SQL)
        self.stdout.write(self.style.SUCCESS("sequence reset 완료"))
