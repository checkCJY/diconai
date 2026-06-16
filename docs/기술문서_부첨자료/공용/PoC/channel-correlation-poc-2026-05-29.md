# 전력 16채널 watt 시계열 상관성 1차 PoC (2026-05-29)

> **목적:** 강사 multivariate IF 제안 (Panel-multivariate IF + SHAP 채택 변경) 의 도메인 적합성 1차 baseline 확보. **D+30~D+90 sprint #4 (채널 상관성 측정) 의 시연 전 더미 baseline** — D+30 운영 데이터 재측정과의 비교 기준선 확보가 본 PoC 의 본질.
>
> **결론 (관찰 한정):** 더미 데이터에서 동질군 cluster **후보** 가 관찰됨 (motor ch1/3/8/13, panel ch11/16). Null baseline (셔플 DTW) 대비 실측 평균 0.69배 — 무작위보다 닮은 신호는 측정됨. 단, 이 cluster 가 **더미 생성 함수의 카테고리 분류를 더미 분석에서 재발견한 tautology 인지 진짜 도메인 신호인지 본 PoC 로 분리 불가**. Architecture (16ch 일괄 vs cluster 단위 vs 채널별) 의사결정은 D+30 운영 데이터 재측정 + 3 architecture 학습 F1 비교 후.

---

## 1. 측정 배경

- **강사 지적 (2026-05-29):** "디바이스 기준으로 묶어서 multivariate IF 로 이상탐지하는 게 표준" — 현 단변량 4채널 구조에 대한 외부 검증 요청.
- **plan 위치:** [skill/study/power-ai-트레이드오프-2026-05-21.md §3.3](power-ai-트레이드오프-2026-05-21.md) D+30~D+90 sprint #4 "★ 채널 간 상관성 측정 (Pearson / DTW / time-lagged corr)" — 원래 운영 데이터 누적 후 진행 예정.
- **시연 전 진행 결정 (D-17):** ① Pearson/DTW + null baseline 만 PoC. ② Panel IF + SHAP 채택 변경 + 3 architecture F1 비교는 D+30 plan 그대로 유지. 시연 운영 코드 영향 0.

---

## 2. 측정 방법

| 항목 | 값 |
|---|---|
| 데이터 범위 | 2026-05-22 ~ 2026-05-28 (6일치) |
| 디바이스 | PowerDevice pk=1 (`63200c3afd12`) — **단일 디바이스 (N=1)** |
| 측정 종류 | `watt` 만 (current/voltage 는 PoC 범위 외) |
| 총 row | 1,123,920 → wide-format 9,853 timestamp × 16 channel |
| Pearson | 전체 데이터 16×16 (`pandas.corr`) |
| DTW | 1,000 다운샘플 (10배 축소) + Z-score 정규화 후 numpy 직접 구현 |
| **Null baseline** | **각 채널 독립 셔플 (seed=42) × 5회 평균 DTW** — "강한 cluster" 의 비교 기준선 |
| 채널 카테고리 | dummy 합성 분류 (`fastapi-server/dummies/power_dummy.py`) — motor {1~8, 12~14} / lighting {15} / panel {9~11, 16} |
| 실행 명령 | `python manage.py measure_channel_correlation --since 2026-05-22 --until 2026-05-28 --dtw-samples 1000` |
| 코드 위치 | [drf-server/apps/ml/management/commands/measure_channel_correlation.py](../../drf-server/apps/ml/management/commands/measure_channel_correlation.py) |

---

## 3. 결과

### 3.1 Null baseline vs 실측 DTW (전체 평균)

| 항목 | 값 | 의미 |
|---|---|---|
| **Null baseline** (셔플 5회) | **0.2655 ± 0.0006** | 시간 순서 파괴 시 평균 DTW. 분산 매우 작음 (안정) |
| **실측 DTW** (raw 16채널 평균) | **0.1841** | |
| **비율 (실측/null)** | **0.693** | < 1 = 셔플보다 닮음 = 무작위 대비 의미있는 신호 존재 |

> **해석:** 실측 평균이 null baseline 의 약 69% — 16채널 전체 평균이 무작위 셔플보다 명확히 닮음. 단 "얼마나 닮으면 강한 cluster 인지" 의 절대 기준은 여전히 모름 (운영 데이터 비교 후 판단).

### 3.2 카테고리별 평균 (null baseline 대비)

| 카테고리 쌍 | Pearson r | DTW d | null 대비 비율 | 해석 |
|---|---|---|---|---|
| panel-panel | +0.455 | **0.1157** | **0.436** | null 의 44% — 가장 닮음 |
| motor-motor | +0.416 | **0.1456** | **0.549** | null 의 55% — 두번째 닮음 |
| lighting-panel | +0.499 | 0.1823 | 0.687 | lighting n=1 통계 의미 약함 |
| lighting-motor | +0.491 | 0.1857 | 0.700 | 동일 |
| **motor-panel** | +0.337 | **0.2413** | **0.909** | **null 의 91% — 거의 무작위 수준 = 카테고리 간 분리 명확** |

