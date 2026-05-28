# 디코나이 관제 센서 플랫폼 — 기술문서 초안 (cjy)

> **작성 안내**: 본 문서는 [기술문서(디코나이).md](기술문서(디코나이).md) 양식 + [메모용.md](메모용.md) 의 4단 패턴 (무엇/왜/어떻게/증빙) 에 맞춰 작성된 **초안**입니다.
> **본인 담당 영역**: 전력 AI 추론·5축 정책 엔진 + 알람 시스템 재설계 (CM-07 / MN-04 / T1~T7).
> **자료 출처**: [기술문서-자료인덱스.md](기술문서-자료인덱스.md) + [알람-자료인덱스.md](알람-자료인덱스.md).
> **placeholder**: `[___]` 는 본인이 직접 채워야 하는 정보 (이름·학력·캡처 등).

---

# 1장. 표지 / About Me

```
프로젝트명 : 디코나이 (DICONAI) 산업재해 예방 통합 관제 시스템
제작 기간   : [___] ~ [___]
팀 구성     : [___]명 (백엔드 / 프론트엔드 / AI / 디자인)
담당 범위   : 전력 AI 추론·알람 시스템 재설계
기술 키워드 : Django · DRF · FastAPI · scikit-learn · statsmodels · Redis · Celery · Docker · Prometheus · Grafana · WebSocket
```

### About Me

| 항목 | 내용 |
|---|---|
| 이름 | [___] |
| 학력·경력 | [___] |
| 담당 영역 | **전력 AI 추론 (Isolation Forest + ARIMA + Z-score + Change Point 5축 결합) + 알람 시스템 재설계 (CM-07 알람 팝업 + MN-04 geofence 알람 + T1~T7)** |
| 주요 기술 | Python 3.12 · Django/DRF · FastAPI · scikit-learn · statsmodels · Redis Pub/Sub · Celery · Prometheus/Grafana · Docker Compose · WebSocket |
| 결과물 | 5축 정책 엔진 (전력 도메인 un-downgrade architecture) + decide_alarm 6 매트릭스 (AI vs 정적 단일 결정자) + AI mute (ai_fired:* Redis 키) 로 AI vs rule 중복 알람 0% |

---

# 2장. 목차

```
1장. 표지 / About Me
2장. 목차
3장. 프로젝트 개요 및 수행 범위
4장. 요구사항 분석 및 구현 매핑
5장. 시스템 아키텍처 및 데이터 흐름
6장. 데이터 계약 및 데이터베이스 설계
7장. 실시간 대시보드 / 위험 판단 / 알람 구현
8장. AI 분석 및 예측 구조
9장. 운영 구조 및 모니터링
10장. 트러블슈팅 / 성능 개선 / 한계 및 향후 계획
11장. 결론
```

---

# 3장. 프로젝트 개요 및 수행 범위

### 이 장의 핵심 목적
```
디코나이 R&D 요구사항 기반으로 시작된 산업재해 예방 통합 관제 시스템의
배경·목표·구현 범위를 정리하고, 본인이 실제로 담당한 영역을 명확히 구분합니다.
```

### 무엇을 수행하는가?
```
디코나이 (DICONAI) R&D 요구사항을 기반으로,
유해가스 센서와 스마트 파워 시스템 데이터를 실시간 수집·시각화하고,
위험 판단·알람·AI 예측·운영 관찰 기능이 연결된 산업 안전 관제 시스템을 설계·구현하였습니다.

본 프로젝트는 단순 화면 구현이 아닌, 실시간 데이터 수집부터 위험 판단·AI 분석·
비동기 처리·대시보드 반영·운영 구조까지 이어지는 실무형 안전 관제 플랫폼 구현이 목표입니다.

본인은 그 중 다음 영역을 담당하였습니다:
- 전력 AI 추론·5축 정책 엔진 (Isolation Forest + ARIMA + Z-score + Change Point + Threshold)
- 알람 시스템 재설계 (decide_alarm 6 매트릭스, AI mute, fingerprint dedup)
- 알람 팝업 UI 개선 (모달·토스트 분리)
- geofence 진입 알람 (작업자 위치 기반)
```

### 왜 필요한가?
```
산업 현장에서 가스 누출·전력 과부하·작업자 위험구역 진입 같은 사고는
"임계치를 명백히 초과한 시점"에 알리는 것만으로는 부족합니다.
임계치 도달 전의 조기 신호 (점진적 부하 증가, 평소 대비 튐, 패턴 변화 시점)
를 인지해 사전 대응 가능하도록 만드는 것이 R&D 의 핵심 요구입니다.

따라서 본 프로젝트는:
- 실시간 데이터 수집 인프라 (1Hz 가스 + 1Hz 전력 16채널)
- 통합 관제 대시보드 (모든 채널·위치·알람 한 화면)
- 다축 AI 정책 엔진 (5축 결합으로 조기 경고 + 운영자 추적 가능한 driver 라벨)
- AI 침묵 시 정적 임계가 책임지는 운영 안전망 (decide_alarm 매트릭스)
- 비동기 운영 구조 (Celery/Redis + Docker Compose + Prometheus/Grafana)

위 5가지를 실제 동작하는 시스템으로 통합하여 R&D 요구의 "기술 검증"과
운영 관점의 "관찰 가능한 시스템"이라는 두 목표를 동시에 만족해야 합니다.
```

### 어떻게 수행했나?
```
회사가 제공한 R&D 계획서·요구사항 문서를 분석해 핵심 기능을
센서 연계, 실시간 모니터링, 위험 판단, 알람 처리, AI 예측, 운영 관리로 분류하고,
시스템을 6 계층 (수집/저장/위험판단/AI분석/시각화/운영) 으로 나누어 설계하였습니다.

본인이 담당한 영역의 구현 범위:
- 전력 AI 추론 — 4채널 (압연기 / 메인 전력반 / 공조 / 조명) IF + ARIMA + Z + CP + Threshold 5축 결합
- 도메인 의사결정 — 전력 = un-downgrade architecture (가스의 격하와 비대칭, 도메인별 차등)
- 알람 시스템 재설계 — fastapi 단일 결정자 (decide_alarm 6 매트릭스), AI state 5종 분리
- AI mute 도입 — ai_fired:* Redis 키로 AI vs rule 알람 중복 차단
- fingerprint dedup — Celery retry 중복 push 차단 (NX EX 30s)
- 알람 팝업 UI — 모달(danger) + 토스트(warning) 분리, EventAcknowledgement 다중 ack 추적

제외 범위 (향후 고도화):
- 실 IoT 게이트웨이 연동 (현재 dummy 시뮬레이터로 구조 검증)
- SARIMA seasonal 모델 (시각 휴리스틱으로 우회)
- 16채널 전체 활성화 (현재 4채널 PoC, D+30 sprint 에 확장)
- PostgreSQL/TimescaleDB 전환 (현재 SQLite, 4차 단계로 이관)
```

### 증빙자료 ⭐⭐⭐⭐⭐

- 연구개발 계획서 핵심 문구 캡처 → `[증빙 1: ___]`
- 요구사항 요약표 (아래)
- 구현 범위 정리표 (아래)
- 전체 기능 범위 다이어그램 → `[증빙 2: 6 계층 구조 다이어그램]`
- 본인 담당 박스 강조 다이어그램 → `[증빙 3: 6 계층 안 본인 담당 영역 표시]`

#### 1) 요구사항 요약표

