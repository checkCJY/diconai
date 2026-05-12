# 트러블슈팅 — 도커 환경에서 대시보드 알람 팝업이 뜨지 않음

> 발생일: 2026-05-12 / 환경: docker-compose (drf + fastapi + redis + celery×2 + prom + grafana)
> 영향: 대시보드 실시간 알람 팝업 100% 누락 (DB 기록은 정상)
> 짝꿍 문서: [docker_setup.md](docker_setup.md)

## 1. 증상

대시보드(`localhost:8000/dashboard/`)에서:
- **이벤트 패널**: "알 수 없음 / power_overload" 같은 항목이 채워짐 (즉, DB Event는 정상 적재)
- **알람 팝업**: 한 번도 뜨지 않음
- **이벤트 목록 페이지**(`/admin-panel/.../이벤트 현황`): "유해가스 초과", "power_overload" 등으로 정상 표시

즉 **DB → 화면(목록)** 경로는 살아 있고, **DB → WS → 브라우저 팝업** 경로만 끊긴 상태.

## 2. 정상 흐름 (복습)

```
센서 → fastapi (수신/검증) → drf (Event/AlarmRecord 저장)
                                    │
                                    └─ Celery 태스크 ──► POST fastapi:/internal/alarms/push/
                                                                │
                                                                ▼
                                                       active_alarms 큐 (메모리)
                                                                │
                                                       alarm_flush_loop(1초 틱)
                                                                │
                                                                ▼
                                                       sensor_clients (WebSocket)
                                                                │
                                                                ▼
                                                       브라우저 알람 팝업
```

끊긴 구간은 **Celery → fastapi 푸시** 한 줄이었다. 그리고 그 한 줄이 **세 가지** 이유로 동시에 막혀 있었다.

## 3. 원인 진단 (3단)

### 원인 ① — Celery에서 `localhost:8001` 하드코딩

[drf-server/apps/alerts/tasks.py](../../drf-server/apps/alerts/tasks.py) 의 `_push_to_ws`가
`FASTAPI_INTERNAL_URL = "http://127.0.0.1:8001/internal/alarms/push/"` 를 상수로 박아 사용하고 있었다.

도커 네트워크에서 `127.0.0.1`은 **celery-worker 컨테이너 자기 자신**을 가리키므로 POST가 8001번 포트에 닿지 않고 `[Errno 111] Connection refused`로 즉시 실패.

로그 증거:
```
[2026-05-12 14:33:40,805: WARNING/ForkPoolWorker-2]
  FastAPI WS 알람 푸시 실패 (WS 알림 누락): [Errno 111] Connection refused
```

`drf-server/config/settings.py:200`에 이미 `FASTAPI_INTERNAL_URL = env(...)` 가 정의돼 있고
[docker-compose.yml](../../docker-compose.yml)도 celery-worker에 `FASTAPI_INTERNAL_URL=http://fastapi:8001` 을 주입하고 있었는데, **tasks.py가 settings를 무시하고 자체 상수만 쓴 것**이 1차 원인.

### 원인 ② — celery-worker / fastapi 컨테이너에 소스 마운트 누락

원인 ①을 코드 수정으로 해결한 뒤에도 동일 에러가 반복됐다.
이유: celery-worker / fastapi 서비스는 **소스 코드 볼륨 마운트가 없어** `docker compose restart`만으로는 호스트의 코드 변경이 컨테이너에 반영되지 않음. (이미지에 baked-in된 옛 코드로 계속 실행)

drf 서비스만 `./drf-server:/app` 마운트를 가지고 있었다.

### 원인 ③ — fastapi `/internal/alarms/push/`의 localhost-only IP 화이트리스트

①②를 해결한 뒤 새로 드러난 마지막 단계.
[fastapi-server/internal/routers/alarm_router.py](../../fastapi-server/internal/routers/alarm_router.py) 의 `push_alarm`이
```python
if client_host not in ("127.0.0.1", "::1", "localhost"):
    raise HTTPException(status_code=403, detail="내부 전용 엔드포인트입니다.")
```
로 시작해 **Bearer 토큰 검증보다 먼저** IP를 검사했다.

도커 네트워크에서는 celery-worker가 `172.18.0.x` 컨테이너 IP로 접속하므로 토큰 자격이 멀쩡해도 **403 Forbidden**으로 거부된다.

로그 증거:
```
fastapi-1 | 2026-05-12 05:38:59 INFO uvicorn.access:
  172.18.0.8:48468 - "POST /internal/alarms/push/ HTTP/1.1" 403
```

## 4. 해결

### 수정 1 — Celery 푸시 URL을 settings 기반으로 (env 주입 활용)

`drf-server/apps/alerts/tasks.py`:

