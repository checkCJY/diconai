# 알람 스트림 전환 — Step 4: E2E 검증 런북 (풀스택)

> **목적:** plan "Verification" 9단계를 풀스택(drf+fastapi+celery+redis)에서 실행.
> **SoT:** [skill/plan/alarm-stream-migration.md](../plan/alarm-stream-migration.md) §Verification
> **선행:** Step 1~3 코드 머지 + 단위 227 passed + 실 redis 통합 스모크 통과
> **작성일:** 2026-06-01 (환경 기동 후 실행 예정)

단위·실 redis 스모크에서 **큐/루프/타입가드 메커니즘**은 검증됐다. 이 런북은 **실제
알람이 IoT→Celery→Redis Stream→브라우저까지 끝까지 도달하는지** 와 **시연 A/B/C 회귀**를 본다.

---

## 0. 전제 (환경 기동 후 확인)

```bash
# fastapi(8001)/drf(8000)/redis/celery(alarm,metric)가 모두 떠 있어야 함.
# compose 라면 localhost:8001/8000, minikube 라면 port-forward/서비스 URL 로 치환.
FASTAPI=http://localhost:8001
DRF=http://localhost:8000

curl -s $FASTAPI/health/                     # {"status":"ok"}
curl -s $FASTAPI/internal/scenario/mode      # {"mode":"..."}
```

**부팅 직후 WRONGTYPE 가드 확인 (가장 먼저):**
```bash
# fastapi 컨테이너/pod 로그에 startup 시 reset 동작 + XADD 에러 없음
docker logs <fastapi> 2>&1 | grep -iE "reset_legacy_list|WRONGTYPE|action=startup" | tail
# 키 타입이 stream 인지
redis-cli TYPE diconai:ws:alarms             # "stream" (또는 첫 알람 전이라 "none")
```

---

## 1. 단위 테스트 (이미 통과 — 재확인용)
```bash
docker run --rm --entrypoint sh -v "$PWD/fastapi-server":/app -w /app \
  diconai/fastapi:dev -c "pytest -q"          # 227 passed
```

## 2. 알람 발화 → 브라우저 도달 (시나리오 A=가스 / B=전력)
```bash
# 브라우저 WS 한쪽에서 열어두기 (websocat 또는 브라우저 대시보드 /dashboard/)
websocat "ws://localhost:8001/ws/sensors/"   # 인증 옵트인 시 ?token=<access>

# 다른 쪽에서 danger 유발
curl -s -XPOST $FASTAPI/internal/scenario/mode -H 'Content-Type: application/json' -d '{"mode":"co_leak"}'   # 가스(A)
# 또는
curl -s -XPOST $FASTAPI/internal/scenario/mode -H 'Content-Type: application/json' -d '{"mode":"overload"}'  # 전력(B)
```
**기대:** WS 스트림에 `{"alarms":[{...risk_level:"danger"...}]}` 1건 도달. 패널/팝업 표시.

## 3. RESOLVED 전이 → 팝업 close
```bash
# DRF 에서 해당 Event 를 RESOLVED 로 전이 (어드민 패널 또는 API)
# 예: PATCH /api/events/<id>/status  {"status":"RESOLVED"}  (실제 경로는 환경 확인)
```
**기대:** 같은 event_id 팝업이 자동 닫히고 "위험 해소" 토스트. (fingerprint `event:<id>:resolved`
가 원래 알람과 분리돼 dedup 통과 — Step 1)

## 4. dedup — celery retry 모사
```bash
# 같은 payload 2회 push (event_id 동일)
for i in 1 2; do curl -s -XPOST $FASTAPI/internal/alarms/push/ -H 'Content-Type: application/json' \
  -d '{"alarm_type":"gas_threshold","risk_level":"danger","source_label":"테스트","summary":"x","is_new_event":true,"event_id":99999}'; done
```
**기대:** 브라우저엔 **1건만**. `alarm_push_dedup_hits_total` +1. (`localhost` 외 호출 시 403 —
컨테이너 내부/포트포워드로 실행)

