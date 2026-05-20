# Power AI 다채널 IF + ARIMA 적용 복습 및 보고 문서

> **작성일:** 2026-05-21
> **작성자:** cjy (with Claude)
> **브랜치:** `feature/0519_power_add_chanel`
> **commit:** `e60dd2f`, `d9a0bbb`, `a1dddc1`
> **목적:** 전력 AI 추론을 디바이스 `63200c3afd12` × ch1 단독 상태에서 ch1+ch9+ch14+ch15 (부하 종류 3분화) 로 확장한 작업의 적용 증거·검증·트러블슈팅 기록

---

## 1. 작업 개요

| 항목 | 내용 |
|---|---|
| 핵심 목표 | 4채널 IF+ARIMA 일관 동작 → 모델 일반화 검증 + D+30 un-downgrade 정식 적용 근거 데이터 수집 시작 |
| 접근 방식 | 부하 종류 다양성 기준 채널 추가 (ch9 메인 전력반 / ch14 공조 / ch15 조명) — ch2~8/12/13 모터 동질군은 제외 |
| 변경 전 | 1채널 (ch1 압연기 watt) IF+ARIMA. ch1 IF 는 sensor_identifier 가 비어있던 옛 학습 (id=4, sid='') |
| 변경 후 | 4채널 (ch1·ch9·ch14·ch15 watt) IF+ARIMA. 모든 모델 mac 단위 sensor_identifier (`power:device_63200c3afd12:chN:watt`) |
| 최종 상태 | 4채널 추론 분기 진입 + DRF forward 400 0건 + ARIMA ci 폭 정상화 + night_abnormal 시각 격상은 KST 주간 시연 시 미발동 |

### 활성 모델 매트릭스 (적용 후)

```
디바이스 63200c3afd12
┌──────┬───────────────────────┬──────────────────┬──────────────────────────────┐
│ 채널 │ 부하 종류             │ IF 모델 (id, ver)│ ARIMA 모델 (id, ver)         │
├──────┼───────────────────────┼──────────────────┼──────────────────────────────┤
│ ch1  │ 압연기  7.5kW  모터   │  id=17, v11      │  id=21, v3 (max_rows=10000)  │
│ ch9  │ 메인 전력반 15kW 3상  │  id=13, v9       │  id=20, v2 (max_rows=10000)  │
│ ch14 │ 공조설비 5.5kW 모터   │  id=15, v10      │  id=22, v2 (max_rows=10000)  │
│ ch15 │ 조명/제어 1kW 220V    │  id=12, v8       │  id=23, v2 (max_rows=10000)  │
└──────┴───────────────────────┴──────────────────┴──────────────────────────────┘

sensor_identifier 표기: power:device_63200c3afd12:chN:watt  (전부 동일 패턴 — mac 단위)
```

비활성 (옛 모델):
- id=4 (IF, sid='') — ch1 옛 학습. sensor_identifier 비어있어 추론 측 mac 매칭 실패 — 재학습 후 비활성화
- id=10 (IF, sid=`power:device_1:ch15:watt`) — IF 학습 명령 mac 변환 누락 시점에 생성. 표기 잘못 — 재학습 후 비활성화
- id=8/9/11/14/16 (ARIMA) — 초기 max_rows=3000 학습본. ci 폭 0 회귀 — 재학습 후 비활성화

---

## 2. 변경·추가된 파일 목록

| 파일 | 구분 | 주요 변경 내용 |
|---|---|---|
| `fastapi-server/power/services/power_service.py` | 수정 | `_INFERENCE_ENABLED_CHANNELS` 에 (9,14,15) 추가 + `_COMBINED_TO_RISK_LEVEL` / `_FIRE_LEVELS` 에 "warning" 매핑 추가 |
| `fastapi-server/power/services/decide_alarm.py` | 수정 | `_ai_combined_to_risk_level` 에 "warning" 매핑 추가 + docstring "AI 5단계 → UI 3단계" 갱신 |
| `drf-server/apps/ml/management/commands/train_anomaly_model.py` | 수정 | power 분기에서 PowerDevice PK → raw mac 변환 추가 (sensor_identifier 표기 통일) |
| `drf-server/apps/ml/management/commands/train_arima_power_model.py` | 수정 | `--max-rows` default 3000 → 10000 (ConvergenceWarning 회피) |
| `drf-server/apps/ml/models/ml_anomaly_result.py` | 수정 | `RiskClassified` enum 에 `WARNING="warning"` 추가 (4단계 → 5단계) |
| `drf-server/apps/ml/migrations/0003_alter_mlanomalyresult_risk_classified.py` | **신규** | auto-generated migration (choices 변경, schema 영향 없음) |
| `drf-server/apps/ml/tests/test_anomaly_result_create.py` | 수정 | invalid 테스트 값 "warning" → "bogus" (warning 은 이제 valid) |
| `docs/codereviews/2026_05_21/power-ai-multichannel-activation.md` | **신규** | 코드리뷰 문서 (Before/After) |
| `skill/plan/power-ai-multichannel-activate.md` | **신규** (.gitignore) | plan 문서 (4 phase 분할) |

