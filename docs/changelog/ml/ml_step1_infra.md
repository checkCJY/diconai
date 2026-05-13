# ML 트랙 STEP 1 — IF 이상탐지 인프라 (학습·추론 동작)

> **2026-05-13 업데이트**: 가스 도메인 분기는 [`gas_phase3.md`](gas_phase3.md) (G7/G8) 에서 활성화 — 본 STEP 1 인프라가 이제 전력/가스 두 도메인 모두 사용 가능.

> **요약 한 줄**: `apps/ml/` Django 앱과 `fastapi-server/ai/` 라우터를 신설해 sklearn IsolationForest 학습 → .pkl 저장 → MLModel 메타 → FastAPI 실시간 추론까지 end-to-end 동작하는 인프라를 구축한다. sensor_type 분리로 전력/가스 양 도메인이 같은 ml 앱을 공유한다.

**브랜치**: `feature/power_refactory` (Phase 3 후속) · **상세 plan**: [skill/plan/if-integration-guide.md](../../../skill/plan/if-integration-guide.md) §1단계 · **선행**: 전력 Phase 3 (라벨 데이터 인프라, [`power_phase3.md`](../power_phase1_2/power_phase3.md))

---

## 왜 이 작업을 했나

### Phase 3 종료 시점 한계

| 항목 | Phase 3 종료 시점 | STEP 1 미해결 |
|---|---|---|
| 학습 데이터 | 정상 263k / 라벨 9.7k 적재 | 정상 row를 모델로 학습할 인프라 부재 |
| 추론 결과 영속 | — | 추론 결과(score/prediction) 저장 모델 없음 |
| 모델 메타 추적 | — | 학습 이력(파라미터·데이터 범위·버전) 영속 안 됨 |
| 실시간 추론 경로 | — | Django ML 계산이 메인 API 흐름을 막을 위험 |

### 코드 검토에서 확인한 결함 5가지

| # | 문제 | 영향 |
|---|---|---|
| 1 | sklearn / joblib / numpy 의존성 없음 | 학습/추론 자체 불가 |
| 2 | 모델 파일 저장 표준 부재 | 학습마다 별도 위치 → 일관성 깨짐 |
| 3 | drf와 fastapi 간 모델 파일 공유 경로 부재 | docker 환경에서 fastapi가 drf의 .pkl 접근 불가 |
| 4 | feature engineering 표준 없음 | 학습/추론이 다른 수식이면 모델 무효 |
| 5 | 가스 트랙과 ml 앱 인터페이스 합의 부재 | 양 도메인이 ml 앱에 코드 추가 시 충돌 위험 |

### 도메인 협업 결정 (가스 트랙과 공유)

가스 인원도 같은 ml 앱을 사용하기로 결정. ml 앱 설계 원칙:

1. **`MLModel.sensor_type` = power|gas** 분리 — 학습 모델·active row 모두 sensor_type 별
2. **`MLAnomalyResult.sensor_identifier`** — 도메인 무관 자유 문자열 (예: `power:device_1:ch3:watt`, `gas:co`)
3. **dataset_service** 는 도메인별 함수로 분리 (`extract_normal_power_series`, 가스는 `extract_normal_gas_series` 추가)
4. **feature_service** 는 도메인 무관 — numpy 1D 시계열만 받음
5. **train_anomaly_model** 커맨드는 `--sensor-type power|gas` 옵션으로 generic

가스 인원이 자기 트랙(Phase 3 동등 작업 = GasData 라벨 필드 + gas_dummy 라벨 송신)을 끝낸 후, `dataset_service.py`에 `extract_normal_gas_series()` 함수 한 개만 추가하면 학습/추론 파이프라인이 그대로 동작.

---

## 핵심 결정사항

