"""
PowerDevice.channel_meta 16채널 추정값 시드 (전력 Phase 1).

[목적]
power-threshold-roadmap.md §1단계 — 채널별 라벨+정격(W·A·V)을 DB에서 관리.
이전: power_alarm.py / power_service.py의 하드코딩된 8개 설비명 매핑.
이후: evaluate_*_risk()가 channel_meta[ch]["rated_*"]로 정격 % 환산.

[per-key merge]
기존 channel_meta에 운영자가 입력한 키는 보존. 누락된 채널/필드만 채움.
운영 DB에 손상 없음을 보장.

[revert]
운영자 정정값과 시드값 구분이 불가능하므로 no-op. 채널 메타 자체를 비우려면
어드민에서 직접 편집할 것.
"""

from django.db import migrations

DEFAULT_CHANNEL_META = {
    "1": {"name": "압연기", "rated_w": 7500, "rated_a": 30, "rated_v": 380},
    "2": {"name": "송풍기", "rated_w": 3700, "rated_a": 15, "rated_v": 380},
    "3": {"name": "집진기", "rated_w": 5500, "rated_a": 22, "rated_v": 380},
    "4": {"name": "전자기 교반기", "rated_w": 4000, "rated_a": 16, "rated_v": 380},
    "5": {"name": "냉각펌프", "rated_w": 2200, "rated_a": 10, "rated_v": 380},
    "6": {"name": "유압장치", "rated_w": 3700, "rated_a": 15, "rated_v": 380},
    "7": {"name": "컨베이어", "rated_w": 1500, "rated_a": 7, "rated_v": 380},
    "8": {"name": "분쇄기", "rated_w": 5500, "rated_a": 22, "rated_v": 380},
    "9": {"name": "메인 전력반", "rated_w": 15000, "rated_a": 50, "rated_v": 380},
    "10": {"name": "분전반 1호", "rated_w": 7500, "rated_a": 30, "rated_v": 380},
    "11": {"name": "분전반 2호", "rated_w": 7500, "rated_a": 30, "rated_v": 380},
    "12": {"name": "보조 모터 1", "rated_w": 3000, "rated_a": 14, "rated_v": 380},
    "13": {"name": "보조 모터 2", "rated_w": 3000, "rated_a": 14, "rated_v": 380},
    "14": {"name": "공조설비", "rated_w": 5500, "rated_a": 22, "rated_v": 380},
    "15": {"name": "조명/제어", "rated_w": 1000, "rated_a": 5, "rated_v": 220},
    "16": {"name": "예비", "rated_w": 2200, "rated_a": 10, "rated_v": 380},
}


def seed(apps, schema_editor):
    PowerDevice = apps.get_model("facilities", "PowerDevice")
    for device in PowerDevice.objects.all():
        meta = dict(device.channel_meta or {})
        changed = False
        for ch_key, defaults in DEFAULT_CHANNEL_META.items():
            existing = meta.get(ch_key) or {}
            merged = {**defaults, **existing}
            if merged != existing:
                meta[ch_key] = merged
                changed = True
        if changed:
            device.channel_meta = meta
            device.save(update_fields=["channel_meta", "updated_at"])


def revert(apps, schema_editor):
    # 운영자 정정값 보호 — 시드 키만 골라 제거하기 어려워 no-op.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("facilities", "0016_seed_facility_default_group"),
    ]

    operations = [
        migrations.RunPython(seed, revert),
    ]
