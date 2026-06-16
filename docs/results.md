# 핵심 성과 (검증 결과 요약)

> 모든 수치는 **데모/스터디 환경(단일 머신·더미 IoT) 측정값**이며 운영 벤치마크가 아닙니다.
> 방법과 도구를 함께 표기해 재현 가능하도록 정리합니다.

---

## 1. 부하 테스트 — 가스 병목 진단 & 개선

**도구**: [iot_load_test.py](../fastapi-server/dummies/iot_load_test.py) — N개 가상 IoT 기기가 1초마다 동시에 FastAPI로 POST, 기기 수를 단계별로 올리며 p95·RPS·에러율 측정 (`make iot-seed-devices gas=N power=N`으로 기기 수 조절).

**문제 (before)** — 50대 동시 가스 송신 시 *congestion collapse*: 단일 DRF 워커 + 무거운 가스 엔드포인트 + 동기 forward가 겹쳐 요청이 직렬화되고, RPS가 20대(12.8)보다 50대(8.5)에서 **오히려 하락**.

**개선 후 (after) — 50대 동시:**

| 지표 | before | after | 변화 |
|---|---|---|---|
| 가스 p95 | 4,197 ms | 892 ms | **4.7배 ↓** |
| 가스 RPS | 8.5 | 33.3 | **3.9배 ↑** |
| 에러율 | 91% | 0% | **소멸** |
| FastAPI→DRF forward timeout | ~21/s | 0 | **소멸** |

- 가스 RPS 궤적: before `2.9→8.2→12.8→8.5`(20대서 꺾여 붕괴) → after `4.7→9.4→17.6→33.3`(단조 상승).
- **전력은 fire-and-forget + 0.5s race forward** 설계 덕에 5→50대까지 p95 155ms 이내·에러 0으로 **선형 확장** — 부하 내성이 설계 효과.
- 개선 후 병목은 "가스 per-request 비효율" → "공유 머신 자원 천장"으로 이동 → 다음 단계 = 수평 확장(replica).
- 가스 에러의 실체는 서버 크래시가 아니라 **client 5s timeout**("느려서 포기") — 진단 단계에서 구분.

---

## 2. AI 이상탐지 정확도 (오프라인 재현)

**방법**: 라벨(`is_anomaly`) vs 모델 출력을 행별 혼동행렬로 비교. 운영과 동일한 모델 `.pkl` + feature_service로 오프라인 재현.

| 도메인 | recall | 비고 |
|---|---|---|
| 가스 (IsolationForest) | 0.65 | `co_leak` 약점 · FP 18.8% |
| 전력 (5축) | 0.87 | FP 34% |

- **야간 격상 룰 제거 시 오탐 34% → 3% (약 10배 ↓)**, 탐지율은 유지 — 가장 큰 개선 포인트.
- 전력 주력 판정은 threshold 룰(정격 %), AI는 보조. ARIMA 조기예측 리드타임은 작음(데이터-목표 불일치) — 과장 없이 표기.

---

## 3. 관측성 (Observability)

- Prometheus가 6개 타깃(`drf`·`fastapi`·`node`·`postgres`·`redis`·`prometheus`)을 scrape, 전부 `up`.
- Grafana 대시보드로 HTTP·Celery 큐·DB·AI 추론 메트릭 시각화.
- `prometheus-client` 멀티프로세스 모드 — gunicorn·celery 워커 메트릭을 `/metrics`에서 합산 노출.

---

## 4. 인프라 개선

- **SQLite → PostgreSQL 16** 전환 (`CONN_MAX_AGE=60` 연결 재사용).
- **Celery 단일 워커 → alarm/metric 큐 분리** — 실시간 알람이 주기 메트릭 수집에 밀리지 않도록.
- 데이터 수명 3계층(보관 정책) + `RotatingFileHandler` 파일 로그(시연·사고 추적).

---

> 더 큰 규모(예: 80대)의 부하 테스트 결과가 확보되면 §1 표에 추가합니다.
