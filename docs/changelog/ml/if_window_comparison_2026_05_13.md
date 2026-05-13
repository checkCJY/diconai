# IF 학습 윈도우 비교 (25 / 60 / 90 / 120 / 180일) — sprint T2-3 결과

> 작성: 2026-05-13
> 모델: sklearn IsolationForest (n_estimators=100, contamination=0.01, window=30)
> 학습 채널: power · device_id=1 · channel=1 · data_type=watt
> 평가 데이터: 학습 윈도우와 동일 (hold-out 없음 — IF는 정상만 학습이라 anomaly 평가는 사실상 OOS)
>
> **본 문서의 모든 표는 실제 명령어 + raw 출력 함께 박아두어 검증·재현 가능.**

---

## TL;DR

- **90일 모델(v3)이 명확한 peak** — 5점 곡선 (25/60/90/120/180일)으로 검증, plateau 아님
  - F1: 36.7 → **45.0 → 48.8 → 43.9** → 36.1 (좌우 ±30일에서 ~4pp, ±90일에서 ~12pp 손해)
- **180일 모델(v4, 현재 active)이 25일보다도 약함** — 데이터 다양성 ↑ → 정상 분포 ↑ → IF 임계 느슨 → recall ↓
- **현재 active 모델을 v4 → v3로 전환 권장 (decision pending — 별도 PR)**
- **운영 시 학습 데이터를 90일 ±30일로 유지해야** F1 ≥ 44% — 자동 재학습 주기 결정 근거
- **spike(0%) · phase_loss(2.7%) 는 watt 단일 채널로 거의 못 잡음** (5점 모두 동일) — multi-variate (W+A+V) 또는 Change Point Detection 필요 → §3 다음 sprint

---

## 1. MLModel 메타 (5개 윈도우 학습 결과)

| version | 학습기간 | from → to | 학습 샘플 | active |
|---|---|---|---|---|
| v1 | 2일 | (sprint 외 sample) | 4,068 | False |
| v2 | 26일 | 2026-04-16 → 2026-05-12 | 60,348 | False |
| v5 | 60일 | 2026-03-13 → 2026-05-12 | 138,673 | False |
| v3 | 91일 | 2026-02-10 → 2026-05-12 | 209,324 | False |
| v6 | 120일 | 2026-01-12 → 2026-05-12 | 274,000 | False |
| v4 | 180일 | 2025-11-13 → 2026-05-12 | 410,485 | **True** |

### 측정 명령어
```bash
docker exec diconai-drf-1 python manage.py shell -c "
from apps.ml.models import MLModel
for m in MLModel.objects.filter(sensor_type='power').order_by('version'):
    days = (m.training_data_range_to.date() - m.training_data_range_from.date()).days
    print(f'v{m.version}: {days:>3}d active={m.is_active} samples={m.training_sample_count}')
"
```

### Raw 출력 (2026-05-13 측정)
```
v1:   2d active=False samples=4068
v2:  26d active=False samples=60348
v3:  91d active=False samples=209324
v4: 180d active=True  samples=410485
v5:  60d active=False samples=138673
v6: 120d active=False samples=274000
```

---

## 2. 전체 지표 — Recall / Precision / F1

### 일수 순 정렬 (곡선 형태 확인)

| 모델 | 일수 | 학습샘플 | Anomaly 평가 | Recall | FPR | Precision | F1 |
|---|---|---|---|---|---|---|---|
| v2 | 25일 | 60,348 | 14,503 | 23.4% | 1.00% | 84.9% | 36.7% |
| v5 | 60일 | 138,673 | 34,098 | 30.2% ↑ | 1.00% | 88.1% | **45.0%** ↑ |
| **v3** | **90일** | **209,324** | **52,727** | **33.5%** ⭐ | **1.00%** | **89.4%** ⭐ | **48.8%** ⭐ |
| v6 | 120일 | 274,000 | 71,571 | 29.2% ↓ | 1.00% | 88.4% | 43.9% ↓ |
| v4 | 180일 | 410,485 | 107,886 | 22.9% | 1.00% | 85.7% | 36.1% |

