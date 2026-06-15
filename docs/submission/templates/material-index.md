# 기술문서 (디코나이) 자료 인덱스 — 시연 2026-06-14 제출용

> **목적**: [기술문서(디코나이).md](기술문서(디코나이).md) 의 11장 구조 + [메모용.md](메모용.md) 의 4단 패턴 ("무엇/왜/어떻게/증빙") 에 맞춰 **각 장에 들어갈 자료 위치 + 인용 단락**을 한 자리에 모음.
> **본인 담당 영역** (가정): 백엔드 + AI — **5·6·8·9·10장 두껍게**, 나머지 장 얇게.
> **사용법**: 11장 각각의 "끌어올 자료" 행에서 파일을 열어 해당 단락을 복사·재서술. "보강 필요" 행은 새로 작성·캡처 필요.

---

## 0. 본 인덱스의 자료 분류

| 카테고리 | 위치 | 갯수 | 용도 |
|---|---|---|---|
| **종합문서** | [skill/study/](../../study/) | 5개 | 의사결정·적용현황·트레이드오프·로드맵 흡수 |
| **사용자 본인 정리** | [AI 관련 미정리 총 내용.md](../../../AI%20관련%20미정리%20총%20내용.md) | 1개 (50KB) | 가스 vs 전력 4영역 비교 — 본인 톤 유지 |
| **DB 설계 문서** | [skill/DB/](../../DB/) | 49개 | 6장 ERD·테이블 인용 |
| **시스템 plan** | [skill/plan/](../../plan/) + [docs/plan/](../../../docs/plan/) | 20+개 | 4·5·9장 운영 의도 |
| **트러블슈팅** | [skill/troubleshooting/](../../troubleshooting/) | 9개 | 10장 직접 인용 |
| **코드리뷰·changelog** | [docs/codereviews/](../../../docs/archive/codereviews/) + [docs/changelog/](../../../docs/archive/changelog/) + [drf-server/docs/refactoring/](../../../drf-server/docs/refactoring/) | 다수 | 10장 보강 |
| **인시던트** | [docs/incidents/](../../../docs/incidents/) | 1개 | 10장 사례 |
| **기능정의서** | [docs/features/](../../../docs/features/) | 10+개 | 4·7장 요구사항 |
| **단계별 보고서** | [docs/phases/](../../../docs/archive/phases/) | 30+개 | 3·4장 단계 회고 |
| **컨벤션·규격** | [docs/conventions/](../../../docs/conventions/) + [docs/specs/](../../../docs/specs/) | 다수 | 5·6장 보강 |

---

## 1·2장. 표지 / About Me / 목차 (2p)

가이드 요구: 이름·역할·학력/경력·프로젝트명·제작기간·팀원·**담당 범위**·기술 키워드.

### 끌어올 자료

| 자료 | 인용 단락 |
|---|---|
| [README.md](../../../README.md) | 프로젝트명 + 기술 스택 |
| [.claude/CLAUDE.md](../../../.claude/CLAUDE.md) | "산재 예방 통합 관제 시스템" 한 줄 정의 + 모노레포 구조 + 5축 행동 규칙 |
| [memory: project_team_context](../../../../../.claude/projects/-home-cjy-diconai/memory/project_team_context.md) | 팀 협업 형태 (외부 기업 협업 아님, 내부 팀) |

### 보강 필요

- 본인 이름·학력·경력 (개인 정보)
- 담당 범위 명시 — **"전력 AI 추론·5축 정책 엔진·알람 시스템"** 정도 (본 인덱스 §8·§10 흡수)
- 기술 키워드: Django/DRF · FastAPI · Python 3.12 · scikit-learn (Isolation Forest) · statsmodels (ARIMA) · Redis · Celery · Prometheus/Grafana · Docker Compose · WebSocket · SQLite (→ PostgreSQL/TimescaleDB)

---

## 3장. 프로젝트 개요 및 수행 범위 (1p)

가이드 요구: 배경 / 문제 정의 / 목표 / **내가 구현한 범위**.

### 끌어올 자료

| 자료 | 인용 단락 |
|---|---|
| [skill/4차_향후확장방향_문서.md §1.1](../../4차_향후확장방향_문서.md) | "MVP 검증 완료(3차) → 실서비스 운영 준비(4차)" + 3차에서 검증한 것 vs 4차에서 채울 것 |
| [4차 §1.2 3차 vs 4차 비교표](../../4차_향후확장방향_문서.md) | 13개 영역 비교 (DB / 통신 / AI / 등급 / 보안 등) |
| [4차 §1.3 4차 핵심 목표 3가지](../../4차_향후확장방향_문서.md) | 실데이터 전환 / AI 정식 적용 / 운영 안정화 |
| [skill/디코나이_전체문제_통합본.md](../../디코나이_전체문제_통합본.md) | 프로젝트 전반 문제 정의 (다른 영역도 포함, 본인 영역만 발췌) |
| [memory: demo-2026-06-14-arima-roadmap](../../../../../.claude/projects/-home-cjy-diconai/memory/demo_2026_06_14_arima_roadmap.md) | "2년 과제 중간 발표. 시연 전까지 최대한 작업 진행" |

### 보강 필요

