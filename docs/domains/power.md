# 전력 모니터링 도메인

> 코드리뷰용 흐름 이해 문서. 관련 커밋: `d58799f`(파이프라인 e2e)
> 데이터 흐름: **IoT 전력센서 → fastapi(수신·5축 AI 판정) → drf(저장·알람) → Celery → WebSocket**
> 가스 위에 **5축 AI 와 채널 3축 종합**이 얹힌 구조. 가스([gas.md](gas.md)) 먼저 읽으면 이해가 빠름.

---

## 1. 파일 맵

| 레이어 | 파일 | 핵심 심볼 |
|---|---|---|
| fastapi 수신 | `power/routers/power_router.py` | `receive_power_{watt,current,voltage,onoff}` |
| fastapi 스키마 | `power/schemas/power.py` | `Power*Payload`, `SLAVE_KEYS`(slave01~72) |
| fastapi 처리 ★ | `power/services/power_service.py` | `process_anomaly_inference`, `build_equipment`, `update_power_state`, `to_channel_list` |
| fastapi 룰 평가 | `power/services/threshold_eval.py` | `evaluate_threshold_risk`, `calculate_power_risk`, `PCT_POLICY` |
| fastapi AI 엔진 ★ | `power/services/anomaly_inference.py` | `process_anomaly_inference` (605줄, 5축 오케스트레이션) |
| fastapi 결정 | `power/services/decide_alarm.py` | `decide_alarm`, `AlarmDecision`, `ALARM_SOURCE_REASON` |
| fastapi Z/CP | `power/services/zscore_anomaly.py`, `change_point_service.py` | `_zscore_check`, `detect_change_point` |
| fastapi 야간 | `power/services/night_escalation.py` | `_is_night_kst_iso`, `_NIGHT_ESCALATION` |
| fastapi sync | `power/services/threshold_sync.py`, `channel_meta_cache.py` | `get_threshold_meta`, `get_channel_entry` (DRF 5분 sync) |
| fastapi 결합 | `ai/risk_combine.py` | `combine_risk_5axis` ★ |
| drf 시리얼라이저 | `monitoring/serializers/power_data.py` | `PowerDataBulkIngestSerializer`, `PowerEventIngestSerializer` |
| drf 알람판정 ★ | `monitoring/services/power_alarm.py` | `trigger_power_alarms`, `_aggregate_risk`, `_shadow_audit` |

## 2. 전체 시퀀스

```
전력센서 (16채널 × watt/current/voltage + ON/OFF)
  │ POST /api/power/{watt,current,voltage,onoff}   slave01~72 형식
  ▼
[fastapi] power_router → schemas (slave → 채널16 정규화)
  └─ update_power_state(): power_latest[data_type] 갱신 (WS broadcast 용)
  └─ process_anomaly_inference(): ★ 5축 AI (아래 §4)
       └─ decide_alarm(): source 매트릭스 → push_alarm 직접 (활성화 모드)
  └─ POST /api/monitoring/power/data/  (16채널 bulk)
  ▼
[drf] PowerDataBulkIngestSerializer.create
  └─ bulk_create(16행, ignore_conflicts) → 저장된 것만 재조회
  └─ trigger_power_alarms(saved, device)
  ▼
[drf] power_alarm.trigger_power_alarms — 채널별 3축 max 종합 → 분기
  └─ fire_power_{danger,warning,clear}_task.delay()  → [alerts 도메인]
  ▼
브라우저
```

## 3. 채널 3축(W·A·V) 종합 — power_alarm

가스(9종 동시)와 달리 **16채널 독립**, 각 채널에 watt/current/voltage 3축. 종합 위험도 = **3축 max** (power_alarm.py:123 `_aggregate_risk`):
```python
def _aggregate_risk(device_id, channel, axis, this_risk):
    cache.set(_axis_risk_key(device_id, channel, axis), this_risk, _AXIS_TTL)  # 이번 축 캐시
    cached = cache.get_many([watt_key, current_key, voltage_key])             # 3축 모두 read
    return _max_risk([cached.get(k, NORMAL) for k in 3축])                    # 최댓값
```
- 한 번에 한 축만 도착(watt 따로/current 따로) → 도착한 축만 갱신, 나머지는 캐시된 마지막 값과 max. **한 채널 = 한 알람** 유지.
- `value is None`(통신 불능) 채널은 판정 제외 — 해당 축 캐시 미갱신, 다른 축에 영향 없음.

## 4. 5축 AI (전력의 핵심 — ai/risk_combine.combine_risk_5axis)

```python
def combine_risk_5axis(
    threshold_risk: str,      # A. 정격 % (normal/warning/danger)
    if_prediction: str,       # B. Isolation Forest (normal/anomaly)
    arima_violation: bool,    # C. ARIMA 1-step 예측 95% CI 위반
    z_score_anomaly: bool,    # D. 슬라이딩 윈도우 |z|>=3
    change_point: bool,       # E. two-window 평균/분산 급변
) -> tuple[str, str]:         # (combined_risk, escalation_source)
```

