"""
DataRetentionPolicy 신규 카테고리 기본 정책 시드.

[idempotent — 운영자 수정 보호]
get_or_create 사용. 마이그 재실행 시 기존 row 발견하면 skip —
운영자가 어드민에서 수정한 값을 덮어쓰지 않음.

[보관 기간 근거]
- ml_result      : 6개월 — 추론 결과·feature snapshot 용량 크므로 짧게
- ml_model       : 90일  — is_active=False 후 90일 경과한 비활성 모델 정리
- system_log     : 1년   — 운영 감사 목적, 법적 의무 없음
- integration_log: 3개월 — FastAPI→DRF 호출 빈도 높아 용량 누적 빠름
- app_log        : 3개월 — Python logging 영속화, 단기 디버깅 목적
- login_log      : 1년   — 보안 감사 목적
- notification   : 3개월 — 발송 이력, 운영자 확인 후 불필요
"""

from django.db import migrations

NEW_POLICIES = [
    # ── AI/ML ────────────────────────────────────────────────────
    {
        "device_type": "ml",
        "data_category": "ml_result",
        "raw_retention_days": 180,
        "history_retention_days": 180,
        "delete_cycle": "monthly_15",
        "memo": "AI 추론 결과 (MLAnomalyResult) — 매월 15일 6개월 초과 row 삭제",
    },
    {
        "device_type": "ml",
        "data_category": "ml_model",
        "raw_retention_days": 90,
        "history_retention_days": 90,
        "delete_cycle": "monthly_15",
        "memo": "비활성 AI 모델 — 매월 15일 is_active=False + 90일 초과 시 DB행 + .pkl 삭제",
    },
    # ── 시스템 로그 ──────────────────────────────────────────────
    {
        "device_type": "system",
        "data_category": "system_log",
        "raw_retention_days": 365,
        "history_retention_days": 365,
        "delete_cycle": "monthly_1",
        "memo": "시스템·사용자활동·지도편집 로그 — 매월 1일 1년 초과 row 삭제",
    },
    {
        "device_type": "system",
        "data_category": "integration_log",
        "raw_retention_days": 90,
        "history_retention_days": 90,
        "delete_cycle": "monthly_15",
        "memo": "FastAPI→DRF 연동 로그 — 매월 15일 3개월 초과 row 삭제",
    },
    {
        "device_type": "system",
        "data_category": "app_log",
        "raw_retention_days": 90,
        "history_retention_days": 90,
        "delete_cycle": "monthly_15",
        "memo": "앱 에러/경고 로그 — 매월 15일 3개월 초과 row 삭제",
    },
    {
        "device_type": "system",
        "data_category": "login_log",
        "raw_retention_days": 365,
        "history_retention_days": 365,
        "delete_cycle": "monthly_1",
        "memo": "로그인·로그아웃 이력 — 매월 1일 1년 초과 row 삭제",
    },
    {
        "device_type": "system",
        "data_category": "notification",
        "raw_retention_days": 90,
        "history_retention_days": 90,
        "delete_cycle": "monthly_15",
        "memo": "알림 발송 이력 — 매월 15일 3개월 초과 row 삭제",
    },
]


def seed(apps, schema_editor):
    DataRetentionPolicy = apps.get_model("operations", "DataRetentionPolicy")
    for p in NEW_POLICIES:
        DataRetentionPolicy.objects.get_or_create(
            device_type=p["device_type"],
            data_category=p["data_category"],
            defaults={
                "raw_retention_days": p["raw_retention_days"],
                "history_retention_days": p["history_retention_days"],
                "delete_cycle": p["delete_cycle"],
                "is_active": True,
                "memo": p["memo"],
            },
        )


def revert(apps, schema_editor):
    DataRetentionPolicy = apps.get_model("operations", "DataRetentionPolicy")
    for p in NEW_POLICIES:
        DataRetentionPolicy.objects.filter(
            device_type=p["device_type"],
            data_category=p["data_category"],
        ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0004_data_retention_new_categories"),
    ]

    operations = [
        migrations.RunPython(seed, revert),
    ]