## 5. 가스 9-clear 붕괴 → 패널 1줄
```bash
# 가스 danger 후 정상 복귀 시 9종 clear 가 같은 source_label 로 동시 발생
curl -s -XPOST $FASTAPI/internal/scenario/mode -d '{"mode":"normal"}' -H 'Content-Type: application/json'
```
**기대:** 정상화 패널 **1줄** (source_label 단위 dedup — Step 1 fingerprint).

## 6. [M-1] 보존 — 클라 0인 동안 발생 → 접속 시 전달
```bash
# 1) 모든 브라우저 WS 끊기 (sensor_clients=0)
# 2) 그동안 danger 유발
curl -s -XPOST $FASTAPI/internal/scenario/mode -d '{"mode":"co_leak"}' -H 'Content-Type: application/json'
# 3) 잠시 후 WS 재접속
websocat "ws://localhost:8001/ws/sensors/"
```
**기대:** 재접속 직후 누적분이 **배치로** 전달 (커서 동결 → XREAD 한 번에). 스트림 미삭제 확인:
```bash
redis-cli XLEN diconai:ws:alarms             # 클라 0 동안에도 적재돼 있음
```

## 7. E2E latency 메트릭
```bash
curl -s $FASTAPI/metrics | grep e2e_alarm_latency_seconds | head
```
**기대:** danger 발화 후 `e2e_alarm_latency_seconds_count{risk_level="danger"}` 증가, 관측치 기록.

## 8. ⭐ stream lag 메트릭 (이번 PR 신규)
```bash
curl -s $FASTAPI/metrics | grep fastapi_alarm_stream_lag_seconds
```
**기대(평상시):** ≈ 0.
**인위 지연 검증:** alarm_flush_loop 을 일시 지연(예: 브레이크포인트, 또는 알람 폭주 주입)
시켰을 때 값이 **증가**하는지 — 말단이 커서보다 앞서가면 lag↑.
```bash
# 폭주 주입 예: 짧은 시간에 다수 push (서로 다른 event_id 로 dedup 회피)
for i in $(seq 1 200); do curl -s -XPOST $FASTAPI/internal/alarms/push/ -H 'Content-Type: application/json' \
  -d "{\"alarm_type\":\"gas_threshold\",\"risk_level\":\"warning\",\"source_label\":\"L$i\",\"summary\":\"x\",\"is_new_event\":true,\"event_id\":$((100000+i))}" >/dev/null; done
curl -s $FASTAPI/metrics | grep fastapi_alarm_stream_lag_seconds   # 일시적으로 > 0 관찰
```

## 9. 회귀 — 시연 시나리오 A/B/C
| 시나리오 | 트리거 | 확인 |
|---|---|---|
| A 가스 | `mode=co_leak`/`fire`/`chemical_spill` | danger 팝업·AI mute·정상화 1줄 |
| B 전력 | `mode=overload`/`voltage_drop`/`phase_loss` | 5축 라벨·격상 모달 아님(전력 narrative) |
| C 어드민 정책 | 어드민 패널에서 AlertPolicy 변경 | 변경 즉시 반영 (알람 스트림과 독립 — 회귀 영향 0 기대) |

> C는 알람 *정책*이라 큐 전송 계층과 직교 — 본 PR이 건드린 부분 아님. A/B의 알람 발화·도달이
> 핵심 회귀 대상.

---

## 합격 기준 (전부 충족 시 Step 4 완료)
- [ ] 부팅 시 WRONGTYPE 없음 + 키 타입 stream
- [ ] A/B danger 알람 브라우저 1건 도달
- [ ] RESOLVED 팝업 close
- [ ] dedup 1건만 (retry 모사)
- [ ] 가스 9-clear 패널 1줄
- [ ] [M-1] 클라 0 → 재접속 시 누적분 배치 전달
- [ ] `e2e_alarm_latency_seconds` 기록
- [ ] `fastapi_alarm_stream_lag_seconds` 평상시≈0 / 인위지연 시 증가
- [ ] 시연 A/B/C 정상