---

## 3. 트러블슈팅 기록

### 3-1. IF 학습 명령의 sensor_identifier 표기 불일치 — 추론 매칭 실패

**증상:**

```
# IF 학습 결과
MLModel.id=10 sensor_identifier='power:device_1:ch15:watt'  ← PowerDevice.id (정수)
# ARIMA 학습 결과
MLModel.id=11 sensor_identifier='power:device_63200c3afd12:ch15:watt'  ← raw mac

# fastapi 추론 측 (power_service.py:367)
sensor_identifier = f"power:device_{device_id}:ch{channel}:{data_type}"  ← raw mac 기준

→ IF 모델 매칭 실패 (DRF 404 silent fallback) → IF 추론 미동작
```

**원인 파악 과정:**

```bash
# 학습 결과 MLModel rows 비교
docker compose exec drf python manage.py shell -c "
from apps.ml.models import MLModel
for m in MLModel.objects.filter(sensor_type='power').order_by('id'):
    print(f'id={m.id} kind={m.algorithm} sid={m.sensor_identifier!r}')
"

# 결과:
# id=10 kind=isolation_forest sid='power:device_1:ch15:watt'  ← 표기 PK
# id=11 kind=arima            sid='power:device_63200c3afd12:ch15:watt'  ← 표기 mac
```

**근본 원인:**

`train_arima_power_model.py:96-104` 는 PowerDevice 조회 후 `device_obj.device_id` (raw mac) 로 sensor_identifier 생성. 반면 `train_anomaly_model.py:258` 은 `opts["device_id"]` (parse_args 의 정수 PK) 그대로 사용. 두 학습 명령의 표기가 달라 추론 측 (mac 단위 매칭) 과 호환 안 됨.

**해결책:**

ARIMA 명령의 패턴을 IF 명령에도 이식:

```python
# train_anomaly_model.py — power 분기에 추가
if sensor_type == "power":
    try:
        device_obj = PowerDevice.objects.get(pk=opts["device_id"])
    except PowerDevice.DoesNotExist as exc:
        raise CommandError(f"PowerDevice PK={opts['device_id']} 없음") from exc
    sensor_identifier = (
        f"power:device_{device_obj.device_id}"
        f":ch{opts['channel']}:{opts['data_type']}"
    )
```

수정 후 ch1/9/14/15 IF 재학습 → 모든 모델 sensor_identifier 가 `power:device_63200c3afd12:chN:watt` 형식으로 통일.

---

### 3-2. DRF `RiskClassified` enum 의 "warning" 누락 — forward 400 폭주

**증상:**

```
fastapi-1 | [anomaly_forward_ml] action=non_success status=400 body=
'{"error":{"code":"validation_failed",
  "message":"\"warning\"은 유효하지 않은 선택입니다.",
  "details":{"risk_classified":["\"warning\"은 유효하지 않은 선택입니다."]}}}'

→ 15분 관찰 동안 549건 발생. ch9/14/15 활성화 후 빈도 폭증.
```

**원인 파악 과정:**

