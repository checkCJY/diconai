# Discord 알람 연동 — as-built (실제 구현 기록)

> **성격**: 구현 현황(as-built) 레퍼런스 + 학습용 설명. 각 단계를 "① 왜 ② 실제 코드 1:1 ③ 트러블슈팅" 으로 기록.
> **기획·결정 배경**: [skill/plan/discord-alarm-integration.md](../plan/discord-alarm-integration.md)
> **작성 시작**: 2026-06-01

## 전체 그림

기존 알람(가스/전력/지오펜스/정상화)을 **외부 Discord 채널로도 발송**하는 기능. "Discord 연결 = 관리자/작업자 디바이스"로 가정.

구현은 두 Phase로 나뉜다. 둘은 의존성 없이 독립이다.

- **Phase A (T0)** — 인앱 WS 뿌리 갭 정정: 작업자가 소속 시설 가스/전력 DANGER를 받게 한다. (Discord 이전 문제)
- **Phase B (T1~T7)** — Discord 미러: 같은 알람을 외부 채널로 발송.

---

## Phase A / T0 — 작업자도 가스/전력 DANGER 수신 (인앱 WS)

### ① 왜 했는가

**발견된 설계 갭.** 기존 시스템에서 알람이 나가는 통로는 두 갈래였다:

- **센서 대시보드** `/ws/sensors/` (`sensor_clients`) — 모든 알람을 broadcast. 관제 화면.
- **작업자 개인 채널** `/ws/worker/{id}/` (`worker_clients`) — **지오펜스 진입만** 개인 전송.

즉 **가스/전력 DANGER는 작업자 개인 채널로 한 번도 가지 않았다.** 작업자가 대시보드를 직접 띄우지 않는 한 위험을 인지할 수 없었다. 이 갭은 그동안 **관리자 계정으로만 점검**했기 때문에 드러나지 않았다 — 관리자 화면(sensor_clients)에는 다 보였으니까.

가스/전력 DANGER는 본질적으로 **대피(life-safety) 알람**이다. 현장 작업자가 "지금 위험하니 빠져나와라"를 알아야 한다. 관리자만 아는 것은 설계 미스다. → **작업자도 가스/전력 DANGER 수신**으로 교정.

**왜 "소속 시설 작업자 전원"인가 (옵션 b).** 수신 대상 후보는 세 가지였다:
- (a) 전체 작업자 — 다른 시설 작업자에게도 핑. 노이즈 큼. 기각.
- (b) **해당 시설 작업자 전원** — 채택. 가스는 구역 무관 확산하므로 시설 전원 통보가 안전.
- (c) 위험 구역 안에 현재 있는 작업자만 — 가장 정밀하지만, 확산하는 가스에서는 옆 구역 작업자를 누락해 오히려 위험. 후속(v2)으로.

**왜 대상 계산을 DRF가 하는가.** 발송 분배는 FastAPI(`worker_clients` 보유)가 하지만, FastAPI는 **Django ORM이 없어 `CustomUser`를 직접 조회할 수 없다.** 그래서 대상 worker_id 목록은 DRF에서 계산해 payload로 넘기고, FastAPI는 그 목록으로 fan-out만 한다. 이 분리의 부수 효과: **(b)→(c) 전환이 DRF 셀렉터 교체만으로** 끝나고, 분배 코드(FastAPI)는 그대로다.

### ② 실제 코드 (1:1)

**T0a — 대상 셀렉터 신규** [apps/alerts/selectors/alarm_targets.py](../../drf-server/apps/alerts/selectors/alarm_targets.py)

```python
def get_facility_worker_ids(facility_id: int) -> list[int]:
    """해당 시설의 활성 작업자(user_type=worker) id 목록.

    가스/전력 DANGER 대피 알림 수신 대상. ... idx_user_facility_type_active 인덱스로 조회.
    수신 범위를 "현재 위험 구역 안에 있는 작업자"로 좁히려면 본 셀렉터만 교체.
    """
    if not facility_id:
        return []
    return list(
        User.objects.filter(
            facility_id=facility_id,
            user_type=UserType.WORKER,
            is_active=True,
        ).values_list("id", flat=True)
    )
```

**T0b — DANGER 태스크 payload에 대상 주입** [apps/alerts/tasks.py](../../drf-server/apps/alerts/tasks.py)

`fire_danger_alarm_task`(가스)·`fire_power_danger_task`(전력) 두 곳에만 추가. WARNING·정상화는 제외(노이즈).