| 구분 | 핵심 내용 |
|---|---|
| 데이터 연계 | 유해가스 9종 (CO·H2S·CO2·O2·NO2·SO2·O3·NH3·VOC) + 스마트 파워 16채널 (W·A·V·on/off) |
| 모니터링 | 통합 대시보드, 16채널·작업자·알람 한 화면 |
| 위험 판단 | 임계치 + 다축 AI (IF·ARIMA·Z·CP) 결합 + 시각 컨텍스트 |
| AI 분석 | 채널별 IF·ARIMA, 평소 대비 튐 (Z), 패턴 변화 시점 (CP), 5축 우선순위 결합 |
| 알람 | AI vs rule 중복 방지, 모달·토스트 분리, EventAcknowledgement |
| 운영 구조 | Celery/Redis 비동기, Docker Compose 7-서비스, Prometheus/Grafana |

#### 2) 구현 범위 정리표

| 항목 | 구현 여부 | 비고 |
|---|---|---|
| 가스 데이터 수신·저장 | 구현 | 9 가스 1Hz dummy |
| 전력 데이터 수신·저장 | 구현 | 16채널 × W/A/V/onoff |
| 통합 대시보드 | 구현 | WebSocket Redis BRPOP 실시간 반영 |
| 임계치 위험 판단 | 구현 | DRF FacilityThreshold 단일 진실 공급원 |
| **전력 AI 5축 결합 (본인 담당)** | **구현** | 4채널 PoC — IF/ARIMA/Z/CP/Threshold + night_abnormal |
| **알람 재설계 (본인 담당)** | **구현** | decide_alarm 6 매트릭스, AI mute, fingerprint dedup |
| **알람 팝업 UI (본인 담당)** | **구현** | 모달/토스트 분리, EventAcknowledgement |
| **geofence 알람 (본인 담당)** | **구현** | 위치 + 가스 위험 매핑, worker_clients 개인 송신 |
| 가스 다변량 IF (CO+H2S+CO2 15피처) | 구현 (가스 담당자) | ARIMA 격하 |
| 16채널 전체 AI 활성 | 미구현 | 4채널 PoC, D+30 sprint |
| SARIMA seasonal | 미구현 | 휴리스틱 (night_abnormal) 우회 |
| 실 IoT 게이트웨이 연동 | 미구현 | dummy 로 구조 검증 |
| PostgreSQL/TimescaleDB 전환 | 미구현 | 4차 단계 |

---

# 4장. 요구사항 분석 및 구현 매핑

### 이 장의 핵심 목적
```
R&D 요구사항을 기능 단위로 분해하고, 실제 구현·부분 구현·미구현으로 구분해
프로젝트의 현실성과 신뢰도를 명확히 합니다.
```

### 무엇을 수행하는가?
```
회사 제공 요구사항을 분석해 다음 7개 범주로 재구성하고,
각 범주별 구현 여부와 증빙 자료를 매핑하였습니다.

- 외부 센서 및 스마트 파워 시스템 연계
- 통합 대시보드 및 실시간 시각화
- 위험 판단 로직 및 경보 처리
- AI 분석 및 예측 기능 (본인 담당)
- 관리자 기능 및 운영 인터페이스
- Docker/Kubernetes 기반 실행 및 배포 구조
- 알람 시스템 (본인 담당)
```

### 왜 필요한가?
```
디코나이는 센서 연계 · 대시보드 · 위험 판단 · AI 예측 · 알람 · 운영 구조까지
범위가 넓어 "모든 요구사항을 완성했다"고 쓰면 오히려 신뢰도가 떨어집니다.

본 장에서는 요구사항을 기술적으로 해석한 결과 + 구현/부분 구현/미구현 구분 +
각 항목의 증빙 위치를 표로 정리해, 면접관·평가자가 본 프로젝트의 실제 도달 수준을
객관적으로 판단할 수 있도록 합니다.

또한 본인이 담당한 영역 (전력 AI + 알람) 을 명시해, 다른 팀원의 기술문서와
구별되는 본인의 기여 영역을 명확히 합니다.
```

### 어떻게 수행했나?
```
요구사항 문서를 검토해 기능 성격이 유사한 항목끼리 묶고, 다음 범주로 분류하였습니다.
이후 각 항목에 대해 `구현` / `부분 구현` / `미구현` 으로 구분하고,
증빙 자료 위치를 함께 매핑하였습니다.

본인 담당 영역은 4차 R&D 계획의 다음 항목에 대응:
- CM-07 알람 팝업 개선 (디자인·UI·상호작용)
- MN-04 geofence 알람 (작업자 위치 기반)
- 전력 AI 정식 적용 (IF + ARIMA 통합)
- 알람 시스템 신뢰성 (AI vs rule 중복 방지, dedup)
```

### 증빙자료 ⭐⭐⭐⭐⭐

- 요구사항-구현 매핑표 (아래)
- 본인 담당 요구사항 표 (아래)
- 미구현 항목 정당화 표 (아래)
- 원본 요구사항 문서 핵심 키워드 캡처 → `[증빙 1: 원본 요구사항 형광펜 캡처]`

#### 1) 요구사항-구현 매핑표

| 요구사항 | 구현 여부 | 구현 내용 | 증빙자료 |
|---|---|---|---|
| 센서 연계 (가스 + 전력) | 구현 | JSON 수신 API + dummy 1Hz | Swagger 캡처, PowerData 저장 결과 |
| 통합 대시보드 | 구현 | 16채널·작업자·알람 한 화면 + WebSocket 실시간 | 메인 대시보드 캡처 |
| 임계치 위험 판단 | 구현 | DRF FacilityThreshold 단일 출처 + 정격 % 환산 | calculate_power_risk 코드 + 위험도 표시 캡처 |
| **AI 분석·예측 (★ 본인)** | **구현** | 전력 5축 결합 (IF + ARIMA + Z + CP + Threshold) + un-downgrade architecture | 8장 전체, 5축 결합 다이어그램, Grafana 패널 |
| **알람 처리 (★ 본인)** | **구현** | decide_alarm 6 매트릭스, AI mute, fingerprint dedup | 7장 전체, 알람 모달·토스트 캡처 |
| 관리자 기능 | 부분 구현 | Django Admin 활성화 + 일부 메뉴 | Django Admin 화면 |
| Docker 배포 | 구현 | 7-서비스 Compose | docker compose ps 결과 |
| Kubernetes | 미구현 | 4차 단계 | — |
| AI 결과 저장·화면 연동 | 구현 | MLAnomalyResult + AlarmRecord.algorithm_source | DB 저장 결과 + UI 라벨 |
| SMS·이메일 외부 알림 | 미구현 | 4차 단계 | — |
| 가스 확산 시뮬레이션 | 미구현 | CFD 영역, 4차 고도화 | — |

#### 2) 본인 담당 요구사항 표 (CM-XX / MN-XX 매핑)

| 코드 | 요구사항 | 구현 결과 | 자료 |
|---|---|---|---|
| **CM-07** | 알람 팝업 개선 | 모달(danger) + 토스트(warning) 분리, 회색 처리 정상화 신호 | [docs/features/cjy_CM-07_알람팝업개선_기능정의서.md](../../docs/features/cjy_CM-07_알람팝업개선_기능정의서.md) |
| **MN-04** | geofence 진입 알람 | 위치 + 가스 위험 매핑, worker_clients[user_id] 개인 송신 | [docs/features/cjy_MN-04_geofence_alarm.md](../../docs/features/cjy_MN-04_geofence_alarm.md) |
| Power-AI-1 | 전력 IF + ARIMA 정식 적용 | un-downgrade architecture, 4채널 PoC | [skill/study/power-ai-종합문서-2026-05-21.md](../study/power-ai-종합문서-2026-05-21.md) §1·§2 |
| Power-AI-2 | 5축 정책 엔진 (STEP 5 권고) | combine_risk_5axis (base=3축 + Z/CP 격상) | [fastapi-server/ai/risk_combine.py](../../fastapi-server/ai/risk_combine.py) |
| Alarm-T1+T6 | 알람 정보 통일 (운영자 톤) | ML 용어 제거 + algorithm_source 6종 한글 워딩 | [drf-server/docs/refactoring/2026_05_19_alarm_t1_t6.md](../../drf-server/docs/refactoring/2026_05_19_alarm_t1_t6.md) |
| Alarm-T3 | fingerprint dedup | NX EX 30s 4 분기 (event_id/ai_meta/clear/cover) | [skill/plan/alarm-t3-dedup-unification.md](../plan/alarm-t3-dedup-unification.md) |
| Alarm-T4 | AI vs 정적 계층화 | decide_alarm 6 매트릭스 + AI state 5종 | [skill/plan/alarm-t4-ai-static-hierarchy.md](../plan/alarm-t4-ai-static-hierarchy.md) |