```bash
# 1. fastapi 측 출력 도메인 확인 (ai/risk_combine.py:148)
#   docstring: combined: "normal" | "caution" | "predict_warn" | "warning" | "danger" (5단계)
#   3축 매트릭스 L67-72:
#     ("warning", "normal", True):  "warning"
#     ("warning", "anomaly", False): "warning"
#     ("normal",  "anomaly", True):  "warning"

# 2. DRF 측 enum 확인 (apps/ml/models/ml_anomaly_result.py:17)
#   NORMAL / CAUTION / PREDICT_WARN / DANGER  ← warning 없음 (4단계)

# 3. 직접 POST 검증
docker compose exec drf curl -sS -X POST -H "Content-Type: application/json" \
  -d '{"ml_model":null,"model_version_snapshot":1,"sensor_type":"power",
       "sensor_identifier":"power:device_test:ch1:watt",
       "measured_at":"2026-05-21T08:00:00Z","anomaly_score":0.1,
       "prediction":"normal","risk_classified":"warning",
       "feature_snapshot_json":{}}' \
  http://localhost:8000/api/ml/anomaly-results/
# → 400 validation_failed (enum 거부 확정)
```

**근본 원인:**

fastapi `combine_risk_5axis` 의 출력 도메인이 5단계인데 DRF enum 이 4단계라 `warning` forward 시 거부. 외부 리뷰어 [[alarm_dataflow_review_2026_05_20]] #1 (a/c path 충돌) 의 본체. ch1 단독일 때는 빈도가 낮아 노출이 적었음.

**해결책 — DRF 를 fastapi 에 맞추는 방향 (5단계 통일)**:

```python
# drf-server/apps/ml/models/ml_anomaly_result.py
class RiskClassified(models.TextChoices):
    NORMAL = "normal", "정상"
    CAUTION = "caution", "주의"
    PREDICT_WARN = "predict_warn", "예측경고"
    WARNING = "warning", "경고"     # ← 추가
    DANGER = "danger", "위험"
```

추가로 fastapi 측 3곳도 "warning" 매핑 보강 — 없으면 silent fallback "normal" 잠재 회귀:

```python
# fastapi-server/power/services/power_service.py
_COMBINED_TO_RISK_LEVEL = {..., "warning": "warning", ...}
_FIRE_LEVELS = {"caution", "predict_warn", "warning", "danger"}

# fastapi-server/power/services/decide_alarm.py
def _ai_combined_to_risk_level(combined: str) -> str:
    return {..., "warning": "warning", ...}.get(combined, "normal")
```

migration 0003 자동 생성·적용. DB schema 변경 없음 (CharField choices 변경만).

**검증 — 직접 POST 게이트:**

```bash
docker compose exec drf curl -sS -w "\nHTTP_STATUS=%{http_code}\n" \
  -X POST -H "Content-Type: application/json" \
  -d '{... "risk_classified":"warning" ...}' \
  http://localhost:8000/api/ml/anomaly-results/
# → HTTP_STATUS=201 ✓
```

더미 흐름 검증: forward 400 549건 → **0건**.

> **첫 시도 시 enum 추가 후에도 400 잔존** 미스터리가 한 번 있었음 (정확한 원인 미상). 같은 변경을 단계별 게이트로 끊어서 다시 적용했더니 정상 작동. 진단 절차에서 "코드 변경 → migrate → restart → 직접 POST 게이트" 를 별도 단계로 끊어 확인하는 게 안전.

---

### 3-3. ARIMA `max_rows` 부족 → ConvergenceWarning → CI 폭 0 → predict_warn 폭주

**증상:**

```
# 학습 시 statsmodels 경고
ConvergenceWarning: Maximum Likelihood optimization failed to converge.
  Check mle_retvals

# 추론 시 ci 폭 0
[anomaly_inference] ch=9 watt value=7329.1 arima_fc=7447.1 ci=[7447.1,7447.1]
                                                              ↑ lower == upper

# 결과: 거의 모든 actual 값이 ci 위반 판정 → predict_warn / warning 폭주
# FP율: ch9/14/15 100%, ch1 73%  (15분 관찰)
```

**원인 파악 과정:**

