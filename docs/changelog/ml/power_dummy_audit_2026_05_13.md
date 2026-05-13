# 전력 더미 (power_dummy v3) audit — IF 학습 데이터 적합성 검증

> 작성: 2026-05-13
> 대상: `power_data` 테이블 24,883,200 row (2025-11-13 ~ 2026-05-11, 180일)
> 데이터 출처: `python manage.py backfill_power_data --start-date 2025-11-13 --duration-days 180 --interval-sec 30`
> 목적: IF 학습 전 시뮬레이션 데이터가 [power_dummy.py v3](../../../fastapi-server/dummies/power_dummy.py) 의 의도된 패턴을 정확히 반영하는지 6항목 검증
> 결과: **6항목 모두 통과** — IF 학습 진입 OK

---

## 무엇을 했나

[backfill_power_data.py](../../../drf-server/apps/monitoring/management/commands/backfill_power_data.py)
가 power_dummy v3 로직을 인라인 복제해서 시간 가속 백필을 수행한다.
실시간 더미는 `measured_at = now_utc_iso()` 고정이라 6개월치를 만들 방법이
없어서 신규 management 커맨드를 작성했다.

복제된 로직이 더미 v3 의도와 일치하는지 audit 6항목으로 점검했다.
결함 발견 시 backfill 코드를 수정하고 재실행해야 IF 학습으로 진입할 수 있다.

---

## 검증 결과 요약

| 항목 | 측정 | 의도 | 판정 |
|---|---|---|---|
| [1] 시나리오 watt 값 | overload avg 7768W (max 9259) · spike avg 9754W · degradation avg 6131W · voltage_drop avg 6073W · phase_loss avg 534W | overload 8250 · spike 9750 · degradation 7875 · voltage_drop 6375 · phase_loss 375 (정격 7500W × factor) | ✅ HOLD 구간 ≈ 의도값, RAMP 평균 효과로 약간 낮음 |
| [2] 시나리오 voltage 값 | overload 355V · voltage_drop 338V · spike 380V · phase_loss 44V · degradation 380V | overload 353 · voltage_drop 334 · spike 380 · phase_loss 19 · degradation 380 | ✅ |
| [3] 채널별 정상 watt | ch9 7501W (정격 15000) · ch10/11 3750W (정격 7500) · ch15 400W (정격 1000) · ch16 1100W (정격 2200) · ch1 모터 평균 2677W | 분전반 0.5 × 정격 · 조명 0.4 × 정격 · 모터 시간 평균 ~0.36 × 정격 | ✅ 정확 |
| [4] 시간대별 곡선 (ch1 watt) | 0–7시 1125W · 8–11 4500W · 12 1126W (점심) · 13–17 5250W · 18 1125 · 19–21 2249 · 22–23 1125 | 0.15 / 0.6 / 0.15 / 0.7 / 0.15 / 0.3 / 0.15 (정격 7500 기준) | ✅ `base_load_ratio()` 분기 그대로 |
| [5] 시나리오 진입 비율 | overload 857 · voltage_drop 569 · phase_loss 281 · spike 272 · degradation 136 (ratio 6.3:4.2:2.0:2.1:1.0) | 가중치 [6:4:2:2:1] | ✅ |
| [6] streak 평균 길이 | overload 74 · voltage_drop 37 · phase_loss 36 · degradation 94 · spike 2 (모두 min=max, deterministic) | RAMP_UP+HOLD+RAMP_DOWN: 75 / 38 / 37 / 95 / 3 | ✅ ±1 boundary 차 (정상) |

추가 검증 — **자기상관성** (overload 첫 streak 시작):
```
2025-11-13 04:18:00  1174W  normal
2025-11-13 04:18:30  1132W  normal
2025-11-13 04:19:00  1199W  normal
2025-11-13 04:19:30  2438W  overload  ← RAMP_UP tick 1
2025-11-13 04:20:00  3974W  overload  ← tick 2
2025-11-13 04:20:30  5399W  overload  ← tick 3
2025-11-13 04:21:00  6607W  overload  ← tick 4
2025-11-13 04:21:30  8154W  overload  ← tick 5 (HOLD 진입)
2025-11-13 04:22:00  8554W  overload  ← HOLD
```
정상 → 5틱 점진 증가 → HOLD 진입. RAMP_UP 선형 보간이 `mix(normal, scenario, weight)` 의도대로 작동.