- "내가 구현한 범위" 박스 명시 — 전력 AI · 알람 시스템 · 5축 결합 등
- 본인이 미참여한 영역 (가스 추론 / 위치 추적 / 모바일 등) 은 "전체 흐름 안 역할" 정도로만

---

## 4장. 요구사항 분석 및 구현 매핑 (1p)

가이드 요구: 요구사항 요약 + 구현/미구현 범위 + **요구사항-구현 매핑표**.

### 끌어올 자료

| 자료 | 인용 단락 |
|---|---|
| [4차 §3 실데이터 수용 준비](../../4차_향후확장방향_문서.md) | Pydantic 검증 강화 / JSON 인터페이스 / 결측치 정책 (수신 측 책임) |
| [4차 §8.2 Must/Should/Could 분류](../../4차_향후확장방향_문서.md) | Must-Have 8 / Should-Have 7 / Could-Have 5 |
| [docs/features/cm07_mn03_가스센서_수신저장.md](../../../docs/features/cm07_mn03_가스센서_수신저장.md) | 가스 수신 기능정의서 |
| [docs/features/cjy_CM-07_알람팝업개선_기능정의서.md](../../../docs/features/cjy_CM-07_알람팝업개선_기능정의서.md) | 알람 팝업 기능정의서 (본인 영역) |
| [docs/features/cjy_MN-04_geofence_alarm.md](../../../docs/features/cjy_MN-04_geofence_alarm.md) | geofence 알람 (본인 영역) |
| [docs/features/cjy_VR교육관리_*.md](../../../docs/features/) | VR 교육관리 (본인 영역) |
| [docs/features/hjh_CM-07_MN-03_*.md](../../../docs/features/hjh_CM-07_MN-03_이벤트현황_유해가스현황_기능정의서.md) | 이벤트현황·유해가스현황 (참조) |

### 보강 필요

- 본인 담당 요구사항 표 (CM-XX / MN-XX 매핑) — "내가 구현 ✅ / 미구현 ❌"
- 시뮬레이션 데이터로 검증한 부분 명시 ("실 IoT 미연동 — 구조 검증 단계")

---

## 5장. 시스템 아키텍처 및 데이터 흐름 (2p, ★ 두껍게)

가이드 요구: 전체 구조 / 서버 역할 / **전체 데이터 흐름**.

### 끌어올 자료

| 자료 | 인용 단락 |
|---|---|
| [.claude/CLAUDE.md](../../../.claude/CLAUDE.md) | 모노레포 구조 표 (drf-server :8000 / fastapi-server :8001) + 데이터 흐름 한 줄 (IoT → fastapi → drf / WS) + 앱 레이어 (models/selectors/services/serializers/views) |
| [skill/study/power-ai-종합문서-2026-05-21.md §0.2](../../study/power-ai-종합문서-2026-05-21.md) | **큰 그림 다이어그램** (dummy/IoT → fastapi → drf + Redis + broadcast_loop) |
| [skill/study/power-ai-종합문서 §8](../../study/power-ai-종합문서-2026-05-21.md) | E2E 데이터 흐름 — router → service → AI 추론 → DRF 3종 forward → WebSocket broadcast |
| [docs/specs/url-structure.md](../../../docs/specs/url-structure.md) | URL 분리 원칙 (페이지·API·어드민·kebab-case) |
| [docs/specs/directory-structure.md](../../../docs/specs/directory-structure.md) | 디렉토리 구조 |
| [AI 관련 미정리 총 내용.md §3](../../../AI%20관련%20미정리%20총%20내용.md) | 가스 vs 전력 데이터 흐름 비교 (1단계 vs 6단계) |
| [docs/features/gas_sensor_http_pipeline.md](../../../docs/features/gas_sensor_http_pipeline.md) | 가스 센서 HTTP 파이프라인 (5장 큰 그림 보강) |
| [docs/features/websocket_realtime_panel.md](../../../docs/features/websocket_realtime_panel.md) | WebSocket 실시간 패널 |
| [memory: docker-infra-decision-2026-05-11](../../../../../.claude/projects/-home-cjy-diconai/memory/docker_infra_decision_2026_05_11.md) | 7-서비스 Compose (drf + fastapi + redis + celery×2 + prom + grafana) |
| [memory: data-lifecycle-3tier-principle](../../../../../.claude/projects/-home-cjy-diconai/memory/data_lifecycle_3tier_principle.md) | Raw 7~14일 / Event 영구 / ML 별도 — 보존 정책 원칙 |

### 핵심 인용 단락 (CLAUDE.md 헤더)

```
## 모노레포 구조 (두 서버)

| 서버 | 포트 | 역할 |
|---|---|---|
| drf-server/ | 8000 | 인증·HTML 렌더링·DB 영속성·REST API (Django + DRF) |
| fastapi-server/ | 8001 | 센서 수신·WebSocket 브로드캐스트·Celery 브리지 (FastAPI) |

데이터 흐름: IoT → fastapi-server (수신·검증) → drf-server (저장) / WebSocket (브라우저 실시간)
```

### 보강 필요

- **★ 전체 아키텍처 다이어그램 1개** — 팀 공통. 본인 담당 박스 강조 색
- 서비스 7개 컨테이너 그림 (Docker Compose)
- E2E 흐름 시퀀스 다이어그램 1개

---

## 6장. 데이터 계약 및 데이터베이스 설계 (2p, ★ 두껍게)