---

## 실행 결과 (2026-06-01, compose 풀스택)

| # | 검증 | 결과 | 실측 |
|---|---|---|---|
| 0 | 부팅 WRONGTYPE 가드 | ✅ | startup 로그 `action=reset_legacy_list` — **잔존 LIST 실제 1회 정리**. 재시작 시엔 stream이라 미삭제(보존) 확인 |
| 1 | 단위 + 실 redis 스모크 | ✅ | 227 passed / 통합 스모크 PASS |
| 2 | WS 도달 | ✅ | 인증 push→XADD→XREAD 배치→broadcast, 브라우저 1건 도달 |
| 4 | dedup 1건 | ✅ | 같은 event_id 2회 → WS 1건 |
| 6 | [M-1] 보존 | ✅ | 워밍업으로 커서 전진 → 클라0 동안 push → 재접속 시 누적 전달 |
| 7 | `e2e_alarm_latency` | ✅ | `count{risk_level="danger"}` 증가 |
| 8 | `stream_lag` | ✅ | 평상시 0.0 / 30클라+600 burst 시 0.010s↑ / 소화 후 0 복귀 |
| 9-A | 시나리오 A(가스) 풀파이프라인 | ✅ | gas_dummy(co_leak)→DRF→Celery→push→WS. `gas_threshold`/`gas_anomaly_ai`(danger)/`gas_clear` 도달 |
| 9-B | 시나리오 B(전력) 풀파이프라인 | ✅ | power_dummy(overload). `power_overload`(source 보존)/`power_anomaly_ai`/`power_clear` 14건 도달 |

**메트릭 실측:** `redis_command_duration_seconds_count{command="xadd"}` emit(브pop/xread 없음, parity),
`fastapi_alarm_queue_length`=XLEN 동기.

**미실행(이 PR과 직교 — 단위+전송 E2E로 커버):**
- #3 RESOLVED — fingerprint `event:<id>:resolved` 로직, DRF Event 전이 필요. 단위 ✅
- #5 가스 9-clear "1줄" — A 구동 중 `gas_clear`가 source_label 단위로 묶여 도달(부수 확인). 단위 ✅

### ⚠ 발견한 시맨틱 경계 — `"$"` 커서 손실 창
부팅 후 **첫 실제 read가 성립하기 전**(`last_id="$"` 구간), XREAD의 `"$"`는 매 호출 시점의
최신 ID로 재해석되므로 **iteration 간극에 들어온 push는 누락**될 수 있다. 첫 read 이후
커서가 실제 ID로 바뀌면 무손실. 이는 D3("부팅 $=신규만") 의도대로지만, [M-1] 보존은
**"한 번이라도 소비한 뒤의 재접속"** 에 대해 성립함을 명확히 해둔다 (워밍업 없이 부팅 직후
0클라 구간의 알람은 보존 대상 아님 — 과거 무한 replay 방지와 trade-off).

---

## 변경된 메트릭 라벨 목록 (대시보드 점검용 — 사용자가 손봄)
- **신규:** `fastapi_alarm_stream_lag_seconds` (Gauge, 라벨 없음, liveall) — 스트림 말단↔커서 시간차(초).
- **라벨 값 변경:** `redis_command_duration_seconds{command=...}` — `lpush`→`xadd` (실제 emit).
  `brpop`→`xread`는 **정의만, emit 안 함**(parity). 대시보드에 `command="lpush"`/`"brpop"` 쿼리가
  있으면 `"xadd"`로 교체 필요. `command="brpop"` 패널은 데이터 끊김 → 제거 검토.
- **의미 변경(이름 동일):** `fastapi_alarm_queue_length` — 이제 LIST LLEN 이 아니라 Stream XLEN.
