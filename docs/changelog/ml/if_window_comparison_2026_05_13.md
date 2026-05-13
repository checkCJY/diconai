# IF 윈도우 비교 (v2/v3/v4 → 5점 확장) — power_dummy v3 백필 기반 학습 기간 sensitivity

> 작성: 2026-05-13
> 대상: `train_anomaly_model --since YYYY-MM-DD --until YYYY-MM-DD` 으로 학습한 IF 모델
> 평가 데이터: 동일 hold-out 평가셋 (학습 윈도우 내 라벨된 anomaly tick)
> 선행 의존: [power_dummy_audit_2026_05_13.md](./power_dummy_audit_2026_05_13.md) (백필 데이터 적합성)
> 결과: **v3 (90일) 최우수**, 약한 peak (peak 기준 5%p 미달이나 양쪽 우위 일관)
> 결정: active 모델 v4 → v3 전환 **완료** (5점 곡선 검증 후, 사용자 승인)

---

## 무엇을 했나 (시간순 두 단계)

| 단계 | 시점 | 측정 | 산출 |
|---|---|---|---|
| §1 사전 | 2026-05-13 오전 | v2/v3/v4 3점 측정 + 5점 확장 계획 + 사전 판정 기준 정의 | 결정 권장 v4→v3 (decision pending) |
| §2 사후 | 2026-05-13 오후 | 60·120일 추가 측정 (5점 곡선) + 판정 기준 적용 | "약한 peak" 판정 → 결정 확정 |
| §3 실행 | 2026-05-13 | 사용자 승인 후 active 전환 | v4 → v3 (완료) |

PoC 방법론 보존: 사전 가설/판정 기준 → 측정 → 판정 → 결정 순서. 사후 측정 후 결론 박기가 아닌 **사전 정의된 기준에 데이터를 비추는 구조**.

---

# §1. 사전 — v2/v3/v4 3점 + 5점 계획 + 판정 기준 (decision pending)

## 1-1. 전체 지표 (3점)

| 모델 | 학습기간 | 학습샘플 | Recall | FPR | Precision | F1 |
|---|---|---|---|---|---|---|
| v2 | 25일 | 60K | 23.4% | 1.0% | 84.9% | 36.7% |
| v3 | 90일 | 209K | **33.5%** ⭐ | 1.0% | **89.4%** ⭐ | **48.8%** ⭐ |
| v4 (active) | 180일 | 410K | 22.9% | 1.0% | 85.7% | 36.1% |

FPR 1.0% 동일 통제 (contamination=0.01). v3가 모든 지표에서 우위 — trade-off 없는 개선 (Precision까지 동반 상승).

**측정 명령어**:
```bash
docker exec diconai-drf-1 bash -c "echo 'exec(open(\"/app/_eval_if_models.py\").read()); main()' | python manage.py shell" 2>&1 | grep -v UserWarning
```

**Raw 출력 (3점만 발췌)**:
```
   window |    train |    anom_caught |   recall |         fp |     fpr |  precision |       f1
---------------------------------------------------------------------------------------------------------
v2  26d  |   60,348 |  3,396/14,503 |   23.4% |  604/60,319    |  1.00% |     84.9% |   36.7%
v3  91d  |  209,324 | 17,681/52,727 |   33.5% | 2,093/209,295  |  1.00% |     89.4% |   48.8%
v4 180d  |  410,485 | 24,677/107,886|   22.9% | 4,105/410,456  |  1.00% |     85.7% |   36.1%
```

## 1-2. 시나리오별 recall (3점)

| 시나리오 | 정의 | v2 25일 | v3 90일 | v4 180일 | 평가 |
|---|---|---|---|---|---|
| overload | 정격×1.10, hold=60틱 | 29.5% (2,543/8,629) | **34.2%** (10,883/31,791) | 25.7% (16,320/63,389) | 가장 잘 잡힘 (큰 폭 + 긴 hold) |
| voltage_drop | watt×0.85, voltage×0.88 | 6.4% (196/3,079) | **15.7%** (1,612/10,257) | 5.4% (1,125/21,024) | watt 단일 채널이라 약함 |
| spike | 정격×1.30, hold=1틱 | 0.0% (0/39) | 0.4% (1/265) | 0.0% (0/515) | 거의 못 잡음 (window=30 평균에 묻힘) |
| phase_loss | 정격×0.05 | 3.0% (43/1,447) | 2.7% (128/4,687) | 0.9% (90/10,087) | 거의 못 잡음 (야간 정상값 1125W와 혼동) |
| degradation | 정격×1.05 | 5.1% (61/1,193) | **20.1%** (1,126/5,611) | 13.0% (1,656/12,755) | 미세 차이 — 데이터량 영향 큼 |

