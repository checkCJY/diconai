# 작업자 위치 / 지오펜스 도메인

> 코드리뷰용 흐름 이해 문서. 관련 커밋: `d91aa88`(positioning + geofence)
> 데이터 흐름: **IoT 위치장비 → fastapi(WS 수신) → drf(저장·지오펜스 판정) → Celery(진입 알람)**

---

## 1. 파일 맵

| 레이어 | 파일 | 핵심 심볼 |
|---|---|---|
| fastapi 수신 | `websocket/routers/ws_router.py` | `position_stream` (WS /ws/position/) |
| fastapi 스키마 | `positioning/schemas/position.py` | `WorkerPositionSchema`, `WorkerPositionPayload` |
| drf 처리 ★ | `positioning/services/position_service.py` | `handle_position_receive`, `_get_dangerous_sensors_in_geofence`, `_is_near_any_geofence`, `recalculate_worker_positions_for_facility` |
| drf 모델 | `positioning/models/worker_position.py` | `WorkerPosition` + `update_geofence_cache()` |
| drf 시리얼라이저 | `positioning/serializers/serializers.py` | 위치 입출력 |
| geofence 모델 | `geofence/models/geofence.py` | `GeoFence` + `contains_point()`, `validate_polygon` |
| geofence 서비스 | `geofence/services/geofence_service.py` | `create_geofence`, `update_polygon` (→ 재계산 트리거) |

## 2. 전체 시퀀스

```
위치장비 (작업자 태그)
  │ WS /ws/position/  { worker_id, facility_id, x, y }   (도면 픽셀 좌표)
  ▼
[fastapi] ws_router.position_stream
  └─ 필수 필드 검증 → POST /api/positioning/receive/ (drf)
  └─ worker_positions[worker_id] 갱신 (WS broadcast 용 공유 상태)
  ▼
[drf] handle_position_receive  @transaction.atomic
  ① WorkerPosition.create(...)              ◀── 항상 저장 (이력 완전 보존)
  ② pos.update_geofence_cache()             ◀── 현재 속한 지오펜스 캐시 갱신
  ③ if geofence and _is_near_any_geofence(30px):
       danger_info = _get_dangerous_sensors_in_geofence(geofence)
  ④ if danger_info:
       fire_geofence_alarm_task.delay(worker_id, geofence_id, risk_level, ...)
  ▼
[drf] alerts.fire_geofence_alarm_task  → fastapi WS push (worker_id 동봉)
  ▼
브라우저 맵 + 해당 작업자 개인 알림 (/ws/worker/{id}/)
```

## 3. 핵심 설계 — 저장과 알람의 분리 (가장 중요)

```python
# handle_position_receive — 항상 저장, 알람은 근접 시에만
pos = WorkerPosition.objects.create(worker_id=..., x=x, y=y, ...)   # ① 무조건
pos.update_geofence_cache(); pos.save(...)                          # ② 캐시
if geofence and _is_near_any_geofence(facility_id, x, y):           # ③ 근접 시에만
    danger_info = _get_dangerous_sensors_in_geofence(geofence)
```
- **왜**: "근접 시에만 저장" 으로 두면 대부분 위치 이력이 유실 → 사고 소급 분석·동선 추적 불가. 그래서 저장은 항상, 위험 판정(비싼 쿼리)만 30px 근접 시.
- `GEOFENCE_CHECK_DURATION` 메트릭은 geofence 있을 때만 측정 (None 케이스 제외).

## 4. 지오펜스 위험도 = 동적 (정적 risk_level 아님)

```python
def _get_dangerous_sensors_in_geofence(geofence):
    # polygon 안에 위치한 GasSensor/PowerDevice 중 최신값이 warning/danger 인 것의 최댓값
    for sensor in GasSensor.objects.filter(facility=geofence.facility, is_active=True):
        if not geofence.contains_point(sensor.x, sensor.y): continue
        latest = GasData.objects.filter(gas_sensor=sensor).order_by("-measured_at").first()
        if latest.max_risk_level != "normal": best = max(best, ...)
    # PowerDevice 도 동일
    return best   # {"risk_level", "source_label"} or None
```
- 지오펜스 자체의 정적 `risk_level` 이 아니라, **그 구역 안 센서의 지금 위험도**를 본다.
- 즉 알람 의미 = "작업자가, 지금 위험한 센서가 있는 구역에 들어갔다". alarm_type = `geofence_intrusion`.

## 5. 기하 연산 (도면 픽셀 좌표계)

```python
PROXIMITY_THRESHOLD = 30   # px
contains_point(x, y)                      # polygon 내부 (geofence 모델, ray-casting)
_distance_to_geofence(x, y, polygon)      # 작업자→경계 최단거리 (선분 거리 min)
_is_near_any_geofence(facility, x, y)     # 내부 OR 경계 30px 이내 면 True
```
- 위경도 아님 — 설비 **도면 픽셀** 기준. `WorkerPositionSchema.x/y` 는 `ge=0`.

## 6. 개인 알림 라우팅

지오펜스 진입 알람은 해당 작업자에게만 개인 전송:
- `fire_geofence_alarm_task` 가 payload 에 `worker_id` 동봉 → fastapi `alarm_router` 가 `worker_clients[worker_id]` WS 조회 → 개인 push.
- 동시에 관리자 broadcast 에도 포함 (관리자는 전체 상황 봄).
- ⚠ **단일 워커 전제** — 멀티워커 시 작업자가 어느 워커에 붙었는지 모름. `skill/plan/fastapi-multiworker-redis-pubsub.md` §3 참조.

## 7. 지오펜스 polygon 수정 시 재계산 (geofence_service.update_polygon)

```python
geofence.polygon = new_polygon; geofence.save()
recalculate_worker_positions_for_facility(geofence.facility_id)   # 최근 24h 위치 캐시 재계산
log_action(GEOFENCE_UPDATE, ...)                                  # 감사 로그
```
- polygon 바뀌면 최근 24h `WorkerPosition.current_geofence` 캐시를 전부 재계산. 안 하면 옛 polygon 기준 stale 캐시.

## 8. 리뷰 시 주의 (함정)

1. **current_geofence 는 캐시 컬럼** — polygon 변경 시 `recalculate_*` 안 하면 stale. update_polygon 이 자동 호출하지만, polygon 을 다른 경로로 바꾸면 누락 위험.
2. **센서 전수 순회 비용**: `_get_dangerous_sensors_in_geofence` 가 facility 의 모든 가스/전력 센서를 순회 + 각자 최신값 쿼리. 센서 많으면 N+1·느림 → `GEOFENCE_CHECK_DURATION` p99 ≥ 100ms 면 인덱스/스케일 점검. 30px 근접 게이트가 이 비용을 대부분 막아줌.
3. **디바이스/UX 미정**: 작업자 알람 수신 디바이스 종류·UX 미결정. 현재는 sensor broadcast 로 시연 충분, 작업자 라우팅은 디바이스 결정 후 재설계 예정.
4. **node_id None 허용**: 펌웨어 페이로드 갱신 전이라 `node_id` 없으면 `received_node=None` 저장 (데이터 손실보다 NULL 우선).
5. 알람 생성은 [alerts.md](alerts.md) `create_alarm_and_event` 공유 (geofence_id 인자).

## 9. 관련 문서
- 알람 생성: [alerts.md](alerts.md)
- WS 개인 알림: [websocket.md](websocket.md)