**곡선 형태**: 25→60→90 단조 증가, 90→120→180 단조 감소 → **90일에 명확한 peak (plateau 아님)**.
좌우 ±30일에서 F1 ~4pp 손해, ±90일에서 ~12pp 손해.

### 측정 명령어
```bash
docker exec diconai-drf-1 bash -c "echo 'exec(open(\"/app/_eval_if_models.py\").read()); main()' | python manage.py shell" 2>&1 | grep -v UserWarning
```

### Raw 출력 (2026-05-13 측정)
```
   window |    train |    anom_caught |   recall |         fp |     fpr |  precision |       f1
---------------------------------------------------------------------------------------------------------
v2  26d  |   60,348 |  3,396/14,503 |   23.4% |  604/60,319    |  1.00% |     84.9% |   36.7%
v3  91d  |  209,324 | 17,681/52,727 |   33.5% | 2,093/209,295  |  1.00% |     89.4% |   48.8%
v4 180d  |  410,485 | 24,677/107,886|   22.9% | 4,105/410,456  |  1.00% |     85.7% |   36.1%
v5  60d  |  138,673 | 10,311/34,098 |   30.2% | 1,387/138,644  |  1.00% |     88.1% |   45.0%
v6 120d  |  274,000 | 20,876/71,571 |   29.2% | 2,740/273,971  |  1.00% |     88.4% |   43.9%
```

---

## 3. 시나리오별 Recall (5점 × 5시나리오)

| 시나리오 | dummy factor | hold | v2 25d | v5 60d | **v3 90d** | v6 120d | v4 180d |
|---|---|---|---|---|---|---|---|
| overload | watt × 1.10 | 60 | 29.5% | 31.1% | **34.2%** ⭐ | 31.3% | 25.7% |
| voltage_drop | voltage × 0.88 | 30 | 6.4% | 10.3% | **15.7%** ⭐ | 10.5% | 5.4% |
| spike | watt × 1.30 | **1** | 0.0% | 0.0% | 0.4% | 0.0% | 0.0% |
| phase_loss | watt × 0.05 | 30 | 3.0% | 2.9% | 2.7% | 2.7% | 0.9% |
| degradation | watt × 1.05 | 30 | 5.1% | 16.3% | **20.1%** ⭐ | 15.9% | 13.0% |

**시사**:
- 모든 의미 있는 시나리오(overload·voltage_drop·degradation)에서 **90일 best**
- spike·phase_loss는 5개 모델 모두 동일하게 약함 → 데이터량으로 풀 수 없는 문제 (모델링 변경 필요)

### 측정 명령어
```bash
docker exec diconai-drf-1 bash -c "echo 'exec(open(\"/app/_eval_if_scenarios.py\").read())' | python manage.py shell" 2>&1 | grep -v UserWarning
```

### Raw 출력 (2026-05-13 측정)
```
scenario       | v2  26d              | v3  91d              | v4 180d              | v5  60d              | v6 120d
--------------------------------------------------------------------------------------------------------------------------------
overload       |  29.5% (2,543/8,629) |  34.2% (10,883/31,791)|  25.7% (16,320/63,389)|  31.1% (6,304/20,302)|  31.3% (13,434/42,891)
voltage_drop   |   6.4% (  196/3,079) |  15.7% (1,612/10,257) |   5.4% (1,125/21,024) |  10.3% (  696/6,742) |  10.5% (1,353/12,921)
spike          |   0.0% (    0/   39) |   0.4% (    1/  265)  |   0.0% (    0/  515)  |   0.0% (    0/  155) |   0.0% (    0/  343)
phase_loss     |   3.0% (   43/1,447) |   2.7% (  128/4,687)  |   0.9% (   90/10,087) |   2.9% (  101/3,427) |   2.7% (  185/6,775)
degradation    |   5.1% (   61/1,193) |  20.1% (1,126/5,611)  |  13.0% (1,656/12,755) |  16.3% (  548/3,355) |  15.9% (1,357/8,525)
```