#### 3) 미구현 항목 정당화

| 항목 | 정당화 |
|---|---|
| 16채널 전체 AI 활성 | 시연 일정 (D-24) 제약 — 4채널 (압연기/메인전력반/공조/조명) 부하 다양성 검증 후 D+30 sprint 확장 |
| SARIMA seasonal | 1~2주 운영 데이터 누적 선행 필요 — 시각 휴리스틱 (KST 22-05 + 정격 30%) 으로 우회 |
| 실 IoT 게이트웨이 연동 | 외부 의존 (에어위드 게이트웨이 일정) — dummy 시뮬레이터로 구조 검증 (4차 단계 합의) |
| PostgreSQL/TimescaleDB | SQLite 12GB 폭증 인시던트 후 DataRetentionPolicy 적용 — PG 전환은 4차 |
| CFD 가스 확산 | 외부 R&D 영역 |
| SMS·외부 알림 | 4차 모바일 FCM 단계 |

---

# 5장. 시스템 아키텍처 및 데이터 흐름

### 이 장의 핵심 목적
```
센서 → API → DB → 위험 판단 → AI → 알람 → WebSocket → Dashboard 흐름을
한 장의 다이어그램과 서버 역할표로 명확히 정의합니다.
```

### 무엇을 수행하는가?
```
모노레포 2-tier 아키텍처 (DRF + FastAPI) 위에서 다음 7-서비스 Docker Compose 로 운영:
- drf-server (Django + DRF, 인증·HTML·DB 영속화·REST API)
- fastapi-server (센서 수신·WebSocket 브로드캐스트·AI 추론)
- redis (Celery broker + alarm queue + AI mute 키)
- celery-worker × 2 (알람·시계열 비동기 태스크)
- prometheus (메트릭 수집)
- grafana (시각화)

전체 데이터 흐름 (E2E):
센서/dummy → fastapi router → service (수신·검증·추론) → DRF (영속화)
                                                       → Redis BRPOP → broadcast_loop → 브라우저
```

### 왜 필요한가?
```
산업 안전 관제는 1초 단위 실시간 + 영속 보존 + 다중 클라이언트 동시 알림이
모두 필요한 시스템입니다. 한 서버에서 다 처리하면:

- 동기 처리 (실시간 vs DB 영속화) 가 서로 latency 발생
- WebSocket 다중 클라이언트가 DB 쓰기와 경합
- AI 추론이 무거우면 수신 자체가 지연

따라서 fastapi (실시간 수신·추론·broadcast) 와 drf (영속화·인증·HTML) 를
역할 분리하고, 비동기 Redis 큐 + Celery 로 무거운 작업 격리, Prometheus/Grafana 로
운영 관찰까지 함께 두는 구조가 필수입니다.
```

### 어떻게 수행했나?
```
서버 분리 원칙:
- drf-server (포트 8000) — 인증·HTML 렌더링·DB 영속성·REST API
- fastapi-server (포트 8001) — 센서 수신·WebSocket·Celery 브리지

URL 분리:
- 페이지 (HTML) — 루트 (/dashboard/, /admin-panel/...)
- API (JSON) — /api/ 프리픽스 (/api/sensors/, /api/power/...)
- 어드민 패널 — /admin-panel/ (Django Admin 과 분리)

데이터 흐름 단계:
1. 수신 — fastapi gas/power/position router 가 JSON 수신·Pydantic 검증
2. 상태 갱신 — websocket.state 의 in-memory dict (power_latest 등)
3. AI 추론 분기 — 전력 watt 만 process_anomaly_inference 호출 (5축 결합)
4. 영속화 — DRF /api/monitoring/power/data/ 등으로 raw + AI 결과 + 알람 전송
5. WebSocket — push_alarm → Redis LPUSH "diconai:ws:alarms" → broadcast_loop 1초 BRPOP
6. 브라우저 - alarm-popup.js / monitoring-realtime.js 가 WS 메시지 수신·렌더링

Docker Compose 7-서비스:
- 모든 의존성이 컨테이너 내부 (host uv 직접 실행 금지 — runtime_docker_environment)
- 볼륨 공유: ml_models/ 폴더가 drf-server 학습 + fastapi-server 로드 공통
```

### 증빙자료 ⭐⭐⭐⭐⭐

- 전체 시스템 아키텍처 다이어그램 → `[증빙 1: 7-서비스 컨테이너 + 데이터 흐름 화살표]`
- 서버 역할 표 (아래)
- E2E 시퀀스 다이어그램 → `[증빙 2: router → service → AI → DRF + WS broadcast → 브라우저]`
- Docker Compose ps 결과 캡처 → `[증빙 3: docker compose ps]`

#### 1) 서버 분리 표

| 서버 | 포트 | 역할 | 본인 작업 |
|---|---|---|---|
| drf-server | 8000 | 인증·HTML·DB 영속성·REST API | apps/alerts (재설계) · apps/ml (학습 명령) |
| fastapi-server | 8001 | 센서 수신·WebSocket·AI 추론·Celery 브리지 | power/services/anomaly_inference (5축 추론) · websocket/services/alarm_queue (dedup) |
| redis | 6379 | Celery broker + alarm queue + ai_fired:* mute 키 | 본인 사용 (AI mute) |
| celery-worker × 2 | — | 알람·시계열 비동기 처리 | 본인 사용 (Celery task) |
| prometheus | 9090 | 메트릭 수집 | POWER_AI_* + alarm_push_dedup_hits 등 본인 추가 |
| grafana | 3000 | 메트릭 시각화 | 본인 패널 (algorithm_source 분포 등) |

#### 2) 큰 그림 데이터 흐름

```
[dummy 또는 IoT]                                                  [DRF :8000]
    │                                                                ▲
    │ POST /api/power/watt                                           │ /api/monitoring/power/data/
    │ POST /api/power/current                                        │ /api/ml/anomaly-results/
    │ POST /api/power/voltage                                        │ /api/monitoring/power/event/
    │ POST /api/power/onoff                                          │
    │ POST /api/sensors/gas                                          ▼
    ▼                                                          AlarmRecord
[fastapi router :8001]                                         Event
    │                                                          MLAnomalyResult
    ├─ 가스 router → process_gas_data ──────┐                  PowerData
    │                                        │
    ├─ 전력 router (watt) → process_anomaly_inference (★ 본인)
    │                          │
    │                          ├─ quality_guard
    │                          ├─ 정적 임계 평가
    │                          ├─ 4채널 → 5축 추론 (IF + ARIMA + Z + CP + threshold)
    │                          ├─ combine_risk_5axis → combined + escalation_source
    │                          ├─ night_abnormal 격상
    │                          ├─ algorithm_source priority 6단계
    │                          ├─ rate limit (60s) + AI mute (ai_fired:* TTL 60s)
    │                          ├─ decide_alarm 6 매트릭스 → source 결정
    │                          ├─ push_alarm (★ fingerprint dedup NX EX 30s)
    │                          └─ forward_inference_e2e → DRF
    │
    └─ position router → geofence 진입 → fire_geofence_alarm_task

[Celery (DRF)]
    │ create_alarm_and_event (atomic)
    │ + AI mute 가드 (alarm_dedupe.is_ai_mute_active)
    ▼
POST /internal/alarms/push/  (localhost 전용)
    │
    ▼
[Redis LPUSH "diconai:ws:alarms"]
    │
    │ broadcast_loop 1초 BRPOP
    ▼
[WS sensor_clients[] + worker_clients[user_id]]
    │
    ▼
[브라우저 — alarm-popup.js / monitoring-realtime.js]
```

