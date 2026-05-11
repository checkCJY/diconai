"""
0003_loginlog — noop fix (Phase 1 통합 PR)

원래 본 파일은 LoginLog를 CreateModel로 다시 만들고 있었으나, 0001_initial이
LoginLog partial 정의를 만들고 0002_initial이 user FK + indexes 추가로 완전체화하므로
0003의 CreateModel은 중복이며 새 환경에서 'table already exists' 충돌을 일으킨다.

운영 DB에는 이미 0003가 "적용됨"으로 표시되어 있어 본 변경이 실행되지 않는다 →
운영 영향 없음. 새 환경에서는 noop으로 통과 → 충돌 해소.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_initial"),
    ]

    operations = []
