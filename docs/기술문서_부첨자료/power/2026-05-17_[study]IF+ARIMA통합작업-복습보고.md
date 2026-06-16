# IF + ARIMA 통합 작업 리뷰 문서

> **작성일:** 2026-05-17
> **작성자:** 이성현
> **브랜치:** `feature/0511_gas_scenario_dummy`
> **목적:** 가스 이상탐지 IsolationForest 12피처 → 15피처(ARIMA 잔차 추가) 확장 작업 복습·보고·트러블슈팅 기록

---

## 1. 작업 개요

|항목|내용|
|---|---|
|핵심 목표|가스 AI 이상탐지 정확도 향상|
|접근 방식|IsolationForest(IF)에 ARIMA 잔차 피처 3개 추가|
|변경 전|12피처 (CO 4개 + H2S 4개 + CO2 4개)|
|변경 후|15피처 (CO 5개 + H2S 5개 + CO2 5개, 각 가스에 `arima_resid` 1개 추가)|
|최종 상태|15피처 학습·추론 모두 정상 작동 확인|

### 피처 구조 (변경 후)

```
인덱스  피처명              설명
──────────────────────────────────────────────────────
  0    co_value            CO 원본 측정값
  1    co_roll_mean_30     CO 30틱 이동 평균
  2    co_roll_std_30      CO 30틱 이동 표준편차
  3    co_diff             CO 직전 틱 대비 변화량
  4    co_arima_resid      CO ARIMA 잔차 ← 신규 추가
  5    h2s_value           H2S 원본 측정값
  6    h2s_roll_mean_30    H2S 30틱 이동 평균
  7    h2s_roll_std_30     H2S 30틱 이동 표준편차
  8    h2s_diff            H2S 직전 틱 대비 변화량
  9    h2s_arima_resid     H2S ARIMA 잔차 ← 신규 추가
 10    co2_value           CO2 원본 측정값
 11    co2_roll_mean_30    CO2 30틱 이동 평균
 12    co2_roll_std_30     CO2 30틱 이동 표준편차
 13    co2_diff            CO2 직전 틱 대비 변화량
 14    co2_arima_resid     CO2 ARIMA 잔차 ← 신규 추가
```

---

## 2. 변경·추가된 파일 목록

|파일|구분|주요 변경 내용|
|---|---|---|
|`drf-server/apps/ml/services/feature_service.py`|수정|`compute_arima_residuals()` 추가, `build_multi_features()`에 `arima_results` 파라미터 추가|
|`drf-server/apps/ml/management/commands/train_anomaly_model.py`|수정|gas 분기에서 ARIMA pkl 로드 후 `build_multi_features`에 전달|
|`drf-server/apps/ml/management/commands/train_arima_model.py`|**신규 생성**|가스별 ARIMA 학습 Django 관리 명령어|
|`fastapi-server/ai/router.py`|수정|`_compute_arima_resid()` 헬퍼 추가, `_build_multi_feature_row()`에 `arima_results` 파라미터 추가|
|`fastapi-server/gas/services/gas_service.py`|수정|모듈 레벨 ARIMA pkl 로드, `_build_multi_feature_row` 호출에 `arima_results` 전달|
|`drf-server/requirements.txt`|수정|`statsmodels==0.14.2` 추가|
|`fastapi-server/requirements.txt`|수정|`statsmodels==0.14.2`, `pandas==2.3.3` 추가|

---

## 3. 트러블슈팅 기록

### 3-1. FastAPI statsmodels 임포트 오류

**증상:**

```
TypeError: deprecate_kwarg() missing 1 required positional argument: 'new_arg_name'
  File ".../statsmodels/compat/pandas.py", line ...
```

**원인 파악 과정:**