가이드 요구: 센서 JSON 구조 / 수집 주기 / 전처리 / **ERD** / 핵심 테이블.

### 6.1 핵심 테이블 4개 (메모용.md 명시)

| 테이블 | 자료 | 인용 |
|---|---|---|
| **GasReading** (= GasData) | [skill/DB/monitoring/gas_data.py.md](../../DB/monitoring/gas_data.py.md) | 9 가스 컬럼·sensor_status·is_anomaly·max_risk_level |
| **PowerReading** (= PowerData) | [skill/DB/monitoring/power_data.py.md](../../DB/monitoring/power_data.py.md) | 16채널 JSON · data_type · device_id |
| **AlarmEvent** (= AlarmRecord + Event) | [skill/DB/alerts/alarm_record.py.md](../../DB/alerts/alarm_record.py.md) + [event.py.md](../../DB/alerts/event.py.md) | algorithm_source·risk_level·source·channel |
| **AIResult** (= MLAnomalyResult) | [skill/DB/ml/ml_anomaly_result.py.md](../../DB/ml/ml_anomaly_result.py.md) | risk_classified 5단계·feature_snapshot·anomaly_score |

### 6.2 추가 핵심 테이블 (본인 작업 흔적)

| 테이블 | 자료 |
|---|---|
| MLModel (4축 매칭) | [skill/DB/ml/ml_model.py.md](../../DB/ml/ml_model.py.md) |
| EventAcknowledgement | [skill/DB/alerts/event_acknowledgement.py.md](../../DB/alerts/event_acknowledgement.py.md) |
| EventLog | [skill/DB/alerts/event_log.py.md](../../DB/alerts/event_log.py.md) |
| HazardType / HazardTypeGroup | [skill/DB/alerts/hazard_type.py.md](../../DB/alerts/hazard_type.py.md) + [hazard_type_group.py.md](../../DB/alerts/hazard_type_group.py.md) |
| AlertPolicy | [skill/DB/alerts/alert_policy.py.md](../../DB/alerts/alert_policy.py.md) |
| PowerEvent | [skill/DB/monitoring/power_event.py.md](../../DB/monitoring/power_event.py.md) |
| FacilityThreshold | [skill/DB/facilities/thresholds.py.md](../../DB/facilities/thresholds.py.md) |
| PowerDevice·channel_meta | [skill/DB/facilities/devices.py.md](../../DB/facilities/devices.py.md) |
| DataRetentionPolicy | [skill/DB/operations/data_retention_policy.py.md](../../DB/operations/data_retention_policy.py.md) |
| SystemLog | [skill/DB/core/system_log.py.md](../../DB/core/system_log.py.md) |

### 6.3 데이터 계약 (JSON·수집 주기)

| 자료 | 인용 |
|---|---|
| [4차 §3.2 Pydantic 검증 강화](../../4차_향후확장방향_문서.md) | 422 응답 구조 표준화 + 값 범위·시간 시제 검증 |
| [4차 §3.3 JSON 인터페이스 정립·동결](../../4차_향후확장방향_문서.md) | `schema_version` 도입 + major/minor 변경 정책 |
| [4차 §3.4 결측치 처리 정책](../../4차_향후확장방향_문서.md) | `o2 null` = 산소 결핍 / 일반 가스 null = 검출 한계 이하 |
| [docs/specs/json_fields_specification.md](../../../docs/specs/json_fields_specification.md) | JSON 필드 명세 |
| [memory: sensor-spec-truth-source](../../../../../.claude/projects/-home-cjy-diconai/memory/sensor_spec_truth_source.md) | 센서 정의서 = 백엔드 진실 공급원 |
| [skill/study/power-ai-종합문서 §7.3](../../study/power-ai-종합문서-2026-05-21.md) | MLModel 4축 매칭 (sensor_type / algorithm / sensor_identifier / version) |
| [skill/DB/DB 변경사항_최재용.md](../../DB/DB%20변경사항_최재용.md) | DB 변경 이력 |

### 6.4 수집 주기

- 가스: 1Hz (9 가스 동시 1 payload)
- 전력: 1Hz (4 측정 × 16 채널 분리)
- 학습 데이터: 1분 리샘플링 (~13,000 row / 1주)

### 보강 필요

- **★ ERD 1개** — 팀 공통 (4개 핵심 테이블 + FK 관계)
- 본인 담당 도메인 ERD 부분만 강조

---

## 7장. 실시간 대시보드 / 위험 판단 / 알람 구현 (2p)

가이드 요구: Dashboard / 위험 상태 표시 / 임계치 판정 / 알람 이력.

### 끌어올 자료

