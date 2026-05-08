# B 운영 트랙 PR-B — BaseModel 컨벤션 10개 모델 일괄 통일

> 작업일: 2026-05-09
> 브랜치: `feature/0508_refactory`
> 부모 plan: [`~/.claude/plans/b-cozy-panda.md`](../../../home/cjy/.claude/plans/b-cozy-panda.md) §3 PR-B
> 직전 PR: [post_phase4_b_track_pr_a_report.md](post_phase4_b_track_pr_a_report.md) (`f4b50d0`)

---

## 1. 작업 목적

기존에 `models.Model`을 직접 상속하면서 `created_at`/`updated_at`을 직접 정의하던 10개 모델을 `BaseModel` 상속으로 통일. `updated_by` FK + `updated_at` 자동 추가 — 운영 추적성 + 컨벤션 정합. APPEND-ONLY 4개 (AppLog/IntegrationLog/SystemLog/EventLog/LoginLog) 제외.

---

## 2. 검증 결과

| 항목 | 명령 | 결과 |
|---|---|---|
| Django 시스템 검사 | `manage.py check` | ✅ 통과 |
| 마이그 일관성 | `makemigrations --dry-run --check` | ✅ "No changes detected" |
| 마이그 적용 (6 apps) | `migrate` | ✅ 모두 OK |
| 마이그 reverse + re-apply | 6 apps 각각 reverse → re-apply | ✅ 모두 OK |
| pytest 회귀 | `.venv/bin/pytest` | ✅ **56 passed** |
| pre-commit | `pre-commit run --files <변경파일>` | ✅ Passed |

### 마이그 reverse 흐름
```
alerts.0008      ← reverse → alerts.0007    → re-apply OK
facilities.0014  ← reverse → facilities.0013 → re-apply OK
geofence.0003    ← reverse → geofence.0002  → re-apply OK
monitoring.0005  ← reverse → monitoring.0004 → re-apply OK
notifications.0003 ← reverse → notifications.0002 → re-apply OK
safety.0011      ← reverse → safety.0010    → re-apply OK
```

---

## 3. 변경 파일

### 3-1. 모델 (10개) — `models.Model` → `BaseModel` 상속

| 모델 | 파일 | 추가 필드 |
|---|---|---|
| DeviceBase (abstract) | [devices.py](../../drf-server/apps/facilities/models/devices.py) | updated_by → 자식 GasSensor/PowerDevice/PositionNode 자동 적용 |
| Facility | [facility.py](../../drf-server/apps/facilities/models/facility.py) | updated_by |
| GasSensorInspection | [gas_sensor_inspection.py](../../drf-server/apps/facilities/models/gas_sensor_inspection.py) | updated_by |
| PowerDeviceInspection | [power_device_inspection.py](../../drf-server/apps/facilities/models/power_device_inspection.py) | updated_by |
| GeoFence | [geofence.py](../../drf-server/apps/geofence/models/geofence.py) | updated_by |
| SafetyStatus | [safety.py](../../drf-server/apps/safety/models/safety.py) | updated_by |
| AlarmRecord | [alarm_record.py](../../drf-server/apps/alerts/models/alarm_record.py) | updated_at + updated_by (save override로 수정 차단 유지) |
| Event | [event.py](../../drf-server/apps/alerts/models/event.py) | updated_at + updated_by |
| Notification | [notification.py](../../drf-server/apps/notifications/models/notification.py) | updated_at + updated_by |
| PowerEvent | [power_event.py](../../drf-server/apps/monitoring/models/power_event.py) | updated_at + updated_by |

각 모델: `class X(BaseModel):` + `created_at`/`updated_at` 직접 정의 제거 + `# created_at / updated_at / updated_by 는 BaseModel 상속` 주석 명시.

### 3-2. 마이그레이션 (6개 자동 생성)

| 파일 | 내용 |
|---|---|
| `alerts/0008_alarmrecord_updated_at_alarmrecord_updated_by_and_more.py` | AlarmRecord/Event 모두 updated_at + updated_by FK |
| `facilities/0014_facility_updated_by_gassensor_updated_by_and_more.py` | Facility/GasSensor/GasSensorInspection/PositionNode/PowerDevice/PowerDeviceInspection 6 모델 updated_by |
| `geofence/0003_geofence_updated_by_alter_geofence_created_at_and_more.py` | GeoFence updated_by |
| `monitoring/0005_powerevent_updated_at_powerevent_updated_by_and_more.py` | PowerEvent updated_at + updated_by |
| `notifications/0003_notification_updated_at_notification_updated_by_and_more.py` | Notification updated_at + updated_by |
| `safety/0011_safetystatus_updated_by_and_more.py` | SafetyStatus updated_by |

---

## 4. 사용자 결정 사항

본 PR은 plan §3 PR-B 그대로 진행. 결정 사항 없음.

### 명확화 사항 (실행 중)
- AlarmRecord/PowerEvent는 docstring상 "불변 기록" 성격이지만 BaseModel 상속 적용 — `save()` override로 수정 자체가 차단되어 있어 `updated_at` 변경 불가. 컨벤션 일관성을 위해 BaseModel 상속하되 동작에 영향 없음.
- DeviceBase는 abstract → BaseModel(abstract) 상속. `updated_by`의 `related_name="updated_%(class)s_set"`이 `%(class)s` placeholder로 자동 치환되어 `updated_gassensor_set` / `updated_powerdevice_set` / `updated_positionnode_set` 충돌 없이 생성.

---

## 5. 발견 사항 / 주의

### 5-1. APPEND-ONLY 모델 제외 (Phase 1 결정 일관)
- AppLog, IntegrationLog (`apps/operations/models/`) — APPEND-ONLY 정책으로 BaseModel 미상속 유지
- SystemLog (`apps/core/models/system_log.py`) — 동일
- EventLog (`apps/alerts/models/event_log.py`) — 동일
- LoginLog (`apps/accounts/models/login_log.py`) — 동일
- PowerData / GasData / WorkerPosition — 시계열 데이터, `measured_at` 기준 운영 (수정 미발생)

### 5-2. updated_by FK related_name 충돌 회피
BaseModel의 `related_name="updated_%(class)s_set"` 패턴이 모든 모델에 자동 적용. 충돌 검증 OK (`manage.py check` 통과).

### 5-3. 6 apps 마이그 한 번에 자동 생성
`makemigrations` 1회로 6개 마이그 동시 생성. Django가 의존 그래프 자동 분석 → 동시 적용/reverse 가능.

### 5-4. 호출자 영향 0
`save(update_fields=[...])` 호출처에서 `updated_at`은 BaseModel `auto_now=True`로 자동 갱신. 호출자 코드 변경 불필요. `updated_by`는 nullable이라 명시 안 해도 OK.

---

## 6. 다음 단계

PR-C (DataRetentionPolicy 5종 + AlertPolicy 9종 seed) 진입. plan §4 의존 그래프 일관.

---

## 7. 누적 결과

| PR | commit | 변경 |
|---|---|---|
| PR-A | `f4b50d0` | fixture 시드 마이그 historical apps 패턴 (4건) |
| **PR-B** | (본 commit) | BaseModel 컨벤션 10개 모델 일괄 |