---

# 6장. 데이터 계약 및 데이터베이스 설계

### 이 장의 핵심 목적
```
센서 JSON 구조·수집 주기·DB 핵심 테이블 (GasReading / PowerReading / AlarmEvent /
AIResult) + 본인이 추가·수정한 모델들을 ERD 와 함께 정리합니다.
```

### 무엇을 수행하는가?
```
센서 JSON 인터페이스를 Pydantic 으로 검증하고, DB 모델을
아래 4개 핵심 + 보조 테이블로 설계하였습니다.

핵심 4개:
- GasData (= GasReading) — 9 가스 1Hz raw
- PowerData (= PowerReading) — 16채널 W/A/V/onoff raw
- AlarmRecord + Event (= AlarmEvent) — 알람 이력 + 활성 Event lifecycle
- MLAnomalyResult (= AIResult) — AI 5축 추론 결과 영속화

본인이 추가·수정한 모델:
- MLModel (4축 unique: sensor_type/algorithm/sensor_identifier/version) — un-downgrade 인프라
- AlarmRecord.algorithm_source 컬럼 추가 — 5축 driver 라벨 (W4.a migration)
- AlarmRecord.channel 컬럼 추가 — 전력 16채널 식별
- EventAcknowledgement — 다중 관리자 ack 시그널
- HazardType / HazardTypeGroup — 알람 type 분류
- AlertPolicy — 알람 정책 (자동 해제 vs 수동 해제)
```

### 왜 필요한가?
```
산업 안전 관제 데이터는 다음 3가지 특성을 동시에 만족해야 합니다:

1. 영속성 — 알람·이벤트는 법규상 추적 가능해야 함 (APPEND-ONLY)
2. 실시간성 — 1초 단위 raw 데이터 손실 없이 누적
3. 추적성 — 운영자가 "어떤 AI 가 어느 채널을 잡았나" 추적 가능

따라서 단순히 raw 데이터만 저장하지 않고, AlarmRecord 와 Event 를 분리해
"같은 사건당 한 Event 에 여러 AlarmRecord 가 모이는" merge 정책 + APPEND-ONLY
EventLog 로 lifecycle 감사 + AI 결과는 MLAnomalyResult 에 별도 영속화 + AlarmRecord
는 algorithm_source 로 driver 추적이라는 구조가 필요합니다.

또한 본인이 도입한 MLModel 4축 매칭은 향후 N device · 다중 algorithm · 다중 sensor
환경에서 모델 추적·rollback·staleness 모니터링의 인프라가 됩니다.
```

### 어떻게 수행했나?
```
모델 설계 단계:

1. 데이터 계약 정의 — Pydantic Schema 로 fastapi 측 입력 검증 (422 응답 표준화)
2. 핵심 테이블 4개 — wide table 패턴 (gas 9 가스 컬럼 / power channels JSON)
3. AlarmRecord ↔ Event 분리 — merge_policy 로 같은 사건당 1 Event + N AlarmRecord
4. MLModel 4축 unique — sensor_type × algorithm × sensor_identifier × version
5. APPEND-ONLY — AlarmRecord / Event / EventLog / SystemLog 4 모델에 save/delete 가드

본인이 적용한 migration:
- migration 0002 (W1.1) — MLModel.algorithm + MLModel.sensor_identifier 추가
- migration 0016 — AlarmRecord.channel 추가
- migration 0017 (W4.a) — AlarmRecord.algorithm_source 추가
- migration 0003 (ml) — RiskClassified enum 5단계 (warning 추가)

데이터 정합성 가드:
- create_alarm_and_event — transaction.atomic + select_for_update 로 race 방지
- 결측치 정책 — o2 null = 산소 결핍 (위급) vs 기타 가스 null = 검출 한계 이하
- sensor_status — comm_failure / sensor_fault_overflow / sensor_fault_stuck 라벨
```

### 증빙자료 ⭐⭐⭐⭐⭐

- ERD 다이어그램 → `[증빙 1: 4 핵심 테이블 + FK 관계 — django-extensions graph_models]`
- 본인 담당 모델 강조 ERD → `[증빙 2: MLModel + AlarmRecord.algorithm_source 강조]`
- 센서 JSON 구조 표 (아래)
- 핵심 테이블 표 (아래)
- DB 저장 결과 캡처 → `[증빙 3: AlarmRecord + Event 동시 생성 확인]`

#### 1) 센서 JSON 구조 (요약)

| 채널 | 엔드포인트 | 페이로드 |
|---|---|---|
| 가스 | `POST /api/sensors/gas` | `{device_id, measured_at, co, h2s, co2, o2, no2, so2, o3, nh3, voc}` |
| 전력 (watt) | `POST /api/power/watt` | `{device_id, measured_at, channels: {1: 7500, ...}, anomaly_map?}` |
| 전력 (current) | `POST /api/power/current` | `{device_id, measured_at, channels: {...}}` |
| 전력 (voltage) | `POST /api/power/voltage` | `{device_id, measured_at, channels: {...}}` |
| 전력 (onoff) | `POST /api/power/onoff` | `{device_id, measured_at, snapshot: {...}}` |
| 위치 | `POST /api/positioning/receive` | `{worker_id, x, y, facility_id, timestamp}` |

수집 주기: 1Hz (1초당 1 payload).

#### 2) 핵심 테이블 (메모용.md 명시 4개)

| 테이블 | 핵심 필드 | 역할 |
|---|---|---|
| **GasData** (= GasReading) | device_id, measured_at, 9 가스 컬럼, sensor_status, max_risk_level | 9 가스 raw + 위험도 |
| **PowerData** (= PowerReading) | device_id, measured_at, data_type, channels JSON | 16채널 raw |
| **AlarmRecord** (= AlarmEvent 일부) | event FK, risk_level, source, **algorithm_source**, channel, summary, measured_value | 알람 이력 (algorithm_source 본인 추가) |
| **Event** (= AlarmEvent 일부) | facility FK, alarm_type, status, opened_at, resolved_at | 활성 Event lifecycle |
| **MLAnomalyResult** (= AIResult) | ml_model FK, sensor_identifier, anomaly_score, prediction, **risk_classified 5단계**, feature_snapshot JSON | AI 추론 결과 영속화 (5단계 enum 본인 추가) |

본인이 추가·수정한 보조 모델:
- **MLModel** (4축 unique) — algorithm/sensor_identifier/version 추가로 channel별 ARIMA·IF 추적
- **EventAcknowledgement** — 다중 관리자 ack
- **EventLog** — APPEND-ONLY lifecycle 감사

---

# 7장. ★ 실시간 대시보드 / 위험 판단 / 알람 구현 (본인 깊은 영역)

### 이 장의 핵심 목적
```
본인이 담당한 알람 시스템 — fastapi 단일 결정자 (decide_alarm 6 매트릭스),
AI mute (ai_fired:* Redis 키), fingerprint dedup (NX EX 30s), algorithm_source
6 종 priority — 의 구조·운영자 UX·증빙을 정리합니다.
```