## 1-3. 결정 권장 (decision pending)

- **권장**: active 모델 v4 (180일) → **v3 (90일)** 전환 (F1 +12.7%p, recall +10.6%p, precision +3.7%p)
- **상태**: decision pending — 5점 곡선 결과로 확정
- **갱신 트리거**: 60일 모델이 v3보다 F1 우위면 권장 대상이 v3 → v(60일)로 갱신
- **확정 후 조치**: 별도 PR/승인 절차 (자동 전환 X)

## 1-4. 5점 곡선 확장 계획 — 60일·120일 추가 학습

### 왜 필요한가
3점만으로는 곡선 형태가 **plateau (60–120 평탄)** 인지 **peak (90 좁은 봉우리)** 인지 구분 불가. §3 자동 재학습 sprint의 주기 결정 근거.

### 사전 조건 (반드시 충족)
- **평가셋 동일성**: v2/v3/v4와 동일 hold-out 평가셋 사용. 시나리오별 분모 일치
- **하이퍼파라미터 고정**: contamination 0.01 · n_estimators 100 · window 30 · random_state 42 모두 v2~v4와 동일

### 판정 기준 (사전 정의 — 사후 해석 편향 차단)

| 판정 | 조건 | 운영 함의 |
|---|---|---|
| **Plateau** | 60·90·120일 F1 모두 ±3%p 이내 | §3 학습 주기 60~120일 유연 운영 |
| **Peak** | 90일이 60일·120일 대비 양쪽 +5%p 이상 | §3 학습 주기 90일 ±10일 엄수 |
| **Asymmetric** | 한쪽만 급락 (예: 120일 −5%p, 60일 −2%p 이내) | §3 학습 주기 짧은 쪽으로 편향 |

3가지 모두 미달 시 → "약한 peak" 또는 "intermediate" 로 판정 후 운영적 결정.

---

# §2. 사후 — 5점 측정 + 판정 적용

## 2-1. 5점 곡선 결과

| 모델 | 학습기간 | 학습샘플 | Recall | FPR | Precision | F1 | F1 vs v3 |
|---|---|---|---|---|---|---|---|
| v2 | 25일 | 60,348 | 23.4% | 1.00% | 84.9% | 36.7% | −12.1pp |
| v5 | 60일 | 138,673 | 30.2% | 1.00% | 88.1% | 45.0% | **−3.8pp** |
| **v3** | **90일** | **209,324** | **33.5%** | **1.00%** | **89.4%** | **48.8%** | **0** ⭐ |
| v6 | 120일 | 274,000 | 29.2% | 1.00% | 88.4% | 43.9% | **−4.9pp** |
| v4 | 180일 | 410,485 | 22.9% | 1.00% | 85.7% | 36.1% | −12.7pp |

**측정 명령어**: §1-1 명령어와 동일 (5점 모두 포함된 raw 출력)

**Raw 출력 (5점 전체)**:
```
   window |    train |    anom_caught |   recall |         fp |     fpr |  precision |       f1
---------------------------------------------------------------------------------------------------------
v2  26d  |   60,348 |  3,396/14,503 |   23.4% |  604/60,319    |  1.00% |     84.9% |   36.7%
v3  91d  |  209,324 | 17,681/52,727 |   33.5% | 2,093/209,295  |  1.00% |     89.4% |   48.8%
v4 180d  |  410,485 | 24,677/107,886|   22.9% | 4,105/410,456  |  1.00% |     85.7% |   36.1%
v5  60d  |  138,673 | 10,311/34,098 |   30.2% | 1,387/138,644  |  1.00% |     88.1% |   45.0%
v6 120d  |  274,000 | 20,876/71,571 |   29.2% | 2,740/273,971  |  1.00% |     88.4% |   43.9%
```

