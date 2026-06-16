"""테스트용 IoT 기기 대량 등록/삭제 커맨드.

사용:
  python manage.py seed_iot_test_devices --gas 10 --power 10   # 등록
  python manage.py seed_iot_test_devices --clean                # 삭제
"""
from django.core.management.base import BaseCommand

from apps.facilities.models import Facility, GasSensor, PowerDevice

PREFIX = "test_iot_"


class Command(BaseCommand):
    help = "IoT 부하 테스트용 기기 등록/삭제"

    def add_arguments(self, parser):
        parser.add_argument("--gas", type=int, default=0, metavar="N", help="가스 센서 등록 수")
        parser.add_argument("--power", type=int, default=0, metavar="N", help="전력 장치 등록 수")
        parser.add_argument("--clean", action="store_true", help="테스트 기기 전체 삭제")

    def handle(self, *args, **options):
        if options["clean"]:
            self._clean()
            return
        facility = Facility.objects.first()
        if not facility:
            self.stderr.write("Facility 없음. 먼저 make seed 실행.")
            return
        if options["gas"]:
            self._seed_gas(facility, options["gas"])
        if options["power"]:
            self._seed_power(facility, options["power"])

    def _seed_gas(self, facility, n: int) -> None:
        created = 0
        for i in range(1, n + 1):
            device_id = f"{PREFIX}gas_{i:03d}"
            device_code = f"TG{i:03d}"
            _, is_new = GasSensor.objects.update_or_create(
                device_id=device_id,
                defaults={
                    "facility": facility,
                    "device_code": device_code,
                    "device_name": f"테스트 가스센서 {i:03d}",
                    "x": float(100 + (i % 10) * 100),
                    "y": float(100 + (i // 10) * 100),
                    "is_active": True,
                },
            )
            if is_new:
                created += 1
        self.stdout.write(f"  가스 센서 {n}개 등록 완료 (신규 {created}개)")

    def _seed_power(self, facility, n: int) -> None:
        created = 0
        for i in range(1, n + 1):
            device_id = f"{PREFIX}pwr_{i:03d}"
            device_code = f"TP{i:03d}"
            _, is_new = PowerDevice.objects.update_or_create(
                device_id=device_id,
                defaults={
                    "facility": facility,
                    "device_code": device_code,
                    "device_name": f"테스트 전력장비 {i:03d}",
                    "x": float(500 + (i % 10) * 100),
                    "y": float(100 + (i // 10) * 100),
                    "channel_count": 16,
                    "is_active": True,
                },
            )
            if is_new:
                created += 1
        self.stdout.write(f"  전력 장치 {n}개 등록 완료 (신규 {created}개)")

    def _clean(self) -> None:
        g = GasSensor.objects.filter(device_id__startswith=PREFIX).delete()
        p = PowerDevice.objects.filter(device_id__startswith=PREFIX).delete()
        self.stdout.write(f"  테스트 기기 삭제 완료 — 가스 {g[0]}개, 전력 {p[0]}개")
