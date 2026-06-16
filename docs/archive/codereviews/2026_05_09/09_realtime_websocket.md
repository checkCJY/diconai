# 09. 실시간·WebSocket 횡단 (state.py · broadcast loops · 동시성 · contract)

## 1. 범위

이 도메인은 fastapi-server의 실시간 처리 인프라를 횡단으로 리뷰. 04(알람), 06(데이터 수집), 07(위치)에서 부분적으로 다룬 내용을 종합 + 깊이 있는 동시성/contract 분석.

### 1.1 핵심 파일
- [fastapi-server/websocket/state.py](../../../../fastapi-server/websocket/state.py) — **41줄, 9개 mutable globals** ⭐
- [fastapi-server/websocket/routers/ws_router.py](../../../../fastapi-server/websocket/routers/ws_router.py) — 180줄
- [fastapi-server/websocket/services/broadcast.py](../../../../fastapi-server/websocket/services/broadcast.py) — 119줄 ⭐
- [fastapi-server/services/drf_client.py](../../../../fastapi-server/services/drf_client.py) — DRF 통신 헬퍼
- [fastapi-server/app.py](../../../../fastapi-server/app.py) — 156줄, 라이프사이클 + 전역 예외 핸들러
- [fastapi-server/core/config.py](../../../../fastapi-server/core/config.py) — `BROADCAST_INTERVAL_SEC`, `DATA_STALE_THRESHOLD_SEC`, `DUMMY_RISK_PROBABILITY`

### 1.2 프론트엔드 매칭 파일
- [drf-server/static/js/shared/ws-client.js](../../../../drf-server/static/js/shared/ws-client.js) — 단일 연결 캐시
- [drf-server/static/js/dashboard/websocket.js](../../../../drf-server/static/js/dashboard/websocket.js)
- [drf-server/static/js/detail/websocket_gas.js](../../../../drf-server/static/js/detail/websocket_gas.js)
- [drf-server/static/js/detail/websocket_power.js](../../../../drf-server/static/js/detail/websocket_power.js)
- [drf-server/static/js/shared/alarm-ws.js](../../../../drf-server/static/js/shared/alarm-ws.js)
- [drf-server/static/js/shared/worker-ws.js](../../../../drf-server/static/js/shared/worker-ws.js)

## 2. 기능 흐름

### 2.1 두 broadcast loop의 협업
```
[startup — app.py:39-42]
  task1 = broadcast_loop()       — 5초 주기 정기 송신
  task2 = alarm_flush_loop()      — alarm_signal 깨어남 즉시 송신

broadcast_loop:
  while True:
    await asyncio.sleep(BROADCAST_INTERVAL_SEC)
    if sensor_clients:
      _send_to_all(build_broadcast_payload())

alarm_flush_loop:
  while True:
    await alarm_signal.wait()      ← alarm_router.push_alarm이 set()
    alarm_signal.clear()
    if not sensor_clients: continue
    if not any(is_new_event): continue
    _send_to_all(build_broadcast_payload())   ← 같은 함수, 알람 flush 포함
```

### 2.2 build_broadcast_payload의 통합 페이로드
```
{
  device_id: "sensor-01",         ← 하드코드 (모니터링 1대 가정)
  timestamp: ISO,
  level: "위험" | "정상",          ← random.random() 기반 더미!!
  total_power_kw: float | null,    ← stale면 null
  power_change_pct: float | null,
  equipment: [{...} × 16] | [],    ← stale면 빈 배열
  power_loading: bool,             ← 빈 배열일 때 true
  gas_loading: bool,               ← gas stale일 때 true
  ai_power_equipment, ai_eta_min,  ← random 더미 (모델 미연동)
  ai_max_load_kw, ai_max_load_pct,
  worker_positions: dict,          ← 복사본
  alarms: list[:5],                ← 상위 5개만 (드랍 발생!)
  ...latest_gas_snapshot,          ← gas 측정값 spread (o2/co/co2/h2s/lel/no2/so2/o3/nh3/voc + *_risk)
}

송출 후: del active_alarms[:5] (소비된 알람 제거)
```

### 2.3 공유 상태 변경자/소비자 매트릭스