| 결정 사항 | 채택안 | 근거 |
|---|---|---|
| ml 앱 위치 | **`drf-server/apps/ml/` 별도 Django 앱** | monitoring/facilities 와 분리 — ML 변경이 운영 도메인을 흔들지 않게 |
| 모델 .pkl 저장 경로 | **`settings.ML_MODELS_DIR` (default `BASE_DIR/ml_models`)** + 권한 0700 + .gitignore | MEDIA_ROOT 밖, 웹 서버 서빙 차단 (skill 보안 권고). dev 환경엔 `drf-server/ml_models/` 사용 |
| drf↔fastapi 모델 공유 | **docker-compose volume `./drf-server/ml_models:/app/ml_models:ro`** | drf가 학습·쓰기, fastapi 는 읽기만 (read-only 마운트). named volume 대신 host bind 로 백업 용이 |
| 모델 메타 조회 경로 | **`GET /api/ml/models/active/?sensor_type=power`** (DRF API) | fastapi가 active 모델 메타 조회 → file_path/version 으로 .pkl 로드. Django ORM 직접 의존성 회피 |
| feature engineering 수식 | **roll_mean / roll_std / diff (window=30 기본)** + `drop_warmup=True` | skill STEP 2 sliding window 패턴. NaN 행을 학습 입력에서 제외 — sklearn 거부 회피 |
| 모델 캐시 | **fastapi 프로세스 메모리 + threading.Lock + TTL 3600s** | 요청마다 .pkl 로드는 지연. TTL 만료 또는 `/ai/reload` 수동 호출로 재로드 |
| feature 추론 수식 위치 | **fastapi `_build_feature_row()` inline 구현** (drf feature_service 와 동일 시맨틱) | 추론 시 drf 의존성 분리. 단점: 두 곳 동기화 책임 — docstring 명시 |
| 가스 추가 절차 | **dataset_service docstring 에 3단계 가이드 명시** | placeholder 함수 두지 않고 가이드만 — 가스 인원이 자기 도메인 작업 후 자연스럽게 추가 |
| dev 의존성 | **drf-server/requirements-dev.txt 에 `jupyterlab`/`matplotlib`/`pandas`** | production 이미지엔 미포함. EDA 시점에 `pip install -r requirements-dev.txt` |

---

## 단계별 변경 (C1~C7)

본 STEP 1 은 단일 PR. C1~C7 로직 단위 분할.

### C1 — `apps/ml/` Django 앱 골격 + INSTALLED_APPS

**무엇**
- 신규 `drf-server/apps/ml/{__init__.py,apps.py}` — `MlConfig` (BigAutoField, name='apps.ml')
- 폴더 구조: `models/`, `services/`, `tasks/`, `management/commands/`, `migrations/`
- 수정 [drf-server/config/settings.py](../../../drf-server/config/settings.py) — `INSTALLED_APPS` 에 `apps.ml` 추가 + `ML_MODELS_DIR` env 변수 등록

**왜**
- ML 변경이 monitoring/facilities 같은 운영 도메인을 흔들지 않게 분리
- 폴더 구조는 monitoring 앱 패턴과 동일 — 가스 트랙이 추가할 위치 명확

### C2 — `MLModel` 모델 (학습 메타 영속)

**무엇**
- 신규 [drf-server/apps/ml/models/ml_model.py](../../../drf-server/apps/ml/models/ml_model.py)
  - `SensorType` (power/gas) · `ModelType` (isolation_forest)
  - `version`, `file_path`, `feature_columns`(JSON), `params_json`(JSON), `is_active`
  - `training_data_range_from/to`, `training_sample_count`, `trained_at`
  - `UniqueConstraint(sensor_type, version)` + 인덱스 2건
- 신규 [drf-server/apps/ml/models/ml_anomaly_result.py](../../../drf-server/apps/ml/models/ml_anomaly_result.py)
  - `Prediction` (normal/anomaly) · `RiskClassified` (normal/caution/predict_warn/danger)
  - `ml_model` FK (SET_NULL) + `model_version_snapshot` (모델 삭제되어도 버전 보존)
  - `sensor_type` + `sensor_identifier` (도메인 무관 자유 키)
  - `anomaly_score`, `feature_snapshot_json`(디버깅용)
- 마이그 0001_initial 자동 생성·적용 (Django 6 makemigrations)

**왜**
- `MLModel.is_active` — sensor_type 별 활성 모델 1개 추적. `--activate` 옵션으로 명시 활성화
- `MLAnomalyResult.sensor_identifier` 자유 문자열 — 가스/위치 등 추가 센서 도메인 들어와도 스키마 변경 없음
- `model_version_snapshot` — 운영자가 MLModel row 삭제하더라도 추론 이력의 버전 정보는 보존

### C3 — `dataset_service.py` + 가스 협업 가이드

