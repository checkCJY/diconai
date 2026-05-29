"""
더미 송출에 필요한 마스터 데이터 시드.

생성 항목:
- Facility(id=1) — 도면 1290x590 (위치 더미 좌표 범위)
- CustomUser × 4 (worker_a~d, user_type=WORKER) — 위치 더미가 username 기반 lookup
- GasSensor(device_id="63200c3afd12") — 가스 더미가 송출하는 device_id
- PowerDevice(device_id="63200c3afd12") — 전력 더미가 송출하는 device_id

실행: python manage.py seed_dummy_data
재실행 안전 (idempotent).

[2026-05-29 변경] 워커 pk=1~4 하드코딩 제거 — PG 환경에서 admin/manager 등이 이미
pk=1~4 를 점유한 상태에서 seed 가 skip 되어 worker_a~d 가 생성되지 않던 문제 수정.
username 기반 lookup 으로 전환. PK 는 sequence 가 자동 부여.
※ 와이어 프로토콜 (`worker_id: int = PK`) 는 별도 — 작업자 디바이스 결정 후 정렬 예정.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import CustomUser
from apps.core.constants import UserType
from apps.facilities.models import Facility, GasSensor, PowerDevice

DUMMY_DEVICE_ID = "63200c3afd12"
DEFAULT_PASSWORD = "worker1234!"

DUMMY_WORKERS = [
    {"username": "worker_a", "name": "작업자 A"},
    {"username": "worker_b", "name": "작업자 B"},
    {"username": "worker_c", "name": "작업자 C"},
    {"username": "worker_d", "name": "작업자 D"},
]


class Command(BaseCommand):
    help = "더미 송출용 마스터 데이터 시드 (Facility, CustomUser×4, GasSensor, PowerDevice)"

    @transaction.atomic
    def handle(self, *args, **options):
        facility = self._seed_facility()
        self._seed_workers(facility)
        self._seed_gas_sensor(facility)
        self._seed_power_device(facility)
        self.stdout.write(self.style.SUCCESS("✓ 더미 마스터 데이터 시드 완료"))

    def _seed_facility(self) -> Facility:
        facility, created = Facility.objects.update_or_create(
            pk=1,
            defaults={
                "name": "테스트 공장",
                "address": "더미 주소",
                "map_width": 1290,
                "map_height": 590,
                "is_active": True,
            },
        )
        self._log("Facility(id=1)", created)
        return facility

    def _seed_workers(self, facility: Facility) -> None:
        # username 기반 lookup — PK 는 sequence 가 자동 부여. 기존 워커는 skip.
        for w in DUMMY_WORKERS:
            existing = CustomUser.objects.filter(username=w["username"]).first()
            if existing:
                self.stdout.write(
                    f"  · CustomUser(username={w['username']}) 이미 존재 "
                    f"(id={existing.id}) — skip"
                )
                continue
            user = CustomUser(
                username=w["username"],
                name=w["name"],
                user_type=UserType.WORKER,
                facility=facility,
            )
            user.set_password(DEFAULT_PASSWORD)
            user.save()
            self.stdout.write(
                f"  · CustomUser(id={user.id}, {w['username']}) 생성 "
                f"[비밀번호: {DEFAULT_PASSWORD}]"
            )

    def _seed_gas_sensor(self, facility: Facility) -> None:
        _, created = GasSensor.objects.update_or_create(
            device_id=DUMMY_DEVICE_ID,
            defaults={
                "facility": facility,
                "device_code": "G001",
                "device_name": "더미 가스센서",
                "x": 200.0,
                "y": 200.0,
                "is_active": True,
            },
        )
        self._log(f"GasSensor(device_id={DUMMY_DEVICE_ID})", created)

    def _seed_power_device(self, facility: Facility) -> None:
        _, created = PowerDevice.objects.update_or_create(
            device_id=DUMMY_DEVICE_ID,
            defaults={
                "facility": facility,
                "device_code": "P001",
                "device_name": "더미 전력장비",
                "x": 400.0,
                "y": 400.0,
                "channel_count": 16,
                "is_active": True,
            },
        )
        self._log(f"PowerDevice(device_id={DUMMY_DEVICE_ID})", created)

    def _log(self, label: str, created: bool) -> None:
        action = "생성" if created else "업데이트"
        self.stdout.write(f"  · {label} {action}")