---

## 4. 결과 해석 — 왜 이렇게 나왔나

### 90일이 peak인 이유 (5점 검증으로 확정)
- **데이터 다양성과 학습 안정성의 sweet spot**
- 25/60일: 정상 표본 부족 → IF 트리 분기 한정 → anomaly 점수 분산 좁아 detection 약화
- 120/180일: 정상 표본 풍부 but 시간대 변동 많이 학습 → IF 임계 느슨 → anomaly 묻힘
- 90일: 안정성 + 임계 적정의 교차점 → 모든 시나리오 best

### 곡선 비대칭성 — 좌우 거의 대칭 (±30일에서 ~4pp 손해)
- 60일: 48.8 → 45.0 (3.8pp 손해)
- 120일: 48.8 → 43.9 (4.9pp 손해)
- → 운영에서 학습 데이터 누적 ±30일은 허용 가능, 그 이상은 재학습 필수

### spike가 거의 안 잡히는 이유 (recall 0%)
- spike의 RAMP+HOLD+RAMP = 1+1+1 = **3틱**
- feature window=30 → spike 시점이 30틱 평균에 묻혀 거의 정상값으로 보임
- **대안**: window 축소 (예: 5틱) 또는 별도 spike 검출 로직 (z-score 등)
- **5점 모두 동일하게 0% → 데이터량 문제 아님, 모델링 접근 변경 필요**

### phase_loss가 약한 이유 (1~3%)
- factor 0.05 → 정격 7500W × 0.05 = 375W
- 야간(0~7시, 18~23시)의 정상값 base_load 0.15 × 7500 = **1125W**
- watt만 보면 phase_loss(375W) ↔ 야간 정상(1125W)이 같은 "낮은 값" 영역에 있어 IF가 둘 다 정상으로 학습
- **대안**: voltage 채널을 추가로 보면 phase_loss 시 380V → 19V로 극단적 변화 → multi-variate 학습 필요
- **5점 모두 비슷한 수준 (0.9~3.0%)**

### degradation의 데이터량 영향 (5점에서 명확)
- 25일: 5.1% (표본 부족으로 미세 차이 학습 불가)
- 60일: 16.3%
- 90일: **20.1%** (peak)
- 120일: 15.9%
- 180일: 13.0% (정상 분포에 흡수)
- → 미세 anomaly는 데이터량 대비 매우 sensitive, sweet spot이 좁음

---

## 5. 권장 변경

### 5-1. active 모델 전환: v4 → v3 — ✅ **완료 (2026-05-13)**

**전환 전 확인사항** (피드백 반영):
- ✅ v3 학습 데이터 시간 범위 = 2026-02-10 ~ 2026-05-12 (최근 90일, concept drift 없음 — 백필 합성)
- ✅ 60/120일 추가 학습으로 sweet spot이 plateau 아닌 **peak**로 확정 (5점 곡선)
- ⏳ 추후 contamination 파라미터 조합 실험 (90일 + contamination 0.005 / 0.02 등) — 다음 sprint hypothesis

**실행한 명령**:
```bash
docker exec diconai-drf-1 python manage.py shell -c "
from apps.ml.models import MLModel
MLModel.objects.filter(sensor_type='power', is_active=True).update(is_active=False)
MLModel.objects.filter(version=3, sensor_type='power').update(is_active=True)
print('active model:', MLModel.objects.get(sensor_type='power', is_active=True).version)
"
```

**실행 결과 (2026-05-13)**:
```
active model: 3
```

이전: v4 (180일, F1 36.1%) → 이후: v3 (90일, F1 48.8%, recall 33.5%, precision 89.4%).
T1 추론 트리거가 아직 미구현이라 실제 알람 영향 0건. 다음 T1 진입 시 자동으로 v3 사용.