```bash
# ① statsmodels 버전 비교 → 동일 (원인 아님)
docker compose exec drf python -c "import statsmodels; print(statsmodels.__version__)"
# → 0.14.2
docker compose exec fastapi python -c "import statsmodels; print(statsmodels.__version__)"
# → 0.14.2  (동일)

# ② scipy 버전 비교 → 동일 (원인 아님)
docker compose exec drf pip show scipy | grep Version
# → 1.17.1
docker compose exec fastapi pip show scipy | grep Version
# → 1.17.1  (동일)

# ③ pandas 버전 비교 → 다름! (원인 발견)
docker compose exec drf pip show pandas | grep Version
# → 2.3.3
docker compose exec fastapi pip show pandas | grep Version
# → 3.0.3  ← 여기가 문제
```

**근본 원인:**

`statsmodels.compat.pandas`의 `deprecate_kwarg` 함수가 pandas 3.0에서 시그니처가 변경됨. statsmodels 0.14.2는 pandas 2.x 기준으로 작성 → pandas 3.0과 호환 불가. DRF는 `pandas==2.3.3`이었지만 FastAPI는 requirements에 pandas가 없어 pip이 최신(3.0.3)을 자동 설치.

**해결책:**

`fastapi-server/requirements.txt`에 `pandas==2.3.3` 명시 → DRF와 동일 버전 고정.

```bash
# 수정 후 재빌드
docker compose up -d --build fastapi

# 확인
docker compose exec fastapi python -c "from statsmodels.tsa.arima.model import ARIMA; print('OK')"
# → OK
```

---

### 3-2. entrypoint.sh 실행 권한 오류

**증상:**

```
permission denied: /app/entrypoint.sh
```

**원인:** entrypoint.sh 파일에 실행 권한(-x)이 없었음.

**해결:**

```bash
chmod +x /home/ltw17/diconai/fastapi-server/entrypoint.sh
docker compose up -d --build fastapi
```

---

### 3-3. 가스 더미 실행 시 ModuleNotFoundError

**증상:**

```
ModuleNotFoundError: No module named 'core'
```

**원인:** `python dummies/gas_dummy.py` 실행 시 Python이 `/app/dummies`를 루트로 인식해 `/app`의 모듈을 찾지 못함.

**해결:**

```bash
docker compose exec -e PYTHONPATH=/app fastapi python dummies/gas_dummy.py
```

`-e PYTHONPATH=/app` : Python이 `/app` 디렉터리를 모듈 검색 경로에 포함하도록 환경변수를 임시로 추가.

---

## 4. 학습 명령어

### STEP 1 — ARIMA 모델 학습 (DRF 컨테이너)

```bash
docker compose exec drf python manage.py train_arima_model \
    --sensor-id 1 \
    --gas-names co,h2s,co2 \
    --since 2026-05-06 \
    --until 2026-05-17
```

생성 파일: `ml_models/arima_co.pkl`, `arima_h2s.pkl`, `arima_co2.pkl`

### STEP 2 — IsolationForest 15피처 학습 (DRF 컨테이너)

```bash
docker compose exec drf python manage.py train_anomaly_model \
    --sensor-type gas \
    --sensor-id 1 \
    --gas-name co,h2s,co2 \
    --since 2026-05-06 \
    --until 2026-05-17 \
    --contamination 0.01 \
    --activate
```

`feature shape = (XXXX, 15)` 출력 확인 필수.

### STEP 3 — FastAPI 모델 캐시 갱신

```bash
curl -X POST "http://localhost:8001/ai/reload?sensor_type=gas"
```

---

## 5. 코드 리뷰 — 파일별 함수 단위

---

### 5-1. `drf-server/apps/ml/services/feature_service.py`

#### `compute_arima_residuals()` — 128줄 (신규 추가)

```python
def compute_arima_residuals(
    values: np.ndarray,
    arima_result,
) -> np.ndarray:
    new_result = arima_result.apply(endog=values.tolist())
    resid = np.asarray(new_result.resid, dtype=np.float64)
    return np.where(np.isnan(resid), 0.0, resid)
```