| 자료 | 인용 |
|---|---|
| [skill/study/power-ai-종합문서 §4 알람 결정](../../study/power-ai-종합문서-2026-05-21.md) | AI state 5종 + quality_guard + decide_alarm 6 매트릭스 + rate limit + algorithm_source priority |
| [skill/study/power-ai-종합문서 §8.4 WebSocket broadcast](../../study/power-ai-종합문서-2026-05-21.md) | Redis BRPOP → broadcast_loop → sensor_clients |
| [skill/study/power-ai-종합문서 §8.5 16채널 equipment](../../study/power-ai-종합문서-2026-05-21.md) | AI 결과와 무관한 대시보드 색상 표시 |
| [docs/features/cjy_CM-07_알람팝업개선_기능정의서.md](../../../docs/features/cjy_CM-07_알람팝업개선_기능정의서.md) | 알람 팝업 기능정의 (본인) |
| [docs/features/hjh_alarm-core-service_기능정의서.md](../../../docs/features/hjh_alarm-core-service_기능정의서.md) | 알람 core 서비스 (참조) |
| [skill/alarm/t4-d2-implementation-spec.md](../../alarm/t4-d2-implementation-spec.md) | T4 D2 알람 정책 구현 spec |
| [skill/alarm/t4-source-message-spec.md](../../alarm/t4-source-message-spec.md) | algorithm_source 별 운영자 메시지 (한글 워딩 통일) |
| [skill/alarm/t4-d2-changelog.md](../../alarm/t4-d2-changelog.md) | T4 D2 적용 changelog (본인) |
| [skill/alarm/t4-d3-changelog.md](../../alarm/t4-d3-changelog.md) | T4 D3 changelog |
| [skill/alarm/t4-d4-changelog.md](../../alarm/t4-d4-changelog.md) | T4 D4 changelog |
| [docs/codereviews/2026_05_19/alarm-business-logic-as-is.md](../../../docs/archive/codereviews/2026_05_19/alarm-business-logic-as-is.md) | 알람 비즈니스 로직 코드리뷰 |
| [docs/codereviews/2026_05_19/power-5axis-policy-flow.md](../../../docs/archive/codereviews/2026_05_19/power-5axis-policy-flow.md) | 5축 정책 흐름 코드리뷰 |
| [drf-server/apps/alerts/services/alarm_dedupe.py](../../../drf-server/apps/alerts/services/alarm_dedupe.py) | AI vs rule 알람 dedupe (`ai_fired:*` 키) |

### 보강 필요

- **★ 대시보드 화면 캡처** — 실시간 16채널 패널 + 알람 토스트
- 위험도 표시 색상 매트릭스 (normal/warning/danger)
- 알람 lifecycle 시퀀스 (발화 → ack → resolved)

---

## 8장. ★ AI 분석 및 예측 구조 (2p, **가장 두껍게 — 본인 핵심 영역**)

가이드 요구: AI 적용 목적 / 입력 데이터 / **feature(특징값)** / 예측 흐름 / AI 결과 저장 및 화면 연동.

### 8.1 종합 흡수 자료 (전체 8장 뼈대)

| 자료 | 인용 단락 |
|---|---|
| **[skill/study/power-ai-종합문서-2026-05-21.md](../../study/power-ai-종합문서-2026-05-21.md)** | **전체 §1~§12 통째로 흡수 가능**. 의사결정·적용현황·한계·로드맵 1064줄 |
| **[skill/study/power-ai-트레이드오프-2026-05-21.md](../../study/power-ai-트레이드오프-2026-05-21.md)** | 트레이드오프 15개 (아키텍처 8 + 운영·UI 4 + 인프라 3) |
| **[skill/study/power-ai-design-decisions-2026-05-21.md](../../study/power-ai-design-decisions-2026-05-21.md)** | 외부 리뷰 6항목 단답 (watt 단독·4채널·window 30·night_abnormal·1-step ARIMA·un-downgrade) |
| **[AI 관련 미정리 총 내용.md](../../../AI%20관련%20미정리%20총%20내용.md)** | 본인 톤 — 가스 vs 전력 4영역 비교 (명령어 / DB / 데이터 흐름 / 함수 분기) |

### 8.2 AI 적용 목적

| 자료 | 인용 |
|---|---|
| [ai-model-study-2026-05-17 §2.4](../../study/ai-model-study-2026-05-17.md) | "전력 = 예측 정비 (Predictive Maintenance) 비즈니스 framing — ARIMA forecast + 신뢰구간 위에 서있음" |
| [종합문서 §1.2 ARIMA 4가지 본질 가치](../../study/power-ai-종합문서-2026-05-21.md) | 신뢰구간 위반 / Trend break / Multi-step forecast / Seasonal |
| [IF_ARIMA_팀공유.md Part 1](../../study/IF_ARIMA_팀공유.md) | "사람이 차트를 노려보지 않아도, 가스 누출이나 전력 이상 같은 사건을 시스템이 먼저 인지" |

### 8.3 입력 데이터 (윈도우·1Hz)

| 자료 | 인용 |
|---|---|
| [종합문서 §2.4.1 4피처 선택 근거](../../study/power-ai-종합문서-2026-05-21.md) | value / roll_mean / roll_std / diff — 위치 + 분산 + 변화율 |
| [IF_ARIMA_팀공유 Part 5](../../study/IF_ARIMA_팀공유.md) | 1분 리샘플링 약 13,000행 (1주 분량) / watt 평균 2000~2666W |
| [zscore_anomaly.py 모듈 헤더](../../../fastapi-server/power/services/zscore_anomaly.py) | _INFERENCE_WINDOW=30 (1Hz × 30초) |

### 8.4 ★ 5축 정책 엔진 (8장 핵심)