```python
"message": alarm.get_short_message(),
# 소속 시설 작업자에게도 대피 알림 — FastAPI가 이 목록으로만
# worker_clients 분배(전체 broadcast 아님). 누락 시 작업자 미전송.
"target_worker_ids": get_facility_worker_ids(facility_id),
```

**T0c — FastAPI 분배** [internal/routers/alarm_router.py](../../fastapi-server/internal/routers/alarm_router.py)

`AlarmPayload`에 필드 추가 (`extra:ignore`라 기존 발신자 무영향):

```python
target_worker_ids: list[int] = []
```

`push_alarm_handler`에서 ① 스트림 push 전 pop(브라우저 유출 방지) ② 지오펜스 분기 옆 fan-out:

```python
payload.pop("target_worker_ids", None)   # 브라우저 broadcast 엔 미포함
...
elif alarm.alarm_type in ("gas_threshold", "power_overload") and (
    alarm.risk_level == "danger"
):
    for worker_id in alarm.target_worker_ids:
        ws = worker_clients.get(worker_id)
        if ws:
            try:
                await ws.send_json({"type": "worker_alert", **payload})
            except Exception:
                worker_clients.pop(worker_id, None)
```

**프론트 무수정.** [worker-ws.js](../../drf-server/static/js/shared/worker-ws.js)가 `worker_alert`→`AlarmPopup.show`로 처리하고, `AlarmMapper.fromWorkerAlert`가 공통 매퍼(`_common`)라 가스/전력 payload도 그대로 렌더된다.

### ③ 트러블슈팅 / 안전성 확인

작업 전 "다른 데가 깨지지 않나"를 코드로 검증한 항목들:

| 우려 | 확인 결과 | 근거 |
|---|---|---|
| 새 payload 필드가 기존을 깨나 | 안전 — 순수 추가 | `AlarmPayload.model_config = {"extra": "ignore"}`. 옛 발신자는 기본값 `[]`로 통과 |
| 알람 dedup이 틀어지나 | 불변 | `_payload_fingerprint`는 `event_id+risk_level`만 사용 — payload 필드 추가 무관 |
| 관리자가 중복 팝업 받나 | 1회만 표시 | 대시보드 보는 작업자/관리자가 sensor broadcast + worker_alert 둘 다 받아도 [alarm-popup.js](../../drf-server/static/js/shared/alarm-popup.js) event_id 60s dedup이 흡수 |
| 대상 id 목록이 브라우저로 새나 | 차단 | 스트림 push 전 `payload.pop("target_worker_ids")` |
| cross-facility 핑(타 시설 작업자) | 원천 차단 | 전체 broadcast가 아니라 DRF가 계산한 시설 한정 목록만 순회 |
| 기존 경로 수정 위험 | 0 | sensor broadcast·지오펜스 전송·dedup·WARNING/정상화 전부 미수정. 작업자 DANGER 분기만 추가 |

**주의점 (운영):**
- `target_worker_ids` 는 알람 발생 **시점**의 시설 작업자 스냅샷. 이후 접속한 작업자는 그 알람을 못 받는다(알람은 point-in-time). 기존 알람 동작과 동일.
- 작업자가 접속 안 했으면(worker_clients에 없음) 인앱 전송은 누락 — 이 갭을 닫는 것이 Phase B(Discord, 폰 도달).

**lint**: drf-server / fastapi-server 양쪽 `ruff check` + `ruff format --check` 통과.

### ④ 검증 결과 (2026-06-01, 컨테이너)

- **T0a 셀렉터 (실 DB)**: `get_facility_worker_ids(1)` → `[3,4,5,9,10,11,12]` — DB의 시설1 활성 작업자와 정확히 일치. `get_facility_worker_ids(0)` → `[]`.
- **T0c 모델 (fresh 프로세스)**: `AlarmPayload`가 `target_worker_ids` 파싱 · 옛 발신자(필드 없음) → `[]` · 스트림 push 전 pop 후 payload에서 제거 확인 · fan-out 조건은 가스/전력 danger만 True.
- **라이브 wire (fastapi 재기동 후)**: 워커 JWT로 `/ws/worker/3/` 접속 → 내부 push 2회.
  - 양성 `target_worker_ids=[3]` → 워커 3이 `worker_alert`(gas_threshold/danger) **수신**, payload에 `target_worker_ids` 미포함(누출 없음).
  - 음성 `target_worker_ids=[9999]` → 워커 3 **미수신** (대상 외 작업자 제외 확인).