**무엇**
- 신규 [drf-server/apps/ml/services/dataset_service.py](../../../drf-server/apps/ml/services/dataset_service.py)
  - `TimeSeries` dataclass (sensor_identifier, measured_at, values, is_anomaly, anomaly_type)
  - `extract_normal_power_series(device_id, channel, data_type, since, until)` — `is_anomaly=False AND value > 0` (통신불능 -1 제외)
  - `extract_labeled_power_series(...)` — `is_anomaly=True` 평가용
  - `_to_arrays()` 헬퍼 — QuerySet → numpy 배열 일괄 변환

**가스 도메인 추가 가이드 (모듈 docstring 명시)**
1. GasData 모델에 `is_anomaly`/`anomaly_type` + 마이그 (전력 Phase 3 패턴 복제)
2. 본 파일에 `extract_normal_gas_series(gas_type, since, until)` 함수 추가
3. ml 앱 자체는 도메인 무관 — train_anomaly_model 이 `--sensor-type gas` 분기 활성화

**왜**
- pandas 의존성 회피 — numpy 1D 배열로 feature_service 와 통합
- 도메인별 함수 분리 — 가스 인원 추가 시 merge 충돌 영역 최소화

### C4 — `feature_service.py` (도메인 무관 sliding window)

**무엇**
- 신규 [drf-server/apps/ml/services/feature_service.py](../../../drf-server/apps/ml/services/feature_service.py)
  - `FeatureMatrix` dataclass (columns, features, measured_at, is_anomaly)
  - `build_features(series, window=30, drop_warmup=True)` — value / roll_mean / roll_std / diff 4 컬럼
  - `_rolling_mean` (cumsum O(N)) / `_rolling_std` (ddof=0) / `_first_diff`

**왜**
- skill STEP 2 sliding window 패턴 — IF 가 시간 종속성 학습할 수 있게
- 도메인 무관 (numpy 1D 입력만) — 가스/전력 동일 호출
- `drop_warmup=True` — sklearn 이 NaN 입력 거부하므로 워밍업 구간(앞 window-1 행) 제외

### C5 — `train_anomaly_model` management command

**무엇**
- 신규 [drf-server/apps/ml/management/commands/train_anomaly_model.py](../../../drf-server/apps/ml/management/commands/train_anomaly_model.py)
  - argparse: `--sensor-type` `--device-id` `--channel` `--data-type` `--since` `--until` `--window 30` `--contamination 0.01` `--n-estimators 100` `--random-state 42` `--activate`
  - 5단계 흐름: dataset 추출 → feature engineering → IsolationForest fit → joblib.dump → MLModel row 생성
  - `--activate` 지정 시 동일 sensor_type 의 기존 활성 모델 자동 비활성화 (transaction.atomic)
  - 학습 후 in-sample 예측으로 anomaly 비율 + score range 출력

**예시 호출**
```bash
python manage.py train_anomaly_model \
    --sensor-type power --device-id 1 --channel 3 --data-type watt \
    --since 2026-05-12 --until 2026-05-14 \
    --contamination 0.01 --activate
```

**왜**
- 학습은 오프라인 (Celery beat 자동화는 STEP 3) — 운영자가 데이터 분포 보고 contamination 조정
- 모델 파일과 MLModel row 가 1:1 — joblib.dump 실패 시 row 도 안 생성 (transaction.atomic)

### C6 — DRF active 모델 메타 API

**무엇**
- 신규 [drf-server/apps/ml/views.py](../../../drf-server/apps/ml/views.py) — `ActiveMLModelView` (`RetrieveAPIView`)
  - `GET /api/ml/models/active/?sensor_type=power` 응답: `{id, version, file_path, feature_columns, params_json, ...}`
- 신규 [drf-server/apps/ml/urls.py](../../../drf-server/apps/ml/urls.py) — `models/active/` 경로
- 수정 [drf-server/config/urls.py](../../../drf-server/config/urls.py) — `path("api/ml/", include("apps.ml.urls"))`

**왜**
- fastapi 가 Django ORM 직접 의존하지 않게 (서비스 분리)
- 운영자가 어드민에서 활성 모델 교체 → fastapi 캐시 만료 시 자동 반영

**알려진 보안 위험 (STEP 2 후속)**
- 현재 `permission_classes=[]` — 내부망 가정. 운영 진입 시 `INTERNAL_SERVICE_TOKEN` 권장 (drf↔fastapi 공유)

### C7 — FastAPI `ai/router.py` (실시간 추론 + 모델 캐시)

