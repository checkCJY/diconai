# 데이터베이스 설계

> 센서 JSON → 검증 → DB 저장 → 위험 판단·AI 결과 분리 저장 구조.
> 상세 필드 정의: [docs/specs/json_fields_specification.md](specs/json_fields_specification.md)

---

## 무엇을 수행하는가

외부 유해가스 센서 및 스마트 파워 시스템에서 수신되는 JSON 데이터를 검증 후 PostgreSQL에 저장하고, 위험 이벤트·AI 분석 결과를 원본 데이터와 분리해 보관합니다.

## 왜 분리 저장하는가

| 구분 | 이유 |
|---|---|
| **원본 시계열 (GasData / PowerData)** | 실시간 모니터링·재학습용. 보존 7~14일 (raw 수명 정책) |
| **이벤트 (AlarmRecord / Event)** | 위험 발생 이력. 영구 보존 — 사후 추적·법적 증거 |
| **AI 결과 (MLAnomalyResult)** | 모델별 분석 결과. 모델 버전·feature 추적용. 별도 보존 정책 |
| **시간 필드 2종** | `measured_at` (센서 측정 시각) ≠ `received_at` (서버 수신 시각) — 통신 지연·누락 추적 가능 |

데이터 수명 3계층 원칙은 2026-05-14 SQLite 12GB 폭증 사건에서 도출. 상세: [docs/incidents/2026_05_14_sqlite_lock_and_db_bloat.md](incidents/2026_05_14_sqlite_lock_and_db_bloat.md)

## 핵심 테이블

| 테이블 | 앱 | 모델 파일 | 역할 |
|---|---|---|---|
| `GasData` | monitoring | [apps/monitoring/models/gas_data.py](../drf-server/apps/monitoring/models/gas_data.py) | 가스 농도 시계열 (CO/H2S/CO2/O2/VOC 등) |
| `PowerData` | monitoring | [apps/monitoring/models/power_data.py](../drf-server/apps/monitoring/models/power_data.py) | 전류·전압·전력 채널별 |
| `PowerEvent` | monitoring | [apps/monitoring/models/power_event.py](../drf-server/apps/monitoring/models/power_event.py) | 전력 이벤트성 데이터 (전원 상태) |
| `WorkerPosition` | positioning | [apps/positioning/models/worker_position.py](../drf-server/apps/positioning/models/worker_position.py) | 작업자 실시간 위치 |
| `AlarmRecord` | alerts | [apps/alerts/models/alarm_record.py](../drf-server/apps/alerts/models/alarm_record.py) | 알람 발생 이력 (활성/해소) |
| `Event` | alerts | [apps/alerts/models/event.py](../drf-server/apps/alerts/models/event.py) | 위험 이벤트 본체 |
| `EventLog` | alerts | [apps/alerts/models/event_log.py](../drf-server/apps/alerts/models/event_log.py) | 이벤트 상태 변경 이력 |
| `EventAcknowledgement` | alerts | [apps/alerts/models/event_acknowledgement.py](../drf-server/apps/alerts/models/event_acknowledgement.py) | 운영자 확인 처리 이력 |
| `MLModel` | ml | [apps/ml/models/ml_model.py](../drf-server/apps/ml/models/ml_model.py) | AI 모델 메타 (버전·feature) |
| `MLAnomalyResult` | ml | [apps/ml/models/ml_anomaly_result.py](../drf-server/apps/ml/models/ml_anomaly_result.py) | 모델별 이상탐지 결과 |
| `SystemLog` | core | [apps/core/models/system_log.py](../drf-server/apps/core/models/system_log.py) | 시스템 동작 로그 |
| `LoginLog` | accounts | [apps/accounts/models/login_log.py](../drf-server/apps/accounts/models/login_log.py) | 로그인 시도 이력 |

## 데이터 검증·전처리 기준

수신 직후 적용:
- 필수 필드 누락 → 400 반환
- 통신불능값(`-1`) → `None`으로 정규화 (센서 데이터에서 `0`은 유효값이므로 구별 필수)
- 타입 변환 (문자열 숫자 → 숫자)
- ISO 8601 timestamp 정렬
- 이벤트성(전원 상태) vs 주기성(센서값) 라우팅

## 어떻게 구현했는가

1. **수신**: fastapi `gas_router` / `power_router` → DRF 내부 API 호출
2. **검증**: serializer 단계에서 필드·타입·범위
3. **저장**: 원본은 `GasData`/`PowerData`, 위험 단계 판정 시 `Event` + `AlarmRecord` 동시 생성
4. **AI 분석**: Celery 비동기 → `MLAnomalyResult` 저장
5. **알람 푸시**: `AlarmRecord` → Redis `active_alarms` 큐 → fastapi WebSocket broadcast

## 증빙자료 추천

| 증빙 | 위치 / 캡처 대상 | 추천 제목 |
|---|---|---|
| **ERD** | [docs/img/ERD 일부분.png](img/) 기존 파일 + 전체 ERD 추가 권장 (DBeaver/dbdiagram.io) | `[그림 1] 디코나이 핵심 ERD` |
| **JSON 수신 예시** | [docs/specs/json_fields_specification.md](specs/json_fields_specification.md) 인용 | `[그림 2] 유해가스/전력 JSON 구조 예시` |
| **DB 저장 결과 캡처** | DBeaver에서 `GasData`/`AlarmRecord`/`MLAnomalyResult` 최근 100건 조회 | `[그림 3] 핵심 테이블 저장 결과` |
| **measured_at vs received_at 비교** | 같은 row의 두 컬럼 SELECT, 지연 ms 확인 | `[표 1] 측정/수신 시각 차이를 통한 통신 지연 추적` |
| **validation 코드 일부** | [drf-server/apps/monitoring/serializers/](../drf-server/apps/monitoring/) 일부 캡처 | `[그림 4] 수신 데이터 validation 코드` |
| **PG 전환 비교 (SQLite → PG16)** | [docs/migration/2026-05-22-postgres.md](migration/2026-05-22-postgres.md) 앞부분 인용 | `[표 2] DB 전환 전후 비교` |

## 참고 문서

- JSON 필드 명세: [docs/specs/json_fields_specification.md](specs/json_fields_specification.md)
- API 명세: [docs/specs/api_specification.md](specs/api_specification.md)
- PG 전환: [docs/migration/2026-05-22-postgres.md](migration/2026-05-22-postgres.md)
- SQLite 사고: [docs/incidents/2026_05_14_sqlite_lock_and_db_bloat.md](incidents/2026_05_14_sqlite_lock_and_db_bloat.md)