> 운영 상태 메모: 검증 위해 **fastapi는 새 코드로 재기동**됨(fan-out 동작 중). `celery-worker-alarm`은 아직 옛 코드라, 실제 가스/전력 DANGER 태스크가 `target_worker_ids`를 싣기 시작하려면 해당 워커 재기동(배포 시점) 필요. 그 전까지 실알람의 작업자 전송은 비활성(payload 필드 부재 → 빈 목록 → 미전송)으로 안전.

---

## Phase B / T1~T7 — Discord 미러

### ① 왜 했는가

인앱 알람(Phase A 포함)은 **대시보드/앱 화면을 봐야** 닿는다. 현장 작업자가 폰만 들고 있으면 못 본다. 작업자 수신 디바이스가 미정이라 막혀 있던 문제를, **"Discord = 디바이스"로 가정**해 폰 푸시로 닿게 한다. 같은 알람을 외부 채널로 한 번 더 미러하는 것이라, 위험 탐지·정책·DB는 일절 건드리지 않고 **출력 채널만 추가**한다.

**라우팅 결정** — 관리자/작업자 성격이 다르므로 채널별로 다르게:
- 관리자 채널: 모든 알람 broadcast (관제 목적, 멘션 없음).
- 작업자 채널: 지오펜스는 본인 개인 멘션 / 가스·전력 **DANGER**는 `@here` 대피 broadcast / WARNING·정상화는 미발송(노이즈).

**메트릭 미도입** (사용자 결정) — 실패는 `logger.warning`으로만. 필요해지면 추후.

### ② 실제 코드 (1:1)

| T | 파일 | 변경 |
|---|---|---|
| T2 | [config/settings/base.py](../../drf-server/config/settings/base.py) | `DISCORD_ALARM_ENABLED`(기본 False) + webhook 2개 env |
| T1 | [user.py](../../drf-server/apps/accounts/models/user.py) + migration `0011_customuser_discord_id` | `discord_id` CharField(blank) |
| T3 | [discord_service.py](../../drf-server/apps/notifications/services/discord_service.py) (신규) | 라우팅·임베드·발송 |
| T4 | [tasks.py](../../drf-server/apps/alerts/tasks.py) `_push_to_ws` | WS 성공 시 `send_alarm_to_discord` 호출 |
| T6 | [admin.py](../../drf-server/apps/accounts/admin.py) | fieldsets에 `discord_id` |
| T7 | `.env.example` × 2 | 변수 3개 + webhook 발급 안내 |

`send_alarm_to_discord(alarm_data)` 핵심:
```python
if not settings.DISCORD_ALARM_ENABLED: return          # 기본 OFF
if not admin_url and not worker_url: return
embed = _build_embed(alarm_data)                        # 색상/제목/본문/길이자르기
if admin_url: _post(admin_url, {"embeds":[embed]})      # 관리자: 모든 알람
# 작업자: 지오펜스 개인멘션 / 가스·전력 DANGER @here
if worker_id and (did := _get_worker_discord_id(worker_id)):
    _post(worker_url, {"content":f"<@{did}>", "embeds":[embed],
                       "allowed_mentions":{"users":[did]}})
elif alarm_type in ("gas_threshold","power_overload") and risk=="danger":
    _post(worker_url, {"content":"@here 🚨 즉시 대피", "embeds":[embed],
                       "allowed_mentions":{"parse":["everyone"]}})
```

T4 주입 — WS 푸시 성공(`pushed`)일 때만:
```python
if pushed:
    try:
        from apps.notifications.services.discord_service import send_alarm_to_discord
        send_alarm_to_discord(alarm_data)
    except Exception:
        pass  # Discord 실패는 알람 본류 비차단
```

### ③ 트러블슈팅 / 안전성

| 포인트 | 처리 |
|---|---|
| `<@id>`/`@here`가 핑이 안 울림 | **`allowed_mentions` 필수** — `{"users":[id]}` / `{"parse":["everyone"]}` 동봉 (없으면 렌더만 되고 알림 안 감 → 대피/멘션이 조용히 깨짐) |
| Discord 지연이 worker 점유 | `timeout=3.0` |
| retry 중복 발송 | `_push_to_ws`의 `pushed` 게이팅 — 성공 tick 1회만 (Discord엔 dedup 없음) |
| 임베드 길이 초과 | `_truncate`로 title≤256·description≤4096 |
| 머지해도 기존 영향 0 | 기본 `DISCORD_ALARM_ENABLED=False` + 예외 완전 격리 |