```bash
# 1. ARIMA forecast 의 ci 폭 분포 조사 (3분 윈도우, 100 샘플)
docker compose logs fastapi --since 3m | grep -oE "ci=\[[0-9.]+,[0-9.]+\]" | head -100 | \
  awk -F'[][,]' '{ w=$3-$2; if(w<0.1) z++; else nz++ } END {
    print "ci 폭 0:", z+0, "건"; print "ci 폭 > 0:", nz+0, "건" }'
# 결과: ci 폭 0 = 75건 / 100 (75%)

# 2. 학습 데이터 분포 확인 (cv = std/mean — 변동성 정상 여부)
ch 1: n=31451, cv=0.466
ch 9: n=34951, cv=0.345
ch14: n=32850, cv=0.454
ch15: n=34723, cv=0.391
# → 변동성 부족이 원인 아님. 학습 데이터 자체는 정상

# 3. max_rows 3000 → 10000 으로 한 채널 재학습 (ch9)
docker compose exec drf python manage.py train_arima_power_model \
  --device-id 1 --channel 9 --data-type watt \
  --since 2026-05-13 --until 2026-05-20 --max-rows 10000 --activate
# → ConvergenceWarning 사라짐

# 4. 학습 결과 fit summary 확인
sigma2=291667  sigma=540  (이전: sigma2 ≈ 0)
1-step forecast: 7500.00, 95% CI: [6441.50, 8558.50], width=2117  ← 정상 폭
```

**근본 원인:**

`--max-rows 3000` (이전 default) 은 5분 주기 데이터 기준 약 10일치만 사용. 하루 시간대별 부하 패턴 (주간 0.55 / 저녁 0.30 / 야간 0.15) 중 **최근 윈도우 한 시간대 부근만 학습** → 변동 폭 추정 실패 → sigma2 ≈ 0 → ARIMA(1,1,1) ConvergenceWarning + 95% CI 폭 0.

**해결책 — `max_rows` default 3000 → 10000:**

```python
# drf-server/apps/ml/management/commands/train_arima_power_model.py
parser.add_argument(
    "--max-rows",
    type=int,
    default=10000,
    # 3000 (이전 default) 시 5분 주기 데이터 기준 ~10일 윈도우 — 하루의 시간대
    # 변동(주간 0.55 / 야간 0.15) 일부만 학습되어 ConvergenceWarning + ci 폭 0
    # 회귀 발생 (2026-05-21 확인). 10000 으로 전체 시간대 패턴 학습 보장.
    help="학습에 사용할 최근 row 수 상한 (학습 시간 제한)",
)
```

4채널 ARIMA 모두 max_rows=10000 으로 재학습 + fastapi cache evict (`POST /ai/reload?sensor_type=power`).

**검증:**

```
재학습 전: ci 폭 0 비율 75%  (sigma2 붕괴)
재학습 후: ci 폭 0 비율  0%  (모든 forecast 가 [lo, hi] 폭 보유, 평균 1672)
```

---

### 3-4. night_abnormal 시각 격상 — caution 폭주의 원인 (의도된 동작)

**증상:**

ARIMA 정상화 후에도 caution 빈도가 채널당 96~97% 로 높음. 모든 추론 축이 normal 인데도 combined=caution.

```
[anomaly_inference] ch=1 value=4044.3 threshold=normal pred=normal arima_v=False
                    z=False cp=False combined=caution  ← 모든 축 normal/False 인데 caution
```

**원인 파악 — 격상 로그 추적:**

```bash
docker compose logs fastapi --since 3m | grep "night_abnormal"

# 결과:
[night_abnormal] 야간 가동 의심 device=63200c3afd12 ch=1 value=3949.0 threshold=2250
                 combined=normal->caution
[night_abnormal] 야간 가동 의심 device=63200c3afd12 ch=9 value=7359.8 threshold=4500
                 combined=normal->caution
...

# 카운트: 1276건 추론 중 472건 (37%) 이 night_abnormal 격상
```

**근본 원인:**

`fastapi-server/power/services/power_service.py:108-119` 의 휴리스틱 시각 분기:

```python
_KST_OFFSET_HOURS = 9
_NIGHT_GATE_KST = (22, 5)         # 22 ~ 익일 05 KST 야간
_NIGHT_THRESHOLD_RATIO = 0.30     # 정격 30% 초과 시 격상
_NIGHT_ESCALATION = {
    "normal": "caution",          # ← 격상 매핑
    "caution": "warning",
    "predict_warn": "warning",
}
```

- 검증 시각이 KST 새벽 (00:30) → `_is_night_kst_iso(measured_at)` True
- 더미가 시각 무관 watt 생성 → 모든 채널에서 value > 정격 × 30% 초과
- → IF/ARIMA 둘 다 normal 이어도 night_abnormal 로 normal → caution 격상