| 상태 | 변경자 | 소비자 | 동시성 가드 |
|---|---|---|---|
| `sensor_clients` (list) | ws_router의 connect/disconnect | _send_to_all | **없음** (asyncio 단일 스레드 의존) |
| `worker_clients` (dict) | ws_router worker_stream connect/disconnect | alarm_router.push_alarm | **없음** |
| `worker_positions` (dict) | ws_router의 _save_iot_position 성공 시 | broadcast.build_broadcast_payload | **없음** (dict 복사 후 송신은 안전) |
| `active_alarms` (list) | alarm_router.push_alarm | broadcast — `[:5]` 송신 후 `del [:5]` | **없음** |
| `alarm_signal` (Event) | alarm_router.push_alarm `set()` | alarm_flush_loop `wait()/clear()` | asyncio.Event 자체 |
| `latest_gas_snapshot` (dict) | gas_service.process_gas_data | broadcast | **없음** (dict 갱신은 atomic 아님) |
| `power_latest` (dict) | power_service.update_power_state | broadcast의 build_equipment | **없음** |
| `_prev_total_kw` (broadcast.py 모듈 글로벌) | broadcast.build_broadcast_payload | 자기 자신 (다음 호출) | **없음** |
| `scenario_mode` (dict) | internal/scenario_router | dummy/sensor 폴링 | **없음** |

## 3. 백엔드 소견

