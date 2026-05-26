"""
AI 알람 (gas_anomaly_ai · power_anomaly_ai) 정책 정식 시드.

0009 에서 USER_FACING 9종 시드 후 0014 에서 AI enum 만 추가되고 정책 시드는
누락된 상태. power_anomaly_ai 는 임시명 "POWER_ANOMALY_AI default" 로 행이
존재하나 channels=[]·message_template='' 등 미완.

[idempotent]
- power_anomaly_ai: name="POWER_ANOMALY_AI default" 인 임시 행만 정상화.
  운영자가 이미 변경한 경우 패스.
- gas_anomaly_ai: get_or_create — 이미 있으면 패스.
"""

from django.db import migrations

GAS_ANOMALY_AI_ACTIONS = {
    "danger": [
        "해당 구역 작업자 대피",
        "누출 의심 센서 위치 확인",
        "환기 설비 가동",
        "센서/설비 상세 점검",
    ],
    "warning": [
        "해당 센서 농도 모니터링",
        "이상 지속 시 점검",
        "센서/설비 상세 점검",
    ],
}

POWER_ANOMALY_AI_ACTIONS = {
    "danger": [
        "설비 정지",
        "AI 이상 패턴 확인 후 센서/설비 상세 점검",
        "정밀 점검 후 책임자 보고",
        "정상화 후 가동 재개",
    ],
    "warning": [
        "부하·발열 추이 확인",
        "센서/설비 상세 점검",
        "이상 지속 시 정지",
    ],
}


def seed(apps, schema_editor):
    AlertPolicy = apps.get_model("alerts", "AlertPolicy")

    AlertPolicy.objects.filter(
        event_type="power_anomaly_ai",
        name="POWER_ANOMALY_AI default",
    ).update(
        name="전력 AI 이상 감지 전사 알림",
        target_user_types=["facility_admin", "worker"],
        channels=["popup"],
        message_template="{{ source_label }} 전력 AI 이상 — {{ summary }}",
        description="전력 설비 AI 이상 패턴 감지 시 관리자/작업자 알림",
        recommended_actions=POWER_ANOMALY_AI_ACTIONS,
    )

    AlertPolicy.objects.get_or_create(
        event_type="gas_anomaly_ai",
        target_facility=None,
        name="가스 AI 이상 감지 전사 알림",
        defaults={
            "policy_kind": "immediate",
            "target_user_types": ["super_admin", "facility_admin", "worker"],
            "target_sensor_ids": [],
            "target_device_ids": [],
            "target_geofence_ids": [],
            "channels": ["popup"],
            "message_template": "{{ source_label }} 가스 AI 이상 — {{ summary }}",
            "description": "가스 센서 AI 이상 패턴 감지 시 모든 사용자에게 즉시 알림",
            "is_active": True,
            "recommended_actions": GAS_ANOMALY_AI_ACTIONS,
        },
    )


def revert(apps, schema_editor):
    AlertPolicy = apps.get_model("alerts", "AlertPolicy")
    AlertPolicy.objects.filter(
        event_type="gas_anomaly_ai",
        name="가스 AI 이상 감지 전사 알림",
    ).delete()
    AlertPolicy.objects.filter(
        event_type="power_anomaly_ai",
        name="전력 AI 이상 감지 전사 알림",
    ).update(name="POWER_ANOMALY_AI default")


class Migration(migrations.Migration):
    dependencies = [
        ("alerts", "0021_seed_recommended_actions"),
    ]

    operations = [
        migrations.RunPython(seed, revert),
    ]