### 무엇을 수행하는가?
```
다채널 실시간 알람 시스템을 다음 4 컴포넌트 직교 구조로 설계·구현하였습니다:

1. decide_alarm 6 매트릭스 — fastapi 가 AI state × static_risk → source 단일 결정
2. push_alarm fingerprint dedup — event_id/ai_meta/clear/cover 4 분기 NX EX 30s
3. AI mute (ai_fired:* TTL 60s) — DRF rule task 의 is_ai_mute_active 가드
4. rate limit (sensor_identifier 60s) — 같은 센서 폭주 회피

UI 측:
- 모달 (danger) + 토스트 (warning) 분리 — CM-07 알람 팝업 개선
- EventAcknowledgement 다중 관리자 ack 시그널 — "(N 확인 중)" 토스트 표시
- algorithm_source 6 종 한글 워딩 ("이상 수치 탐지" / "이상 패턴 탐지" / "야간 이상 가동" 등)

WebSocket 측:
- Redis BRPOP 1초 주기 broadcast_loop
- sensor_clients[] (가스/전력 전체) vs worker_clients[user_id] (geofence 개인) 분리
```

### 왜 필요한가?
```
산업 현장 알람의 핵심 운영 요구 3가지:

1. AI vs rule 알람 중복 방지 — 같은 채널의 두 시스템이 동시 발화하면 운영자 폭주
2. 운영자가 driver 추적 가능 — "어느 알고리즘이 잡았나" 명시 (알고리즘 신뢰도 측정)
3. AI 침묵 시 정적 임계가 책임 — AI 가 "있으면 좋은 것" 이지 "없으면 안 되는 것" 아님

기존 구현 (재설계 전, 2026-05-09 코드리뷰 시점):
- fastapi 와 DRF Celery 가 각자 발화 → 중복 가능
- algorithm_source 라벨 없음 → 운영자가 추적 불가
- AI 실패 시 정적 cover 분기 없음 → AI 침묵 = 알람 없음

본인이 재설계한 결과:
- fastapi 가 5축 + 정적 평가 모두 가지므로 단일 결정자 — race 자체 차단
- decide_alarm 6 매트릭스 + algorithm_source 6 종 — 운영자 추적 + AI 침묵 4 분기 cover
- AI mute (ai_fired:*) — Celery rule 알람도 mute 가드로 차단
```

### 어떻게 수행했나?
```
2주 sprint (2026-05-15 ~ 2026-05-21) 안 7 단계 진화:

1. 2026-05-15 — 알람 시스템 재설계 plan (PR #57)
   3대 요구 + 회색지대 5건 결정 → 시각화 단순화 + 운영자 ack + 자동/수동 해제

2. 2026-05-15 — AI mute + cooldown 도입
   ai_fired:{device_id}:{channel} Redis TTL 60s 키 + alarm_dedupe.is_ai_mute_active

3. 2026-05-17 — D 옵션 (도메인별 결정)
   가스 = 격하 / 전력 = un-downgrade → algorithm_source 분기 출발

4. 2026-05-17 — Phase 2 UI refactor
   알람 팝업 모달/토스트 분리, 회색 처리 디자인 옵션

5. 2026-05-19 — T1+T6 정보 통일
   message·summary 운영자 톤 (ML 용어 제거) + algorithm_source 6 종 한글

6. 2026-05-19 — T3 dedup 통일
   push_alarm 진입부 fingerprint NX EX 30s — Celery retry 중복 차단

7. 2026-05-20 — T4 AI vs 정적 계층화
   decide_alarm 6 매트릭스 + AI state 5종 — fastapi 단일 결정자

decide_alarm 매트릭스 (T4 D2 핵심):

| AI state             | 정적 결과 | source                       |
|----------------------|-----------|------------------------------|
| FIRED                | *         | "ai"                         |
| INFERRED_NORMAL      | fired     | "static_cover_miss"          |
| INFERRED_FAILED      | fired     | "static_cover_inference_fail"|
| DISABLED             | fired     | "static_no_ai_available"     |
| WARMING_UP           | fired     | "static_cover_warmup"        |
| None (Redis 장애)    | fired     | "static_no_ai_available"     | (fail-safe)
| *                    | not fired | None (알람 없음)              |

fingerprint dedup 4 분기:
- 룰: event:{event_id}:{risk_level}
- AI: ai:{alarm_type}:{device_id}:{channel}:{risk_level}
- 정상화: clear:{alarm_type}:{source_label}
- 정적 cover: cover:{source}:{source_label}:{risk_level}
```

### 증빙자료 ⭐⭐⭐⭐⭐

- 알람 흐름 시퀀스 다이어그램 → `[증빙 1: router → 5축 → decide_alarm → push → WS → 브라우저]`
- decide_alarm 6 매트릭스 시각화 (위 표 그대로)
- 알람 모달 캡처 (danger, algorithm_source="이상 수치·패턴 동시 탐지" 표시) → `[증빙 2]`
- 알람 토스트 캡처 (warning, source_label="압연기A" + 측정값) → `[증빙 3]`
- 회색 토스트 캡처 (resolved) → `[증빙 4]`
- "(N 확인 중)" EventAcknowledgement 시그널 캡처 → `[증빙 5]`
- algorithm_source 분포 Grafana 패널 캡처 → `[증빙 6]`
- 운영 시나리오 영상 (정상 → 가스 누출 → 모달 + 토스트 → ack → resolved) → `[증빙 7]`

---

# 8장. ★ AI 분석 및 예측 구조 (본인 핵심 영역)

### 이 장의 핵심 목적
```
전력 도메인 AI 의 5축 정책 엔진 + un-downgrade architecture + 도메인 의존 결정을
정리합니다. 본인 차별화 핵심: "AI 모델 자체보다 입력·결합·도메인 결정·운영
연계가 어떻게 설계되었는가" 를 4단 패턴으로 증명합니다.
```

### 무엇을 수행하는가?
```
전력 도메인의 4채널 (압연기 / 메인 전력반 / 공조 / 조명) 에 대해 다음 5축을
독립 계산 후 우선순위 결합으로 위험도를 산출하는 정책 엔진을 구현하였습니다:

1. Threshold — 정격 % 기반 정적 임계 (warning 80% / danger 100%)
2. Isolation Forest — 4피처 (value, roll_mean, roll_std, diff) 분포 이상
3. ARIMA — 1-step forecast + 95% 신뢰구간 위반 (un-downgrade)
4. Z-score — 슬라이딩 윈도우 평균 대비 |z|>=3σ (조기 경고)
5. Change Point — two-window (60틱) 비교 STABLE→SHIFT 시점 (패턴 변화)

추가 시각 컨텍스트:
- night_abnormal — KST 22-05 야간 + 정격 30% 초과 → 1단계 격상 휴리스틱

운영 연계:
- algorithm_source 6 종 (priority: night > combined > change_point > arima > zscore > IF)
- AlarmRecord.algorithm_source 라벨링 → 운영자 추적
- MLAnomalyResult — 5축 features + risk_classified 5단계 영속화
- AI mute (ai_fired:* Redis TTL 60s) → DRF rule 알람 중복 차단
```

### 왜 필요한가?
```
산업 안전 AI 의 핵심 가치 = "임계치 도달 후가 아닌, 도달 전 조기 경고".
이를 위해 다음 5가지 패턴을 잡아야 합니다:

| 패턴 | 잡는 축 |
|---|---|
| 절대값 초과 (정격 100%) | Threshold |
| 학습 분포 밖 spike (단발 surge) | Isolation Forest |
| 점진 부하 증가 (베어링 마모) | ARIMA trend break |
| 평소 대비 튐 (조기 경고) | Z-score |
| 가동 모드 전환 (패턴 변화 시점) | Change Point |
| 야간 비정상 가동 | night_abnormal 휴리스틱 |

단일 모델 (IF 만 / ARIMA 만) 로는 위 5가지를 다 잡을 수 없습니다.
도메인 특성에 따라 다른 축이 다른 패턴을 잡으므로, 5축 직교 결합이
robustness + 운영자 추적성 (어느 축이 잡았나) 동시 확보.

또한 가스 (즉시 위험 도메인) 와 전력 (점진 변화 도메인) 은 ARIMA 의 가치가
달라, 가스 = 격하 / 전력 = un-downgrade 로 도메인 의존 architecture 를
선택했습니다 (의도된 비대칭).
```