### 3.1 일반 코드 리뷰
- **[상] broadcast.py에 random 더미가 운영 페이로드에 섞임**
  [broadcast.py:73,49-60](../../../../fastapi-server/websocket/services/broadcast.py#L73) `is_danger = random.random() < DUMMY_RISK_PROBABILITY` → `"level": "위험" if is_danger else "정상"`. 운영 환경에서도 broadcast 페이로드 `level` 필드가 **랜덤**. 또한 `ai_eta_min/ai_max_load_*` 4개 필드 모두 random. 더미 모드와 실데이터 모드가 같은 코드에서 분기 안 됨 — feature flag(`if settings.IS_DUMMY:`)로 분리 시급.
- **[상] `del active_alarms[:5]`로 5개 초과 알람 silent drop**
  [broadcast.py:113,117](../../../../fastapi-server/websocket/services/broadcast.py#L113) `alarms[:5]` 송신 후 `del [:5]` — 6번째 이후 알람은 다음 broadcast tick에서야 처리됨 (이때도 5개 제한). 1초 안에 10개 알람이 쌓이면 5개씩 2 tick = 2초 후에야 모두 송신. **알람 폭주 시 누락 위험은 없으나 지연 발생**. 대신 의도라면 주석 명시.
- **[중] _prev_total_kw가 broadcast.py 모듈 글로벌**
  [broadcast.py:26](../../../../fastapi-server/websocket/services/broadcast.py#L26) state.py 외 또 다른 글로벌. state.py로 통합하거나 캡슐화. 단위 테스트 시 reset 어려움.
- **[중] timestamp는 timezone-naive**
  [broadcast.py:104](../../../../fastapi-server/websocket/services/broadcast.py#L104) `datetime.now().isoformat()` — timezone 정보 없음. gas_latest는 `datetime.now(timezone.utc).isoformat()` 사용. 두 곳이 어긋남 → JS 측 시각 비교 시 오류 가능.
- **[하] device_id="sensor-01" 하드코드**
  [broadcast.py:103](../../../../fastapi-server/websocket/services/broadcast.py#L103) 단일 모니터링 가정. 다중 facility 환경에선 어긋남.
- **[하] CORS allow_methods 제한**
  [app.py:84](../../../../fastapi-server/app.py#L84) `allow_methods=["GET","POST"]`. PUT/DELETE 미사용이라 OK이나 향후 확장 시 주의.

### 3.2 아키텍처/레이어
- **[참고] 응답 봉투 표준이 fastapi에도 일관 적용**
  [app.py:99-150](../../../../fastapi-server/app.py#L99-L150) `{error:{code,message,details?}}` 봉투, drf-server의 standard_exception_handler와 동일 정책. **모범**.
- **[참고] 라이프사이클로 broadcast_loop 시작·정리**
  [app.py:33-48](../../../../fastapi-server/app.py#L33-L48) lifespan으로 task 시작 + finally cancel. **모범**.
- **[참고] state.py 단일 파일에 모든 공유 상태 집중**
  의도적 설계. 상태 변경 위치가 분산되어 있으나 origin은 한 곳 — 디버깅 시 grep 용이.

### 3.3 동시성/안정성 — **이 도메인의 핵심**
- **[상] 다중 워커 배포 시 100% 깨짐**
  현재 모든 공유 상태가 프로세스 메모리(state.py 모듈 글로벌). uvicorn `--workers 4`로 띄우면:
  - sensor_clients가 워커별로 분리 → 같은 사용자가 워커 A 연결 시 워커 B의 broadcast 못 받음
  - active_alarms도 워커별 → 한 워커가 받은 알람을 다른 워커는 모름
  - worker_positions가 워커별 분기 → 위치가 워커마다 다름
  → **단일 워커 + Redis(상태)/Pub-Sub(broadcast)** 또는 **Sticky session + 단일 워커** 강제 필요. 현재 운영이 단일 워커라면 운영 문서에 명시.
- **[상] 단일 슬로우 클라이언트가 broadcast 차단**
  [ws_router.py:32-43](../../../../fastapi-server/websocket/routers/ws_router.py#L32-L43) `_send_to_all`이 순차 await. 한 클라이언트의 send_json이 5초 걸리면 나머지 모두 5초 지연. 모바일 약전계 환경에서 빈번. **`asyncio.gather(*[ws.send_json(...) for ws in clients])` + timeout per send** 권장.
- **[중] worker_positions 등 dict 갱신 비원자성**
  Python dict assignment(`d[k]=v`)은 단일 키는 원자적이지만, dict 자체를 spread/list화할 때 동시 갱신과 race 가능. broadcast가 `dict(worker_positions)` 복사 — 복사 시점에 갱신되면 일부 누락 가능. 단일 asyncio 스레드라 yield 지점 사이엔 안전하나, 코드 변경으로 yield 도입되면 위험. **명시적 lock + snapshot 패턴** 권장.
- **[중] WS 핸드셰이크 인증 표준 부재**
  [ws_router.py](../../../../fastapi-server/websocket/routers/ws_router.py) 어떤 WS도 인증 검증하지 않음. ws-client.js의 `attachToken` 옵션은 토큰을 query에 붙이지만 **서버에서 검증 미적용** (04 D2 / 07 G1 추적). 표준 WS 인증 미들웨어 필요.
- **[중] heartbeat/ping 정책 부재**
  WebSocket 스펙은 ping/pong 자동 처리하나, 애플리케이션 레벨 heartbeat 부재. 클라이언트는 받은 메시지가 없으면 끊긴 건지 데이터가 없는 건지 모름. 30초 등에 빈 ping 송신 + 클라이언트 timeout 필요.
- **[중] back-pressure 처리 부재**
  send_json에 timeout 없음. 클라이언트가 receive 안 하면 send 큐가 쌓여 메모리 폭주. uvloop/uvicorn 기본 정책 확인 + `websockets.WebSocketServerProtocol(max_queue=...)` 설정 권장.

### 3.4 데이터 영속성
- **[중] 재시작 시 모든 휘발 상태 손실**
  worker_positions, active_alarms, latest_gas_snapshot 모두 메모리. 재시작 후 다음 IoT 메시지가 도착하기 전까지 브라우저는 빈 상태. **DRF에 매번 저장하므로 영속성은 거기에** — 재시작 시 fastapi가 DRF에서 마지막 상태를 복원하는 startup hook 권장.

## 4. 프론트엔드(JS/WS contract) 소견

### 4.1 contract 정합성 매트릭스
fastapi `build_broadcast_payload` 송신 키 → 클라이언트 소비:

| fastapi 키 | dashboard/websocket.js | detail/websocket_gas.js | detail/websocket_power.js | shared/alarm-ws.js |
|---|---|---|---|---|
| `device_id` | ✓ | ? | ? | - |
| `timestamp` | ✓ | ? | ? | (자체 생성) |
| `level` (랜덤!) | ? | - | - | - |
| `total_power_kw` | ✓ | - | ✓ | - |
| `power_change_pct` | ? | - | ✓ | - |
| `equipment[]` | ✓ | - | ✓ (16채널) | - |
| `power_loading` | ✓ | - | ✓ | - |
| `gas_loading` | ✓ | ✓ | - | - |
| `ai_*` (4개, 랜덤) | ✓ | - | - | - |
| `worker_positions` | ✓ | - | - | - |
| `alarms[]` | ✓ | ? | ? | ✓ (가공) |
| `o2/co/co2/...` (gas) | ✓ | ✓ | - | - |
| `*_risk` (gas 위험도) | ✓ | ✓ | - | - |

> **문제**: contract가 코드로만 표현되어 있고 명세 문서 부재. 서버 키 변경 시 silent break. 타입 정의 또는 OpenAPI/AsyncAPI 스펙 권장.

### 4.2 알람 키 변환 (04에서 다룸 — 재확인)
- alarm-ws.js가 `risk_level→alarm_level`, `summary→message`, `source_label→sensor_name` 리네이밍. **fragility 핵심**.

### 4.3 worker-ws.js 인증
- 클라이언트가 user_id 결정 → 서버는 검증 안 함 (07 G1).

### 4.4 WSClient 캐시의 부작용
- 같은 path는 1개 연결만 — alarm-ws.js와 dashboard/websocket.js가 같은 페이지에 로드되면 두 핸들러 모두 같은 메시지 수신. 의도된 설계지만, **두 핸들러가 같은 알람을 두 번 처리하면 팝업 중복**. 현재는 dashboard/websocket.js와 alarm-ws.js의 책임이 명확히 분리되어 있는지 검증 필요.

## 5. 개선 제안

### I1. 운영 vs 더미 모드 분리 [상 · 중]
- **왜 필요?**: 운영 broadcast의 `level`/`ai_*` 필드가 random. 사용자가 화면에서 보는 위험도가 실제 위험과 무관. 신뢰성 핵심 침해.
- **장점**: 신뢰성 / 더미 모드와 실모드 명시 분리.
- **단점**: scenario_mode와 통합 정책 필요.
- **변경 위치**: [broadcast.py:73,49-60](../../../../fastapi-server/websocket/services/broadcast.py#L73) `if settings.IS_DUMMY: ... else: ...` 분기. settings에 `IS_DUMMY` flag 추가. 실데이터에선 `level=None` 또는 alarms 기반 derived value.

### I2. 다중 워커 대비 (Redis 또는 단일 워커 강제) [상 · 대]
- **왜 필요?**: 현재 코드는 단일 워커 가정인데 운영 배포에서 워커 수를 늘리면 100% 깨짐. 사고 발생 시 원인 추적 어려움.
- **장점**: 수평 확장 가능 / 명시적 운영 모델.
- **단점**: Redis 인프라 추가 또는 워커 수 명시 운영 절차.
- **변경 위치**:
  - 단기: 운영 배포 스크립트에 `--workers 1` 강제 + 문서화.
  - 장기: state.py를 [websocket/state_redis.py](../../../../fastapi-server/websocket/) 또는 채널별 pub/sub.

### I3. _send_to_all 병렬화 + per-send timeout [상 · 소]
- **왜 필요?**: 슬로우 클라이언트 1명이 broadcast 전체 차단 → 다른 사용자 모두 영향.
- **장점**: 한 클라이언트의 지연이 다른 사용자에 영향 안 줌.
- **단점**: timeout 정책 결정 필요(2초?).
- **변경 위치**: [ws_router.py:32-43](../../../../fastapi-server/websocket/routers/ws_router.py#L32-L43)
  ```python
  async def _send_one(ws):
      try:
          await asyncio.wait_for(ws.send_json(payload), timeout=2.0)
      except (asyncio.TimeoutError, Exception):
          dead.append(ws)
  await asyncio.gather(*[_send_one(ws) for ws in list(sensor_clients)])
  ```

### I4. WS 인증 미들웨어 표준화 [상 · 중]
- **왜 필요?**: 04 D2 / 07 G1과 통합. WS별로 따로 검증하지 말고 한 곳.
- **장점**: 누락 방지 / 일관 정책.
- **단점**: FastAPI WS는 표준 미들웨어 적용 어려움 — Depends 데코레이터로 처리.
- **변경 위치**: [websocket/auth.py](../../../../fastapi-server/websocket/) 신규 — `get_current_user_from_ws_token(websocket)` Depends. 모든 WS endpoint가 사용.

### I5. active_alarms 5개 drop 정책 명시 [중 · 소]
- **왜 필요?**: silent drop은 디버깅 어려움.
- **장점**: 동작 명확.
- **단점**: 없음.
- **변경 위치**: [broadcast.py:113-117](../../../../fastapi-server/websocket/services/broadcast.py#L113-L117) 주석 명시 + 6번째 이후는 다음 tick으로 ROLL OVER 명시. 또는 5개 제한을 옵션화.

### I6. timestamp UTC 통일 [중 · 소]
- **왜 필요?**: 일부는 utc, 일부는 naive — JS 측 비교 오류 가능.
- **장점**: 일관성.
- **단점**: 없음.
- **변경 위치**: [broadcast.py:104](../../../../fastapi-server/websocket/services/broadcast.py#L104) `datetime.now(timezone.utc).isoformat()`로 통일. 다른 위치도 grep.

### I7. heartbeat / 빈 ping [중 · 소]
- **왜 필요?**: 클라이언트가 끊김인지 정상 무데이터인지 구분 못 함.
- **장점**: UI에서 "연결 상태 표시" 가능.
- **단점**: 트래픽 약간 증가.
- **변경 위치**: broadcast_loop이 5초마다 송신하므로 사실상 heartbeat 역할. 다만 데이터가 없을 때 명시적으로 `{type:"heartbeat"}` 또는 빈 페이로드 송신 보장.

### I8. WS contract 명세 [중 · 중]
- **왜 필요?**: 코드로만 표현된 contract — 키 변경 시 silent break.
- **장점**: 협업 명확 / 타입 검증.
- **단점**: AsyncAPI/JSON Schema 학습 필요.
- **변경 위치**: [docs/specs/ws_contract.md](../../../../docs/specs/) + 가능하면 JSON Schema. 또는 클라이언트 측 타입 정의 (`shared/types.js` typedef JSDoc).

### I9. 재시작 시 상태 복원 hook [중 · 중]
- **왜 필요?**: 재시작 후 빈 상태 → 브라우저가 잠시 가짜 정보 또는 깜빡임.
- **장점**: 부드러운 재시작.
- **단점**: 시작 시 DRF 호출 (지연 1~2초).
- **변경 위치**: [app.py lifespan](../../../../fastapi-server/app.py#L33-L48) startup에서 DRF로부터 latest gas/power/positions fetch.

### I10. _prev_total_kw 캡슐화 [하 · 소]
- **왜 필요?**: state.py 외 또 다른 글로벌. 테스트 reset 어려움.
- **변경 위치**: [broadcast.py](../../../../fastapi-server/websocket/services/broadcast.py)에 class 또는 state.py로 통합.

## 6. 구현 추천 순서

### 1단계 — 신뢰성 핵심 (즉시) ⚡
- **I1** 운영 vs 더미 모드 분리 (랜덤 `level` 제거)
- **I3** _send_to_all 병렬화 + timeout
- **I6** timestamp UTC 통일
- **이유**: 사용자가 보는 정보의 신뢰성 직결. I1은 한 줄 분기로 사고 방지. I3은 한 클라이언트 지연이 모두에 미치는 영향 차단.

### 2단계 — 보안 (1주 내) 🔐
- **I4** WS 인증 미들웨어 (04 D2 / 07 G1과 통합)
- **이유**: 산업 안전 시스템의 정보 누출·위변조 차단.

### 3단계 — 운영 모델 명시 (다음 sprint) 📐
- **I2** 다중 워커 대비 (단기: `--workers 1` 강제 문서화 / 장기: Redis)
- **I9** 재시작 시 상태 복원 hook
- **I7** heartbeat 명시
- **I8** WS contract 명세
- **이유**: 운영 사고 시 원인 추적·수평 확장 대비. 즉시 위험 아니지만 명시 필요.

### 4단계 — 클린업 (여유 시) 🧹
- **I5** alarms drop 정책 명시
- **I10** _prev_total_kw 캡슐화

### ⚠️ 주의사항 (초보자용)
- **I1 더미 모드 분리는 시연/QA 시 필요한 동작 보존**: 무조건 더미 제거하면 시연이 깨짐. `IS_DUMMY` 환경변수로 분기해 dev/staging은 true, prod는 false.
- **I2 단일 워커 강제는 trade-off**: 성능 한계 시점에 Redis 도입 시급. 현재 트래픽 수준이면 단일 워커로 충분.
- **I3 timeout은 너무 짧으면 정상 클라이언트도 cut**: 2초로 시작해 운영 모니터링 후 조정. 끊긴 클라이언트는 ws-client.js 자동 재연결로 복구.
- **I4 WS 인증은 e2e 테스트 회귀 위험 큼**: PR-H 통합 테스트가 인증 없이 작성되어 있다면 새 토큰을 fixture에 추가하는 작업 동반.
- **I6 timestamp 변경 시 JS도 동시 갱신**: 일부 JS가 `new Date(timestamp)`로 파싱하면 timezone naive vs utc 차이로 KST 시간 어긋남. 한 PR에 양쪽 모두 변경.
