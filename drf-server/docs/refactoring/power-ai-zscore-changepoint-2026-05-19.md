# 전력 AI Z-score + Change Point + 5축 우선순위 엔진 (D2 + E1 + F + 코드리뷰 보강)

작성일: 2026-05-19
브랜치: `feature/power_zscore_cp`
commits:
- `0a9f3d6 feat(power-ai): D2 — Z-score 통계 이상 판정 헬퍼 (STEP D)`
- `b6d305c feat(power-ai): E1 — Change Point 전력 (STEP E)`
- `ef91525 feat(power-ai): F — 5축 우선순위 엔진 (Z-score/CP 발화 반영)`
- `(pending) refactor(power-ai): 코드리뷰 보강 — escalation_source / z_value / reset_state / ASCII 로그`

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

---

## 코드리뷰 후속 보강 (2026-05-19)

D2/E1/F 머지 (3 commits) 직후 self-code-review 진행. 식별된 7건 중 **4건 적용 / 3건 보류**. 본 섹션은 적용 4건의 상세 — 다른 팀원이 본 문서만 읽고도 변경 의도·전후 차이·운영 영향 파악 가능하도록.

### 리뷰 분류표

| 항목 | 분류 | 상태 | 근거 |
|---|---|---|---|
| §2.1 algorithm_source 라벨 의미론 불일치 | 주요 (Should-fix) | ✅ 적용 | 운영자가 라벨을 driver 로 오인 — 시연 학습 가치 ↓ |
| §3.1 Z-score 발화 시점 가시성 비대칭 | 보조 (Nice-to-fix) | ✅ 적용 | CP 는 dedicated fire 로그 있는데 Z-score 는 없음 |
| §3.3 테스트 상태 격리 책임 분산 | 보조 | ✅ 적용 | private dict 직접 접근 → 향후 신규 테스트 파일 의 fragility |
| §4 CP fire 로그 unicode `→` | 마이너 (Nit) | ✅ 적용 | 다른 로그는 ASCII 만 사용 — 로그 shipping 도구 호환성 |
| §2.2 Z-score / CP 단독 알람 발화 | 주요 | ❌ 보류 | plan §F 의도된 동작. 시연 리허설 (D-7) 에서 노이즈 측정 후 임계치 튜닝 |
| §3.2 Z-score > IF priority 디자인 | 보조 | ❌ 보류 | "운영자 친화" 디자인 결정 — 시연 후 운영자 피드백으로 재검토 |
| §3.4 DRF 라벨 dict 동기 수동 | 보조 | ❌ 보류 | 크로스 모듈 SoT 신설 필요 — 별도 task 분리 |
| §3.5 멀티 워커 시 상태 불일치 | 보조 | ❌ 보류 | 현재 `--workers 1`. 운영 확장 시 Redis 기반 공유 state 필요 |

### §2.1 — algorithm_source 라벨이 실제 driver 와 어긋날 수 있음 (주요)

#### 문제 시나리오 (보강 전)

운영자가 받은 알람 토스트가 misleading. 예시:

```
[3:14 PM] [급변 감지] CH1 watt=8500 (combined=danger)
```

운영자 해석: "급변(Change Point) 이 위험을 일으켰구나 → 단계적 부하 증가 패턴 의심"

**실제 코드 흐름**:
- threshold=8500W ≥ 정격 7500W → threshold_risk="danger"
- IF 추론 결과 normal, ARIMA 정상, z=False
- 그러나 CP 윈도우는 60틱 누적 후 prev/curr 비교에서 우연히 trigger 발생
- `combine_risk_5axis` → base=combine_risk_3axis("danger", "normal", False)="danger" → CRITICAL 최상위라 z/cp 무시 → combined="danger"
- algorithm_source priority 는 base 결과 모름 — `elif change_point: → "change_point"` 매칭
- 결과: combined="danger" (threshold 가 driver) BUT 라벨="change_point"

**실제 driver 는 threshold=danger 인데 라벨이 "급변"** → 운영자가 잘못된 가설로 대응 시작.

비슷한 사례:
```
threshold=warning + IF=normal + ARIMA=F + cp=True
→ combined="caution" (3축 warning matrix)
→ algorithm_source="change_point" (priority 매칭)
→ UI: "[급변 감지] caution"
```
실제 caution 의 driver 는 threshold=warning. CP 는 격상에 기여 X.

#### 보강 — `combine_risk_5axis` 가 escalation_source 도 반환

**변경된 시그니처**:

```python
# Before
def combine_risk_5axis(threshold, if_pred, arima, z, cp) -> str:
    base = combine_risk_3axis(threshold, if_pred, arima)
    if base != "normal":
        return base
    if z or cp:
        return "predict_warn"
    return "normal"

# After
def combine_risk_5axis(threshold, if_pred, arima, z, cp) -> tuple[str, str]:
    """Returns (combined, escalation_source)."""
    base = combine_risk_3axis(threshold, if_pred, arima)
    if base != "normal":
        return base, ""  # ← z/cp 가 격상에 기여 X 면 source=""
    if change_point:
        return "predict_warn", "change_point"
    if z_score_anomaly:
        return "predict_warn", "zscore"
    return "normal", ""
```

`escalation_source` 는 "**z/cp 가 실제 risk 격상에 기여했는가**" 를 명시. 값:
- `""` — 3축 결과 (threshold/IF/ARIMA) 가 driver. z/cp 는 격상 영향 X.
- `"zscore"` — base=normal 인 상태에서 Z-score 가 predict_warn 으로 격상.
- `"change_point"` — base=normal 인 상태에서 CP 가 predict_warn 으로 격상.

z + cp 둘 다 True 면 `"change_point"` 우선 (algorithm_source priority 와 일치).

**caller 측 (`power_service.py`) 변경**:

```python
# Before
combined = combine_risk_5axis(threshold_risk, prediction, arima_v, z, cp)
...
elif change_point:                    # ❌ base 무관, 라벨 misleading
    algorithm_source = "change_point"
elif arima_violation:
    algorithm_source = "arima"
elif z_score_anomaly:                 # ❌ base 무관
    algorithm_source = "zscore"

# After
combined, escalation_source = combine_risk_5axis(...)
...
elif escalation_source == "change_point":  # ✅ z/cp 가 실제 격상 시만 라벨
    algorithm_source = "change_point"
elif arima_violation:
    algorithm_source = "arima"
elif escalation_source == "zscore":        # ✅
    algorithm_source = "zscore"
```

#### 보강 후 동작

| 시나리오 | base (3축) | combined | escalation_source | algorithm_source | UI 라벨 |
|---|---|---|---|---|---|
| threshold=danger + cp=True | danger | danger | "" | "" (Or IF/ARIMA 매칭) | "AI" (fallback) |
| threshold=warning + cp=True | caution | caution | "" | "" | "AI" (fallback) |
| threshold=normal + z=True | normal | predict_warn | "zscore" | "zscore" | "Z-score" |
| threshold=normal + cp=True | normal | predict_warn | "change_point" | "change_point" | "급변" |
| threshold=normal + IF=anomaly + z=True | predict_warn (IF) | predict_warn | "" | "isolation_forest" | "IF" |
| threshold=danger + z=True + cp=True | danger | danger | "" | "" | "AI" |

**핵심**: 라벨이 "이 알람의 위험도가 어떻게 결정됐는가" 와 일치. CP/Z-score 가 격상에 기여하지 않으면 그쪽 라벨 사용 X.

#### 보강 후 misleading 사라진 사례 (위 시나리오 #1 재방문)

```
[3:14 PM] [AI] CH1 watt=8500 (combined=danger)  ← 변경 후 (CP 단순 발생만으로는 라벨 X)
```

운영자가 "AI 가 어떤 축으로 잡았는지 모름 — 8500W 가 정격 초과인 게 명백히 driver" 로 정확히 해석. 라벨 misleading 제거.

CP fire 자체는 별도 `[change_point] STABLE->SHIFT mean_shift=X std_ratio=Y` info 로그에 남으므로 운영 분석 시 추적 가능 (logger.info 발화 시점 로그).

### §3.1 — Z-score 발화 시점 가시성 보강

#### 문제 (보강 전)

CP 발화는 dedicated 로그 있음 ([power_service.py](../../fastapi-server/power/services/power_service.py) §2.E1):
```
[change_point] device=63200c3afd12 ch=1 watt STABLE->SHIFT mean_shift=4.21 std_ratio=1.05
```

Z-score 발화는 메인 추론 로그의 `z=True` 필드로만 확인:
```
[anomaly_inference] device=... z=True cp=False combined=predict_warn score=...
```

**비대칭 문제**:
- 운영자가 grep 으로 "Z-score 가 언제 발화했는가" 추출 시 메인 로그 라인 전체를 파싱해야 함
- z 값 (실제 |z|) 이 로그에 노출 안 됨 — 발화가 z=3.1 (경계 근처) 인지 z=15.0 (극단) 인지 구분 불가
- 시연 시연 시 "방금 Z-score 발화한 시점" 캡처 어려움

#### 보강 — `_zscore_check` 가 z 값도 반환 + dedicated fire 로그

**시그니처 변경**:

```python
# Before
def _zscore_check(window, value, threshold=3.0) -> bool:
    ...
    z = abs(value - mean) / (std + 1e-9)
    return bool(z >= threshold)

# After
def _zscore_check(window, value, threshold=3.0) -> tuple[bool, float]:
    """Returns (is_anomaly, z) — z 는 실제 |z| 값 (로깅용)."""
    if len(window) < _INFERENCE_WINDOW:
        return False, 0.0
    ...
    z = abs(value - mean) / (std + 1e-9)
    return bool(z >= threshold), float(z)
```

**caller 측 fire 로그**:

```python
# After
z_score_anomaly, z_value = _zscore_check(win, float(value), threshold=3.0)
if z_score_anomaly:
    logger.info(
        "[zscore] device=%s ch=%s %s value=%s |z|=%.2f >= 3.0",
        device_id, channel, data_type, value, z_value,
    )
```

이제 Z-score 발화 시점은 CP 와 같은 패턴으로 추적 가능:
```
[zscore] device=63200c3afd12 ch=1 watt value=5341.0 |z|=4.17 >= 3.0
```

운영자가 `grep '\[zscore\]\|\[change_point\]\|\[night_abnormal\]'` 한 줄로 모든 AI fire 시점 추출 가능. z 값 노출로 발화 강도 구분 가능 (z=3.1 보더라인 vs z=15 극단).

### §3.3 — change_point_service.reset_state() public helper

#### 문제 (보강 전)

`change_point_service.py` 의 module-level mutable dict (`_cp_windows`, `_cp_states`) 는 테스트 간 누적된다 (모듈 import 1회 → 상태 유지). 격리를 위해 `test_change_point_service.py` 의 autouse fixture 가 private 필드를 직접 접근:

```python
from power.services.change_point_service import (
    _cp_states, _cp_windows, detect_change_point,
)

@pytest.fixture(autouse=True)
def _reset_state():
    _cp_windows.clear()
    _cp_states.clear()
    yield
    _cp_windows.clear()
    _cp_states.clear()
```

**향후 리스크**:
- 본 모듈의 신규 state 변수 (예: `_cp_thresholds_override`) 추가 시 모든 테스트 파일에서 같은 fixture 수정해야 함
- 다른 테스트 파일 (예: integration test) 이 `detect_change_point` import 하면 또 fixture 작성 필요 — 캡슐화 위반 + 책임 분산

#### 보강 — public `reset_state()` 헬퍼

`change_point_service.py` 에 추가:

```python
def reset_state(key: tuple[int, str] | None = None) -> None:
    """채널 단위 또는 전체 CP 상태 초기화 — 주로 테스트 격리용.

    운영 코드는 사용 X — fastapi 재시작 시 모듈 단위 dict 가 자연 초기화 됨.

    Args:
        key: (channel, data_type) — 특정 채널만 초기화. None 이면 전체.
    """
    if key is None:
        _cp_windows.clear()
        _cp_states.clear()
    else:
        _cp_windows.pop(key, None)
        _cp_states.pop(key, None)
```

테스트 fixture 가 public API 만 사용:

```python
# After
from power.services.change_point_service import (
    _cp_states, detect_change_point, reset_state,
)

@pytest.fixture(autouse=True)
def _reset_state():
    reset_state()  # ← public 헬퍼
    yield
    reset_state()
```

**의의**:
- 향후 module-level state 변수 추가 시 `reset_state()` 본문만 수정. 테스트 파일들은 0 변경
- 다른 테스트 파일이 `detect_change_point` 쓰면 `reset_state` 도 같이 import → 캡슐화 유지
- `_cp_states[KEY]` assertion (테스트가 state 검증용으로 읽는 부분) 은 그대로 — public 읽기는 허용. write 만 helper 경유

### §4 — CP fire 로그 unicode `→` → ASCII `->`

#### 문제 (보강 전)

`[change_point] STABLE→SHIFT` 의 화살표 (U+2192 RIGHTWARDS ARROW) 는 unicode. 다른 모든 로그 ([anomaly_inference], [night_abnormal] 등) 는 ASCII 만 사용:

```
[night_abnormal] 야간 가동 의심 device=... combined=normal->caution  ← ASCII
[change_point] STABLE→SHIFT mean_shift=...                          ← Unicode
```

**리스크**:
- 로그 shipping 도구 (예: Filebeat → Elasticsearch) 가 UTF-8 인코딩 보장 안 하면 깨질 수 있음
- grep 패턴 일관성 — `'->'` 로 일괄 검색 시 CP 로그만 빠짐
- 한글 라벨 ("야간 가동", "급변") 은 의도적 UTF-8 이지만 ASCII 로 가능한 부분은 ASCII 가 안전

#### 보강

```python
# Before
"[change_point] device=%s ch=%s %s STABLE→SHIFT mean_shift=%.2f std_ratio=%.2f"

# After
"[change_point] device=%s ch=%s %s STABLE->SHIFT mean_shift=%.2f std_ratio=%.2f"
```