| 자료 | 인용 |
|---|---|
| [종합문서 §2 — 5축 정책 엔진](../../study/power-ai-종합문서-2026-05-21.md) | STEP B (Threshold) + STEP F (IF) + STEP G (ARIMA) + STEP D (Z-score) + STEP E (Change Point) 단계별 도입 |
| [종합문서 §2.2 각 축의 책임 분담](../../study/power-ai-종합문서-2026-05-21.md) | 5축 직교성 — 각 축이 잡는 패턴 / 못 잡는 패턴 |
| [종합문서 §2.8 combine_risk_5axis](../../study/power-ai-종합문서-2026-05-21.md) | base 3축 위임 + Z/CP 격상 분리 |
| [risk_combine.py:108-163](../../../fastapi-server/ai/risk_combine.py) | 실제 결합 코드 (12 cell 매트릭스 + Z/CP 격상) |
| [STEP 5 학습자료](../../STEP%205%20—%20디코나이%20AI%20기반%20위험%20예측%20개발%20로드맵.md) | 6단계 우선순위 매트릭스 (CRITICAL > ML_ANOMALY > ANOMALY_WARNING > TREND_SHIFT > PREDICTIVE_ALERT > NORMAL) |

### 8.5 도메인 의사결정 (시연 차별화 포인트)

| 자료 | 인용 |
|---|---|
| **[ai-model-study-2026-05-17 §2.4](../../study/ai-model-study-2026-05-17.md)** | **격하 vs un-downgrade 결정 매트릭스** — 도메인 의존 |
| [종합문서 §1.3 도메인별 필요성 매트릭스](../../study/power-ai-종합문서-2026-05-21.md) | 가스 (즉시 위험) vs 전력 (점진 변화) |
| [memory: power-ai-architecture-decision-2026-05-18](../../../../../.claude/projects/-home-cjy-diconai/memory/power_ai_architecture_decision_2026_05_18.md) | "전력 = un-downgrade 필수, 가스 = 격하 유지" 결정 |

### 8.6 학습 파이프라인

| 자료 | 인용 |
|---|---|
| [종합문서 §7 학습 파이프라인](../../study/power-ai-종합문서-2026-05-21.md) | train_anomaly_model + train_arima_power_model + MLModel 4축 매칭 + TTL 캐시 |
| [skill/DB/ml/ml_model.py.md](../../DB/ml/ml_model.py.md) | MLModel 스키마 |
| [memory: ai-anomaly-scope-2026-05-11](../../../../../.claude/projects/-home-cjy-diconai/memory/ai_anomaly_scope_2026_05_11.md) | sklearn IF 채택, apps/ml/ 신설, 4일 작업 |
| [docs/phases/ai_anomaly_team_brief_2026_05_11.md](../../../docs/archive/phases/ai_anomaly_team_brief_2026_05_11.md) | AI 이상탐지 팀 브리핑 |
| [skill/plan/if-integration-guide.md](../../plan/if-integration-guide.md) | IF 통합 가이드 plan |

### 8.7 AI 결과 저장·화면 연동

| 자료 | 인용 |
|---|---|
| [종합문서 §8.3 DRF forward 3종](../../study/power-ai-종합문서-2026-05-21.md) | MLAnomalyResult 매번 / PowerData 매번 / AlarmRecord source=ai 만 |
| [services/anomaly_alarm.py](../../../fastapi-server/services/anomaly_alarm.py) | forward_inference_e2e 함수 |
| [skill/DB/ml/ml_anomaly_result.py.md](../../DB/ml/ml_anomaly_result.py.md) | RiskClassified 5단계 enum + feature_snapshot JSON |

### 8.8 학습용 보조 자료 (외부 시연에서 활용 가능)

| 자료 | 인용 |
|---|---|
| [IF_ARIMA_팀공유.md Part 2 ARIMA 기초](../../study/IF_ARIMA_팀공유.md) | AR(p) + I(d) + MA(q) 풀이 + 잔차 의미 |
| [IF_ARIMA_팀공유 Part 3 Isolation Forest 기초](../../study/IF_ARIMA_팀공유.md) | "이상치일수록 적은 분할로 격리" 직관 |
| [IF_ARIMA_팀공유 Part 4 결합](../../study/IF_ARIMA_팀공유.md) | ARIMA + IF 파이프라인 (잔차 → IF) |
| [IF_ARIMA_적용현황_2026_05_19.md](../../study/IF_ARIMA_적용현황_2026_05_19.md) | STEP B~G 적용도 매트릭스 + Part 1~8 단계별 회고 |

### 보강 필요

- **★ 5축 결합 다이어그램** (Threshold + IF + ARIMA + Z + CP → combine_risk_5axis → algorithm_source)
- **★ AI 추론 시퀀스** (input window → 5축 추론 → combined → night 격상 → algorithm_source → decide_alarm → push)
- IF feature 4개 시각화 (value / roll_mean / roll_std / diff) — Python plot
- ARIMA forecast + 95% CI 그래프 (시계열 + 위반 시각화)
- 운영 데이터로 어느 축이 발화했는지 비율 (`POWER_AI_AXIS_FIRED_TOTAL` 메트릭 캡처) — D-7 ~ D-3 측정 후

---

## 9장. 운영 구조 및 모니터링 (1p)

가이드 요구: Celery/Redis / 관리자 기능 / Docker/K8s / **Prometheus/Grafana** / 실시간 모니터링 시나리오 / 사후 보완 기준.

### 끌어올 자료