> **null baseline 의 기여:** "0.05 = 강함, 0.24 = 멀다" 의 직관적 표현 대신 **"motor-panel 거리가 null 의 91% = 셔플과 거의 같다"** 가 정확. tautology 우려 (#1) 에 대한 일부 답변 — 더미 안에서도 카테고리 간엔 셔플 수준 무관함이 측정됨.

### 3.3 Top-5 닮은 채널쌍

**Pearson 절대값 top-5:**

| # | 채널쌍 | 카테고리 | r |
|---|---|---|---|
| 1 | ch8 ↔ ch13 | motor-motor | +0.928 |
| 2 | ch1 ↔ ch8 | motor-motor | +0.895 |
| 3 | ch3 ↔ ch8 | motor-motor | +0.878 |
| 4 | **ch9 ↔ ch15** | **panel-lighting** | **+0.877** ⚠ |
| 5 | ch3 ↔ ch13 | motor-motor | +0.836 |

**DTW 거리 짧은 top-5:**

| # | 채널쌍 | 카테고리 | d |
|---|---|---|---|
| 1 | ch3 ↔ ch13 | motor-motor | 0.0321 |
| 2 | ch8 ↔ ch13 | motor-motor | 0.0390 |
| 3 | ch1 ↔ ch13 | motor-motor | 0.0424 |
| 4 | **ch11 ↔ ch16** | **panel-panel** | 0.0455 |
| 5 | ch1 ↔ ch3 | motor-motor | 0.0461 |

> **관찰된 cluster 후보 (가설):** 모터 hub = ch1/3/8/13, 패널 pair = ch11/16. Pearson·DTW 둘 다 일관. **단 이 관찰이 더미 카테고리 정의의 재발견인지 도메인 신호인지는 본 PoC 로 분리 불가** (§4.2 참고).

### 3.4 시각화

![Pearson heatmap](img/correlation_poc_2026_05_29/pearson_heatmap.png)
![DTW heatmap](img/correlation_poc_2026_05_29/dtw_heatmap.png)

> 원본 CSV: [pearson_16x16.csv](img/correlation_poc_2026_05_29/pearson_16x16.csv) / [dtw_16x16.csv](img/correlation_poc_2026_05_29/dtw_16x16.csv)

---

## 4. 해석 (관찰 + 가설 단계, 결론 아님)

### 4.1 관찰된 사실

- **Null baseline 대비 의미있는 신호 측정됨** — 실측 DTW (0.184) < null (0.266), 비율 0.69
- **카테고리 간 분리는 명확** — motor-panel DTW (0.241) ≈ null (0.266) 의 91%
- **카테고리 내 cluster 후보 관찰** — 모터 ch1/3/8/13, 패널 ch11/16

### 4.2 본 PoC 로 답할 수 없는 것

| 질문 | 본 PoC | 답하려면 |
|---|---|---|
| cluster 가 더미 카테고리 분류 정의의 산물인가? | ❌ 분리 불가 | 운영 데이터로 같은 cluster 재현 여부 측정 |
| 16ch 일괄 multivariate IF 가 cluster 단위보다 부적합한가? | ❌ 미검증 가설 | 3 architecture 학습 → F1 비교 |
| ch9 ↔ ch15 cross-category 강한 Pearson 이 운영에서도 유지? | ❌ 모름 | 운영 데이터 재측정 + 감쇠 여부 확인 |
| cluster 가 시간 안정적인가? | ❌ 측정 안함 | 시간 분할 (전반 vs 후반) 매트릭스 비교 |

### 4.3 Pearson vs DTW 비교 (정정된 표현)

- **❌ 이전 표현:** "Pearson 은 일주기 트렌드 때문에 카테고리 분리 약함"
- **✅ 정확한 표현:** Pearson 이 "트렌드를 본다" 가 틀린 게 아니라, **공통 일주기 트렌드가 있으면 그게 진짜 상관으로 잡힘**. 본 PoC 에서 측정된 cross-category 강한 Pearson (ch9↔ch15 r=+0.877) **중 일부는 운영에서 깨질 수 있음** — DTW Z-score 정규화 후엔 같은 쌍이 다른 cluster 로 분리됨 (DTW 0.86 / 0.59).

---

## 5. 강사 대응 narrative (정정판)

> "Pearson + DTW + null baseline 1차 측정 결과:
>
> 1. **실측 DTW (0.184) < null baseline (0.266)** → 무작위 셔플보다 명확히 닮은 신호 측정됨 (비율 0.69)
> 2. **카테고리 간 분리는 명확** — motor-panel DTW (0.241) ≈ null (0.266) 의 91% = 셔플 수준 무관함
> 3. **동질군 cluster 후보 관찰** — 모터 ch1/3/8/13, 패널 ch11/16
>
> 다만 본 PoC 는 더미 데이터 기반이라 **(a) 관찰된 cluster 가 더미 생성 함수의 카테고리 정의를 다시 발견한 tautology 인지 진짜 도메인 신호인지 분리 불가, (b) 16ch 일괄 vs cluster 단위 vs 채널별 architecture 비교는 상관성 매트릭스만으로 결정 불가** 라는 한계가 있습니다.
>
> 그래서 plan 은:
>
> - **시연 전 1단계 (오늘 완료):** 더미 baseline 매트릭스 + null baseline 확보 → D+30 비교 대상으로 활용
> - **D+30 운영 데이터 누적 후 2단계:** 동일 명령어 운영 데이터로 재실행 → (a) cluster 재현 여부 (b) cross-category 상관 감쇠 여부 (c) null baseline 대비 비율 변화
> - **D+30~D+90 3단계:** 검증된 cluster 가 있다면 3 architecture (16ch 일괄 / cluster 단위 / 채널별) 학습 → F1 비교로 architecture 의사결정. SHAP attribution 으로 출처 식별 보완.
>
> 본 PoC 의 가치는 '정답 도출' 이 아니라 **분석 파이프라인 + 비교 baseline + null 기준선** 확보입니다."

---

## 6. 한계 + 후속

### 6.1 본 PoC 의 한계 (강사 보고 시 명시)

- **❗ Tautology 위험 (가장 큰 한계):** 더미가 카테고리별 템플릿으로 생성됨 → 카테고리별 cluster 발견이 도메인 신호인지 더미 구조 재발견인지 분리 불가
- **데이터 더미 한정** — 운영 데이터로 같은 cluster 재현 여부 미검증
- **단일 디바이스 (N=1)** — 디바이스 간 cluster 일관성 별도 PoC 필요 (D+90+ 디바이스 클러스터링)
- **6일치 (1주 미만)** — 주간 사이클 1회 미만, 시간 안정성 미측정
- **DTW 다운샘플 10배 (9,853 → 1,000)** — 정보 손실 동반
- **lighting 카테고리 n=1 (ch15)** — 카테고리 통계 의미 약함
- **time-lagged correlation 미측정** — 동시각 Pearson 만
- **current / voltage 미측정** — watt 단독
- **Architecture 비교 미실시** — 16ch 일괄 vs cluster vs 채널별 학습 F1 비교 안 함

### 6.2 D+30 sprint 진입 시 재측정 항목

| # | 작업 | 더미 baseline 대비 검증할 것 |
|---|---|---|
| 1 | 운영 데이터 2주치 wide-format 추출 | timestamp 수 9,853 → 1.2M+ 예상 |
| 2 | Pearson + DTW + null baseline 재측정 | 카테고리 평균 / null 비율 변화율 |
| 3 | cross-category 상관 (ch9↔ch15) 감쇠 여부 | 더미 한계 시그널 검증 |
| 4 | cluster 경계 재확인 (motor ch1/3/8/13 / panel ch11/16) | 운영에서도 같은 cluster 유지? |
| 5 | 시간 분할 재현성 (전반 1주 vs 후반 1주) | cluster 시간 안정성 |
| 6 | time-lagged corr (lag = 1~30 tick) | 인과 관계 단서 |

### 6.3 ② 단계 (Architecture 의사결정) 진입 조건

- 운영 데이터에서 cluster 재현 확인 (D+30~D+45)
- 3 architecture 학습 + F1 측정
  - (A) 16ch 일괄 multivariate IF
  - (B) cluster 단위 multivariate IF (모터군 + 패널군 분리)
  - (C) 현재 채널별 단변량 IF (baseline)
- 출처 식별 = SHAP attribution (어느 채널/feature 가 anomaly 기여)
- ARIMA / Z / CP 와의 4축 직교 재설계 (multivariate 채택 시 짝 정렬)

---

## 7. 관련 문서

| 문서 | 역할 |
|---|---|
| [power-ai-트레이드오프-2026-05-21.md](power-ai-트레이드오프-2026-05-21.md) §3.3 #4~#5 | 본 PoC 의 모태 plan (D+30~D+90 sprint) |
| [power-ai-design-decisions-2026-05-21.md](power-ai-design-decisions-2026-05-21.md) §2 | 4채널 선정 의도 (16채널 단계적 확장 근거) |
| [ai-pipeline-실제코드-2026-05-27.md](ai-pipeline-실제코드-2026-05-27.md) §4-1 | 가스 다변량 vs 전력 단변량 코드 매핑 |
| [power-ai-종합문서-2026-05-21.md](power-ai-종합문서-2026-05-21.md) | 전력 AI SoT (통합 의사결정 + 로드맵) |

## Changelog

- 2026-05-29 v1: 강사 multivariate IF 제안 1차 PoC. 더미 데이터 1주치 Pearson + DTW 측정. cluster 후보 식별. D+30 운영 데이터 재측정 plan 명시.
- 2026-05-29 v2 (외부 리뷰 반영): (a) Null baseline (셔플 DTW) 추가 측정 — 실측/null 비율 0.69 / motor-panel 0.91 (셔플 수준). (b) 결론 톤 다운 — "정답 후보" → "관찰 + 가설". (c) Tautology 위험 §6.1 최상위 명시. (d) Pearson vs DTW framing 정정. (e) ② 단계 진입 조건에 3 architecture F1 비교 명시.
2