한글 변수값 (algorithm_source 라벨 "Z-score"/"급변") 은 그대로 UTF-8. 화살표 같은 cosmetic unicode 만 ASCII 화.

### 보류 3건의 근거

#### §2.2 단독 신호 발화 (Z-score / CP 만으로 알람)

**현황**: `combine_risk_5axis(normal, normal, F, True, F) = ("predict_warn", "zscore")` → `predict_warn ∈ _FIRE_LEVELS` → 알람 발화.

**리스크**: Z-score 3σ 규칙은 정상 가우시안 데이터에서 약 1/370 비율 false positive. 1Hz 샘플링 시 약 6분에 1번. rate_limit 60s 가 캡 하지만 시연 중 노이즈 가능.

**보류 근거**: plan §F 의 의도된 동작. 시연 리허설 (D-7, 2026-06-07) 에서 실제 노이즈로 발화 빈도 측정 → 필요 시 threshold 상향 (3.0 → 3.5 또는 4.0). 코드 변경 없이 임계치만 튜닝 가능.

#### §3.2 Z-score > IF priority 디자인

**현황**: `algorithm_source` priority 에서 zscore 가 isolation_forest 보다 위. 의도: Z-score 가 explainable (평소대비 N σ 튐) → 운영자 친화.

**보류 근거**: 디자인 결정. 시연 후 운영자 피드백 ("어떤 라벨이 더 유용한가") 으로 재검토. 코드 변경 없이 priority 순서만 swap 가능.

#### §3.4 DRF / fastapi 라벨 dict 동기

**현황**: `_ALGORITHM_SOURCE_LABEL` (fastapi) ↔ `ALGORITHM_SOURCE_LABEL` (DRF constants) 별도 정의. 수동 동기.

**보류 근거**: 단일 진실 공급원 (SoT) 정리는 크로스 모듈 (별도 패키지 또는 DRF → fastapi import 경로) 필요. 시연 후 별도 task 로 분리. 단기 완화는 PR 체크리스트 / pre-commit 훅으로.

#### §3.5 멀티 워커 시 상태 불일치

**현황**: `--workers 1` 환경에선 module-level dict 가 단일 인스턴스. `--workers > 1` 변경 시 워커별로 독립 상태 → 채널 CP 검출 일관성 깨짐.

**보류 근거**: 운영 확장 시점에 Redis 기반 공유 state 또는 워커 affinity 도입. 현재 시연 환경 영향 0.

### 코드리뷰 보강 commit 의 변경 통계

| 파일 | 변경 |
|---|---|
| `fastapi-server/ai/risk_combine.py` | `combine_risk_5axis` 시그니처 + 분기 로직 (+~15 / -~5) |
| `fastapi-server/power/services/power_service.py` | `_zscore_check` 시그니처 + 호출 흐름 + algorithm_source priority + 로그 (+~25 / -~10) |
| `fastapi-server/power/services/change_point_service.py` | `reset_state()` 헬퍼 (+~15) |
| `fastapi-server/tests/test_risk_combine.py` | parametrize tuple 확장 + 신규 1 케이스 (+~25 / -~10) |
| `fastapi-server/tests/test_power_service_zscore.py` | 6 케이스 tuple unpacking + z 값 검증 (+~20 / -~10) |
| `fastapi-server/tests/test_change_point_service.py` | `reset_state()` 경유로 변경 (+~5 / -~5) |

**검증**: fastapi pytest 173/173 통과 (기존 172 + 신규 `test_combine_risk_5axis_zcp_both_true_prefers_change_point`).

### 코드리뷰 자체의 학습 포인트

1. **`combine_risk_5axis` 의 "기여" 명시** — 단순히 combined_risk 만 반환하면 라벨링 로직이 외부에서 base 결과를 재계산해야 함 (DRY 위반 + 의도 불투명). 튜플 반환으로 "함수가 알고 있는 정보를 외부에 명시" — caller 책임 줄임.
2. **모듈 단위 mutable state 의 public 접근 헬퍼** — 테스트 격리를 위해 private dict 직접 접근하면 캡슐화 깨짐. `reset_state()` 같은 좁은 public API 가 더 깔끔.
3. **로그 가시성의 비대칭** — 한 알고리즘 (CP) 만 dedicated 로그 두면 다른 알고리즘 (Z-score) 의 발화 추적이 불편. 패턴 통일 (모두 dedicated fire 로그) 이 운영 분석 비용 ↓.
4. **라벨링 vs 위험도 결정의 분리** — `combined_risk` (위험도) 와 `algorithm_source` (라벨) 은 의미가 다름. 라벨이 위험도 driver 와 일치해야 운영자가 오인 X.
