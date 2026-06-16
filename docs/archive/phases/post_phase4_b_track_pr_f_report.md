# B 운영 트랙 PR-F — fastapi-server pytest 인프라 + 스모크 테스트

> 작업일: 2026-05-09
> 브랜치: `feature/0508_refactory`
> 부모 plan: [`~/.claude/plans/b-cozy-panda.md`](../../../home/cjy/.claude/plans/b-cozy-panda.md) §3 PR-F
> 직전 PR: [post_phase4_b_track_pr_e_report.md](post_phase4_b_track_pr_e_report.md) (`af80d69`)

---

## 1. 작업 목적

fastapi-server 측에 단위 테스트 인프라 부재 — 회귀 점검 Step 3에서 drf-server는 pytest 도입 완료(56 tests)이지만 fastapi-server는 0 tests. drf-server 패턴 차용해 pytest + pytest-asyncio 도입 + 1차 스모크 테스트 11종.

---

## 2. 검증 결과

| 항목 | 명령 | 결과 |
|---|---|---|
| pytest 신규 (fastapi) | `cd fastapi-server && .venv/bin/pytest` | ✅ **22 passed** (12 가스 임계치 + 4 위치 스키마 + 3 drf_client + 3 status max_risk) |
| pytest 회귀 (drf-server) | `cd drf-server && .venv/bin/pytest` | ✅ **56 passed** (영향 0) |
| pre-commit | `pre-commit run --files <변경파일>` | ✅ Passed |

### 누적
- fastapi-server: **22 tests** (신규)
- drf-server: **56 tests** (Step 3 + B-track PR-A~E 회귀 유지)

---

## 3. 변경 파일 (신규 7개)

### 3-1. 인프라

| 파일 | 역할 |
|---|---|
| [fastapi-server/pytest.ini](../../../fastapi-server/pytest.ini) | `asyncio_mode = auto` (pytest-asyncio 자동 모드) + 디스커버리 패턴 + `--strict-markers` |
| [fastapi-server/conftest.py](../../../fastapi-server/conftest.py) | placeholder docstring (단위 테스트 위주, 외부 의존 없음). 추후 통합 테스트 도입 시 httpx mock fixture 확장 |
| [fastapi-server/requirements-dev.txt](../../../fastapi-server/requirements-dev.txt) | `pytest==9.0.3`, `pytest-asyncio==1.3.0` |
| [fastapi-server/tests/__init__.py](../../../fastapi-server/tests/__init__.py) | namespace package → 일반 패키지 (drf-server 패턴 일관) |

### 3-2. 스모크 테스트 (3개 — 22 tests)

| 파일 | 회귀 커버 |
|---|---|
| [tests/test_gas_thresholds.py](../../../fastapi-server/tests/test_gas_thresholds.py) | `evaluate_single_gas` 12 분기 (parametrize) + max_risk 합성 + lel 제외 + 9종 키 일관 |
| [tests/test_position_schema.py](../../../fastapi-server/tests/test_position_schema.py) | WorkerPositionSchema `node_id` Optional + x/y >= 0 + movement_status default |
| [tests/test_drf_client.py](../../../fastapi-server/tests/test_drf_client.py) | INTEGRATION_LOG_PATH 자체 호출 시 IntegrationLog 기록 skip (재귀 회피) + fire-and-forget silent fail + 일반 경로 호출 시 IntegrationLog 기록 |

---

## 4. 사용자 결정 사항

본 PR은 plan §3 PR-F 그대로 진행. 결정 사항 없음.

drf-server 패턴 차용:
- pytest 9.0.3 + pytest-asyncio (drf-server는 pytest-django, fastapi는 pytest-asyncio)
- `pytest.ini` (drf-server는 DJANGO_SETTINGS_MODULE, fastapi는 asyncio_mode)
- `conftest.py` placeholder
- `tests/test_*.py` 패턴

---

## 5. 발견 사항 / 주의

### 5-1. 단위 테스트 위주 (1차 스모크)
본 PR은 단위 테스트만 — 외부 의존 없음:
- `evaluate_single_gas` 순수 함수
- `WorkerPositionSchema` Pydantic 검증
- `_record_integration_log` httpx mock

통합 테스트(FastAPI app + DRF mock + WS broadcast)는 별도 트랙 — plan §7 후속.

### 5-2. asyncio_mode = auto
`pytest-asyncio` 자동 모드 — `@pytest.mark.asyncio` 명시 불필요 (auto 적용). drf_client 비동기 함수 테스트 단순화.

### 5-3. DRF 측 임계치 일관 검증
[tests/test_gas_thresholds.py::test_evaluate_single_gas_matches_drf_thresholds](../../../fastapi-server/tests/test_gas_thresholds.py)는 fastapi `GAS_THRESHOLDS`와 DRF `threshold_default.json`이 동일 분기 결과를 내는지 12 케이스 검증. 단일 진실 공급원 정책 위반 시 본 테스트가 실패.

### 5-4. drf-server 영향 0 확인
fastapi-server 변경은 drf-server 측 코드/테스트에 영향 없음. 회귀 점검 Step 3의 56 tests 그대로 통과.

---

## 6. 다음 단계

PR-G (Threshold facility별 정책) 진입. 본 PR은 fastapi-server 독립 — drf-server 트랙(PR-G) 병렬 가능했으나 의존 그래프상 PR-A~E 후 진행됨.

---

## 7. 누적 결과

| PR | commit | 변경 |
|---|---|---|
| PR-A | `f4b50d0` | fixture 시드 마이그 historical apps 패턴 |
| PR-B | `7207a4c` | BaseModel 컨벤션 10개 모델 |
| PR-C | `81e70de` | DataRetentionPolicy + AlertPolicy 시드 |
| PR-D | `cdbeddd` | AppLog/IntegrationLog Celery 비동기 |
| PR-E | `af80d69` | GasTypeChoices.LEL dead code 제거 |
| **PR-F** | (본 commit) | fastapi-server pytest 인프라 + 22 스모크 테스트 |

**누적 pytest**: drf-server 56 + fastapi-server 22 = **78 tests**
