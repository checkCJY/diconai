## `decide_alarm.py` — T4 D2 단일 알람 결정 매트릭스 (순수 함수)

AI 추론 5 state × 정적 평가 결과를 입력받아 source 6종 매트릭스로 분기, `AlarmDecision` 을 반환합니다. T4 sub-plan §5.1 의 "fastapi 단일 결정자" 매트릭스가 본 파일에서 구현됩니다.

**핵심 설계**: I/O 가 없는 순수 함수. `get_ai_state` / `evaluate_static_risk_from_cache` 호출은 호출자 (`anomaly_inference`) 책임 — 분기 로직을 격리해 단위 테스트가 mock 없이 가능합니다.

---

### 전체 구조 한눈에 보기

```
decide_alarm(ai_state, ai_combined_risk, static_risk) → AlarmDecision | None
    │
    ├─ AI state = FIRED          → source="ai"                          (정적 무관)
    │
    ├─ static fired == False     → return None                          (알람 없음)
    │
    └─ static fired == True 일 때 AI state 별:
          ├─ INFERRED_NORMAL     → source="static_cover_miss"
          ├─ INFERRED_FAILED     → source="static_cover_inference_fail"
          ├─ WARMING_UP          → source="static_cover_warmup"
          ├─ DISABLED            → source="static_no_ai_available"
          └─ None (Redis 장애)   → source="static_no_ai_available"      (fail-safe)
```

매트릭스 표:

| AI 상태             | 정적 결과   | source                          | alarm_type           |
|---------------------|------------|---------------------------------|----------------------|
| FIRED               | *          | ai                              | power_anomaly_ai     |
| INFERRED_NORMAL     | fired      | static_cover_miss               | power_overload       |
| INFERRED_FAILED     | fired      | static_cover_inference_fail     | power_overload       |
| WARMING_UP          | fired      | static_cover_warmup             | power_overload       |
| DISABLED            | fired      | static_no_ai_available          | power_overload       |
| None (장애·만료)    | fired      | static_no_ai_available          | power_overload       |
| *                   | not fired  | None                            | —                    |

---

### 왜 순수 함수로 격리했는가

**선택**: `decide_alarm` 안에서 Redis/DRF/DB 호출 전혀 없음. 입력 3개 (AI state, AI combined risk, static risk) 만으로 결정.

**배경**: T4 sub-plan §5 "분기 로직과 I/O 분리" — AI state 조회 (Redis) 와 정적 평가 (캐시) 는 호출자가 미리 끝내고 본 함수에 결과만 전달.

```python
def decide_alarm(
    ai_state: AIInferenceState | None,
    ai_combined_risk: str,
    static_risk: str,
) -> AlarmDecision | None:
```

**트레이드오프**:
- ↑ **단위 테스트 단순** — 36조합 (5 state × None + 5 ai_risk × 3 static) 모두 mock 없이 매트릭스 검증. T4 D2 entry 시 12-step 코드 매핑에서 본 함수가 통과의 핵심이 됨.
- ↑ **분기 변경 시 영향 격리** — 매트릭스 변경 시 본 파일만 수정. anomaly_inference 의 250 줄 흐름 영향 0.
- ↑ **코드 리뷰 용이** — 함수 60 줄, 분기 6개. PR 에서 변경 라인 즉시 식별.
- ↓ **호출자 책임 증가** — anomaly_inference 가 ai_state / static_risk 를 먼저 계산해 본 함수에 넘김. 매트릭스 결정 이전에 두 입력을 정확히 채워야 한다는 contract 가 코드 외부 (plan 문서) 에만 있음.
- ↓ **AlarmDecision 후처리 분산** — 본 함수가 source 결정만 하고 실제 push_payload 조립 (summary 문구, anomaly_meta) 은 anomaly_inference 에서. "source 결정 ↔ 표시 텍스트" 가 두 파일에 걸쳐 있어 신규 source 추가 시 양쪽 수정 필요.

