"""
AlertPolicy.recommended_actions 시드 — event_detail.js 의 RECOMMENDED_ACTIONS
매트릭스를 DB 로 이관.

[idempotent]
JSON 이 빈 dict 인 행에만 채움. 운영자가 이미 편집한 값은 보존.

[누락 event_type]
JS 에 정의 안 된 event_type (safety_check_pending, vr_training_not_done,
inspection_scheduled, sensor_fault) 은 RECOMMENDED_DEFAULT (3 단계 fallback)
로 채움 — 운영자가 빈 화면 대신 편집 출발점 확보.
"""

from django.db import migrations

# event_type → recommended_actions dict
# (alarm_type × risk_level) 매트릭스. level 분기 없는 type 은 "default" 키.
SEED_ACTIONS = {
    "gas_threshold": {
        "danger": [
            "작업자 앱 긴급 알림 발송",
            "현장 작업 중지 및 대피 안내",
            "환기 설비 가동",
            "가스 농도 정상 복귀 후 조치 상태 갱신",
        ],
        "warning": [
            "작업 중단 + 환기",
            "농도 추이 모니터링",
            "책임자 통보",
            "정상화 후 조치 상태 갱신",
        ],
    },
    "gas_anomaly_ai": {
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
    },
    "power_overload": {
        "danger": [
            "해당 설비 즉시 정지",
            "부하·발열 점검",
            "책임자 통보",
            "정상화 후 가동 재개",
        ],
        "warning": [
            "설비 부하·온도 확인",
            "부하 추이 모니터링",
            "이상 지속 시 정지",
        ],
    },
    "power_anomaly_ai": {
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
    },
    "geofence_intrusion": {
        "danger": [
            "해당 작업자에게 즉시 이탈 지시",
            "작업자 위치·안전 확인",
            "책임자 통보",
        ],
        "warning": [
            "작업자 위치 확인",
            "구역 이탈 안내",
            "책임자 통보",
        ],
    },
    "ppe_violation": {
        "default": [
            "작업자에게 PPE 착용 지시",
            "PPE 종류 확인",
            "작업 진행 전 재확인",
        ],
    },
    "sensor_fault": {
        "default": [
            "센서 통신 상태 확인",
            "펌웨어·전원 점검",
            "지속 시 설비팀 연락",
        ],
    },
    "batch_failed": {
        "default": [
            "배치 로그 확인",
            "원인 분석",
            "재실행",
        ],
    },
    "storage_overdue": {
        "default": [
            "보관 주기 도래 항목 확인",
            "점검·갱신",
            "상태 갱신",
        ],
    },
}

# JS RECOMMENDED_DEFAULT — 미정의 event_type 의 fallback.
FALLBACK_ACTIONS = {
    "default": [
        "알람 종류 확인",
        "관리자에게 보고",
        "조치 후 상태 갱신",
    ],
}


def seed(apps, schema_editor):
    AlertPolicy = apps.get_model("alerts", "AlertPolicy")
    for policy in AlertPolicy.objects.filter(recommended_actions={}):
        actions = SEED_ACTIONS.get(policy.event_type, FALLBACK_ACTIONS)
        policy.recommended_actions = actions
        policy.save(update_fields=["recommended_actions"])


def revert(apps, schema_editor):
    AlertPolicy = apps.get_model("alerts", "AlertPolicy")
    AlertPolicy.objects.update(recommended_actions={})


class Migration(migrations.Migration):
    dependencies = [
        ("alerts", "0020_add_recommended_actions"),
    ]

    operations = [
        migrations.RunPython(seed, revert),
    ]
