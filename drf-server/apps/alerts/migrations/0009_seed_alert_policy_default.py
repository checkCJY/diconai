"""
AlertPolicy 기본 9종 시드 (PR-C).

USER_FACING_ALARM_TYPES 9종 (SENSOR_FAULT 제외)에 대해 전사 정책(target_facility=None)
1개씩 자동 생성. 운영 진입 시 어드민에서 facility별 세부 정책 추가.

[idempotent — 운영자 수정 보호]
get_or_create — (event_type, target_facility=None, name) 조합으로 첫 생성만 처리.
운영자가 message_template/target_user_types 수정해도 마이그 재실행 시 보존.

[Channel 값 — Phase 3-e]
Notification.Channel: popup / push / sms / email. Phase 3은 popup만 운영. PR-D에서
SMS/email 채널 인프라 도입 시 어드민에서 추가 설정.

[message_template]
Django Template 문법. context 표준 키: source_label, risk_level, level, summary,
facility_name, event_type. Phase 4-f template_renderer가 렌더.
"""

from django.db import migrations

DEFAULT_POLICIES = [
    {
        "name": "가스 임계치 전사 알림",
        "event_type": "gas_threshold",
        "target_user_types": ["super_admin", "facility_admin", "worker"],
        "channels": ["popup"],
        "message_template": "{{ source_label }} 가스 위험 — {{ summary }}",
        "description": "유해가스 임계치 초과 시 모든 사용자에게 즉시 알림",
    },
    {
        "name": "전력 과부하 전사 알림",
        "event_type": "power_overload",
        "target_user_types": ["facility_admin", "worker"],
        "channels": ["popup"],
        "message_template": "{{ source_label }} 전력 과부하 — {{ summary }}",
        "description": "전력 과부하 감지 시 관리자/작업자 알림",
    },
    {
        "name": "위험구역 진입 전사 알림",
        "event_type": "geofence_intrusion",
        "target_user_types": ["facility_admin", "worker"],
        "channels": ["popup"],
        "message_template": "{{ source_label }} 위험구역 진입 — {{ summary }}",
        "description": "지오펜스 위험구역 진입 시 관리자/작업자 알림",
    },
    {
        "name": "PPE 미착용 전사 알림",
        "event_type": "ppe_violation",
        "target_user_types": ["facility_admin"],
        "channels": ["popup"],
        "message_template": "PPE 미착용 감지 — {{ source_label }}",
        "description": "보호장비 미착용 감지 시 관리자 알림",
    },
    {
        "name": "안전 점검 미완료 전사 알림",
        "event_type": "safety_check_pending",
        "target_user_types": ["worker"],
        "channels": ["popup"],
        "message_template": "안전 점검 미완료 — {{ summary }}",
        "description": "작업 안전 체크리스트 미완료 시 작업자 알림",
    },
    {
        "name": "VR 교육 미이수 전사 알림",
        "event_type": "vr_training_not_done",
        "target_user_types": ["worker"],
        "channels": ["popup"],
        "message_template": "VR 교육 미이수 — {{ summary }}",
        "description": "필수 VR 교육 미수료 시 작업자 알림",
    },
    {
        "name": "정기 점검 예정 전사 알림",
        "event_type": "inspection_scheduled",
        "target_user_types": ["facility_admin"],
        "channels": ["popup"],
        "message_template": "점검 예정 — {{ summary }}",
        "description": "정기 점검 일정 도래 시 관리자 알림",
    },
    {
        "name": "보관 주기 실패 전사 알림",
        "event_type": "storage_overdue",
        "target_user_types": ["facility_admin"],
        "channels": ["popup"],
        "message_template": "보관 주기 실패 — {{ summary }}",
        "description": "데이터 보관 정책 미실행 시 관리자 알림",
    },
    {
        "name": "배치 실패 전사 알림",
        "event_type": "batch_failed",
        "target_user_types": ["super_admin"],
        "channels": ["popup"],
        "message_template": "배치 실패 — {{ summary }}",
        "description": "예약 배치 작업 실패 시 슈퍼 관리자 알림",
    },
]


def seed(apps, schema_editor):
    AlertPolicy = apps.get_model("alerts", "AlertPolicy")
    for p in DEFAULT_POLICIES:
        AlertPolicy.objects.get_or_create(
            event_type=p["event_type"],
            target_facility=None,
            name=p["name"],
            defaults={
                "policy_kind": "immediate",
                "target_user_types": p["target_user_types"],
                "target_sensor_ids": [],
                "target_device_ids": [],
                "target_geofence_ids": [],
                "channels": p["channels"],
                "message_template": p["message_template"],
                "description": p["description"],
                "is_active": True,
            },
        )


def revert(apps, schema_editor):
    AlertPolicy = apps.get_model("alerts", "AlertPolicy")
    for p in DEFAULT_POLICIES:
        AlertPolicy.objects.filter(
            event_type=p["event_type"], target_facility=None, name=p["name"]
        ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("alerts", "0008_alarmrecord_updated_at_alarmrecord_updated_by_and_more"),
    ]

    operations = [
        migrations.RunPython(seed, revert),
    ]