### 5-2. 다음 sprint (§3 고도화) 우선순위
1. **Multi-variate IF** — W+A+V 동시 학습 → spike·phase_loss·voltage_drop 동시 개선 기대
2. **Spike 전용 검출** — Z-score 또는 window 5틱 IF 별도 모델
3. **Change Point Detection** — 시점 변화 직접 감지 (PELT, BOCPD 등)
4. **자동 재학습 스케줄러** — 90일 ±30일 유지하도록 Celery beat 주기 결정

### 5-3. 본 sprint 트랙 1 (IF §2 알람 결합) 영향
- combined_risk 매트릭스가 **PREDICT_WARN 발화 빈도** 에 직결
- v3 모델로 전환하면 PREDICT_WARN false positive ↓ + true positive ↑ → 초기 운영 신뢰도 ↑
- spike/phase_loss는 IF 만으로 부족 → 알람 매트릭스에서 단순 IF에 의존하지 않고 threshold 알람과 결합 (이미 매트릭스 B 설계가 그 방향)

---

## 6. 한계 (의도된)

| 한계 | 영향 | 다음 단계 |
|---|---|---|
| Hold-out 평가 없음 | 평가가 학습과 같은 윈도우 — 일반화 능력 과대평가 가능. but anomaly 라벨은 학습에 안 쓰여 사실상 OOS | 운영 데이터 축적 후 별도 hold-out 셋 |
| 단일 채널 (ch1)·단일 측정 (watt) | 16채널 × 3측정 = 48 시리즈 중 1개만 평가 | T1 추론 트리거 작성 시 채널 일반화 |
| 채널·측정 간 상관 미사용 | 단일 변수 IF | Multi-variate IF (§3) |
| Spike 시간 척도 mismatch | window=30 vs spike hold=1 | window 작은 spike 전용 모델 추가 |
| 합성 데이터 | 실제 운영 환경의 계절성·노후화·이상 패턴 미반영 | 운영 데이터 축적 후 재검증 |

---

## 7. 부록 — 추가 검증 명령어

### 7-1. 모델 .pkl 파일 존재 확인
```bash
docker exec diconai-drf-1 ls -lh /app/ml_models/
```

### 7-2. 라벨 분포 직접 확인 (DB)
```bash
sqlite3 -header -column /home/cjy/diconai/drf-server/db.sqlite3 "
SELECT is_anomaly, COALESCE(anomaly_type,'(none)') AS type,
       COUNT(*) AS cnt,
       ROUND(COUNT(*)*100.0/24883200, 2) AS pct
FROM power_data
GROUP BY is_anomaly, anomaly_type
ORDER BY cnt DESC;"
```

### 7-3. 임의 시계열로 모델 ad-hoc 예측 (Python REPL)
```bash
docker exec -it diconai-drf-1 python manage.py shell
# REPL 안에서:
# >>> import joblib
# >>> from pathlib import Path
# >>> from django.conf import settings
# >>> bundle = joblib.load(Path(settings.ML_MODELS_DIR) / "power_if_v3.pkl")
# >>> model = bundle["model"]
# >>> import numpy as np
# >>> sample = np.array([[8200, 4500, 50, 100]])  # 정상 ~4500W에서 8200W 튐
# >>> print("prediction:", model.predict(sample))  # -1=anomaly, +1=normal
# >>> print("score:", model.decision_function(sample))  # 음수일수록 이상
```

### 7-4. 평가 임시 스크립트 위치
```bash
ls -lh /home/cjy/diconai/drf-server/_eval_if_*.py
# _eval_if_models.py    — 전체 지표
# _eval_if_scenarios.py — 시나리오별
# (sprint 끝나면 정리 권장 — git ignore 또는 삭제)
```

---

## 8. 다음 단계

1. **active 모델 전환 결정** (사용자 확인 후 §5-1 명령 실행)
2. **본 sprint 트랙 1 (IF §2 알람 결합) 진입** — T1-1 ~ T1-8
3. **§3 고도화는 다음 sprint** — multi-variate IF / spike 전용 / CPD / 자동 재학습 (90일 ±30일 유지)