**무엇**
- 신규 [fastapi-server/ai/router.py](../../../fastapi-server/ai/router.py)
  - `_CachedModel` — model + feature_columns + window + version + loaded_at
  - `_get_or_load(sensor_type)` — TTL 만료 시 `GET /api/ml/models/active/` → joblib.load
  - `_build_feature_row()` — 추론 1회용 (value, roll_mean, roll_std, diff) 산출 — drf feature_service 와 동일 시맨틱
  - `POST /ai/predict` — `{sensor_type, sensor_identifier, window_values}` → `{anomaly_score, prediction, model_version, features}`
  - `POST /ai/reload?sensor_type=power` — 학습 직후 강제 무효화
- 수정 [fastapi-server/app.py](../../../fastapi-server/app.py) — ai_router include + "ai" 태그
- 수정 [fastapi-server/core/config.py](../../../fastapi-server/core/config.py) — `ML_MODELS_DIR`, `ML_MODEL_CACHE_TTL_SEC` 환경 변수

**왜**
- skill 권고 — Django ML 계산이 메인 API 흐름 막지 않도록 fastapi 분리
- 모델 프로세스 메모리 캐시 — 요청마다 .pkl 로드 시 추론 지연 (불필요한 disk I/O)
- `_build_feature_row` inline — drf ORM 의존성 없이 fastapi 단독 추론 가능
- **알려진 동기화 책임**: drf `feature_service.build_features` 수식 변경 시 본 함수도 같이 수정 필수 (docstring 명시)

---

## 인프라 영구화 (의존성·볼륨·gitignore)

| 항목 | 변경 | 위치 |
|---|---|---|
| drf 의존성 (production) | `numpy==2.4.4`, `scikit-learn==1.8.0`, `joblib==1.5.3` 추가 | `drf-server/requirements.txt` |
| drf 의존성 (dev/EDA) | `jupyterlab==4.4.10`, `matplotlib==3.10.5`, `pandas==2.3.4` 추가 | `drf-server/requirements-dev.txt` |
| fastapi 의존성 | `numpy`, `scikit-learn`, `joblib`, `requests` 추가 (추론용) | `fastapi-server/requirements.txt` |
| docker volume | fastapi 에 `./drf-server/ml_models:/app/ml_models:ro` 추가 | `docker-compose.yml` |
| gitignore | `drf-server/ml_models/`, `fastapi-server/ml_models/` 추가 | `.gitignore` |

**재빌드 절차** (운영자/협업자 가이드)
```bash
docker compose build drf fastapi
docker compose up -d
# dev EDA 필요시:
docker exec diconai-drf-1 pip install -r requirements-dev.txt
docker exec -d -p 8888:8888 diconai-drf-1 jupyter lab --ip=0.0.0.0 --no-browser --allow-root
```

---

## 검증 결과

### 학습 검증 (MLModel v1 생성)

```bash
python manage.py train_anomaly_model \
    --sensor-type power --device-id 1 --channel 3 --data-type watt \
    --since 2026-05-12 --until 2026-05-14 \
    --contamination 0.01 --activate
```

| 단계 | 결과 |
|---|---|
| dataset 추출 | 4068 raw rows (ch3 정상 watt 데이터, sensor_identifier=`power:device_1:ch3:watt`) |
| feature engineering | (4039, 4) — `[value, roll_mean_30, roll_std_30, diff]` |
| IF fit | contamination=0.01, n_estimators=100, n_jobs=-1 |
| 산출물 | `drf-server/ml_models/power_if_v1.pkl` + `MLModel.id=1` + is_active=True |
| in-sample anomaly | **41 / 4039 = 1.02%** (contamination 1.00% 설정과 정확히 일치) |
| score range | [-0.0528, 0.2504] |

### 추론 검증 (fastapi `/ai/predict`)

| 시나리오 | window_values 끝값 | 결과 |
|---|---|---|
| 정상 baseline (ch3 야간 기저 부하 27%) | 1500W | `score=0.0814, prediction=normal` ✓ |
| drift 4400W plateau (학습 분포 밖) | 4400W (15틱 연속) | `score=-0.0195, prediction=anomaly` ✓ |
| 단일 spike (1500→6050 1회) | 6050W | `prediction=normal` — 단일 튐은 roll_mean 평균이 끌어내려 못 잡음. **이상 run 이 30틱 누적되면 잡힘** (의도된 모델 특성) |