이건 IF/ARIMA 모델 FP 가 아니라 **휴리스틱 시각 분기의 의도된 동작**. ch1 단독일 때도 야간엔 같은 격상이 발생했지만 채널 1개라 빈도가 작아 시연 화면에 묻혔던 것.

**해결책 — 시연 시각으로 자연 해소:**

시연이 KST 주간 (08~18) 으로 결정 → `_NIGHT_GATE_KST=(22,5)` 미발동 → 별도 조치 불필요.

야간 시연 가능성이 생기면 옵션 분리:
- 옵션 A: `_NIGHT_THRESHOLD_RATIO` 상향 (0.30 → 0.50+)
- 옵션 B: 더미가 시각 인지 부하 생성 (야간 baseline 0.15 적용)
- 옵션 C: `_NIGHT_ESCALATION` 임시 비활성

이는 본 plan 범위 외 후속 작업.

---

## 4. 학습 명령어

### STEP 1 — 채널별 IF 학습 (DRF 컨테이너)

```bash
for CH in 1 9 14 15; do
  docker compose exec drf python manage.py train_anomaly_model \
    --sensor-type power \
    --device-id 1 \
    --channel $CH \
    --data-type watt \
    --since 2026-05-13 --until 2026-05-20 \
    --contamination 0.01 \
    --activate
done
```

각 채널마다 다음 출력 확인:

```
[5/5] MLModel row 생성 — version vN  sensor_identifier='power:device_63200c3afd12:chN:watt'
학습 완료
  MLModel.id  = NN
  in-sample anomaly = ~1% (contamination 설정 1.00%)
```

> sensor_identifier 가 `power:device_63200c3afd12:chN:watt` 형식이어야 함. `power:device_1:chN:watt` (PK) 면 commit `e60dd2f` 이전 코드 — 재학습 필요.

### STEP 2 — 채널별 ARIMA 학습 (DRF 컨테이너)

```bash
for CH in 1 9 14 15; do
  docker compose exec drf python manage.py train_arima_power_model \
    --device-id 1 \
    --channel $CH \
    --data-type watt \
    --since 2026-05-13 --until 2026-05-20 \
    --activate
done
```

> commit `a1dddc1` 이후 `--max-rows` default 가 10000. 명시 안 해도 됨. **ConvergenceWarning 출력이 없어야 정상**.

학습 결과 확인:

```bash
docker compose exec drf python manage.py shell -c "
from apps.ml.models import MLModel
for m in MLModel.objects.filter(sensor_type='power', is_active=True).order_by('algorithm','sensor_identifier'):
    print(f'id={m.id:>2} {m.algorithm:>18} ver={m.version} sid={m.sensor_identifier!r}')
"
```

기대 출력:

```
id=20              arima ver=2 sid='power:device_63200c3afd12:ch9:watt'
id=21              arima ver=3 sid='power:device_63200c3afd12:ch1:watt'
id=22              arima ver=2 sid='power:device_63200c3afd12:ch14:watt'
id=23              arima ver=2 sid='power:device_63200c3afd12:ch15:watt'
id=12   isolation_forest ver=8 sid='power:device_63200c3afd12:ch15:watt'
id=13   isolation_forest ver=9 sid='power:device_63200c3afd12:ch9:watt'
id=15   isolation_forest ver=10 sid='power:device_63200c3afd12:ch14:watt'
id=17   isolation_forest ver=11 sid='power:device_63200c3afd12:ch1:watt'
```

### STEP 3 — fastapi 활성화 플래그 확인

```bash
grep -A 6 "_INFERENCE_ENABLED_CHANNELS" fastapi-server/power/services/power_service.py
```

기대 출력:

```python
_INFERENCE_ENABLED_CHANNELS: set[tuple[int, str]] = {
    (1, "watt"),
    (9, "watt"),
    (14, "watt"),
    (15, "watt"),
}
```

### STEP 4 — fastapi 모델 캐시 갱신

```bash
curl -X POST "http://localhost:8001/ai/reload?sensor_type=power"
```

성공 응답:

```json
{"status":"ok","evicted":[
  ["power","isolation_forest","power:device_63200c3afd12:ch1:watt"],
  ["power","arima","power:device_63200c3afd12:ch1:watt"],
  ["power","isolation_forest","power:device_63200c3afd12:ch9:watt"],
  ["power","arima","power:device_63200c3afd12:ch9:watt"],
  ...8 keys
]}
```

---

## 5. 적용 증거 — 추론 분기 진입 검증

> 사용자 질문에 대한 직접 답: "정말 4채널에 IF+ARIMA 둘 다 붙어있는가" 를 입증하는 항목

### 5-1. fastapi 모델 로드 로그

```bash
docker compose logs fastapi --since 5m | grep -E "IF loaded|ARIMA loaded"
```

기대 (캐시 evict 후 첫 추론 시점):

```
[ai] IF    loaded sensor_identifier='power:device_63200c3afd12:ch1:watt'  version=11 file=power_if_v11.pkl
[ai] IF    loaded sensor_identifier='power:device_63200c3afd12:ch9:watt'  version=9  file=power_if_v9.pkl
[ai] IF    loaded sensor_identifier='power:device_63200c3afd12:ch14:watt' version=10 file=power_if_v10.pkl
[ai] IF    loaded sensor_identifier='power:device_63200c3afd12:ch15:watt' version=8  file=power_if_v8.pkl
[ai] ARIMA loaded sensor_identifier='power:device_63200c3afd12:ch1:watt'  version=3  file=power_arima_v3_...pkl  order=(1, 1, 1)
[ai] ARIMA loaded sensor_identifier='power:device_63200c3afd12:ch9:watt'  version=2  file=power_arima_v2_...pkl  order=(1, 1, 1)
[ai] ARIMA loaded sensor_identifier='power:device_63200c3afd12:ch14:watt' version=2  file=power_arima_v2_...pkl  order=(1, 1, 1)
[ai] ARIMA loaded sensor_identifier='power:device_63200c3afd12:ch15:watt' version=2  file=power_arima_v2_...pkl  order=(1, 1, 1)
```

**4채널 × 2 모델 = 8개 로드 라인 확인** — 누락 시 STEP 1/2 재학습 또는 STEP 4 cache evict 재시도.

### 5-2. 채널별 추론 활동 카운트 (3분 윈도우)

```bash
for ch in 1 9 14 15; do
  total=$(docker compose logs fastapi --since 3m | grep -c "ch=${ch} watt")
  printf "ch%-3s: %s건\n" "$ch" "$total"
done
```

기대 (검증 시점):

```
ch1  : 165건
ch9  : 175건
ch14 : 162건
ch15 : 172건
```

→ 4채널 모두 균등 추론 (한 채널 묻히지 않음).

### 5-3. ARIMA ci 폭 정상화 검증

```bash
docker compose logs fastapi --since 3m | \
  grep -oE "arima_fc=[0-9.]+ ci=\[[0-9.]+,[0-9.]+\]" | head -100 | \
  awk -F'[][,= ]' '{ fc=$2; lo=$5; hi=$6; w=hi-lo;
    if(w<0.1) z++; else nz++; sum+=w } END {
      printf "ci 폭 0:        %d 건\nci 폭 > 0:     %d 건\n평균 ci 폭:    %.1f\n",
      z+0, nz+0, (z+nz>0?sum/(z+nz):0) }'
```

기대 (재학습 + cache evict 후):

```
ci 폭 0:     0 건
ci 폭 > 0:   100 건
평균 ci 폭:  1716.9
```

→ 모든 ARIMA forecast 가 정상 신뢰구간 폭 보유. 폭 0 비율 75% → **0%** 로 정상화.

### 5-4. DRF forward 400 0건 검증

```bash
docker compose logs fastapi --since 3m | grep -c "anomaly_forward_ml.*non_success.*status=400"
```

기대: **0** 건. enum 통일 전: 549건/3분.

### 5-5. 직접 POST 게이트 (DRF enum 동작 확인)

```bash
docker compose exec drf curl -sS -w "\nHTTP_STATUS=%{http_code}\n" \
  -X POST -H "Content-Type: application/json" \
  -d '{"ml_model":null,"model_version_snapshot":1,"sensor_type":"power",
       "sensor_identifier":"power:device_test:ch1:watt",
       "measured_at":"2026-05-21T08:00:00Z","anomaly_score":0.1,
       "prediction":"normal","risk_classified":"warning",
       "feature_snapshot_json":{}}' \
  http://localhost:8000/api/ml/anomaly-results/
```