### ④ 검증 결과 (2026-06-01)

- **유닛테스트 5개 pass** ([test_discord_service.py](../../drf-server/apps/notifications/tests/test_discord_service.py), httpx mock):
  가스 DANGER→관리자+작업자(@here) · 가스 WARNING→관리자만 · 지오펜스→개인멘션(users) · discord_id 없음→작업자 미발송 · ENABLED=False→무발송.
- **통합**: `manage.py check` 0 이슈 · `discord_service`·`tasks` import OK · 비활성 호출 무발송 확인.
- **lint**: ruff check + format 통과.
- **마이그레이션**: `accounts.0011_customuser_discord_id` 적용 완료.

> 남은 단계(실 Discord 발송): ① Discord 서버에 관리자/작업자 채널 + webhook 2개 생성 → ② `.env`에 `DISCORD_ALARM_ENABLED=True` + webhook URL 2개 → ③ 작업자별 `discord_id`를 어드민에서 입력(개인 멘션용) → ④ drf·celery-worker-alarm 재기동. 그 전까진 OFF로 안전.

---

## 테스트 방법 (2026-06-01 전 계층 검증 완료)

전부 컨테이너 안에서 실행. 호스트 직접 pytest 금지.

### L1. 유닛테스트 — Discord 라우팅 (httpx mock, DB 불필요)
```bash
docker compose exec drf python -m pytest apps/notifications/tests/test_discord_service.py -v
```
가스 DANGER→관리자+작업자(@here) / WARNING→관리자만 / 지오펜스→개인멘션 / discord_id 없음→스킵 / ENABLED=False→무발송.

### L2. 셀렉터 — 시설 작업자 조회 (실 DB)
```bash
docker compose exec drf python manage.py shell -c "from apps.alerts.selectors.alarm_targets import get_facility_worker_ids; print(get_facility_worker_ids(1)); print(get_facility_worker_ids(0))"
```

### L3. 정적 — lint + 무결성
```bash
cd drf-server && ruff check apps/ config/
docker compose exec drf python manage.py check
docker compose exec drf python manage.py makemigrations --check --dry-run
```

### L4. 라이브 wire — 작업자 WS 실수신 (Phase A)
> 먼저 `docker compose restart fastapi celery-worker-alarm`. JWT를 컨테이너 안에서 만들어 복붙 불필요.
```bash
docker compose exec -T fastapi python -c "
import asyncio, json, time, httpx, jwt, websockets
from core.config import settings
tok = jwt.encode({'user_id':'3','exp':int(time.time())+300}, settings.JWT_SIGNING_KEY, algorithm=settings.JWT_ALGORITHM)
itok = settings.INTERNAL_SERVICE_TOKEN
async def m():
    async with websockets.connect('ws://localhost:8001/ws/worker/3/?token='+tok) as ws:
        await asyncio.sleep(0.6)
        for tw,label in [([3],'양성[3]'),([9999],'음성[9999]')]:
            body={'alarm_type':'gas_threshold','risk_level':'danger','source_label':'T','summary':'테스트','is_new_event':True,'event_id':990000+tw[0],'target_worker_ids':tw}
            async with httpx.AsyncClient() as c:
                await c.post('http://localhost:8001/internal/alarms/push/',json=body,headers={'Authorization':'Bearer '+itok})
            try:
                d=json.loads(await asyncio.wait_for(ws.recv(),timeout=3))
                print(label+': 수신 type='+str(d.get('type'))+' 누출='+str('target_worker_ids' in d))
            except asyncio.TimeoutError:
                print(label+': 미수신(OK)')
asyncio.run(m())
"
```
기대: `양성[3]: 수신 type=worker_alert 누출=False` / `음성[9999]: 미수신(OK)`.
(`InsecureKeyLengthWarning`은 테스트 토큰 생성 경고일 뿐 — 무시 또는 `2>/dev/null`.)