|줄|코드|설명|
|---|---|---|
|1|`arima_result.apply(endog=values.tolist())`|이미 학습된 ARIMA 파라미터를 새 데이터(values)에 적용. 새로 fit하지 않고 기존 계수로만 예측값 계산|
|2|`new_result.resid`|실제값 - ARIMA 예측값 = 잔차 배열. 값이 클수록 정상 패턴 이탈|
|3|`np.where(np.isnan(resid), 0.0, resid)`|첫 번째 원소는 ARIMA 특성상 NaN이 나올 수 있음 → 0으로 대체해 IF 학습 오류 방지|

**왜 잔차를 추가하는가?** ARIMA는 시계열의 정상 패턴(자기회귀 관계)을 학습. 잔차가 크면 정상 패턴을 크게 벗어난 것이므로 IF가 이 신호를 추가로 활용해 이상 탐지 정확도를 높일 수 있음.

---

#### `build_multi_features()` — 146줄 (수정)

**변경 전 시그니처:**

```python
def build_multi_features(series_list, gas_names, window=30, drop_warmup=True):
```

**변경 후 시그니처:**

```python
def build_multi_features(series_list, gas_names, window=30, drop_warmup=True,
                          arima_results: dict | None = None):
```

핵심 변경 부분:

```python
for gas_name, fm, series in zip(gas_names, fms, series_list):  # ① series 추가
    columns.extend(f"{gas_name}_{col}" for col in fm.columns)
    feature_parts.append(fm.features[-min_len:])
    if arima_results and gas_name in arima_results:             # ②
        resid = compute_arima_residuals(series.values, arima_results[gas_name])  # ③
        if drop_warmup:
            start = max(window - 1, 1)
            resid = resid[start:]                               # ④
        columns.append(f"{gas_name}_arima_resid")
        feature_parts.append(resid[-min_len:].reshape(-1, 1))  # ⑤
```

|번호|설명|
|---|---|
|①|기존엔 `zip(gas_names, fms)`였음. ARIMA 잔차 계산에 원본값(`series.values`)이 필요해 `series`도 함께 순회|
|②|`arima_results`가 None이거나 해당 가스 키가 없으면 건너뜀 → 12피처 그대로 유지 (하위 호환)|
|③|해당 가스의 ARIMA 잔차 전체 배열 계산|
|④|`drop_warmup=True`이면 워밍업 구간 제거 → 4피처 행렬 길이와 맞춤|
|⑤|`reshape(-1, 1)`: 1차원 배열을 열 벡터로 변환. `np.column_stack`으로 합칠 수 있게 만듦|

**핵심 설계 원칙:** 피처 순서가 학습(DRF)과 추론(FastAPI)에서 반드시 동일해야 함. `co_value → co_roll_mean_30 → co_roll_std_30 → co_diff → co_arima_resid → h2s_value → ...` 순서로 일치.

---

### 5-2. `drf-server/apps/ml/management/commands/train_arima_model.py` — (신규 파일)

#### 전체 흐름

```
add_arguments()  →  handle()
                      ├─ gas_names 파싱 및 유효성 검사
                      ├─ 날짜 파싱
                      └─ for gas_name in gas_names:
                             ├─ extract_normal_gas_series()   ← DB에서 정상 데이터 추출
                             ├─ values = series.values[-3000:]  ← 최근 3000개만 사용
                             ├─ model = ARIMA(values, order=(1,1,1))
                             ├─ result = model.fit()
                             └─ joblib.dump({"result": result, "order": order}, path)
```

#### `handle()` 주요 포인트

```python
values = series.values[-3000:].tolist()          # ①
model = ARIMA(values, order=order)               # ②
result = model.fit()                             # ③
joblib.dump({"result": result, "order": order}, file_path)  # ④
```