| 자료 | 인용 |
|---|---|
| [memory: docker-infra-decision-2026-05-11](../../../../../.claude/projects/-home-cjy-diconai/memory/docker_infra_decision_2026_05_11.md) | 7-서비스 Compose 결정 (drf + fastapi + redis + celery×2 + prom + grafana) |
| [memory: runtime-docker-environment](../../../../../.claude/projects/-home-cjy-diconai/memory/runtime_docker_environment.md) | "런타임은 Docker Compose. host uv 직접 pytest 금지" |
| [fastapi-server/core/metrics.py](../../../fastapi-server/core/metrics.py) | Prometheus 메트릭 정의 (POWER_AI_* 등 11종) |
| [drf-server/apps/core/metrics.py](../../../drf-server/apps/core/metrics.py) | DRF 측 메트릭 |
| [종합문서 §4.4 AI mute 동기](../../study/power-ai-종합문서-2026-05-21.md) | rate limit 60s + AI mute (`ai_fired:*` Redis 키) |
| [종합문서 §8.4 Redis BRPOP](../../study/power-ai-종합문서-2026-05-21.md) | broadcast_loop 1초 주기 |
| [docker-compose.yml](../../../docker-compose.yml) | 컨테이너 정의 |
| [skill/plan/alarm-reliability-phase1.md](../../plan/alarm-reliability-phase1.md) | 알람 신뢰성 phase1 plan |
| [docs/changelog/alarm_reliability/](../../../docs/archive/changelog/alarm_reliability/) | 알람 신뢰성 changelog 3개 |
| [memory: data-lifecycle-3tier-principle](../../../../../.claude/projects/-home-cjy-diconai/memory/data_lifecycle_3tier_principle.md) | Raw 7~14일 / Event 영구 / ML 별도 보존 정책 |

### Prometheus 메트릭 (8장과 연계)

8장 5축 발화 분포 카운터:
- `POWER_AI_INFERENCE_TOTAL` — 추론 실행 횟수
- `POWER_AI_COMBINED_TOTAL` — combined 분포 (label: normal/caution/predict_warn/warning/danger)
- `POWER_AI_AXIS_FIRED_TOTAL` — 5축별 발화 (label: if/arima/zscore/change_point/night)
- `POWER_AI_ALARM_FIRED_TOTAL` — algorithm_source 별 알람
- `POWER_AI_RATE_LIMITED_TOTAL` — rate limit 차단
- `POWER_AI_QUALITY_SKIP_TOTAL` — quality_guard skip (comm_failure / overflow / stuck)
- `AI_INFERENCE_FAILED_TOTAL` — 추론 실패
- `AI_INFERENCE_DURATION` — 추론 latency
- `AI_BROADCAST_LATENCY` — IoT → push 전체 latency

### 보강 필요

- **★ Grafana 대시보드 캡처** — 메트릭 시각화 + 알람 분포 패널
- Docker Compose 다이어그램 (7 서비스 + 의존성)
- 관리자 페이지 캡처 (만약 본인 작업 영역)

---

## 10장. ★ 트러블슈팅 / 성능 개선 / 한계 및 향후 계획 (1p, **두껍게 — 면접에서 빛남**)

가이드 요구: 문제 → 원인 → 해결 → **개선 전후 비교표** + 한계 + 향후 계획.

### 10.1 트러블슈팅 사례 (본인 직접 경험만)

| 자료 | 사례 핵심 |
|---|---|
| **[skill/troubleshooting/0519_arima-single-spike-limit.md](../../troubleshooting/0519_arima-single-spike-limit.md)** | **★ ARIMA(1,1,1) 단발 spike 한계** — 8000W 강제 주입 검증 + 4축 보완 + "의도된 한계 vs 버그" 명시. 면접 인용 강함 |
| [skill/troubleshooting/0519_statsmodels-image-rebuild-missing.md](../../troubleshooting/0519_statsmodels-image-rebuild-missing.md) | Docker 이미지 rebuild 누락 |
| [skill/troubleshooting/0519_sqlite-alter-default-orm-cache.md](../../troubleshooting/0519_sqlite-alter-default-orm-cache.md) | SQLite ALTER + ORM 캐시 |
| [skill/troubleshooting/0519_alarm-toast-escalate-timer-race.md](../../troubleshooting/0519_alarm-toast-escalate-timer-race.md) | 알람 토스트 격상 타이머 race |
| [skill/troubleshooting/0519_django-template-comment-exposure.md](../../troubleshooting/0519_django-template-comment-exposure.md) | Django template 주석 노출 |
| [skill/troubleshooting/gas-if-feature-mismatch.md](../../troubleshooting/gas-if-feature-mismatch.md) | 가스 IF feature mismatch |
| [skill/troubleshooting/prometheus-multiproc-stale.md](../../troubleshooting/prometheus-multiproc-stale.md) | Prometheus multiproc stale |
| [skill/troubleshooting/sqlite-db-bloat-retention.md](../../troubleshooting/sqlite-db-bloat-retention.md) | SQLite DB 폭증 + retention |
| [skill/troubleshooting/sqlite-lock-busy-snapshot.md](../../troubleshooting/sqlite-lock-busy-snapshot.md) | SQLite lock busy snapshot |
| **[docs/incidents/2026_05_14_sqlite_lock_and_db_bloat.md](../../../docs/incidents/2026_05_14_sqlite_lock_and_db_bloat.md)** | **★ SQLite 12GB 폭증 + lock 인시던트** — 면접 인용 강함 |