### 어떻게 수행했나?
```
5축 결합 코드 (fastapi-server/ai/risk_combine.py):

def combine_risk_5axis(threshold, if_pred, arima, z, cp) -> tuple[str, str]:
    base = combine_risk_3axis(threshold, if_pred, arima)  # 12-cell 매트릭스
    if base != "normal":
        return base, ""               # AI 발화 중 → Z/CP 격상 안 함 (중복 방지)
    if change_point:
        return "predict_warn", "change_point"
    if z_score_anomaly:
        return "predict_warn", "zscore"
    return "normal", ""

설계 결정:
- base 3축 위임 — combine_risk_3axis (W3 12-cell 매트릭스) 결과 그대로 → 회귀 가드
- Z/CP 는 base=normal 일 때만 격상 — false positive 회피 + 운영자 추적성
- escalation_source 반환 — algorithm_source 결정 시 driver 라벨 일관성

도메인 의사결정 (ai-model-study §2.4 매트릭스):

| 도메인 | ARIMA 본질 가치 필요? | 격하 vs un-downgrade |
|---|---|---|
| 가스 (분 단위 즉시 위험) | 낮음 — 잔차 크면 IF 즉시 잡음 | 격하 (IF 입력 피처) |
| 전력 (시간~일 단위 점진 변화) | 높음 — 예측 정비 framing | un-downgrade (IF 동급) |

학습 파이프라인:
- train_anomaly_model (IF, 4피처) — sensor_identifier 채널별
- train_arima_power_model (ARIMA, 1,1,1) — sensor_identifier 채널별
- MLModel 4축 매칭 (sensor_type × algorithm × sensor_identifier × version)
- fastapi 가 DRF /api/ml/models/active/ 조회 → .pkl joblib 로드 + TTL 캐시

운영 적용:
- 현재 4채널 (ch1=압연기 7.5kW / ch9=메인 전력반 15kW 3상 / ch14=공조 5.5kW / ch15=조명 1kW)
- _INFERENCE_ENABLED_CHANNELS 로 부하 종류 다양성 검증
- D+30 sprint 운영 데이터 누적 후 16채널 확장 의사결정
```

### 증빙자료 ⭐⭐⭐⭐⭐

- 5축 결합 다이어그램 → `[증빙 1: Threshold + IF + ARIMA + Z + CP → combine_risk_5axis → algorithm_source]`
- IF feature 4개 시각화 (Python plot — value/roll_mean/roll_std/diff) → `[증빙 2]`
- ARIMA forecast + 95% CI 시계열 그래프 → `[증빙 3]`
- 5축 발화 분포 Grafana 패널 (POWER_AI_AXIS_FIRED_TOTAL) → `[증빙 4]`
- algorithm_source 6 종 라벨 분포 캡처 → `[증빙 5]`
- 추론 로그 샘플 (`[anomaly_inference]` / `[zscore]` / `[change_point]` / `[night_abnormal]`) → `[증빙 6]`
- DB 저장 결과 (MLAnomalyResult + AlarmRecord.algorithm_source) → `[증빙 7]`

#### 1) 도메인 의사결정 매트릭스

| 도메인 | 사고 시간 척도 | ARIMA 도메인 필요성 | 채택 |
|---|---|---|---|
| 가스 | 분 단위 즉시 위험 | 낮음 | **격하** (IF 피처) |
| 전력 | 시간~일 단위 점진 변화 | 높음 | **un-downgrade** (IF 동급) |

#### 2) 5축 책임 분담

| 축 | 잡는 패턴 | 잡지 못하는 패턴 |
|---|---|---|
| Threshold | 절대값 초과 | 임계 직전 조기 경고 |
| IF | 학습 분포 밖 (point) | 시간 의존성 (contextual) |
| ARIMA | trend break / 점진 drift | 단발 spike (빠른 적응으로 CI 따라감) |
| Z-score | 통계 spike (3σ) | trend break 시점 |
| Change Point | 패턴 변화 시점 (STABLE→SHIFT) | 단발 spike, 절대값 위험 |

→ **5축 직교성**: 어떤 모델도 모든 패턴을 잡지 못함. 도메인별 패턴에 맞춰 5축 결합이 robust.

---

# 9장. 운영 구조 및 모니터링

### 이 장의 핵심 목적
```
Celery/Redis 비동기 + Docker Compose 7-서비스 + Prometheus/Grafana 메트릭으로
"단순 구현이 아닌 관찰 가능한 시스템" 임을 증명합니다.
```

### 무엇을 수행하는가?
```
운영 구조 4 영역:

1. 비동기 처리 — Celery 알람 task (fire_danger / fire_warning / fire_geofence /
   fire_clear) + Redis broker
2. Docker Compose — 7-서비스 (drf + fastapi + redis + celery×2 + prom + grafana)
3. 메트릭 수집 — Prometheus client (FastAPI / DRF 양측)
4. 시각화 — Grafana 패널 (POWER_AI_* + alarm_push_dedup_hits + AI mute hits)

본인이 추가한 메트릭 (전력 AI + 알람):
- POWER_AI_INFERENCE_TOTAL (추론 실행 횟수)
- POWER_AI_COMBINED_TOTAL (combined 분포: normal/caution/predict_warn/warning/danger)
- POWER_AI_AXIS_FIRED_TOTAL (5축별 발화: if/arima/zscore/change_point/night)
- POWER_AI_ALARM_FIRED_TOTAL (algorithm_source 별 알람)
- POWER_AI_RATE_LIMITED_TOTAL (rate limit 차단)
- POWER_AI_QUALITY_SKIP_TOTAL (quality_guard skip: comm_failure/overflow/stuck)
- alarm_push_dedup_hits_total (fingerprint dedup 차단)
- anomaly_forward_failures_total (DRF forward 실패 stage 별)
```

### 왜 필요한가?
```
산업 안전 시스템은 24/7 운영 + 다중 클라이언트 + 무거운 작업 (AI 학습·재학습) 이
공존하므로:

- 비동기 처리 — 알람 발화·DB 영속화·WS broadcast 가 서로 latency 격리
- 컨테이너 — 서비스 의존성 격리 + 재시작 자동화 + 환경 동일성
- 메트릭 — "AI 가 추론을 몇 번 했나" / "어느 축이 가장 많이 발화하나" / "rate
  limit 으로 막힌 게 몇 건인가" 같은 운영 질문에 답 가능

특히 본인이 추가한 알람 dedup 메트릭 (alarm_push_dedup_hits_total) 은
"T3 dedup 도입 후 실제로 중복이 얼마나 차단됐는가" 증명 자료가 됩니다.
```

### 어떻게 수행했나?
```
Docker Compose 7-서비스 정의:
- drf-server (포트 8000) — Django + Celery beat
- fastapi-server (포트 8001) — 수집 + WebSocket
- redis (포트 6379) — Celery broker + alarm queue + ai_fired:* 키
- celery-worker × 2 — 알람·시계열 비동기 처리
- prometheus (포트 9090) — 메트릭 수집
- grafana (포트 3000) — 시각화

Celery 알람 task 4 종 (drf-server/apps/alerts/tasks.py):
- fire_danger_alarm_task — DANGER 즉시 발화
- fire_warning_alarm_task — WARNING 30s countdown 후 발화
- fire_geofence_alarm_task — 작업자 위치 기반 (worker_clients 개인 송신)
- fire_clear_notification_task — 정상화 알림

Redis 키 네임스페이스:
- diconai:ws:alarms — 알람 큐 (LPUSH/BRPOP)
- alarm:push:dedup:* — fingerprint dedup (NX EX 30s)
- ai_fired:{device_id}:{channel} — AI mute (TTL 60s)

Prometheus + Grafana:
- /metrics 엔드포인트 (FastAPI + DRF 양측)
- prometheus.yml 에서 scrape 설정
- Grafana 패널: algorithm_source 분포 / rate limit 비율 / dedup hits / 5축 분포 등
```