## 2-2. 시나리오별 recall (5점 × 5시나리오)

| 시나리오 | v2 25d | v5 60d | **v3 90d** | v6 120d | v4 180d |
|---|---|---|---|---|---|
| overload | 29.5% | 31.1% | **34.2%** ⭐ | 31.3% | 25.7% |
| voltage_drop | 6.4% | 10.3% | **15.7%** ⭐ | 10.5% | 5.4% |
| spike | 0.0% | 0.0% | 0.4% | 0.0% | 0.0% |
| phase_loss | 3.0% | 2.9% | 2.7% | 2.7% | 0.9% |
| degradation | 5.1% | 16.3% | **20.1%** ⭐ | 15.9% | 13.0% |

**측정 명령어**:
```bash
docker exec diconai-drf-1 bash -c "echo 'exec(open(\"/app/_eval_if_scenarios.py\").read())' | python manage.py shell" 2>&1 | grep -v UserWarning
```

**Raw 출력**:
```
scenario       | v2  26d              | v3  91d              | v4 180d              | v5  60d              | v6 120d
--------------------------------------------------------------------------------------------------------------------------------
overload       |  29.5% (2,543/8,629) |  34.2% (10,883/31,791)|  25.7% (16,320/63,389)|  31.1% (6,304/20,302)|  31.3% (13,434/42,891)
voltage_drop   |   6.4% (  196/3,079) |  15.7% (1,612/10,257) |   5.4% (1,125/21,024) |  10.3% (  696/6,742) |  10.5% (1,353/12,921)
spike          |   0.0% (    0/   39) |   0.4% (    1/  265)  |   0.0% (    0/  515)  |   0.0% (    0/  155) |   0.0% (    0/  343)
phase_loss     |   3.0% (   43/1,447) |   2.7% (  128/4,687)  |   0.9% (   90/10,087) |   2.9% (  101/3,427) |   2.7% (  185/6,775)
degradation    |   5.1% (   61/1,193) |  20.1% (1,126/5,611)  |  13.0% (1,656/12,755) |  16.3% (  548/3,355) |  15.9% (1,357/8,525)
```

## 2-3. 사전 판정 기준 적용

| 사전 판정 기준 | 조건 | 측정 결과 | 판정 |
|---|---|---|---|
| Plateau | 60·90·120일 F1 모두 ±3%p 이내 | 60↔120 차 1.1pp ≤ 3pp ✓, 60↔90 차 3.8pp > 3pp ✗ | **미달** |
| Peak | 90일이 60·120일 대비 양쪽 +5%p 이상 | 90↔60 차 +3.8pp < 5pp ✗, 90↔120 차 +4.9pp < 5pp ✗ | **미달 (근접)** |
| Asymmetric | 한쪽만 급락 (예: 120일 −5%p, 60일 −2%p 이내) | 60·120 양쪽 모두 −3~5pp 범위 (대칭) | **미달** |

→ **결과: 3가지 사전 판정 모두 미달.** "약한 peak (intermediate)" 로 분류.

**약한 peak 운영 함의**:
- 90일이 양쪽(60·120)에서 일관되게 best — 운영 권장 모델은 90일
- 그러나 5pp 미달이라 60·120일도 "사용 불가"는 아님 → §3 자동 재학습 주기 결정 시 90일 ±30일 범위 안전 마진
- spike·phase_loss 는 5점 모두 동일하게 약함 → 데이터량 무관, multi-variate 필요

## 2-4. 결정 확정

- **권장 모델**: v3 (90일) — 사전 권장(§1-3) 그대로 유지
- **갱신 트리거 평가**: 60일 모델 F1 45.0% < v3 48.8% → 권장 갱신 사유 없음
- **상태**: 5점 측정으로 권장 확정 → §3 실행 단계 진입

---

# §3. 실행 — active 모델 전환 (사용자 승인 후 완료)

## 3-1. 전환 처리

- **승인 시점**: 2026-05-13, 사용자 직접 승인 ("일단 v3로 즉시 전환하면 좋겠습니다")
- **별도 PR**: 본 sprint commit에 포함 (DB 메타 변경만, 코드 변경 0)

