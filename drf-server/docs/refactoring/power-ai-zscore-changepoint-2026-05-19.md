# 전력 AI Z-score + Change Point + 5축 우선순위 엔진 (D2 + E1 + F)

작성일: 2026-05-19
브랜치: `feature/power_zscore_cp`
commits:
- `0a9f3d6 feat(power-ai): D2 — Z-score 통계 이상 판정 헬퍼 (STEP D)`
- `b6d305c feat(power-ai): E1 — Change Point 전력 (STEP E)`
- `ef91525 feat(power-ai): F — 5축 우선순위 엔진 (Z-score/CP 발화 반영)`

선행 plan: [`skill/plan/anomaly-detection-zscore-changepoint.md`](../../../skill/plan/anomaly-detection-zscore-changepoint.md) — 가스·전력 두 도메인 의도
적용 plan: [`skill/plan/power-zscore-changepoint-apply.md`](../../../skill/plan/power-zscore-changepoint-apply.md) — 본 작업 sub-plan (전력 단독)
관련 문서: [`docs/codereviews/2026_05_19/power-5axis-policy-flow.md`](../../../docs/codereviews/2026_05_19/power-5axis-policy-flow.md) — 코드 흐름·함수 분석

---

## 개요

전력 도메인은 직전 sprint (PR #63 머지, 2026-05-18) 에서 IF + ARIMA un-downgrade (3축 정책 엔진) 까지 완료했지만, [STEP 5 — 디코나이 AI 기반 위험 예측 개발 로드맵](../../../skill/AI/시계열AI/STEP%205%20—%20디코나이%20AI%20기반%20위험%20예측%20개발%20로드맵.md) 의 5축 권고 (Threshold + IF + Z-score + Change Point + ARIMA) 중 **STEP D (Z-score) / STEP E (Change Point)** 두 축이 비어 있었다.

본 작업은 시연 (D-26, 2026-06-14) 전 5축 완성 — (a) 임계치 직전 조기 경고 (ANOMALY_WARNING), (b) 추세 변화 시작 시점 명시 (TREND_SHIFT) 를 운영자가 인지하도록 한다.

### 가스 영역 0 touch

상위 plan §2 결정 — 가스는 D1 (Z-score) 만 적용 대상이지만 본 작업 범위에서 제외 (가스 담당자 별도 task). 본 작업은 가스 import / 호출 / config 0 변경. 가스 IF/ARIMA/Threshold 발화 패턴 회귀 0.

---

## 결정 매트릭스 (2026-05-19 사용자 확정)

| 항목 | 결정 | 거부한 옵션 + 이유 |
|---|---|---|
| **5축 엔진 구현 형태** | 우선순위 함수 (`combine_risk_5axis` if/elif) | "48-cell dict": 모든 조합 명시는 유지비용 ↑, 의도 불투명. "3축 + 후처리 함수": 회귀 보존엔 깔끔하나 우선순위 매핑 불명시 |
| **5축 base** | `combine_risk_3axis` 위임 | 신규 매트릭스 작성 시 W3.1 12-cell 회귀 보존 부담. base 위임으로 회귀 0 자동 보장 |
| **Z-score/CP 격상 조건** | base=="normal" 일 때만 "predict_warn" 격상 | base 가 이미 발화 등급이면 ML/threshold 우선 — STEP 5 우선순위 매트릭스 일치 |
| **CP 윈도우** | 별도 `_cp_windows` deque maxlen=60 | _power_windows 확장(30→60) 시 IF startup 시간 2배. CP 권고 W=30 → 2W=60 그대로 |
| **CP 라이브러리** | 자체 two-window 비교 | "ruptures (Bayesian)": 정확도 ↑ 하나 의존성 추가. STEP 4 권고 매트릭스가 단순 비교 기반이라 충분 |
| **algorithm_source 라벨** | "Z-score" / "급변" | "통계 이상" / "추세 변화": 운영자 친화이나 학습 자료의 STEP 키워드 1:1 매칭 X. 시연 가치 ↓ |
| **algorithm_source priority** | night > combined > change_point > arima > zscore > IF | TREND_SHIFT 는 ARIMA forecast 보다 명시적 (확정 발화 시점). Z-score 는 IF 보다 약함 (단변량 통계) |
| **임계치 초기값** | Z-score 3.0, MEAN_K 3.0, STD_K 2.0 | STEP 1·4 권고 그대로. 시연 후 운영 데이터로 튜닝 |

---

## 작업 분할 + 재활용 자산

| 단계 | 작업 | 위치 | 재활용 자산 | 신규 |
|---|---|---|---|---|
| **D2** | `_zscore_check` 헬퍼 | `fastapi-server/power/services/power_service.py` | `_power_windows` (IF deque maxlen=30) | abs((value - mean) / (std + EPS)) >= threshold |
| **D2** | `process_anomaly_inference` 호출 | 같은 파일 | IF 추론 흐름 | `z_score_anomaly = _zscore_check(win, value, 3.0)` |
| **D2** | 단위 테스트 6 | `fastapi-server/tests/test_power_service_zscore.py` | (없음) | window 미충족 / 정상 / +튐 / -튐 / std=0 / threshold |
| **E1** | `change_point_service.py` 신설 | `fastapi-server/power/services/` | Sliding Window 패턴 | two-window 비교 + state machine (STABLE↔SHIFT) |
| **E1** | `process_anomaly_inference` 호출 + fire 로그 | `power_service.py` | night_abnormal fire 로그 패턴 | `change_point, cp_meta = detect_change_point(...)` |
| **E1** | 단위 테스트 6 | `tests/test_change_point_service.py` | (없음) | window 미충족 / 안정 / mean shift 1회 fire / 중복 방지 / 최종 STABLE 복귀 / std 단독 |
| **F** | `combine_risk_5axis` 함수 | `fastapi-server/ai/risk_combine.py` | `combine_risk_3axis` (base 위임) | 5축 우선순위 매트릭스 매핑 |
| **F** | 호출 교체 (3axis → 5axis) | `power_service.py` | 기존 호출 위치 | 5 input 매개변수 |
| **F** | algorithm_source priority 확장 | `power_service.py` | 기존 4단계 priority | 6단계 (night > combined > change_point > arima > zscore > IF) |
| **F** | `_ALGORITHM_SOURCE_LABEL` 동기 | `power_service.py` + `drf-server/apps/core/constants.py` | 기존 4 entries dict | "zscore" / "change_point" 2 entries 추가 |
| **F** | `anomaly_meta` payload 확장 | `power_service.py` | 기존 anomaly_meta 구조 | z_score_anomaly / change_point / cp_mean_shift / cp_std_ratio |
| **F** | 단위 테스트 16 | `tests/test_risk_combine.py` | 기존 3축 테스트 패턴 | 12 parametrize + 4 dedicated (회귀 가드 / Z-score 우선순위 / CP 우선순위 / fail-fast) |

---

## 변경 파일 매핑

| 파일 | D2 | E1 | F | 합계 |
|---|---|---|---|---|
| `fastapi-server/power/services/power_service.py` | +22 -1 | +13 -1 | +29 -7 | ~+55 |
| `fastapi-server/power/services/change_point_service.py` | | 신규 +97 | | +97 |
| `fastapi-server/ai/risk_combine.py` | | | +57 | +57 |
| `drf-server/apps/core/constants.py` | | | +5 | +5 |
| `fastapi-server/tests/test_power_service_zscore.py` | 신규 +77 | | | +77 |
| `fastapi-server/tests/test_change_point_service.py` | | 신규 +120 | | +120 |
| `fastapi-server/tests/test_risk_combine.py` | | | +73 | +73 |
| **합계** | ~+100 | ~+229 | ~+157 | ~+486 |

---

## 검증 결과

### 단위 (172 통과 — 기존 156 + 신규 16)

| 모듈 | 통과 | 신규 케이스 |
|---|---|---|
| test_power_service_zscore.py | 6/6 | window 미충족 / 정상 / +/- 튐 / std=0 EPS / threshold param |
| test_change_point_service.py | 6/6 | window 미충족 / 안정 / mean shift 1회 / 중복 방지 / 최종 STABLE / std 단독 |
| test_risk_combine.py | 16/16 (신규) + 23/23 (기존) | 12 parametrize 우선순위 매트릭스 + 회귀 가드 + Z-score/CP 격상 / fail-fast |

전체 fastapi 회귀 통과 (기존 W0~W4.a 8 테스트 + ARIMA forecast / quality_guard / night / threshold 모두 0 회귀).

### 모듈 sanity (`docker compose exec fastapi python -c`)

```
Z=110 → True                                          # 정상 윈도우 + 큰 튐
CP fires = 1 state = SHIFT                            # 30 normal + 30 shift → 1회 발화
5축(N,N,F,F,F) = normal                              # 회귀 가드
5축(N,N,F,T,F) = predict_warn                        # Z-score 격상
5축(W,N,F,T,F) = caution                             # base=caution → Z-score 무시
5축(D,A,T,T,T) = danger                              # CRITICAL 최상위
labels: ['isolation_forest','arima','combined','night_abnormal','zscore','change_point']
```

### e2e 시나리오 (라이브 — power dummy + scenario_router)

**overload 시나리오** (정격 7500W 초과):
```
value=8110.9 threshold=danger pred=anomaly arima_v=False z=False cp=False combined=danger
```
기존 IF + threshold 발화 패턴 그대로. **5축 회귀 가드 라이브 검증** — Z-score/CP 가 False 이고 base 가 danger → combined=danger 그대로.

**degradation 시나리오** (점진 부하 ↑) — §F 우선순위 매트릭스 라이브 검증:
| value | threshold | z | combined | 의미 |
|---|---|---|---|---|
| 6726.5 | warning | True | **caution** | base=caution(=normal X) → z 무시. **§F 우선순위 가드** |
| 5341.0 | normal | True | **predict_warn** | base=normal + z=True → 격상 (ANOMALY_WARNING) |
| 3920.6 | normal | True | predict_warn | base=predict_warn (IF anomaly 단독) → z 무시 |

CP 라이브 발화는 60+초 점진 누적 필요 — 시연 리허설 (D-7 이후) 에서 충분히 확인 가능.

---

## 핵심 결정 — base = combine_risk_3axis 위임

`combine_risk_5axis` 가 신규 5축 매트릭스를 직접 정의하지 않고 `combine_risk_3axis` 호출 결과를 base 로 사용한 이유:

1. **회귀 가드 자동 보장** — Z-score=F + CP=F 일 때 5축 결과 == 3축 결과. W3.1 12-cell 매트릭스의 "두 AI 동의 격상" 의도 (IF anomaly + ARIMA True → 한 단계 격상) 그대로 보존.
2. **유지비용 ↓** — 5축 = 3 × 2 × 2 × 2 × 2 = 48 cell. 48-cell dict 정의 시 두 AI 동의 격상 같은 미묘한 의도가 5축 모두에서 일관성 있게 표현되어야 함 — 인적 오류 ↑.
3. **STEP 5 우선순위 매트릭스 일치** — base != "normal" 이면 ML/threshold 우선, base == "normal" 이면 Z-score/CP 격상. 우선순위 매핑이 함수 구조에 명시.

테스트 `test_combine_risk_5axis_preserves_3axis_regression` 가 회귀 가드 — 12 × 2 = 24 조합 (3축 12 cell × Z=T/F, CP=F 고정) 으로 base 위임 동작 검증.

---

## 후속

| 항목 | 위치 | 비고 |
|---|---|---|
| 가스 D1 (Z-score 가스) | 상위 plan §3.1 | 가스 담당자 별도 task. 본 작업의 패턴 재활용 가능 |
| W4.b metrics 라벨 | un-downgrade 보고 §10.3 | `ALARM_FIRED_TOTAL` / `RULE_FIRE_SUPPRESSED_BY_AI_TOTAL` 에 algorithm_source 라벨 |
| W5 운영 자동화 | un-downgrade 보고 §10.3 | MLAnomalyResult TTL / ARIMA 재학습 task |
| 임계치 튜닝 | 시연 후 D+1 ~ D+15 | Z-score 3.0 / MEAN_K 3.0 / STD_K 2.0 운영 데이터 기반 조정 |
| SARIMAX seasonal | 상위 plan §5.1 | 시연 후 별도 결정 |
| IF score 다단계 활용 | 상위 plan §5.2 | continuous score 의 5축 매트릭스 보강 가능 |
| 가스 Change Point | 상위 plan §5.3 | 가스 점진 누적 패턴 실제 발견 시 재검토 |

---

## 학습 포인트

1. **base 위임 패턴** — 신규 매트릭스를 직접 정의하지 않고 기존 매트릭스를 base 로 호출 → 회귀 가드 자동.
2. **우선순위 함수 vs Full Matrix** — N 축 매트릭스가 8 cell 넘으면 우선순위 함수가 유지·이해 비용 ↓. 매트릭스는 회귀 가드 강력하지만 의도 불투명.
3. **CP 윈도우 분리** — 윈도우 길이 다른 두 알고리즘(IF 30 / CP 60) 의 윈도우는 분리. 통합 시 startup 시간·메모리 충돌 위험.
4. **numpy bool → Python bool 캐스팅** — `np.bool_` 는 `is False` 검증 실패. helper 반환 시 `bool(...)` 캐스팅 명시 (D2 검증 중 발견).
5. **컨테이너 재시작 후 dummy 죽음** — fastapi 컨테이너 안에 background process 로 실행된 dummy 는 fastapi restart 시 같이 죽음. 코드 변경 후 재시작 시 dummy 재기동 잊지 말 것 (e2e 검증 중 발견).