### L5. Discord 실발송 — webhook.site 로 payload 확인 (Phase B)
https://webhook.site 에서 고유 URL 발급 → 아래 `URL=` 한 곳만 교체:
```bash
docker compose exec -T drf python manage.py shell -c "
URL='https://webhook.site/발급받은-URL'
from django.conf import settings
settings.DISCORD_ALARM_ENABLED=True; settings.DISCORD_WEBHOOK_ADMIN=URL; settings.DISCORD_WEBHOOK_WORKER=URL
from apps.notifications.services.discord_service import send_alarm_to_discord
send_alarm_to_discord({'alarm_type':'gas_threshold','risk_level':'danger','source_label':'GS-001','summary':'가스 위험 테스트','created_at':'2026-06-01T00:00:00Z'})
"
```
webhook.site에 요청 2건: ①관리자=임베드만 ②작업자=`content:"@here 🚨 즉시 대피"` + `allowed_mentions:{parse:[everyone]}`.
개인멘션 확인은 `worker_id` 알람 + `ds._get_worker_discord_id = lambda wid: '123...'` monkeypatch 후 → `content:"<@123...>"`.
(검증: 2026-06-01 두 POST 200 OK)

### L6. 엔드투엔드 (브라우저)
`.env` ENABLED=True + webhook 설정 → drf·celery-worker-alarm 재기동 → 작업자 계정 로그인 → 가스/전력 더미 DANGER → 인앱 팝업 + Discord 작업자 채널 동시 도착.

---

## 실사용 설정 (운영 켜기)

> 모든 서비스가 루트 **`./.env.docker`** 를 읽는다 (`docker-compose.yml` env_file 공통). 실제 값은 `.env.docker`에 넣는다 — `.env.docker.example`은 양식일 뿐.

### 1. Discord 채널 + Webhook 2개
채널 2개(`#관리자-알람`, `#작업자-알람`) 준비. 각 채널: **채널 편집(⚙) → 연동 → 웹훅 → 새 웹훅 → 웹훅 URL 복사**. 관리자/작업자 각 1개 = 총 2개.
- ⚠️ 작업자가 `@here`를 받으려면 그 Discord 계정이 **서버·작업자 채널 멤버**여야 함.

### 2. `.env.docker`에 값 (따옴표 없이)
```
DISCORD_ALARM_ENABLED=True
DISCORD_WEBHOOK_ADMIN=https://discord.com/api/webhooks/관리자URL전체
DISCORD_WEBHOOK_WORKER=https://discord.com/api/webhooks/작업자URL전체
```

### 3. 작업자 `discord_id` 입력 (개인 멘션용. @here broadcast는 불필요)
- Discord **설정 → 고급 → 개발자 모드 ON** → 사용자 우클릭 → **사용자 ID 복사**
- `http://localhost:8000/admin/` → 사용자 → 해당 작업자 → "추가 정보"의 **Discord 사용자 ID**에 붙여넣기 → 저장

### 4. 재생성 (알람 발송 주체 = celery-worker-alarm)
```bash
docker compose up -d --force-recreate drf celery-worker-alarm fastapi
```
> ⚠️ **`docker compose restart`는 안 됨** — env_file은 컨테이너 *생성 시점*에 주입되므로 `restart`(같은 컨테이너 재시작)로는 `.env.docker` 변경이 반영되지 않는다. 반드시 `up -d --force-recreate`(컨테이너 재생성). (코드만 바뀐 경우는 볼륨 마운트라 `restart`로 충분.)

### 5. 확인
```bash
docker compose exec -T celery-worker-alarm python -c "from django.conf import settings; print('ENABLED=',settings.DISCORD_ALARM_ENABLED,'admin=',bool(settings.DISCORD_WEBHOOK_ADMIN),'worker=',bool(settings.DISCORD_WEBHOOK_WORKER))"
```
기대: `ENABLED= True admin= True worker= True`. 이후 더미 DANGER → 관리자 채널 임베드 + 작업자 채널 `@here` + 인앱 팝업.

### 트러블슈팅
| 증상 | 조치 |
|---|---|
| 아무것도 안 옴 | `.env.docker` 변경 후 **`up -d --force-recreate`** 했는지(restart는 env 미반영). `printenv \| grep DISCORD`로 컨테이너 주입 확인. 5번 점검 |
| 로그 `status=404` | webhook URL 오타/만료 → 재발급 |
| 임베드는 오는데 `@here` 핑 안 됨 | 작업자가 채널 멤버 아님 → 초대 |
| `<@숫자>`가 텍스트로만 | 잘못된 ID(3번 재확인) 또는 유저가 서버에 없음 |
| 실알람인데 작업자 미수신 | `celery-worker-alarm` 재기동 누락(`target_worker_ids` 미발신) |

로그: `docker compose logs -f celery-worker-alarm | grep -i discord`