기대: `HTTP_STATUS=201` + `risk_classified: "warning"` 인 row 생성. 400 이면 migration 0003 미적용.

---

## 6. 팀원·팀장 환경 설정 가이드

### STEP 0 — 코드 받기

```bash
git fetch origin
git checkout feature/0519_power_add_chanel
git pull
```

### STEP 1 — DRF migration 적용

```bash
docker compose exec drf python manage.py showmigrations ml
```

`[X] 0003_alter_mlanomalyresult_risk_classified` 확인. 없으면:

```bash
docker compose exec drf python manage.py migrate ml
```

### STEP 2 — 모델 학습 (위 §4 STEP 1, STEP 2)

ch1/9/14/15 IF + ARIMA 총 8회 학습.

### STEP 3 — fastapi 재시작 + 캐시 갱신

활성화 플래그가 코드 변경이라 재시작 필요:

```bash
docker compose restart fastapi
```

이후 캐시 evict (학습 후 새 모델 로드 강제):

```bash
curl -X POST "http://localhost:8001/ai/reload?sensor_type=power"
```

### STEP 4 — 더미 실행

```bash
docker exec -d diconai-fastapi-1 python -m dummies.power_dummy
```

### STEP 5 — 적용 증거 확인 (위 §5 항목 5-1 ~ 5-4 순서대로 실행)

8개 로드 라인 + 4채널 추론 활동 + ci 폭 0건 + DRF 400 0건 — 4가지 모두 통과해야 적용 완료.

---

## 7. 자주 나오는 오류와 해결

| 오류 | 원인 | 해결 |
|---|---|---|
| `sensor_identifier='power:device_1:ch1:watt'` (PK 표기) | commit `e60dd2f` 이전 코드로 IF 학습 | 최신 브랜치로 IF 재학습 |
| forward 400 `"warning"은 유효하지 않은 선택입니다` | migration 0003 미적용 또는 drf 컨테이너 reload 필요 | `migrate ml` + `docker compose restart drf` |
| `ConvergenceWarning: Maximum Likelihood optimization failed` (학습 시) | `--max-rows` 가 명시적으로 3000 같이 작게 지정됨 | default (10000) 사용 또는 더 큰 값 |
| ARIMA 추론 시 `ci=[fc,fc]` (폭 0) | ARIMA 모델이 max_rows 3000 시점 학습본 | ARIMA 재학습 (§4 STEP 2) + cache evict |
| 모든 추론이 `combined=caution` 으로 격상 | KST 야간(22~05) + watt > 정격 30% 시 night_abnormal 격상 | 의도된 동작. 시연이 KST 주간이면 자동 해소 |
| `[ai] IF loaded` 로그가 4채널 다 안 보임 | `_INFERENCE_ENABLED_CHANNELS` 4채널 안 들어감 | 코드 확인 후 `docker compose restart fastapi` |

---

## 8. 후속 작업

- **un-downgrade 정식 적용 (D+30, 2026-07-14 예상)**: 본 작업은 더미 데이터 기반 PoC. 정식 적용 근거는 실측 데이터 30일 별도 수집 — [[demo_2026_06_14_arima_roadmap]] 별도 의제
- **vocabulary 통합 후속**: 본 작업은 enum 5단계 확장. 정적 vocab (3단계) ↔ AI vocab (5단계) 의 본질적 통합 (예: 정적도 5단계로 또는 AI 도 3단계로) 은 외부 리뷰어 #1 의 더 깊은 해결로 별도 plan
- **야간 시각 격상 본질 수정**: 더미가 시각 인지 부하 생성하도록 보강 또는 휴리스틱 임계 상향은 별도 plan
- **current/voltage 추론 확장**: watt 외 data_type 으로 확장 (D+15 sprint 후보)
- **다른 device 확장**: 현재 디바이스 1개. 여러 디바이스 통합 검증 시점은 시연 후

---

## Changelog

- 2026-05-21 작성. 4채널 활성화 완료 + 발견된 회귀 2건 + ARIMA max_rows 본질 + 5개 검증 명령 + 환경 설정 가이드.