---

### 왜 AI FIRED 면 정적 무관 source="ai" 인가

**선택**: FIRED 분기는 static 검사 전에 즉시 return.

```python
if ai_state == AIInferenceState.FIRED:
    return AlarmDecision(
        source="ai",
        alarm_type="power_anomaly_ai",
        risk_level=_ai_combined_to_risk_level(ai_combined_risk),
        reason=ALARM_SOURCE_REASON["ai"],
    )
```

**배경**: AI 가 발화했다 = "확신 있는 이상". 정적 임계는 운영자가 설정한 절대 룰이지만, 정상 상태 (W=50%) 에서도 AI 가 패턴 이상을 잡을 수 있음. AI 발화 시 정적 normal 이어도 알람을 띄워야 함.

**트레이드오프**:
- ↑ **AI 가치 보존** — IF/ARIMA 가 잡은 미세한 이상이 정적 임계 미달이라고 무시되지 않음. 시연 핵심 가치 (W4 un-downgrade plan).
- ↑ **source 라벨 단순** — AI 발화 = "ai" 한 라벨. 운영자가 "AI 가 잡았다" vs "운영자 룰이 잡았다" 를 source 만 보고 구분.
- ↓ **위양성 흡수** — AI 가 잘못 발화해도 "ai" 알람 발송. AI 위양성률이 높으면 운영자 신뢰도↓. rate limit 60s 와 학습 데이터 품질이 이를 부분적으로 막음.
- ↓ **정적 danger + AI fired 케이스 의미 손실** — 두 신호가 동시 발화하는 가장 위험한 케이스인데 source 는 "ai" 한 라벨. risk_level 은 AI combined 기준 — 정적 danger 가 더 강한 신호여도 가려질 수 있음.

---

### 왜 static fired 가 아닌 모든 분기에 None 인가

**선택**: AI state 가 INFERRED_NORMAL/DISABLED/WARMING_UP 이고 정적 normal 이면 알람 없음.

```python
if not static_fired:
    return None
```

**배경**: AI 와 정적 둘 다 정상이면 알람 띄울 이유가 없음. 가장 빈번한 케이스 (정상 운영 시 99% 의 채널) 를 early return 으로 처리.

**트레이드오프**:
- ↑ **noise 0** — 정상 채널에서 추론 함수가 계속 호출되어도 push 없음. 운영자 UX 보호.
- ↑ **빠른 path** — 매트릭스 5x3 = 15 케이스 중 5 케이스 (각 AI state × static normal) 가 단일 분기로 처리.
- ↓ **AI INFERRED_NORMAL 정보 손실** — AI 가 "정상으로 확신" 한 상태와 "확신 못 함" (WARMING_UP/DISABLED) 이 같은 결과. 분석 시 차이를 보려면 ai_state 별도 추적 (Prometheus counter) 필요.
- ↓ **알람 없음 = state 마킹 무의미** — INFERRED_NORMAL/WARMING_UP/DISABLED 의 차이를 운영자가 알 길이 없음 (정상 시 모달 없음). 디버깅용 dev tool 또는 admin panel 필요.

---

### 왜 None (Redis 장애) 를 DISABLED 와 동등 취급하는가

**선택**: ai_state=None (Redis BRPOP 실패·만료) 시 static fired 면 `static_no_ai_available` 으로 분류.

```python
else:
    # None (Redis 장애·만료) — DISABLED 동등 fail-safe 분기.
    source = "static_no_ai_available"
```

**배경**: AI state 조회는 Redis 의존. Redis 가 다운되면 `get_ai_state` 가 None 반환. "AI 가 의도적으로 비활성" (DISABLED) 과 "AI 결과를 못 가져옴" (None) 은 본질적으로 다르지만, 운영자 관점에서는 둘 다 "AI 기여 0".