### 증빙자료 ⭐⭐⭐⭐⭐

- Docker Compose ps 캡처 → `[증빙 1: docker compose ps 7-서비스 healthy]`
- docker-compose.yml 핵심 구간 → `[증빙 2]`
- Grafana 대시보드 캡처 → `[증빙 3: POWER_AI_* 패널 + algorithm_source 분포]`
- Prometheus targets 캡처 → `[증빙 4]`
- Celery task 실행 로그 (fire_danger_alarm_task) → `[증빙 5]`
- 운영 시나리오: dummy 1주 가동 후 메트릭 추이 → `[증빙 6]`

---

# 10장. ★ 트러블슈팅 / 성능 개선 / 한계 및 향후 계획 (본인 직접 경험)

### 이 장의 핵심 목적
```
본인이 직접 겪고 해결한 사례 3개를 4단 (문제 / 원인 / 해결 / 전후) 으로
정리합니다. 면접 차별화 포인트.
```

### 무엇을 수행하는가?
```
본인이 직접 진단·해결한 3가지 운영 사례:

1. T3 dedup — Celery retry 로 인한 중복 push 차단
2. AI vs rule 알람 중복 — fastapi (AI) + DRF (rule) 동시 발화 차단
3. 알람 3대 증상 진단 — _AckStore 24h 영구 차단 가설 (시연 후 sprint 인계)

추가:
- ARIMA(1,1,1) 단발 spike 한계 — "의도된 한계 vs 버그" 명시적 구분 사례
- SQLite 12GB 폭증 인시던트 → DataRetentionPolicy 도입
```

### 왜 필요한가?
```
운영 환경의 문제는 "어떻게 발견했고 / 무엇이 원인이고 / 어떻게 해결했고 /
효과가 측정됐는가" 4단으로 정리하지 않으면 면접·평가자에게 "이 사람이 운영
경험 있다" 증명이 어렵습니다.

특히 트러블슈팅 사례는 다음을 보여줍니다:
- 운영 데이터로 문제 진단 (로그·메트릭 활용 능력)
- 원인 분석 (멘탈 모델 vs 코드 동작 비교)
- 해결 후 효과 측정 (Before/After 정량화)
- 한계 인정 (못 푼 문제는 sprint 분리)
```

### 어떻게 수행했나?

#### 사례 1 — T3 dedup (★ 본인 작업)

```
[문제] Celery `_push_to_ws` retry (max 3) 가 같은 payload 를 최대 3번 push.
         → Redis 큐 중복 적재, 운영자에게 같은 알람 3번 표시.

[원인] choke point 부재. Celery task 안에 dedup 없음 → retry 마다 새 push.

[해결] push_alarm 진입부 fingerprint NX EX 30s 4 분기 도입:
         - 룰: event:{event_id}:{risk_level}
         - AI: ai:{alarm_type}:{device_id}:{channel}:{risk_level}
         - 정상화: clear:{alarm_type}:{source_label}
         - 정적 cover: cover:{source}:{source_label}:{risk_level}
       첫 도착자만 LPUSH, 후속 retry 는 silent drop + alarm_push_dedup_hits Counter.

[효과] 운영 중복 push 0% (Prometheus 카운터로 추적).
       fastapi-server/websocket/services/alarm_queue.py 의 push_alarm 함수.
```

#### 사례 2 — AI vs rule 알람 중복 (★ 본인 작업)

```
[문제] 같은 채널의 AI 알람 + rule 기반 알람 동시 발화. 운영자에게 같은 신호 2개 표시.

[원인] fastapi (AI 추론 후 직접 push) 와 DRF Celery (rule task 가 별도 push) 가
       같은 신호에 각자 발화. 두 시스템 간 sync 부재.

[해결] AI 발화 시 fastapi 가 Redis 에 ai_fired:{device_id}:{channel} 키 TTL 60s
       마킹 → DRF Celery rule task 가 alarm_dedupe.is_ai_mute_active 가드로 mute.
       services/ai_mute.py 의 mark_ai_recent + drf-server alarm_dedupe.py.

[효과] AI 발화 중인 채널의 rule 알람 0% — 운영자 알람 중복 차단.
       AI mute hits Prometheus 카운터로 추적.
```

#### 사례 3 — 알람 3대 증상 진단 (시연 후 sprint 인계)

```
[문제] 운영자가 ack 한 알람이 24시간 동안 재발화 안 됨.
       운영자 멘탈 모델 ("ack 했다고 영구 차단 아님") 과 실제 코드 동작 충돌.

[원인] localStorage _AckStore TTL 24h 가 RESOLVED 신호와 분리되지 않음.
       ack/RESOLVED 두 상태가 같은 키로 관리되어 ack 만 한 알람도 24h 차단.

[해결] 진단만 수행 (시연 D-24 시점 안정성 우선). 수정안:
       _AckStore TTL → RESOLVED 영구 vs ack 단기 (예: 5분) 분리.
       시연 후 sprint 1순위 작업으로 인계.

[효과] 진단 보고서 작성 + 메모리 인계 + 시연 후 sprint plan 등록.
       docs/codereviews/2026_05_20/alarm-symptom-bottleneck-diagnosis.md.
```

#### 사례 4 — ARIMA(1,1,1) 단발 spike 한계 (의도된 동작 명시)

```
[문제] 8000W (정격 7500W 의 107%) 강제 주입 시 ARIMA violation=False.
       기대: (danger, anomaly, True) — 실제: (danger, anomaly, False).

[원인] ARIMA(1,1,1) 의 빠른 적응 특성. apply(endog=values) 호출 시 마지막
       1~3틱 spike 가 입력에 포함되어 forecast 가 spike 근처로 적응.

[해결] ARIMA 단독으로 단발 spike 잡으려고 하지 않음. 4축 보완 명시:
       - 단발 spike → IF + threshold 가 잡음 (combined=danger)
       - 점진 trend → ARIMA 가 잡음
       - seasonal → 시각 휴리스틱 (night_abnormal)
       - 학습 분포 변화 → 재학습 cadence

[효과] "의도된 한계 vs 실제 버그" 구분 명시. 4축 결합으로 전체 시스템 정상.
       skill/troubleshooting/0519_arima-single-spike-limit.md.
```

### 증빙자료 ⭐⭐⭐⭐⭐

- Before/After 비교표 3개 (아래)
- alarm_push_dedup_hits_total Grafana 카운터 캡처 → `[증빙 1]`
- AI mute is_ai_mute_active 차단 카운터 캡처 → `[증빙 2]`
- 8000W 강제 주입 검증 로그 → `[증빙 3]`
- _AckStore 진단 보고서 인용 → `[증빙 4: docs/codereviews/2026_05_20/alarm-symptom-bottleneck-diagnosis.md]`
- SQLite 폭증 인시던트 그래프 (12GB → 200MB) → `[증빙 5]`

#### Before/After 비교표 3개

| 사례 | Before | After |
|---|---|---|
| **T3 dedup** | Celery retry × 3 → 같은 push 최대 3 회 중복 | NX EX 30s fingerprint dedup → 중복 push 0% |
| **AI vs rule 중복** | 같은 채널의 AI + rule 알람 동시 발화 | ai_fired:* Redis TTL 60s 로 rule mute → 중복 0% |
| **SQLite 폭증** | Raw 무한 누적 → DB 12GB 폭증 → lock busy | DataRetentionPolicy + 7~14일 TTL → 200MB |

#### 한계 (정직)