| 축 | 모듈 | 신호 |
|---|---|---|
| A threshold | threshold_eval | 정격 % 초과 |
| B IF | anomaly_inference + ai/router | Isolation Forest |
| C ARIMA | ai/router `_arima_forecast` | 1-step 신뢰구간 위반 |
| D Z-score | zscore_anomaly | \|z\|≥3 |
| E Change Point | change_point_service | two-window 급변 |

**결합 규칙** (우선순위 CRITICAL > ML_ANOMALY > ANOMALY_WARNING > TREND_SHIFT > PREDICTIVE_ALERT > NORMAL):
- base = threshold × IF × ARIMA (`combine_risk_3axis`).
- **Z·CP 는 base 가 normal 일 때만** `predict_warn` 으로 격상 (조기 경고). base 가 이미 발화 등급이면 ML/threshold 우선 → Z·CP 무시.
- 두 번째 반환값 `escalation_source` 는 "Z/CP 가 실제 격상에 기여했나" — base 가 이미 발화면 `""` (라벨 의미론 일관성).
- **night escalation**: KST 야간(22~05시) + 정격 30% 초과 시 combined 한 단계 격상 (`night_escalation.py`, SARIMA 학습 전 휴리스틱).

## 5. 검출 주체(source) 매트릭스 — decide_alarm

AI state × 정적 결과로 "누가 잡았나" 6종 분류:
| source | 의미 |
|---|---|
| `ai` | AI 가 이상 판정 (IF/Z/CP 중 하나라도) |
| `static_cover_miss` | 룰 위험 + AI 정상 (AI 가 놓친 걸 룰이 커버) |
| `static_cover_inference_fail` | AI 추론 실패 → 룰 커버 |
| `static_cover_warmup` | AI 윈도우 warmup 중 → 룰 커버 |
| `static_no_ai_available` | AI 모델 미로드 → 룰 단독 |
| `static_legacy` | DRF fallback (활성화 모드에선 미사용) |

→ AlarmRecord.source 컬럼에 영속, 프론트가 배지·톤 분기. `ALARM_SOURCE_REASON[source]` 로 운영자 친화 문구.

## 6. fastapi 단일 결정자 모드 (STATIC_THRESHOLD_AT_FASTAPI)

```python
# power_alarm.trigger_power_alarms (drf)
if settings.STATIC_THRESHOLD_AT_FASTAPI:        # 활성화 모드
    STATIC_FIRE_SUPPRESSED_BY_FASTAPI_TOTAL.inc()
    _shadow_audit(device_id, channel, aggregate)  # DRF 정적 fire skip, 비교만
    continue
# 비활성(기본): DRF 도 정적 룰로 fire
```
- True 면 fastapi 가 단일 결정자 — DRF 룰 fire 전부 skip, `_shadow_audit` 로 "fastapi 가 누락 안 했나" 모니터링만. 기본 False.

## 7. 임계치 SoT (% + 정격)

- 임계치가 절대값이 아니라 **채널 정격의 %** (예: 80% warning, 100% danger).
- 정격은 DRF `PowerChannelMeta` → fastapi `channel_meta_cache` 가 5분 주기 fetch (`get_channel_entry`).
- % 정책은 DRF `power_facility_default` 그룹 → `threshold_sync` 가 5분 sync. DRF 가 진실 공급원.

## 8. 리뷰 시 주의 (함정)

1. **device_id PK vs mac 함정** ⚠️ (power_alarm.py:185~188):
   ```python
   device_id = device.id          # PK — try_transition / fire_*_task 인자용
   device_iot_id = device.device_id   # raw mac — AI mute 키 read 용
   ```
   AI mute 키는 fastapi 가 **raw mac** 으로 set 하므로 drf 도 `device_iot_id`(mac)로 read 해야 일치. PK 로 read 하면 키 mismatch → mute 안 걸림 → **중복 발화**.
2. **시연 narrative 가드** ⚠️: 전력 시연 main course = **5축 라벨 + AI mute + 데이터 흐름**. **격상 모달은 가스 한정 패턴 — 전력 차용 금지** (발표가이드 별도).
3. **3축 부분 도착**: watt/current/voltage 가 따로 도착 → `_aggregate_risk` 가 캐시로 합침. 한 축만 와도 다른 축 마지막 값과 max. 캐시 TTL(`_AXIS_TTL`) 만료 시 그 축은 normal 로 falls back.
4. **bulk_create ignore_conflicts**: 중복 (device, channel, type, measured_at) 은 silent skip → 저장된 것만 재조회해서 알람 트리거 (미저장 행에 알람 안 울리게).
5. 알람 생성은 가스와 공유 [alerts.md](alerts.md).

## 9. 관련 문서
- 가스 (기본 흐름): [gas.md](gas.md)
- 5축 결합·ARIMA 함정: [ai-ml.md](ai-ml.md)
- 알람 생성: [alerts.md](alerts.md)