**트레이드오프**:
- ↑ **운영자 단순화** — source 라벨이 5종 (FIRED 외) 으로 유지. None 을 별 source 로 분리하면 6종이 되어 운영자 가이드 복잡도 증가.
- ↑ **fail-safe 보장** — Redis 장애 시 정적 임계로라도 알람 발화. 인프라 장애가 알람 사일런스로 이어지지 않음.
- ↓ **장애 가시성 손실** — Redis 가 죽었다는 신호가 알람 source 에 안 드러남. Grafana 알림 (`redis_up` metric) 따로 봐야 함.
- ↓ **None 처리가 None 자체 검사 아니라 else 분기** — DISABLED 와 None 이 같은 `static_no_ai_available` 로 합쳐지는데, 코드상으로는 `elif DISABLED → source = ..., else → source = ...` 두 분기. 미래에 새 AIInferenceState 가 추가되면 else 가 그 신규 state 까지 흡수해 의도 외 동작 가능. enum 확장 시 본 분기 명시 필요.

---

### 왜 alarm_type 이 ai 와 static 으로 갈리는가

**선택**: source="ai" → `alarm_type="power_anomaly_ai"`, 그 외 → `alarm_type="power_overload"`.

**배경**: 알람 타입은 운영자 모달의 큰 카테고리 (AI 이상 vs 정적 룰 위반). DB AlarmRecord.alarm_type 컬럼 인덱스 + 필터링용.

**트레이드오프**:
- ↑ **AlarmRecord 분류 용이** — Django admin 에서 `alarm_type="power_anomaly_ai"` 만 필터링하면 AI 발화만 추출. 모델 평가 시 ground truth 필요한 케이스 즉시 조회.
- ↑ **운영자 모달 분기** — 모달이 alarm_type 으로 색·아이콘 분기. AI 알람은 anomaly_meta 필드 표시, 정적은 단순 임계 정보.
- ↓ **타입 2종으로 단순화 손실** — static_cover_miss vs static_cover_warmup vs static_no_ai_available 의 차이가 alarm_type 에는 안 보임. source 컬럼까지 봐야 구분.
- ↓ **신규 source 추가 시 alarm_type 결정 모호** — "ai 와 static 사이의 중간" (예: AI confidence 가 낮은 발화) 같은 신규 카테고리는 어느 type 에 넣을지 결정 모호. alarm_type vs source 의 책임 경계가 코드에서 안 명시.

---

### 왜 _ai_combined_to_risk_level 의 `warning` 키가 명시되는가

**선택**: combined 도메인 (`normal/caution/predict_warn/warning/danger`) 5종 모두 dict 키로 명시.

```python
return {
    "normal": "normal",
    "caution": "warning",
    "predict_warn": "warning",
    "warning": "warning",      # ← 누락 시 silent fallback "normal"
    "danger": "danger",
}.get(combined, "normal")
```

**배경**: 주석 — `"warning" 누락 시 silent fallback "normal" → 시연 알람 미발화 회귀`. 과거에 발생한 실제 사고. `combine_risk_5axis` 가 "warning" 을 직접 반환할 수 있는데 dict 에 누락하면 `.get(..., "normal")` 이 정상으로 떨어져 알람이 사라짐.

**트레이드오프**:
- ↑ **명시성** — 5종 키 모두 적혀 있어 신규 combined 도메인 추가 시 자연스럽게 검토.
- ↑ **회귀 보호** — 주석으로 "왜 명시했나" 기록 — 미래 cleanup 시 "이거 중복 같은데 지우자" 회피.
- ↓ **mapping 중복** — `_ai_combined_to_risk_level` 가 본 파일과 `anomaly_inference.py` 의 `_COMBINED_TO_RISK_LEVEL` 두 곳에 동일 정의. 한쪽만 수정하면 분기 불일치.

시연 후 정비: 두 dict 중 하나를 단일 진실 공급원으로 통합 — `core/risk_mapping.py` 같은 별 모듈로 추출 후보.