---

## 데이터 분포 한눈에

| 항목 | 수치 |
|---|---|
| 총 row 수 | 24,883,200 |
| 시간 범위 | 2025-11-13 ~ 2026-05-11 (180일) |
| 채널 균등성 | 모든 (channel × data_type) 조합 = 518,400 row |
| DB 사이즈 | 11GB (인덱스 6개 포함) |
| 정상 라벨 비율 | 79.7% (19,838,169 row) |
| 이상 라벨 비율 | 20.3% (5,045,031 row) |

**시나리오별 anomaly tick 비율** (가중치와 hold 시간의 곱셈 효과):

| 시나리오 | 비율 | 진입 횟수 | 평균 streak |
|---|---|---|---|
| overload | 11.91% | 857 | 74 |
| voltage_drop | 3.92% | 569 | 37 |
| degradation | 2.42% | 136 | 94 |
| phase_loss | 1.93% | 281 | 36 |
| spike | 0.11% | 272 | 2 |

*spike는 hold=1로 짧아 비율은 낮지만 진입 횟수는 가중치 비율과 부합.*

---

## 한계 (의도된)

다음은 본 audit에서 검증하지 않은 항목 — 다른 트랙·다음 sprint에서 다룸:

- **실제 환경 변동 패턴 반영 여부**: 더미는 합성이라 계절성·노후화·예상 외 부하 변동이 없음. "기간 길이 효과"는 더미로 검증 불가
- **시나리오 가중치의 현실 부합**: [6,4,2,2,1] 은 도메인 전문가 자료 부재 시 임의값. 운영 데이터 축적 후 보정 필요
- **multi=True 시나리오의 채널 간 상관성**: voltage_drop 은 16채널 동시 발생인데 본 audit는 ch1 단독 측정. 채널 간 상관 계수는 별도 검증 가능
- **노이즈 정규성**: `gauss_noise(stddev=0.05)` 가 진짜 정규분포인지 미측정. 이론상 OK

---

## 다음 단계

1. **T2-2 sanity check** — 25일/3개월/6개월 윈도우별 표본 수, value=NULL/-1 결측 비율 측정
2. **T2-3 IF 학습 3회** — `train_anomaly_model --since-days 25/90/180` 으로 모델 3개 학습 → 라벨된 anomaly 표본에 대해 precision/recall/f1 비교 → [if_window_comparison_2026_05_13.md](./if_window_comparison_2026_05_13.md) 작성

---

## 회귀 비교용 — 더미 변경 시 본 표 재측정 필요

`fastapi-server/dummies/power_dummy.py` 또는 `backfill_power_data.py` 의
`CHANNEL_RATED` / `SCENARIO_PATTERNS` / `base_load_ratio` / `MIXED_TRIGGER_PROBABILITY`
변경 시 다음 SQL 묶음을 재실행해서 본 문서의 표를 갱신한다 (스크립트 없음, ad-hoc 측정).

```bash
# row count + 시간 범위
sqlite3 db.sqlite3 "SELECT COUNT(*), MIN(measured_at), MAX(measured_at) FROM power_data;"

# 시나리오별 값 분포 (ch1 watt)
sqlite3 db.sqlite3 "SELECT anomaly_type, COUNT(*), ROUND(AVG(value), 1) FROM power_data WHERE channel=1 AND data_type='watt' AND is_anomaly=1 GROUP BY anomaly_type;"

# 시간대별 곡선
sqlite3 db.sqlite3 "SELECT CAST(strftime('%H', measured_at) AS INT), ROUND(AVG(value), 0) FROM power_data WHERE channel=1 AND data_type='watt' AND is_anomaly=0 GROUP BY 1 ORDER BY 1;"
```