### 인프라 검증

- DRF `/api/ml/models/active/?sensor_type=power` → 200 OK + active 모델 메타 JSON
- fastapi 컨테이너에서 `/app/ml_models/power_if_v1.pkl` read-only 마운트 확인
- fastapi 재기동 후 `/ai/predict` 동일 score (캐시 일관성)

---

## 알려진 제약 / 후속 작업

| # | 항목 | 본 STEP 처리 | 후속 |
|---|---|---|---|
| 1 | 가스 도메인 학습 | NotImplementedError 명시 | 가스 트랙 Phase 3 동등 작업 후 `extract_normal_gas_series` 추가 |
| 2 | DRF active 모델 API 인증 | `permission_classes=[]` (내부망 가정) | STEP 2 — `INTERNAL_SERVICE_TOKEN` 검증 추가 |
| 3 | 단일 spike 미감지 | 모델 한계 (roll_mean 평균 효과) | STEP 3 ARIMA + Change Point Detection 결합 |
| 4 | feature 수식 drf↔fastapi 중복 | inline 구현 (docstring 동기화 책임 명시) | 공통 utility 패키지 추출 검토 (별도 sprint) |
| 5 | 모델 캐시 evict 자동화 | `/ai/reload` 수동 호출 또는 TTL 만료 | drf 학습 후 자동으로 fastapi reload 호출 (Celery → HTTP) |
| 6 | 재학습 자동화 | 수동 커맨드 | STEP 3 — Celery beat 야간 1회 |
| 7 | 알람 연동 | 추론만 — 알람 발화 없음 | **STEP D (전력 §4-2) — 결합 매트릭스 4단계 분류** |

---

## 변경 파일 요약

| 영역 | 파일 | 변경 유형 | 라인 (대략) |
|---|---|---|---|
| DRF 앱 골격 | `apps/ml/{__init__.py, apps.py}` | 신규 | +9 |
| DRF 모델 | `apps/ml/models/ml_model.py` | 신규 | +80 |
| DRF 모델 | `apps/ml/models/ml_anomaly_result.py` | 신규 | +85 |
| DRF 마이그 | `apps/ml/migrations/0001_initial.py` | 자동 생성 | +65 |
| DRF 서비스 | `apps/ml/services/dataset_service.py` | 신규 | +110 |
| DRF 서비스 | `apps/ml/services/feature_service.py` | 신규 | +125 |
| DRF 커맨드 | `apps/ml/management/commands/train_anomaly_model.py` | 신규 | +190 |
| DRF API | `apps/ml/views.py` + `apps/ml/urls.py` | 신규 | +50 |
| DRF 설정 | `config/settings.py` | INSTALLED_APPS + ML_MODELS_DIR | +5 |
| DRF 설정 | `config/urls.py` | api/ml/ include | +1 |
| FastAPI 라우터 | `ai/router.py` | 신규 | +190 |
| FastAPI 앱 | `app.py` | ai_router + tag | +3 |
| FastAPI 설정 | `core/config.py` | ML_MODELS_DIR, cache TTL | +7 |
| 의존성 | `drf-server/requirements.txt` | numpy/sklearn/joblib | +3 |
| 의존성 | `drf-server/requirements-dev.txt` | jupyterlab/matplotlib/pandas | +5 |
| 의존성 | `fastapi-server/requirements.txt` | numpy/sklearn/joblib/requests | +4 |
| 인프라 | `docker-compose.yml` | fastapi volume (drf-server/ml_models:ro) | +3 |
| 인프라 | `.gitignore` | drf-server/ml_models/ + fastapi-server/ml_models/ | +4 |

**총**: 약 17 files, +939 insertions

---

## 다음 단계

- **STEP C (본학습 + detection rate 검증)**: 라벨 9.7k 중 시나리오별 100건 이상으로 detection rate 측정. 모델 v2 학습 시 contamination 조정 결정
- **STEP D (전력 §4-2 알람 연동)**: `evaluate_power_risk()` dict 반환 확장 + 결합 매트릭스 4단계 분류 + Phase 1 `try_transition` 키 분리 (`:threshold` / `:anomaly`)
- **STEP E (E2E 검증)**: 임계치 주석 토글로 AI 단독 알람 동작 확인 + 회귀 테스트

상세 가이드: [skill/plan/if-integration-guide.md](../../../skill/plan/if-integration-guide.md) §2단계