|번호|설명|
|---|---|
|①|데이터가 많을수록 ARIMA 학습 시간이 급증. 최근 3000개로 제한해 수 분 내 완료|
|②|ARIMA(p=1, d=1, q=1): 1틱 자기회귀, 1차 차분, 1틱 이동평균. 대부분의 가스 시계열에 적합한 기본값|
|③|MLE(최대우도법)으로 파라미터 추정. 완료 시 `ARIMAResultsWrapper` 객체 반환|
|④|`result`와 `order`를 dict로 묶어 pkl 저장. 로드 시 `joblib.load(path)["result"]`로 꺼냄|

---

### 5-3. `drf-server/apps/ml/management/commands/train_anomaly_model.py` — 169~183줄 (수정)

```python
_models_dir = Path(settings.ML_MODELS_DIR)
arima_results = {}
for _gn in gas_names:
    _p = _models_dir / f"arima_{_gn}.pkl"
    if _p.exists():                                           # ①
        arima_results[_gn] = joblib.load(_p)["result"]       # ②
        self.stdout.write(f"      ARIMA 로드: arima_{_gn}.pkl")
    else:
        self.stdout.write(self.style.WARNING(                 # ③
            f"      ARIMA 없음 (건너뜀): arima_{_gn}.pkl"))
fm = build_multi_features(
    series_list, gas_names, window=options["window"], drop_warmup=True,
    arima_results=arima_results if arima_results else None,   # ④
)
```

|번호|설명|
|---|---|
|①|pkl 파일이 없으면 건너뜀 → ARIMA 없이 12피처로 학습 가능. 실수로 빠뜨려도 서버가 죽지 않음|
|②|dict에서 `"result"` 키로 `ARIMAResultsWrapper`만 꺼냄. `"order"`는 학습 시 불필요|
|③|노란색 경고 출력 → 누락 여부를 콘솔에서 눈으로 확인 가능|
|④|`arima_results`가 빈 dict면 None 전달 → `build_multi_features`가 12피처로 폴백|

---

### 5-4. `fastapi-server/ai/router.py`

#### `_compute_arima_resid()` — 140줄 (신규 추가)

```python
def _compute_arima_resid(values: list[float], arima_result) -> float:
    try:
        new_result = arima_result.apply(endog=values)  # ①
        resid = float(new_result.resid[-1])             # ②
        return 0.0 if np.isnan(resid) else resid        # ③
    except Exception:
        return 0.0                                       # ④
```

|번호|설명|
|---|---|
|①|슬라이딩 윈도우 30개를 ARIMA에 적용해 잔차 배열 계산|
|②|배열의 **마지막 원소만** 꺼냄. 실시간 추론이므로 현재 틱의 잔차 1개만 필요|
|③|NaN이면 0 반환 (ARIMA 첫 원소 NaN 방어)|
|④|어떤 이유로든 실패하면 0 반환 → 추론 흐름이 끊기지 않음|

**`feature_service.py`의 `compute_arima_residuals()`와의 차이:**

|구분|`feature_service.py`|`ai/router.py`|
|---|---|---|
|반환값|전체 배열 (N,)|마지막 1개 float|
|용도|학습 시 전체 구간 잔차 계산|실시간 추론 시 현재 틱 잔차 1개|

---

#### `_build_multi_feature_row()` — 153줄 (수정)

**변경 전 시그니처:**

```python
def _build_multi_feature_row(windows, window) -> np.ndarray:
```

**변경 후 시그니처:**

```python
def _build_multi_feature_row(windows, window,
                              arima_results: dict | None = None) -> np.ndarray:
```

핵심 변경 부분:

```python
for gas_name, values in windows.items():
    arr = np.asarray(values[-window:], dtype=np.float64)
    roll_mean = float(arr.mean())
    roll_std  = float(arr.std(ddof=0))
    diff      = float(arr[-1] - arr[-2])
    parts.extend([float(arr[-1]), roll_mean, roll_std, diff])   # ①
    if arima_results and gas_name in arima_results:
        parts.append(_compute_arima_resid(values, arima_results[gas_name]))  # ②
return np.array([parts], dtype=np.float64)
```

