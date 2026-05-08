"""
3c 마이그 (b) — default Revision/Session 백필.

forward 알고리즘:
  1. SafetyStatus.check_item 존재 + session=NULL인 row를 facility별로 묶음
  2. facility별 default Revision get_or_create (version=1, is_active=True, revision_data={"sections": []})
  3. SafetyStatus 각각에 대해:
       - facility = check_item.facility
       - date = checked_at.date() if checked_at else created_at.date()
       - revision = facility의 default Revision
       - (worker, date, revision) Session get_or_create
       - SafetyStatus.session = session
  4. check_item이 NULL인 row는 facility 추론 불가 → skip (session=NULL 유지)
     이후 단계 (e) NOT NULL 전환 전에 별도 정리 필요 — 학습 환경에서는 사실상 0건

reverse:
  1. 본 마이그가 매핑한 모든 SafetyStatus.session을 NULL로 되돌림
  2. 본 마이그가 자동 생성한 default Revision (version=1, revision_data={"sections": []})
     은 안전을 위해 자동 삭제하지 않음 — 운영자가 명시적 정리
"""

from django.db import migrations


def backfill_default_session(apps, schema_editor):
    SafetyStatus = apps.get_model("safety", "SafetyStatus")
    SafetyCheckSession = apps.get_model("safety", "SafetyCheckSession")
    SafetyChecklistRevision = apps.get_model("safety", "SafetyChecklistRevision")

    statuses_with_item = SafetyStatus.objects.filter(
        session__isnull=True, check_item__isnull=False
    ).select_related("check_item")

    revision_cache = {}  # facility_id -> Revision 인스턴스

    for status in statuses_with_item:
        facility_id = status.check_item.facility_id
        if facility_id not in revision_cache:
            revision, _ = SafetyChecklistRevision.objects.get_or_create(
                facility_id=facility_id,
                version=1,
                defaults={
                    "revision_data": {"sections": []},
                    "is_active": True,
                },
            )
            revision_cache[facility_id] = revision
        revision = revision_cache[facility_id]

        date = (
            status.checked_at.date() if status.checked_at else status.created_at.date()
        )
        session, _ = SafetyCheckSession.objects.get_or_create(
            worker_id=status.worker_id,
            date=date,
            revision=revision,
        )
        status.session = session
        status.save(update_fields=["session"])


def revert_backfill(apps, schema_editor):
    SafetyStatus = apps.get_model("safety", "SafetyStatus")
    SafetyCheckSession = apps.get_model("safety", "SafetyCheckSession")

    SafetyStatus.objects.update(session=None)
    SafetyCheckSession.objects.all().delete()
    # Revision은 자동 삭제하지 않음 — 운영자 수동 정리 권장


class Migration(migrations.Migration):
    dependencies = [
        ("safety", "0006_safetychecklistrevision_safetychecksession_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_default_session, revert_backfill),
    ]