### 10.2 추천 인용 사례 3개 (4단 패턴 적용)

| # | 사례 | 4단 (문제 / 원인 / 해결 / 전후) |
|---|---|---|
| 1 | **ARIMA 단발 spike 한계** | 문제: 8000W spike 인데 ARIMA violation=False / 원인: ARIMA(1,1,1) 빠른 적응으로 forecast 가 actual 따라감 / 해결: IF + threshold 가 보완 (4축 결합) / 전후: 단독 → 4축 결합으로 false negative 0 |
| 2 | **SQLite 12GB 폭증** | 문제: SQLite 12GB + 락 busy / 원인: Raw 무한 누적 / 해결: DataRetentionPolicy + 7~14일 TTL / 전후: 12GB → 200MB |
| 3 | **AI vs rule 알람 중복** | 문제: 같은 채널의 AI + rule 알람 동시 발화 / 원인: 두 시스템이 같은 신호에 발화 / 해결: AI mute (`ai_fired:*` Redis 키 60s) + alarm_dedupe.is_ai_mute_active / 전후: 중복 N% → 0% |

### 10.3 한계 (정직)

| 자료 | 한계 |
|---|---|
| [트레이드오프 §2 P1~P14](../../study/power-ai-트레이드오프-2026-05-21.md) | 14개 현재 단계 문제점 (즉시 / 시연 전 / 시연 후 / 장기) |
| [종합문서 §10](../../study/power-ai-종합문서-2026-05-21.md) | 7개 의도된 한계 (ARIMA / SARIMA / IF feature / LRU / auto-arima / Online ARIMA / 가스 가드 회귀) |
| [IF_ARIMA_팀공유 Part 6](../../study/IF_ARIMA_팀공유.md) | 정확도 4문제 + 확장성 3문제 |

### 10.4 향후 계획

| 자료 | 인용 |
|---|---|
| [트레이드오프 §3](../../study/power-ai-트레이드오프-2026-05-21.md) | D-day / D+1~D+30 / D+30~D+90 / D+90+ 4단계 로드맵 |
| [종합문서 §12 후속 로드맵](../../study/power-ai-종합문서-2026-05-21.md) | 정확도 (SARIMA·STL·IF feature 확장) + 확장성 (LRU·16채널·클러스터링·Online ARIMA·Global) |
| [4차 §8 단계별 로드맵](../../4차_향후확장방향_문서.md) | 4차 내부 단계 (4-1/4-2/4-3) + Must/Should/Could |

### 보강 필요

- **★ Before/After 비교표 3개** (10.2 의 3 사례에 대해)
- 한계 인정 + 향후 계획 흐름 시각화 (4단계 로드맵)

---

## 11장. 결론 (1p)

가이드 요구: 전체 회고 + 다음 단계.

### 끌어올 자료

| 자료 | 인용 |
|---|---|
| [트레이드오프 §4.3 의사결정 패턴 재확인](../../study/power-ai-트레이드오프-2026-05-21.md) | 4가지 패턴 (PoC → 본격 / 한계 명시 + 보완 / 도메인 의존 / 데이터 검증) |
| [종합문서 §11 의사결정 패턴 4가지](../../study/power-ai-종합문서-2026-05-21.md) | 동일 |
| [메모용.md 강조 8가지 역량](메모용.md) | 요구사항 해석력 / 데이터 설계력 / 아키텍처 이해도 / 실시간 처리 / AI 연동 / 운영 구조 / 문제 해결 / 증빙 중심 |

### 보강 필요

- 본인 회고 (시간순으로 본인이 경험한 의사결정 흐름)
- 다음 단계 — 4차 본격 도입 / SARIMA / Online ARIMA / 16채널 확장

---

## 부록 A. 4단 패턴 ("무엇/왜/어떻게/증빙") 체크리스트

[메모용.md](메모용.md) 의 모든 장 필수 패턴:

| 단 | 체크 |
|---|---|
| ① 무엇을 수행하는가? | 한 줄 요약 |
| ② 왜 필요한가? | 비즈니스 동기 / 도메인 근거 |
| ③ 어떻게 수행했나? | 기술 스택 + 핵심 코드/구조 |
| ④ ⭐⭐⭐⭐⭐ 증빙 | 화면 캡처 / 로그 / 다이어그램 / 메트릭 — **이게 가장 중요** |

8장 (AI) 의 4단 예시:

| 단 | 8장 채움 |
|---|---|
| 무엇 | 전력 5축 정책 엔진 (Threshold + IF + ARIMA + Z + CP) |
| 왜 | "예측 정비" framing — 임계 도달 전 조기 경고 + 운영자 추적 가능한 algorithm_source 라벨 |
| 어떻게 | combine_risk_5axis + 채널별 IF/ARIMA + base=3축 위임 + Z/CP 격상 |
| 증빙 | 5축 다이어그램 + ARIMA forecast 그래프 + algorithm_source 분포 메트릭 + 운영 시나리오 로그 |

---

## 부록 B. "팀원 공통 vs 본인 담당" 매핑 ([메모용.md](메모용.md) 가이드)