|번호|설명|
|---|---|
|①|가스 4피처를 먼저 추가 (value, roll_mean, roll_std, diff)|
|②|ARIMA 잔차를 4피처 **바로 뒤에** 삽입 → `feature_service.py`의 학습 피처 순서와 완전히 동일|

> **주의:** 피처 순서가 학습과 추론에서 다르면 모델이 엉뚱한 피처를 보게 되어 이상 탐지 오작동 발생. 반드시 동일한 순서 유지.

---

### 5-5. `fastapi-server/gas/services/gas_service.py`

#### 모듈 레벨 ARIMA 로드 — 37~44줄

```python
_arima_models: dict = {}
for _gn in ["co", "h2s", "co2"]:
    _p = Path(settings.ML_MODELS_DIR) / f"arima_{_gn}.pkl"
    if _p.exists():
        try:
            _arima_models[_gn] = joblib.load(_p)["result"]  # ①
        except Exception:
            pass                                              # ②
```

|번호|설명|
|---|---|
|①|서버 시작 시 1회만 로드 → 이후 모든 요청에서 메모리의 객체 재사용. pkl 로드는 수백ms 소요이므로 요청마다 하면 응답 지연 발생|
|②|statsmodels 버전 문제 등으로 로드 실패해도 서버가 죽지 않음 → `_arima_models`가 비어있으면 자동으로 12피처 폴백|

#### `process_gas_data()` 내 추론 호출 변경 — 91~99줄

```python
row = _build_multi_feature_row(
    {
        "co": list(_co_window),
        "h2s": list(_h2s_window),
        "co2": list(_co2_window),
    },
    entry.window,
    arima_results=_arima_models if _arima_models else None,  # ①
)
```

|번호|설명|
|---|---|
|①|`_arima_models`가 비어있으면 None → 12피처 추론. 3개 가스 모두 있으면 15피처 추론|

---

## 6. 팀원·팀장 환경 설정 가이드

> 처음 환경을 세팅하거나, 브랜치를 Pull 받아 실행하는 팀원·팀장을 위한 가이드입니다.

### 전제 조건

- Docker Desktop 또는 Docker Engine + Compose 설치 완료
- 프로젝트 루트 기준 (`docker-compose.yml`이 있는 폴더)

---

### STEP 0 — 코드 받기

```bash
git fetch origin
git checkout feature/0511_gas_scenario_dummy
git pull
```

---

### STEP 1 — Docker 이미지 재빌드

`requirements.txt`가 변경됐으므로 반드시 재빌드해야 합니다. 재빌드 없이 실행하면 `statsmodels`, `pandas` 버전이 맞지 않아 FastAPI가 기동하지 않습니다.

```bash
docker compose up -d --build drf fastapi
```

**빌드 완료 확인:**

```bash
docker compose ps
```

`drf`, `fastapi` 모두 `Up` 상태여야 합니다.

---

### STEP 2 — FastAPI statsmodels 임포트 확인

```bash
docker compose exec fastapi python -c "from statsmodels.tsa.arima.model import ARIMA; print('OK')"
```

`OK`가 출력되면 정상입니다. 오류가 나오면 아래를 확인하세요.

```bash
# pandas 버전이 2.x 인지 확인 (3.x 이면 재빌드 필요)
docker compose exec fastapi pip show pandas | grep Version
# → 2.3.3 이어야 함
```

---

### STEP 3 — ARIMA 모델 학습

ARIMA pkl 파일이 없으면 IF를 15피처로 학습할 수 없습니다. DRF 컨테이너에서 실행합니다.

```bash
docker compose exec drf python manage.py train_arima_model \
    --sensor-id 1 \
    --gas-names co,h2s,co2 \
    --since 2026-05-06 \
    --until 2026-05-17
```

**완료 메시지:**

```
[co] 저장 완료 → /app/ml_models/arima_co.pkl
[h2s] 저장 완료 → /app/ml_models/arima_h2s.pkl
[co2] 저장 완료 → /app/ml_models/arima_co2.pkl
전체 ARIMA 학습 완료
```