```python
# 변경 전
FASTAPI_INTERNAL_URL = "http://127.0.0.1:8001/internal/alarms/push/"
...
httpx.post(FASTAPI_INTERNAL_URL, json=alarm_data, headers=headers, timeout=3.0)

# 변경 후
_ALARM_PUSH_PATH = "/internal/alarms/push/"
...
base = getattr(settings, "FASTAPI_INTERNAL_URL", "") or "http://127.0.0.1:8001"
url = base.rstrip("/") + _ALARM_PUSH_PATH
httpx.post(url, json=alarm_data, headers=headers, timeout=3.0)
```

도커에선 compose env에서 `http://fastapi:8001`이 주입되고, 로컬 비-도커 실행 시엔 기본값 `http://127.0.0.1:8001`로 동작 (양쪽 환경 모두 호환).

### 수정 2 — celery-worker / fastapi에 소스 핫리로드 마운트 추가

`docker-compose.yml`:

```yaml
fastapi:
  ...
  volumes:
    - ./fastapi-server:/app   # 추가

celery-worker:
  ...
  volumes:
    - ./drf-server:/app       # 추가
    - ./drf-server/db.sqlite3:/app/db.sqlite3
    - ./drf-server/media:/app/media
```

이후엔 코드 변경 시 `docker compose restart fastapi` / `restart celery-worker` 한 번으로 반영된다. (drf 서비스의 `--reload` 자동 재시작 패턴과 일관)

### 수정 3 — alarm_router 인증 정책 정리

`fastapi-server/internal/routers/alarm_router.py`:

```python
# 변경 전 — IP 체크 → 토큰 체크 (도커에서 IP 체크에 막힘)
client_host = request.client.host if request.client else ""
if client_host not in ("127.0.0.1", "::1", "localhost"):
    raise HTTPException(status_code=403, detail="내부 전용 엔드포인트입니다.")
expected_token = settings.INTERNAL_SERVICE_TOKEN
if expected_token:
    ...토큰 검증...

# 변경 후 — 토큰 설정 시 토큰만으로 검증, 미설정 시 localhost-only 폴백
expected_token = settings.INTERNAL_SERVICE_TOKEN
if expected_token:
    ...토큰 검증...
else:
    client_host = request.client.host if request.client else ""
    if client_host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(status_code=403, detail="내부 전용 엔드포인트입니다.")
```

근거:
- 토큰 인증은 `.env.docker`의 32바이트 랜덤 토큰으로 이미 강제됨 (양쪽 동일 값)
- 도커 네트워크는 외부 노출 없는 사설망 (`172.18.0.0/16`)이라 IP 화이트리스트는 추가 방어막 의미가 적음
- 토큰 미설정(레거시) 환경에선 기존 localhost-only를 그대로 폴백으로 유지 — 호환성 보존

## 5. 검증

```
fastapi-1 | 2026-05-12 05:40:36 INFO uvicorn.access:
  172.18.0.8:58812 - "POST /internal/alarms/push/ HTTP/1.1" 200
fastapi-1 | 2026-05-12 05:40:36 INFO uvicorn.access:
  172.18.0.8:58820 - "POST /internal/alarms/push/ HTTP/1.1" 200
```

403 → 200 전환 확인. 대시보드에서 알람 팝업이 정상 표시되는지 브라우저로 추가 확인.

## 6. 회고 — 왜 동시에 3개나 막혔는가

- 도커 도입 자체가 **2026-05-11에 이루어진 최근 변경** (메모리: `docker_infra_decision_2026_05_11.md`)이라, 내부 서비스 간 호출 경로(① URL 하드코딩, ② 핫리로드 마운트, ③ localhost 화이트리스트)가 **컨테이너 네트워크 가정에 맞게 일제히 갱신되지 않은 채 누적**돼 있었다.
- 단일 증상(알람 팝업 누락)이지만 원인은 **계층 3곳**에 분산. 한 군데를 고치면 다음 증상이 표면화되는 양파 구조였다.
- 향후 같은 패턴을 빠르게 진단하려면:
  1. **Celery 로그**: `WARNING/ForkPool... 알람 푸시 실패` — Celery 측 발신 실패 여부
  2. **fastapi access log**: `POST /internal/alarms/push/ HTTP/1.1 NNN` — 도달 여부 + 상태 코드
  3. **상태 코드별 매핑**: `403 (localhost 체크)` / `401 (토큰 없음)` / `403 (토큰 불일치)` / `200 (정상)`

## 7. 향후 작업 (별개 이슈)

`fastapi → drf` 통합 로그 호출이 여전히 403:
```
fastapi-1 | httpx: HTTP Request: POST http://drf:8000/api/internal/integration-logs/ "HTTP/1.1 403 Forbidden"
```
같은 부류(IP 화이트리스트 vs 토큰)일 가능성이 높음. 별도 이슈로 분리 처리.

---

## 변경 파일

- [drf-server/apps/alerts/tasks.py](../../drf-server/apps/alerts/tasks.py)
- [fastapi-server/internal/routers/alarm_router.py](../../fastapi-server/internal/routers/alarm_router.py)
- [docker-compose.yml](../../docker-compose.yml)