| 영역 | 공통 / 본인 |
|---|---|
| 프로젝트 배경·요구사항 (3·4장 상위) | 공통 |
| 전체 아키텍처 다이어그램 (5장) | 공통 (본인 박스 강조) |
| ERD (6장 큰 그림) | 공통 |
| 사용 기술 스택 | 공통 |
| **AI 분석·예측 (8장)** | **본인 (깊게)** |
| **트러블슈팅 (10장)** | **본인 (직접 경험만)** |
| 알람 시스템 (7장) | 본인 일부 (CM-07 / T4 작업) |
| Celery/Redis (9장) | 본인 일부 |
| 가스 추론 흐름 | 공통 (얇게) |
| 위치 추적 (geofence) | 공통 (얇게) — 본인 일부 (MN-04) |
| VR 교육 관리 | 본인 일부 (있다면) |
| 모바일 앱 / FCM | 공통 (얇게, 미구현 명시) |

---

## 부록 C. 증빙 자료 체크리스트 (시연 전 수집)

가이드 메모용.md 가 강조하는 "글로만 설명 X — 증빙 필수":

| # | 자료 종류 | 수집 시점 | 위치 |
|---|---|---|---|
| 1 | 대시보드 화면 캡처 (정상 + warning + danger) | D-7 ~ D-3 | 신규 |
| 2 | 알람 토스트·모달 캡처 (AI source + static source) | 동일 | 신규 |
| 3 | Grafana 패널 캡처 (POWER_AI_* 메트릭 + algorithm_source 분포) | 동일 | 신규 |
| 4 | 전체 아키텍처 다이어그램 | 본인 작성 | 신규 (draw.io / excalidraw / mermaid) |
| 5 | 5축 결합 다이어그램 | 본인 작성 | 신규 |
| 6 | ERD | 팀 공통 | 신규 (django-extensions graph_models 또는 dbdiagram.io) |
| 7 | Docker Compose 다이어그램 | 본인 작성 | 신규 |
| 8 | E2E 시퀀스 다이어그램 (router → service → DRF → WS) | 본인 작성 | 신규 |
| 9 | ARIMA forecast + 95% CI 시각화 (시계열 plot) | D-7 ~ D-3 | Python plot |
| 10 | 추론 로그 샘플 (`[anomaly_inference]` / `[zscore]` / `[change_point]` / `[night_abnormal]`) | D-7 운영 1주 | docker logs |
| 11 | Before/After 비교표 (10장 사례 3개) | 본인 작성 | 신규 |
| 12 | 운영 시나리오 1~2개 (정상 → 점진 상승 → IF 발화 → 룰 격상) | 시연 리허설 시 | 영상 또는 캡처 |

---

## 부록 D. 5축 정책 엔진 — 8장 핵심 요약 (한 페이지 분량)

8장의 1~2 페이지가 모자라면 본 요약을 직접 인용·재서술:

```
[전력 AI = 5축 직교 결합 + un-downgrade architecture]

  ┌─ Threshold (정격 % 기준)      ──┐
  ├─ Isolation Forest (4 피처)    ──┤
  ├─ ARIMA forecast + 95% CI     ──┤── combine_risk_5axis ── combined risk
  ├─ Z-score (3σ)                ──┤      │                  │
  └─ Change Point (two-window)   ──┘      │                  │
                                          ▼                  ▼
                                  night_abnormal       algorithm_source
                                  (KST 22-05 +         priority
                                   정격 30% 휴리스틱)   (6단계)
                                          │
                                          ▼
                                  decide_alarm 6 매트릭스
                                  (AI state × static_risk)
                                          │
                                          ▼
                                  push_alarm + DRF forward

[도메인 의사결정]
  - 가스: ARIMA = IF 입력 피처 (격하)         — 분 단위 즉시 위험
  - 전력: ARIMA = IF 동급 algorithm (un-downgrade) — 시간 단위 점진 변화
  → 4가지 ARIMA 본질 가치 (CI 위반 / trend break / multi-step / seasonal) 가 전력에 핵심

[운영 안전망]
  - AI 침묵 4 분기 (DISABLED / WARMING_UP / INFERRED_NORMAL / INFERRED_FAILED)
    모두 정적 임계가 cover (decide_alarm 매트릭스)
  - "AI 는 보조, 정적은 베이스라인"
```

---

## 부록 E. 11장 분량 추천 (가이드 + 본인 영역 반영)

| 장 | 가이드 분량 | 본인 영역 비중 | 우선순위 |
|---|---|---|---|
| 1·2 | 2p | 공통 | 마지막 |
| 3 | 1p | 본인 담당 명시 | 중 |
| 4 | 1p | 본인 담당 표 | 중 |
| 5 | 2p | 공통 + 본인 박스 강조 | 중 |
| 6 | 2p | 공통 ERD + 본인 도메인 강조 | 중 |
| 7 | 2p | 본인 일부 (CM-07/T4) | 중 |
| **8** | **2p** | **★ 본인 핵심** | **최우선** |
| 9 | 1p | 본인 일부 (메트릭) | 후 |
| **10** | **1p** | **★ 본인 직접 경험** | **고우선** |
| 11 | 1p | 본인 회고 | 후 |

**작업 순서 제안**: 8장 → 10장 → 5장 → 6장 → 7장 → 9장 → 3장 → 4장 → 11장 → 1·2장.
8장이 가장 자료 정리되어 있어 초안 빠름. 10장이 면접 차별화 포인트라 다음 우선.