> `--since`와 `--until`은 DB에 실제 데이터가 있는 기간으로 설정하세요. 데이터가 없으면 `데이터 부족: 0개 (최소 50개)` 오류가 납니다.

---

### STEP 4 — IsolationForest 15피처 학습

ARIMA pkl이 준비됐으면 IF를 15피처로 학습합니다.

```bash
docker compose exec drf python manage.py train_anomaly_model \
    --sensor-type gas \
    --sensor-id 1 \
    --gas-name co,h2s,co2 \
    --since 2026-05-06 \
    --until 2026-05-17 \
    --contamination 0.01 \
    --activate
```

**출력에서 반드시 확인할 것:**

```
[2/5] feature engineering — window=30
      ARIMA 로드: arima_co.pkl
      ARIMA 로드: arima_h2s.pkl
      ARIMA 로드: arima_co2.pkl
      feature shape = (XXXX, 15), columns = ['co_value', ..., 'co2_arima_resid']
```

- `feature shape`의 두 번째 숫자가 **15**여야 합니다.
- 12이면 ARIMA pkl이 로드되지 않은 것 → STEP 3 재확인.

---

### STEP 5 — FastAPI 모델 캐시 갱신

IF가 새 모델로 학습됐으므로 FastAPI에서 메모리에 올라온 이전 모델을 교체합니다.

```bash
curl -X POST "http://localhost:8001/ai/reload?sensor_type=gas"
```

**성공 응답:**

```json
{"reloaded": true, "sensor_type": "gas"}
```

---

### STEP 6 — 추론 동작 확인

더미 시뮬레이터로 가스 데이터를 전송해 이상 감지가 작동하는지 확인합니다.

```bash
# 더미 실행
docker compose exec -e PYTHONPATH=/app fastapi python dummies/gas_dummy.py

# 이상 시나리오 전환 (다른 터미널에서)
curl -X POST "http://localhost:8001/internal/scenario/mode" \
     -H "Content-Type: application/json" \
     -d '{"mode": "co_leak"}'

# 이상 감지 로그 확인 (30개 쌓이면 추론 시작)
docker compose logs fastapi --tail=50 | grep "AI 이상탐지"
```

**정상 작동 로그:**

```
WARNING  gas_service:[AI 이상탐지] co+h2s+co2 이상 감지 | device=1 | co=... h2s=... co2=...
```

---

### 전체 플로우 요약

```
git pull
    ↓
docker compose up -d --build drf fastapi
    ↓
statsmodels 임포트 확인 → OK
    ↓
train_arima_model  (ARIMA 3개 pkl 생성)
    ↓
train_anomaly_model --activate  (IF 15피처 학습 + 활성화)
    ↓
curl /ai/reload?sensor_type=gas  (캐시 갱신)
    ↓
더미 실행 + 로그 확인  (이상탐지 동작 검증)
```

---

### 자주 나오는 오류와 해결책

|오류|원인|해결|
|---|---|---|
|`deprecate_kwarg() missing 1 required positional argument`|FastAPI pandas 버전이 3.x|`docker compose up -d --build fastapi`|
|`permission denied: /app/entrypoint.sh`|entrypoint.sh에 실행 권한 없음|`chmod +x fastapi-server/entrypoint.sh` 후 재빌드|
|`feature shape = (XXXX, 12)` (15여야 함)|ARIMA pkl 없거나 로드 실패|STEP 3 `train_arima_model` 재실행|
|`데이터 부족: 0개 (최소 50개)`|`--since`/`--until` 범위에 DB 데이터 없음|날짜 범위를 데이터가 있는 기간으로 변경|
|`ModuleNotFoundError: No module named 'core'`|더미 실행 경로 문제|`-e PYTHONPATH=/app` 추가|
|`/internal/scenario/mode` 404|URL 오타|엔드포인트 정확한 경로: `/internal/scenario/mode`|