| 한계 | 영향 | 후속 plan |
|---|---|---|
| 16채널 중 4채널만 AI 활성 | 12채널은 정적 임계만 의존 | D+30 sprint 확장 |
| SARIMA seasonal 미적용 | 시각 사이클 자동 학습 부재 | 운영 데이터 1~2주 후 도입 |
| auto-arima 미적용 | (p,d,q)=(1,1,1) 고정 | D+30 sprint |
| LRU cache cap 부재 | N device 확장 시 메모리 폭증 위험 | D+30 sprint |
| _AckStore 멘탈 모델 충돌 | 운영자 ack 알람 24h 영구 차단 | 시연 후 sprint 1순위 |
| 실 IoT 미연동 | dummy 로 구조 검증 | 4차 단계 |

#### 향후 계획 (D-day / D+30 / D+90 / 장기)

| 단계 | 주요 작업 |
|---|---|
| D-day (~2026-06-14) | 시연 안정화 — 추가 모델 변경 X, 알려진 P1·P2 수정만 |
| D+1 ~ D+30 | 정확도 본격 — FFT/ACF 분석 + SARIMA 도입 + IF feature 확장 + ARIMA confusion matrix 측정 + _AckStore 패치 |
| D+30 ~ D+90 | 확장성 본격 — LRU cap + 16채널 확장 + auto-arima + CUSUM 결합 + 디바이스 클러스터링 PoC + 가스 ARIMA MLModel 통합 |
| D+90+ | 장기 — Online ARIMA + 클러스터 운영 정착 + Global model 실험 + PG/TimescaleDB 전환 |

---

# 11장. 결론

### 이 장의 핵심 목적
```
본 프로젝트의 성과 + 본인 기여 영역의 기술적 의미 + 한계 + 향후 확장 방향을
요약합니다.
```

### 무엇을 수행하는가?
```
디코나이 R&D 요구사항 기반으로 다음을 완성하였습니다:

전체 프로젝트:
- 7-서비스 Docker Compose 운영 환경 (drf + fastapi + redis + celery×2 + prom + grafana)
- 가스 + 전력 + 위치 1Hz 실시간 수집·저장·시각화
- 통합 대시보드 (16채널 + 작업자 + 알람 한 화면)

본인 기여:
- 전력 AI 5축 정책 엔진 (IF + ARIMA + Z + CP + Threshold) + un-downgrade architecture
- 도메인 의존 의사결정 (가스 격하 vs 전력 un-downgrade)
- 알람 시스템 재설계 (decide_alarm 6 매트릭스, AI mute, fingerprint dedup)
- algorithm_source 6 종 — 운영자 추적 가능한 driver 라벨
- night_abnormal 시각 컨텍스트 휴리스틱
```

### 왜 필요한가?
```
본 결론은 면접관·평가자에게 다음을 마지막으로 요약합니다:

1. R&D 요구사항을 기술적으로 해석한 결과 — 6 계층 + 7-서비스 구조
2. 본인이 담당한 영역의 기술적 차별점 — 5축 결합, un-downgrade, 알람 단일 결정자
3. 정직한 한계 인정 — 16채널 / SARIMA / 실 IoT / PG 전환 모두 단계 분리
4. 다음 sprint 의 명확한 계획 — D+30 sprint 우선순위 표 명시
```

### 어떻게 수행했나?
```
본 프로젝트는 단순 기능 구현이 아니라 다음 의사결정 패턴 4가지를 일관 적용하였습니다:

1. 1차 PoC → 시연 후 본격 확장
   - 4채널 PoC → D+30 16채널
   - 시각 휴리스틱 → D+30 SARIMA
   - 4피처 IF → D+30 hour/day/ACF 확장

2. 모델 한계 명시 + 다른 축으로 보완
   - ARIMA 단발 spike → IF + threshold 가 잡음
   - SARIMA 회피 → night_abnormal 휴리스틱
   - IF feature 빈약 → Z + CP 외부 축 보강

3. 도메인 의존 architecture (비대칭 정당화)
   - 가스 = ARIMA 격하 / 전력 = un-downgrade
   - 전력만 Change Point + night_abnormal + 다채널
   - 가스만 다변량 IF (공기 화학 상관)

4. 운영 데이터 누적 후 정당성 검증
   - ARIMA 가중치 → D+30 confusion matrix
   - 정격 30% cutoff → D+30 채널별 baseline
   - 윈도우 30 → D+30 false positive 빈도

본 4가지 패턴이 신규 axis 도입 시 의사결정 framework 로 재활용 가능합니다.
```

### 증빙자료 ⭐⭐⭐⭐⭐

- 본인 회고 (작업 시간순 의사결정 흐름) → `[증빙 1: 본인 작성]`
- 4 패턴 적용 사례 표 (위 본문 흡수)
- 다음 sprint 우선순위 표 (10장 §향후 계획 인용)
- 학습한 외부 자료 (Hyndman 책 / IF 원논문 / STL 튜토리얼) → `[증빙 2: 본인 작성]`

#### 본인 기여 요약 (한 페이지)

| 영역 | 결과 | 기술적 의미 |
|---|---|---|
| 전력 AI 5축 결합 | 4축 (IF + ARIMA + Z + CP + Threshold) + night_abnormal | 임계 도달 전 조기 경고 + 운영자 추적 가능 |
| un-downgrade architecture | 가스 격하 / 전력 un-downgrade 도메인 의존 결정 | 도메인 fit + ARIMA 본질 가치 4가지 보존 |
| 알람 단일 결정자 (T4) | fastapi 가 decide_alarm 6 매트릭스로 source 결정 | race 자체 차단 + AI 침묵 4 분기 정적 cover |
| AI mute (ai_fired:*) | Redis TTL 60s + DRF alarm_dedupe 가드 | AI vs rule 중복 알람 0% |
| fingerprint dedup (T3) | NX EX 30s 4 분기 | Celery retry 중복 push 0% |
| algorithm_source 6 종 | 운영자 한글 워딩 통일 | "어느 알고리즘이 잡았나" 운영자 추적 |
| 본인 트러블슈팅 3선 | T3 dedup / AI vs rule / 3대 증상 진단 | 운영 데이터로 진단·해결·인계 |

#### 향후 확장 방향 (4단계)

```
시연 (2026-06-14)
   │
   │ D+1 ~ D+30 — 정확도 본격
   │   ├ FFT/ACF 분석 + SARIMA / STL 도입
   │   ├ IF feature 확장 (hour / day_of_week / 자기상관)
   │   ├ ARIMA confusion matrix 측정 → un-downgrade 가중치 검증
   │   └ _AckStore 멘탈 모델 패치
   │
   │ D+30 ~ D+90 — 확장성 본격
   │   ├ LRU cap + 16채널 확장
   │   ├ auto-arima ((p,d,q) 자동 선택)
   │   ├ CUSUM + Change Point 결합
   │   └ 디바이스 클러스터링 PoC
   │
   ▼ D+90+ — 4차 본격 도입
        ├ PostgreSQL + TimescaleDB 전환
        ├ 추론 서버 분리 (3-tier)
        ├ Online ARIMA (Kalman filter)
        └ Global model 실험
```

본 프로젝트는 시연 (2026-06-14) 으로 끝이 아닌, **4차 R&D 본격 단계로
이어지는 architecture 검증 단계**이며, 본인 기여 영역의 후속 plan 까지
명확히 분리·정리되어 있습니다.

---

> **이 문서의 핵심 메시지**:
> 전력 AI 의 5축 정책 엔진 + 도메인 의존 un-downgrade architecture + 알람
> 단일 결정자 (decide_alarm 6 매트릭스) 가 본인 핵심 차별점. 시연 후 sprint
> 4단계 로드맵으로 한계 인정 + 다음 단계 정량적 계획까지 포함.