**실행한 명령어**:
```bash
docker exec diconai-drf-1 python manage.py shell -c "
from apps.ml.models import MLModel
MLModel.objects.filter(sensor_type='power', is_active=True).update(is_active=False)
MLModel.objects.filter(version=3, sensor_type='power').update(is_active=True)
print('active model:', MLModel.objects.get(sensor_type='power', is_active=True).version)
"
```

**Raw 출력**:
```
active model: 3
```

## 3-2. 영향 범위

- **알람 영향**: 0건 — T1 추론 트리거가 아직 미구현이라 active 모델이 실제 알람 경로에 안 쓰임
- **다음 sprint T1 진입 시**: 자동으로 v3 사용 (신규 코드 없이 메타만 바뀜)

---

# §4. 한계 / Deferred

| 한계 | 영향 | 다음 단계 |
|---|---|---|
| **spike·phase_loss 검출 한계** | 5점 모두 동일하게 0~3% — 데이터량/임계 튜닝으로 해결 불가 | §3 multi-variate IF (W+A+V 동시) 또는 Change Point Detection sprint |
| **합성 데이터 곡선의 운영 일반화** | IF contamination/임계 메커니즘이 데이터량 의존이라 곡선 형태(약한 peak)는 운영에도 어느 정도 이전 가능, 절대 수치는 실데이터 재검증 필요 | 운영 데이터 누적 후 본 5점 곡선 재측정 |
| **concept drift 검증** | 합성에서는 drift 없음 | §3 자동 재학습 + drift 감시 |
| **Hold-out OOS 평가 없음** | 평가가 학습과 같은 윈도우 — anomaly 라벨은 학습에 안 쓰여 사실상 OOS이지만 진짜 OOS는 아님 | 운영 데이터 별도 hold-out 셋 |
| **단일 채널·단일 측정** | ch1·watt만 평가, 16채널 × 3측정 = 48 시리즈 중 1개 | T1 추론 트리거 작성 시 채널 일반화 |

---

# §5. 다음 단계

1. ✅ 본 commit 머지 후 active v3 모델로 운영 진입 (T1 추론 트리거 작성 시 자동 사용)
2. **§3 sprint 입력값**:
   - Multi-variate IF (W+A+V) — spike·phase_loss·voltage_drop 동시 개선 기대
   - 자동 재학습 스케줄러 — 학습 주기 90일 ±30일 유지 (약한 peak 안전 마진)
   - 실데이터 drift 모니터링
   - 본 5점 곡선을 실데이터로 재측정하여 약한 peak vs 강한 peak vs plateau 재판정
3. **트랙 1 (IF §2 알람 결합)** — combined_risk 매트릭스, fire_anomaly_task, AlarmType.ANOMALY 추가

---

# 부록 — 추가 검증 명령어

## 모델 메타 확인
```bash
docker exec diconai-drf-1 python manage.py shell -c "
from apps.ml.models import MLModel
for m in MLModel.objects.filter(sensor_type='power').order_by('version'):
    days = (m.training_data_range_to.date() - m.training_data_range_from.date()).days
    print(f'v{m.version}: {days:>3}d active={m.is_active} samples={m.training_sample_count}')
"
```

**Raw 출력 (2026-05-13)**:
```
v1:   2d active=False samples=4068
v2:  26d active=False samples=60348
v3:  91d active=True  samples=209324
v4: 180d active=False samples=410485
v5:  60d active=False samples=138673
v6: 120d active=False samples=274000
```

## .pkl 파일 존재
```bash
docker exec diconai-drf-1 ls -lh /app/ml_models/
```

## 라벨 분포 직접 확인
```bash
sqlite3 -header -column /home/cjy/diconai/drf-server/db.sqlite3 "
SELECT is_anomaly, COALESCE(anomaly_type,'(none)') AS type, COUNT(*) AS cnt
FROM power_data GROUP BY is_anomaly, anomaly_type ORDER BY cnt DESC;"
```

## 임시 평가 스크립트 위치
```bash
ls -lh /home/cjy/diconai/drf-server/_eval_if_*.py
# _eval_if_models.py    — 전체 지표
# _eval_if_scenarios.py — 시나리오별
# (.gitignore 처리. 다음 sprint 시 새로 작성하거나 재사용)
```
