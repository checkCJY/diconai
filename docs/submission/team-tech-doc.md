# 디코나이(DICONAI) 산업재해 예방 통합 관제 시스템 — 팀 기술문서

> **문서 성격**: 4차 R&D 시연·평가 제출용 **팀 기술문서**(전체 시스템 관점).
> 개인 취업용 기술문서([tech-doc.md](tech-doc.md))와 분리된, 시스템·팀 중심 문서입니다.
> **작성 기준**: 2026-06-02 / 브랜치 `feature/0602_power_alarm_flood` (코드 = 진실 공급원).
> `[팀원 확인: ...]` = 담당 팀원 확인 필요 / `[증빙 N: ___]` = 시연 전 채울 캡처·다이어그램 placeholder.

## 목차

| 장 | 제목 | 상태 |
|---|---|---|
| 1 | 프로젝트 개요 및 수행 범위 (팀 구성·역할 포함) | ✅ 초안 |
| 2 | 요구사항 분석 및 구현 매핑 | ✅ 초안 |
| 3 | 시스템 아키텍처 및 데이터 흐름 | ✅ 초안 |
| 4 | 데이터 계약 및 데이터베이스 설계 | ✅ 초안 |
| 5 | 실시간 모니터링 대시보드 | 🟡 스켈레톤(정휘훈) |
| 6 | 위험 판단 및 알람 시스템 | ✅ 초안(최재용) |
| 7 | AI 분석 및 예측 | ✅ 전력(최재용) / 🟡 가스(이성현) |
| 8 | 백오피스 / 운영자 관리 인터페이스 | 🟡 최재용 절 + 스켈레톤(각자) |
| 9 | 운영 구조 및 모니터링 | ✅ 최재용 영역 + 스켈레톤(정휘훈·이성현) |
| 10 | 프로젝트 관리 및 협업 방식 (PM) | ✅ 초안(최재용) |
| 11 | 트러블슈팅 · 한계 · 향후 계획 | ✅ 초안(최재용) |
| 12 | 결론 | ⏳ 최재용 초안 예정 |

---

# 1장. 프로젝트 개요 및 수행 범위

### 이 장의 핵심 목적

```
디코나이(DICONAI) 산업재해 예방 통합 관제 시스템이 무엇을 위해, 어떤 R&D
요구에서 출발했는지를 정의하고, 시스템 전체를 6계층(수집/저장/위험판단/
AI분석/시각화/운영)으로 나눈 본 기술문서의 전체 수행 범위와 팀 구성·역할
분담을 한 장으로 제시한다.
```

본 장은 이후 2~12장 전체의 진입점이다. 여기서 정의한 시스템의 배경·목표·계층 구조·범위·팀 분담은 각 장의 상세 서술이 어디에 위치하는지를 가리키는 지도 역할을 한다.

---

### 무엇을 수행하는가?

디코나이는 산업 현장의 **유해가스 농도, 전력 설비 상태, 작업자 위치**를 1초 단위로 실시간 수집·검증하고, 위험 발생 시 운영자와 작업자 양쪽에 즉시 알람을 전달하는 **산업재해 예방 통합 관제 시스템**이다. 팀은 단순한 화면 구현이 아니라, "데이터 수신 → 저장 → 위험 판단 → AI 분석 → 시각화 → 운영 관찰"로 이어지는 실시간·비동기·관찰 가능한 안전 관제 플랫폼을 설계·구현하였다.

시스템은 두 개의 백엔드 서버를 축으로 구성된다.

| 서버 | 포트 | 스택 | 역할 |
|---|---|---|---|
| `drf-server` | 8000 | Django + DRF | 인증, HTML 렌더링, DB 영속성, REST API |
| `fastapi-server` | 8001 | FastAPI | 센서 수신, WebSocket 브로드캐스트, AI 추론, Celery 브리지 |

데이터 흐름의 큰 그림은 다음과 같다.

```
IoT/더미 센서  →  fastapi-server (수신·검증·AI 추론)  →  drf-server (영속화)
                                       │
                                       └→  WebSocket (브라우저·작업자 실시간)
```

수집 대상은 세 도메인이다.

- **유해가스** — 다종 가스 1Hz 수신, 다변량 AI 이상탐지(3축) + 정적 임계 판단
- **전력** — 다채널 설비 전력(W/A/V/on-off) 1Hz 수신, 5축 AI 정책 엔진 + 정격 % 기반 임계 판단
- **작업자 위치** — 지오펜스 진입 판정 + 가스/전력 위험 시 소속 시설 작업자에게 알람 전송

본 문서가 다루는 전체 범위는 위 세 도메인의 데이터 계약(2·4장), 시스템 아키텍처(3장), 실시간 대시보드(5장), 위험 판단·알람(6장), AI 분석·예측(7장), 백오피스 운영 인터페이스(8장), 운영 모니터링(9장), 프로젝트 관리·협업(10장), 트러블슈팅·한계·향후(11장), 결론(12장)이다.

---

### 왜 필요한가?

산업 현장에서 가스 누출·전력 과부하·작업자 위험구역 진입과 같은 사고는 **"임계치를 명백히 초과한 시점"에만 알리는 것으로는 예방이 불가능**하다. 임계 도달 시점은 이미 위험이 현실화된 시점이기 때문이다. R&D(4차) 단계가 요구한 핵심은 다음 세 가지로 요약된다.

| R&D 요구 | 의미 | 본 시스템에서의 구현 방향 |
|---|---|---|
| ① 임계 도달 **전** 조기 경고 | 점진적 부하 증가, 평소 대비 튐, 패턴 변화 시점을 사전 인지 | 다축 AI 정책 엔진(전력 5축 / 가스 3축) + 정적 임계의 결합 |
| ② **비동기** 운영 | 수신·영속화·AI 추론·브로드캐스트가 서로의 지연에 묶이지 않도록 격리 | Redis Stream + Celery 워커 분리 + 2-서버 역할 분리 |
| ③ **관찰 가능한** 시스템 | "AI가 몇 번 추론했나 / 어느 축이 발화했나 / 알람이 왜 막혔나"에 답할 수 있는 운영 가시성 | Prometheus 메트릭 19종 + Grafana 6 대시보드 |

이 세 요구가 동시에 만족되어야 "기술 검증"(조기 경고가 실제로 동작함)과 "운영 견고성"(24/7 환경에서 관찰·진단 가능함)이라는 두 목표를 함께 달성할 수 있다.

특히 ①의 조기 경고는 단일 모델로는 달성되지 않는다. 절대값 초과·학습 분포 밖 spike·점진적 trend break·통계적 튐·패턴 변화 시점은 서로 다른 축이 잡아내는 직교 패턴이기 때문이다. 따라서 다축 결합 + 도메인별 차등 정책(가스는 즉시 위험 도메인, 전력은 점진 변화 도메인)이 필요하며, AI가 침묵하거나 실패할 때는 정적 임계가 책임지는 안전망(AI는 "있으면 좋은 것"이지 "없으면 안 되는 것"이 아니다)이 함께 설계되어야 한다. 구체적 정책은 6·7장에서 다룬다.

---

### 어떻게 수행했나?

#### (1) 시스템을 6계층으로 분해

팀은 R&D 요구를 기능 단위로 분해한 뒤, 시스템을 다음 6계층으로 설계하였다. 각 계층은 본 문서의 특정 장에 1:1로 대응한다.

| 계층 | 책임 | 핵심 구성요소 | 상세 장 |
|---|---|---|---|
| ① 수집 | 센서 JSON 수신·Pydantic 검증 | fastapi 가스/전력/위치 라우터 | 2·3장 |
| ② 저장 | 영속화·데이터 계약·이력 보존 | PostgreSQL 16, AlarmRecord/Event, MLAnomalyResult | 4장 |
| ③ 위험 판단 | 임계 평가 + 단일 결정 + 알람 발화 | `decide_alarm` 6 매트릭스, Redis Stream 큐 | 6장 |
| ④ AI 분석 | 다축 이상탐지·예측 | 전력 5축 / 가스 3축, AI mute | 7장 |
| ⑤ 시각화 | 실시간 대시보드·작업자/관리자 화면 | WebSocket 브로드캐스트, 알람 모달/토스트 | 5장 |
| ⑥ 운영 | 비동기 인프라·메트릭·백오피스 | Docker 10 컨테이너, Prometheus/Grafana, 어드민 21메뉴 | 8·9장 |

#### (2) 현행 운영 구조의 핵심 사실

설계가 실제로 동작하는 형태로 통합된 현 시점(2026-06-02)의 구조는 다음과 같다.

- **컨테이너 구성 (10개)** — `redis`, `postgres`(PG16), `drf`, `fastapi`, `celery-worker-alarm`(`-Q alarm`, concurrency=2), `celery-worker-metric`(`-Q metric`, concurrency=1), `celery-beat`, `redis_exporter`(:9121), `prometheus`(:9090), `grafana`(:3000)
- **데이터베이스** — PostgreSQL 16으로 전환 완료(2026-05-22). SQLite는 폐기되었으며, TimescaleDB만 4차 과제로 잔존한다.
- **알람 큐** — Redis Stream(key `diconai:ws:alarms`). push는 `XADD`(maxlen ~10000), 소비는 replica별 독립 `XREAD BLOCK` 커서로 fan-out한다. 소비 루프는 `alarm_flush_loop`이며, 센서 통합데이터 주기 송신용 `broadcast_loop`과는 별개다.
- **알람 결정** — fastapi가 단일 결정자로서 `decide_alarm` 6 매트릭스(AI state × 정적 결과 → source)로 알람 출처를 확정한다. 중복은 fingerprint dedup(`alarm:push:dedup:*`, NX EX 30s, 4분기)과 AI mute(`ai_fired:{device}:{channel}:{rule_level}`, TTL 60s)로 차단한다.
- **AI** — 전력은 5축(Threshold/IsolationForest/ARIMA/Z-score/ChangePoint) + `night_abnormal` 휴리스틱, 활성 4채널(ch1 압연기 7.5kW / ch9 메인전력반 15kW 3상 / ch14 공조 5.5kW / ch15 조명 1kW). 가스는 3축(다변량 IsolationForest + ARIMA + ChangePoint), advisory 운영(격상 결정은 정적 임계 우선).
- **알람 안정화** — DANGER 2틱 confirm(`DANGER_CONFIRM_TICKS=2`, 단일 틱 스파이크 false danger 억제), WARNING 5초 지속(`WARNING_DURATION_SEC=5`), 전력 Event RESOLVE는 채널-aware(마지막 활성 채널 정상화 시에만).
- **작업자 알람 확장** — 가스/전력 DANGER가 소속 시설 작업자에게도 전송된다(`target_worker_ids` → `worker_clients` 분배). Discord 알람 연동도 갖추되 기본 OFF(opt-in)로 운영한다.
- **관찰 가능성** — Grafana 6 대시보드(overview/sensor/alarm/power-ai/gas-ai/db-redis), Prometheus 메트릭 19종.
- **백오피스** — `/admin-panel/` 프리픽스의 커스텀 어드민 21메뉴(Django 기본 admin과 별도). 단일 라우터가 페이지 셸을 제공하고 데이터는 JS가 `/api/admin/...`을 fetch하며, 권한은 API단 `IsSuperAdmin`으로 통제한다.

#### (3) 팀 개발 프로세스

팀은 모든 기능을 "① 기능정의서 1차 작성 → ② 필요 데이터(스키마) 정의 → ③ 데이터 흐름 구조 + 동기/비동기 결정 + 로깅 지점 명시 → ④ 코딩 + 완료 기준 체크리스트"의 4단계로 진행하였다. 새 모델 필드·인덱스 추가나 마이그레이션은 팀에 사전 공유하는 것을 원칙으로 하였다. 상세한 협업·PM 방식은 10장에서 다룬다.

#### (4) 본 문서가 다루는 범위와 제외 범위

| 구분 | 항목 |
|---|---|
| **다룸 (1~12장)** | 가스/전력/위치 수집, PG 데이터 계약, 2-서버 아키텍처, 실시간 대시보드, 위험 판단·알람, 전력 5축/가스 3축 AI, 백오피스 21메뉴, Docker 10 컨테이너 운영·모니터링, 협업 방식 |
| **4차 과제로 잔존** | TimescaleDB 도입, 실 IoT 게이트웨이 연동, 16채널 전체 AI 활성화(현재 4채널 PoC), SARIMA seasonal 모델 |

제외 범위는 외부 의존(에어위드 게이트웨이 일정, 측위 하드웨어)이나 운영 데이터 누적 선행 조건에 따른 것으로, 상세 정당화는 2장(요구사항 매핑)과 11장(한계·향후)에서 다룬다.

---

### 팀 구성·역할 분담

본 프로젝트는 외부 기업 협업이 아니라 **팀 내부 프로젝트**로, 백엔드·인프라·AI·프론트가 모두 팀 내부에서 수행되었다. 프로젝트 기간은 [팀원 확인: 공식 수행 기간 시작일·종료일] 이며, 형상 이력 기준으로는 2026-04-15에 첫 커밋이 기록되었다.

역할 분담은 형상 이력(git author), 기능정의서 파일 접두어, 단계별 결정 문서를 근거로 정리하였다.

| 구성원 | 주요 역할 | 담당 영역 (근거) |
|---|---|---|
| **최재용 (PM / 백엔드·AI·알람)** | 프로젝트 관리 + 전력 AI + 알람 시스템 + 백엔드 + 인증 | 전력 5축 AI 정책 엔진, `decide_alarm` 단일 결정자·dedup·AI mute, 알람 팝업(모달/토스트)·작업자 알람 확장, 가스 AI 안정화, 단계별 단독 결정문 작성, 인증/로그인 영역 인수(한지혜 중도 하차分) |
| **정휘훈 (백오피스 / 모니터링)** | 커스텀 백오피스 + 모니터링 대시보드 + 서버 설정 | `/admin-panel/` 어드민 메뉴(기준정보·이벤트이력·임계치·공통코드 등), Grafana 전력/가스 AI 대시보드·Prometheus 메트릭, Django settings dev/prod 분리, 작업자 현황·공지·체크리스트 페이지 *(상세는 본인 작성 예정)* |
| **이성현 (인프라 / DevOps)** | 컨테이너·CI·멀티레플리카·시계열 더미 | k8s manifest·minikube 검증, GitHub Actions CI, Broadcast 공유상태 Redis 이관(멀티레플리카 계층1), Grafana DB·Redis 패널, PG 마이그레이션/시퀀스 정합, 가스 시나리오 더미·체인지포인트 사전필터, DataRetentionPolicy 제안 *(상세는 본인 작성 예정)* |
| **한지혜 (인증 / 프론트) — 중도 하차** | 초기 로그인·인증 + 공통 UI | JWT 기반 로그인 API·로그인 유효성 검사, 공통 헤더·CSS 구조 등을 초기에 구현한 뒤 프로젝트 중간에 이탈. 이후 인증/로그인 영역은 **최재용이 인수·유지** |

> 형상 이력 식별자 매핑(확정): `cjy`/`checkCJY` = 최재용, `Jung HwiHun`/`JUNGHWIHUN` = 정휘훈, `dbst0508-beep` = 이성현, `han jihye`/`hanjihye2712-oss` = 한지혜(중도 하차, 인증/로그인은 최재용 인수). 현재 개발 인원은 **최재용·정휘훈·이성현 3인**이다. 정휘훈·이성현 행의 상세 담당 영역은 각 팀원이 본인 작업 기준으로 최종 작성하며(위 표의 해당 행은 git 이력 기반 초안), [팀원 확인: 디자인·펌웨어 담당 별도 존재 여부, 프로젝트 공식 수행 기간]만 잔여.

---

### 증빙자료 ⭐⭐⭐⭐⭐

- 연구개발계획서 핵심 요구 문구 캡처 (임계 도달 전 조기경고·비동기·관찰가능) → `[증빙 1: 연구개발계획서 형광펜 캡처]`
- 6계층 구조 다이어그램 → `[증빙 2: 수집/저장/위험판단/AI분석/시각화/운영 6계층 + 장 매핑]`
- 전체 시스템 데이터 흐름 다이어그램 (IoT → fastapi → drf / WebSocket) → `[증빙 3: 10 컨테이너 + E2E 화살표]`
- Docker 10 컨테이너 기동 결과 캡처 → `[증빙 4: docker compose ps — 10 서비스 healthy]`
- R&D 3대 요구 ↔ 구현 매핑 요약표 (본 장 표) → `[증빙 5: 요구-구현 매핑 표 캡처]`
- 팀 역할 분담표 + 형상 이력(author별 커밋 분포) 캡처 → `[증빙 6: git shortlog -sn 및 역할 매핑]`
- 메인 통합 대시보드 캡처 (가스·전력·작업자 한 화면) → `[증빙 7: 대시보드 초기 화면]`

---

# 2장. 요구사항 분석 및 구현 매핑

### 이 장의 핵심 목적

```
디코나이 R&D 요구사항을 기능 단위로 분해하고, 각 항목을
구현 / 부분 구현 / 미구현 + 증빙 위치로 매핑한다.
"모든 것을 완성했다"가 아니라 "어디까지 실제로 도달했는가"를
객관적으로 드러내, 시스템의 현실성과 신뢰도를 명확히 한다.
```

### 무엇을 수행하는가?

디코나이는 가스·전력·작업자 위치를 실시간 수집하고, 위험을 판단하며, 다채널로 경보를 보내는 산업 안전 통합 관제 시스템이다. R&D 요구는 센서 연계부터 운영 관찰까지 범위가 넓어, 팀은 이를 다음 **7개 범주**로 재구성하고 각 범주의 구현 수준과 증빙을 표로 정리하였다.

1. **외부 센서 및 스마트 파워 시스템 연계** — 가스 9종 + 전력 16채널 수신·검증·저장
2. **통합 대시보드 및 실시간 시각화** — 채널·작업자·알람 한 화면 + WebSocket 즉시 반영
3. **위험 판단 로직 및 경보 처리** — 임계치 + 다축 AI + 알람 lifecycle
4. **AI 분석 및 예측** — 전력 5축 / 가스 3축 정책 엔진
5. **백오피스 및 운영자 관리 인터페이스** — `/admin-panel/` 커스텀 어드민 21메뉴
6. **비동기·배포 운영 구조** — Redis/Celery + Docker Compose 10 컨테이너 + Prometheus/Grafana
7. **알람 신뢰성** — 단일 결정자·중복 방지·작업자 대피 통보·Discord 연동

각 범주를 `구현` / `부분 구현` / `미구현`으로 판정하고, 그 근거가 되는 코드·문서·캡처 위치를 증빙으로 함께 명시한다. 미구현 항목은 별도 정당화 표로 분리해, 무엇을 왜 다음 단계로 미뤘는지 명확히 한다.

### 왜 필요한가?

산업 안전 관제처럼 범위가 넓은 시스템은 요구사항을 추적성 있게 매핑하지 않으면 두 가지 위험이 발생한다.

- **과대 서술의 위험** — "전부 완성했다"고 쓰면 평가자가 한 항목이라도 미흡함을 발견하는 순간 문서 전체의 신뢰도가 무너진다.
- **추적 불가의 위험** — 피그마 화면설계서, 백엔드 모델, 어드민 페이지가 따로 진화하면 "이 화면의 기능이 백엔드에 있는가"를 누구도 단언하지 못한다.

따라서 본 장은 (1) 요구사항을 기술적으로 해석한 결과, (2) 구현/부분/미구현 구분, (3) 증빙 위치, (4) 미구현 정당화, (5) 화면설계서 ↔ 백엔드 ↔ 어드민 추적성을 한 곳에 모은다. 이로써 평가자가 본 프로젝트의 실제 도달 수준을 정직하게 판단할 수 있고, 팀 내부에서도 잔여 작업의 우선순위를 합의할 수 있다.

특히 디코나이는 **"기능이 없다"와 "운영자 노출 단계만 남았다"를 구분**하는 것이 핵심이다. 다수의 관리 영역은 모델과 Django 기본 admin이 이미 갖춰져 있고, 커스텀 어드민 패널 페이지만 추가하면 즉시 사용 가능한 상태다. 이 차이를 명시하는 것이 매핑 표의 가장 중요한 가치다.

### 어떻게 수행했나?

팀은 두 종류의 원본을 양방향으로 대조하여 매핑을 도출하였다.

- **R&D 요구사항 문서 / 엑셀 기능정의서 v7** — "요구된 것"의 목록 (26개 어드민 그룹 포함)
- **코드 실사 (4-agent 코드베이스 점검) / 피그마 화면설계서** — "실제로 있는 것"의 목록

두 목록을 교차 검증해 일치·부분·누락·역방향(코드만 있고 사양서엔 없음)을 가려냈다. 판정 기준은 다음 4단계로 통일하였다.

| 판정 | 의미 |
|---|---|
| 구현 | 모델·API·페이지(또는 운영 채널)가 모두 동작하고 실시간/영속까지 연결됨 |
| 부분 구현 | 모델과 Django 기본 admin은 있으나 커스텀 어드민 운영자 UI 미노출, 또는 일부 검증/사양 미정 |
| 미구현 | 모델·API·페이지 모두 신규 작업 필요, 또는 외부 의존/사양 미정으로 의도적 보류 |

#### 1) 요구사항-구현 매핑표 (7범주)

| # | 요구사항 범주 | 판정 | 구현 내용 | 증빙 위치 |
|---|---|---|---|---|
| 1 | 센서 연계 (가스 9종 + 전력 16채널) | 구현 | fastapi 라우터가 JSON 수신·Pydantic 검증 후 drf-server에 영속화. 1Hz 더미 시뮬레이터로 전 채널 구동 | gas/power router, Pydantic 스키마, PowerData/GasData 저장 결과 |
| 2 | 통합 대시보드·실시간 시각화 | 구현 | 16채널·작업자·알람 한 화면. WebSocket으로 센서 통합데이터·알람 즉시 반영 | 메인 대시보드 캡처 (5장 상세) |
| 3-a | 임계치 위험 판단 | 구현 | `power_facility_default` % + channel_meta 정격을 단일 진실 공급원으로 정격 % 환산 평가 | 위험 판단 코드 + 위험도 표시 캡처 (6장 상세) |
| 3-b | 알람 lifecycle (Event/AlarmRecord) | 구현 | 같은 사건당 1 Event + N AlarmRecord merge, APPEND-ONLY EventLog 감사 | AlarmRecord/Event 동시 생성 결과 (4·6장 상세) |
| 4-a | 전력 AI 분석·예측 | 구현 | 5축(Threshold/IsolationForest/ARIMA/Z-score/ChangePoint) + night_abnormal 휴리스틱. 활성 4채널 | 5축 결합 다이어그램, Grafana power-ai 패널 (7장 상세) |
| 4-b | 가스 AI 분석·예측 | 구현 | 3축(다변량 IsolationForest + ARIMA + ChangePoint), advisory 운영 | gas-ai Grafana 패널 (7장 상세) |
| 5-a | 백오피스 — 운영 데이터·맵 편집 | 구현 | `/admin-panel/` 커스텀 어드민 21메뉴. 지도 편집기에 가스·전력·위치 노드 통합 CRUD | admin-panel 캡처 (8장 상세) |
| 5-b | 백오피스 — 기준정보 관리 (메뉴·공통코드·직위·위험유형·임계치·위험기준) | 부분 구현 | 모델 + Django 기본 admin은 완비. 커스텀 어드민 운영자 UI는 일부 미노출 (안전 직결 영역은 의도적 위임) | 누락영역 리스트업 §A.1~A.8 |
| 6-a | 비동기 처리 (Redis/Celery) | 구현 | 알람 큐 Redis Stream + Celery 워커 2종 분리 (alarm/metric) | 10 컨테이너 구성 (9장 상세) |
| 6-b | Docker Compose 배포 | 구현 | **10 컨테이너** 운영 환경 | `docker compose ps` 결과 |
| 6-c | Kubernetes 배포 | 미구현 | minikube 실험 단계 — 4차 본격 | — |
| 6-d | 메트릭 관찰 (Prometheus/Grafana) | 구현 | Grafana 6 대시보드 + Prometheus 메트릭 19종 | Grafana 캡처 (9장 상세) |
| 7-a | 알람 단일 결정자·중복 방지 | 구현 | fastapi `decide_alarm` 6 매트릭스 + fingerprint dedup + AI mute | 6장 상세 |
| 7-b | 작업자 DANGER 대피 통보 | 구현 | 가스·전력 DANGER가 소속 시설 작업자에게도 전송 (target_worker_ids, worker_clients) | 6장 상세 |
| 7-c | Discord 외부 알림 연동 | 구현 | 관리자 webhook=전체 broadcast / 작업자 webhook=지오펜스 개인멘션·DANGER @here 대피 (opt-in) | `apps/notifications/discord_service.py` |
| 8 | AI 결과 저장·화면 연동 | 구현 | MLAnomalyResult 영속 + AlarmRecord.algorithm_source 6종 한글 라벨 | DB 저장 결과 + UI 라벨 (7장 상세) |

> `[증빙 1: 원본 R&D 요구사항 / 엑셀 기능정의서 v7 핵심 키워드 형광펜 캡처]`

#### 2) 백오피스 "부분 구현" 상세 (모델은 있고 운영자 UI만 남은 영역)

5-b의 실체를 분리해 보면, 디코나이의 "부분 구현"은 대부분 **모델·Django 기본 admin은 완비되었고 커스텀 어드민 패널 페이지만 추가하면 되는 상태**다. 이는 약점이 아니라, 운영 변경 빈도가 낮거나 안전 직결인 영역을 의도적으로 단계 분리한 결과다.

| 영역 | 모델 | Django 기본 admin | 커스텀 어드민 UI | 보류 사유 |
|---|---|---|---|---|
| 메뉴 관리 (MNU) | 있음 | 있음 | 미노출 | 운영 중 변경 빈도 낮음 → Django admin 위임 |
| 공통 코드 (CMM) | 있음 | 있음 | 미노출 | 시스템 설정 영역 (변경 드묾) |
| 직위 관리 (POS) | 있음 | 있음 | 드롭다운 참조만 | 직위 ↔ 권한 매핑 규칙 미정 [팀원 확인: 권한 매핑 사양] |
| 위험 유형 (RSK-01,02) | 있음 | 있음 | 알림정책 드롭다운 옵션 | enum 1:1 마스터 데이터 → 현 정책 유지 |
| 임계치 (THR) | 있음 | 있음 | 미노출(읽기전용 표시) | 안전 직결 → RBAC·변경이력 정리 후 노출 |
| 위험 기준 (RSK-03,04) | 있음 | 있음 | 미노출 | 안전 직결 → RBAC 정리 후 |
| 이벤트 이력 조회 (EVT, 어드민측) | EventLog 있음 | [팀원 확인: 등록 여부] | 미노출 | 산업안전법 감사 요구 → 시연 후 sprint 우선 |

#### 3) 화면설계서 갭 — 코드는 있고 피그마/노출만 남은 항목

피그마 화면설계서 점검에서, 원본 지적이 이미 코드에 반영되어 있어 **노출만 하면 되는 항목**과 실제 신규 작업이 필요한 항목을 배지로 구분하였다.

| 화면설계서 지적 | 상태 | 근거 |
|---|---|---|
| viewer(열람자) 권한 옵션 누락 | ✅ 구현됨 | `UserType.VIEWER` 이미 정의 — UI 옵션 노출만 필요 |
| 임계치 LEGAL_THRESHOLDS 하드코딩 | ✅ 구현됨 | 이미 DB 이관 완료 (Threshold 모델) |
| 가스 센서 관리 화면이 피그마에 없음 | ✅ 코드는 있음 | 모델·어드민 페이지 존재 → 피그마만 누락 [팀원 확인: 디자이너 피그마 추가] |
| O2 역방향 임계치 검증 (미만 조건) | 🔧 작업 필요 | `evaluate_gas_risk()`는 미만 처리 가능, 어드민 폼 검증만 미반영 |
| RiskLevel enum → DB 이관 | 🔧 합의 필요 | 화면은 DB 동적 관리 전제, 코드는 TextChoices — 4차 합의 |
| 어드민 페이지네이션 컴포넌트 버그 | 🐛 공통 수정 | 운영데이터·로그 8개 화면 공통 — 헬퍼 1곳 수정 |

#### 4) 미구현 항목 정당화

미구현은 "할 수 없었던 것"이 아니라 "외부 의존 / 운영 데이터 누적 선행 / 사양 미정으로 의도적으로 다음 단계에 배치한 것"이다. **PostgreSQL 전환은 2026-05-22 완료되었으므로 미구현 목록에서 제외**하며, 데이터 계층 잔여 과제는 TimescaleDB뿐이다.

| 항목 | 단계 | 정당화 |
|---|---|---|
| 16채널 전체 AI 활성 | 1차 | 현재 부하 다양성을 대표하는 4채널(ch1 압연기 7.5kW / ch9 메인전력반 15kW 3상 / ch14 공조 5.5kW / ch15 조명 1kW) 검증. 운영 데이터 누적 후 전 채널 확장 |
| SARIMA seasonal | 2차 | 계절성 자동 학습은 1~2주 운영 데이터 누적이 선행 필요. 현재는 night_abnormal 시각 휴리스틱(KST 야간 + 정격 30% 초과)으로 우회 |
| 실 IoT 게이트웨이 연동 | 3차 | 외부 하드웨어/펌웨어 일정에 의존. 현재는 1Hz 더미 시뮬레이터로 수집~경보 E2E 구조를 검증 |
| TimescaleDB 전환 | 4차 | PostgreSQL 16 전환은 이미 완료. 시계열 압축·연속집계가 필요한 시점에 TimescaleDB로 확장 |
| Kubernetes 운영 배포 | 4차 | 현재 Docker Compose 10 컨테이너로 충분. minikube 실험 단계 |
| CFD 가스 확산 시뮬레이션 | 외부 R&D | 유체역학 해석 영역으로 별도 과제 |
| SMS / FCM 외부 알림 | 4차 | 외부 게이트웨이·모바일 앱 연동 필요. 현재 외부 알림은 Discord 연동으로 대체 동작 |

> Discord 알람 연동, 작업자 DANGER 대피 통보, danger 2틱 confirm(`DANGER_CONFIRM_TICKS=2`), WARNING 5초 지속(`WARNING_DURATION_SEC=5`), 채널-aware 전력 Event RESOLVE는 **모두 구현 완료** 항목으로, 미구현 목록에 포함하지 않는다.

#### 5) 요구사항 추적성 — 피그마 ↔ 백엔드 ↔ 어드민

요구사항 매핑이 한 번의 점검으로 끝나지 않으려면, **세 산출물(피그마 화면설계서 · 백엔드 모델/API · 어드민 패널 페이지)이 서로를 가리키는 추적 고리**가 있어야 한다. 팀은 엑셀 기능정의서 v7의 26개 어드민 그룹과 코드 실사 결과를 양방향으로 대조해, 세 산출물 간 불일치를 네 유형으로 분류하였다. (1) 세 가지가 모두 일치하는 정상 항목, (2) 피그마·백엔드는 있으나 어드민 운영자 UI만 빠진 "부분 구현"(메뉴·공통코드·직위·위험유형·임계치·위험기준 등 6영역), (3) 백엔드·어드민은 구현되었으나 피그마에만 빠진 역방향 누락(가스 센서 관리 화면), (4) 엑셀 사양엔 항목명만 있고 코드·사양 모두 미정인 영역(수집 항목 관리 COL). 이 분류 자체가 추적성 산출물이며, 어느 화면을 클릭하면 어느 모델·API·페이지로 연결되는지를 코드 위치까지 명시(예: 위치 노드 관리는 별도 CRUD 없이 `/api/map-editor/objects/`로 지도 편집기에 통합)함으로써, 평가자와 팀 모두 "이 화면의 기능이 백엔드에 실재하는가"를 단언할 수 있게 하였다. 반대로 엑셀 사양서에 없는데 코드로 추가된 항목(지도 편집 로그)은 사양서 v8 갱신 권고로 역피드백하여, 추적 고리가 한 방향이 아닌 양방향으로 닫히도록 하였다.

### 증빙자료 ⭐⭐⭐⭐⭐

- 요구사항-구현 매핑표 (7범주, 위 §1)
- 백오피스 부분 구현 상세표 (위 §2)
- 화면설계서 갭 배지표 (위 §3)
- 미구현 항목 정당화표 (위 §4)
- 추적성 4유형 분류 다이어그램 → `[증빙 2: 피그마 ↔ 백엔드 ↔ 어드민 추적 고리 + 4유형 분류]`
- 엑셀 기능정의서 v7 ↔ 코드 실사 양방향 대조 결과 → `[증빙 3: 26개 어드민 그룹 대조표 캡처]`
- 원본 R&D 요구사항 핵심 키워드 → `[증빙 1: 형광펜 캡처]`

> 각 범주의 구체적 구현은 시스템 아키텍처(3장), 데이터 계약·DB 설계(4장), 실시간 대시보드(5장), 알람 시스템(6장), AI 분석·예측(7장), 백오피스(8장), 운영 구조(9장)에서 상세히 다룬다.

---

# 3장. 시스템 아키텍처 및 데이터 흐름

### 이 장의 핵심 목적

이 장의 핵심 목적은, 디코나이 통합 관제 시스템이 **"센서 한 건의 측정값이 들어와서 운영자 화면의 알람으로 뜨기까지"** 어떤 경로를 거치는지를 한눈에 파악할 수 있게 하는 것입니다.

2장에서 정리한 요구사항(실시간 수집·위험 판단·즉시 알람·운영 관리)이 실제로 **어떤 서버에서, 어떤 순서로, 어떤 인프라 위에서** 동작하는지를 구조 차원에서 설명합니다. 개별 기능의 상세(대시보드는 5장, 알람 판단 로직은 6장, AI 분석은 7장, 백오피스는 8장, 운영·모니터링은 9장)는 후속 장으로 넘기고, 이 장에서는 **전체 골격과 데이터가 흐르는 한 줄기 경로**에 집중합니다.

팀은 이 아키텍처를 통해 다음 세 가지를 동시에 달성하고자 했습니다.

1. **책임 분리** — 동기 작업(인증·DB 영속·HTML)과 비동기 작업(센서 수신·실시간 푸시)을 서로 다른 서버로 나눠 한쪽 부하가 다른 쪽에 전이되지 않게 합니다.
2. **비동기 격리** — 알람 발송이 무거운 메트릭 집계나 DB 트랜잭션에 막히지 않도록 작업 큐를 분리합니다.
3. **재현 가능한 운영 환경** — 10개 컨테이너 전체를 노트북 한 대에서 한 번에 띄울 수 있게 Docker Compose로 묶었습니다.

---

### 무엇을 수행하는가?

디코나이는 **모노레포(monorepo) 안의 2-tier 백엔드 서버**와, 이를 받쳐 주는 **인프라 서비스 묶음**으로 구성된 통합 관제 플랫폼입니다.

#### 2개의 백엔드 서버 (2-tier)

| 서버 | 포트 | 프레임워크 | 역할 |
|---|---|---|---|
| `drf-server` | 8000 | Django + DRF | 인증·권한, 대시보드/백오피스 **HTML 렌더링**, **DB 영속화**, **REST API**, 알람 이력 저장 |
| `fastapi-server` | 8001 | FastAPI | 센서/더미 **데이터 수신·검증**, **AI 추론**, **WebSocket 실시간 브로드캐스트**, 알람 Celery 브리지 |

두 서버는 **하나의 저장소(모노레포)** 안에서 관리되어 공통 컨벤션·문서·배포 파이프라인을 공유하면서도, 런타임에서는 각자 독립 프로세스로 분리되어 동작합니다. 동기 모델에 최적화된 Django는 "본체" 웹서버로서 사용자가 보는 화면과 영속 데이터를 담당하고, 비동기에 강한 FastAPI는 초당 다수의 센서 수신과 실시간 푸시 전담 서버로 책임을 나눴습니다.

#### 인프라 서비스 — 합쳐서 10개 컨테이너

운영·시연 환경은 두 백엔드 서버를 포함해 **총 10개의 Docker 컨테이너**로 구성됩니다.

| # | 컨테이너 | 포트 | 책임 |
|---|---|---|---|
| 1 | `drf` | 8000 | Django + DRF — 인증·HTML·REST API·DB 영속·알람 생성 |
| 2 | `fastapi` | 8001 | 센서 수신·검증·AI 추론·WebSocket 브로드캐스트·알람 push |
| 3 | `postgres` | 5432 | 영속 저장소 (**PostgreSQL 16**, `shared_buffers` 256MB) |
| 4 | `redis` | 6379 | Celery 브로커 + WS 알람 **Redis Stream**(`diconai:ws:alarms`) |
| 5 | `redis_exporter` | 9121 | Redis 내부 상태를 Prometheus가 읽도록 변환 |
| 6 | `celery-worker-alarm` | - | **alarm 큐 전용** (`-Q alarm`, concurrency=2) |
| 7 | `celery-worker-metric` | - | **metric 큐 전용** (`-Q metric`, concurrency=1) |
| 8 | `celery-beat` | - | 주기 스케줄러 (정해진 시각에 작업 트리거) |
| 9 | `prometheus` | 9090 | 각 서비스 `/metrics`를 주기 수집해 시계열로 저장 |
| 10 | `grafana` | 3000 | Prometheus 데이터를 대시보드 6종으로 시각화 |

> 참고: 동일한 구성을 Kubernetes(minikube) 매니페스트로도 표현해 두었습니다. Compose와 k8s는 경쟁 관계가 아니라 **같은 시스템의 두 표현**(서비스·포트·이미지가 1:1 대응)이며, 평소 개발·시연은 Compose, 확장 가능한 운영 형태 학습·시연은 k8s를 사용합니다. 운영 구조의 세부와 다중 인스턴스 제약은 **9장**에서 다룹니다.

#### 데이터 저장소 — PostgreSQL 16

모든 영속 데이터(센서 기록·알람 이력·사용자·설비)의 최종 보관소는 **PostgreSQL 16** 컨테이너입니다. 초기에는 SQLite를 사용했으나 동시 쓰기·대용량에서 한계가 드러나 **2026-05-22 PostgreSQL로 전환을 완료**했고, SQLite는 폐기했습니다. 데이터 계약과 스키마 상세는 **4장**에서 다룹니다. (대용량 시계열 최적화를 위한 TimescaleDB 도입은 4차 과제로 남겨 둔 향후 항목입니다.)

---

### 왜 필요한가?

이 아키텍처의 각 결정에는 산업 안전 관제라는 도메인 특성에서 비롯된 분명한 이유가 있습니다.

| 결정 | 왜 이렇게 했는가 |
|---|---|
| **DRF + FastAPI 2서버 분리** | DRF는 인증·DB 영속·HTML 렌더링 등 동기 모델에 최적이고, FastAPI는 센서 수신·WebSocket 브로드캐스트 등 async에 최적입니다. 책임을 분리해 한쪽 부하가 다른 쪽으로 전이되지 않게 했습니다. |
| **알람 큐 = Redis Stream (XADD / replica별 독립 XREAD)** | Pub/Sub은 구독자가 없을 때 메시지가 유실되지만, Stream은 FastAPI 재시작 중에도 알람이 스트림에 적체되어 유실되지 않습니다. 또한 경쟁 소비 방식(한 알람을 한 소비자만 가져감)은 다중 replica로 확장할 때 일부 사용자에게 알람이 누락되므로, **replica별로 독립 커서를 두는 XREAD fan-out** 구조로 모든 replica가 모든 알람을 받게 했습니다. |
| **Celery 큐 alarm / metric 분리** | 알람 태스크가 무거운 주기 메트릭 집계와 같은 워커를 공유하면 알람이 지연됩니다. 안전 알람은 지연되면 안 되므로 **`-Q alarm`(concurrency=2)** 와 **`-Q metric`(concurrency=1)** 을 별도 워커로 분리해 알람 우선순위를 보장했습니다. |
| **PostgreSQL 16 (SQLite 폐기)** | SQLite는 동시 쓰기·대용량에서 락·용량 한계가 있어 2026-05-22 PG16 컨테이너로 전환했습니다. |
| **공유 상태 = 프로세스 메모리 + Redis 분리** | "지금 누가 접속 중인가"(WebSocket 연결 목록)는 각 프로세스가 자기 연결만 관리하면 되므로 프로세스 메모리에 둡니다. 반면 broadcast 스냅샷·알람 큐는 Redis로 외부화해, 확장 시 프로세스 간에 공유할 수 있게 했습니다. |

특히 **알람 전달의 무손실성**은 산재 예방 시스템에서 타협할 수 없는 요구입니다. "센서가 위험을 감지했는데 운영자 화면에는 안 떴다"는 단 한 번의 누락도 치명적이므로, 큐를 휘발성 메모리가 아니라 영속 가능한 Redis Stream으로 두고, 소비 측이 재접속하더라도 커서 이후 누적분을 배치로 다시 받을 수 있게 설계했습니다.

---

### 어떻게 수행했나?

#### E2E 데이터 흐름 (센서 → 화면)

전체 데이터 흐름은 다음 다이어그램으로 요약됩니다. 핵심은 **알람이 Redis Stream을 거쳐 `alarm_flush_loop`을 통해 브라우저로 전달된다**는 점입니다.

```
 [IoT 센서 / 더미 스크립트]
   가스·전력·작업자 위치 측정값
        │  ① HTTP POST  (:8001/api/sensors/gas · /api/power/watt · /api/positioning/receive)
        ▼
 ┌──────────────────────────────────────────────────────────┐
 │  fastapi-server (:8001)                                    │
 │   gas_router / power_router / position_router              │
 │        │                                                   │
 │        ▼  service 계층                                      │
 │   수신·검증  →  AI 추론(전력 5축 / 가스 3축)               │
 │   →  decide_alarm (AI state × 정적 결과 → source 6 매트릭스)│
 └───┬───────────────────────┬───────────────────────────────┘
     │ ② 영속화 POST          │ ③ 위험 판단 시 Celery 의뢰
     ▼                       ▼
 ┌──────────┐          ┌──────────────────────────────────┐
 │   DRF     │          │  Celery 워커 (큐 분리)            │
 │ (:8000)   │          │   • celery-worker-alarm (-Q alarm)│
 │ DB 영속·  │          │   • celery-worker-metric(-Q metric)│
 │ REST API  │          │   • celery-beat (스케줄러)         │
 └────┬─────┘          └────────────────┬─────────────────┘
      │ 저장                            │ ④ POST :8001/internal/alarms/push/
      ▼                                ▼
 ┌──────────┐               ┌────────────────────────────────┐
 │ Postgres │               │  Redis Stream                  │
 │ (PG16)   │               │   key = diconai:ws:alarms      │
 │ 영속 DB  │               │   ⑤ XADD (MAXLEN ~10000)        │
 └──────────┘               └────────────────┬───────────────┘
                                              │ ⑥ XREAD BLOCK
                                              │   (replica별 독립 커서 last_id)
                                              ▼
                              ┌────────────────────────────────┐
                              │  fastapi  alarm_flush_loop      │
                              │   스트림 커서 이후 누적분 배치   │
                              │   소비 → sensor_clients 전체 push│
                              └────────────────┬───────────────┘
                                              │ ⑦ WebSocket
                                              ▼  ws://:8001/ws/sensors/
                                      [브라우저 대시보드]
                                       위험 알람 팝업 표시

 [모니터링 라인]  각 서비스 /metrics ──► Prometheus(:9090) ──► Grafana(:3000) 대시보드 6종
```

##### ① 수신 — fastapi router → service

IoT 센서 또는 더미 스크립트가 측정값을 fastapi-server의 라우터로 POST합니다(가스 `/api/sensors/gas`, 전력 `/api/power/watt` 등). 라우터는 곧바로 service 계층을 호출하고, service에서 **수신·검증·AI 추론**까지 한 흐름으로 처리합니다.

##### ② 영속화 — fastapi → DRF → PostgreSQL

검증된 측정값은 DRF의 내부 수신 API(`POST :8000/api/monitoring/gas/`, `/api/monitoring/power/data/` 등)로 전달되어 PostgreSQL에 영속화됩니다. fastapi는 데이터를 받아 검증·중계하고, **영속화의 책임은 DRF가 단독으로** 집니다.

##### ③ 위험 판단과 AI 추론

전력은 **5축 AI**(Threshold · IsolationForest · ARIMA · Z-score · ChangePoint) + `night_abnormal` 휴리스틱으로 분석하며, 활성 4채널(ch1 압연기 7.5kW / ch9 메인전력반 15kW 3상 / ch14 공조 5.5kW / ch15 조명 1kW)을 대상으로 합니다. 가스는 **3축 AI**(다변량 IsolationForest · ARIMA · ChangePoint)로 분석하되, 격상 결정은 정적 임계가 우선이고 AI는 advisory(보조)로 운영합니다.

최종 알람 발화 여부는 fastapi가 **단일 결정자**로서 `decide_alarm` 함수에서 결정합니다. 이 함수는 **AI 추론 state × 정적 임계 평가 결과**를 입력받아 6가지 source 매트릭스(`ai` / `static_cover_miss` / `static_cover_inference_fail` / `static_cover_warmup` / `static_no_ai_available` / `static_legacy`)로 분기합니다. 단일틱 스파이크·인러시로 인한 false danger를 억제하기 위해 **DANGER는 2틱 연속 확인**(`DANGER_CONFIRM_TICKS=2`), **WARNING은 5초 지속**(`WARNING_DURATION_SEC=5`)을 요구합니다. 위험 판단·알람 시스템의 상세 로직은 **6장**, AI 분석 파이프라인은 **7장**에서 다룹니다.

##### ④~⑥ 알람 큐 — Redis Stream XADD / XREAD

위험으로 판단되면 DRF의 Celery alarm 워커가 알람 레코드를 생성하고, fastapi의 내부 엔드포인트(`POST :8001/internal/alarms/push/`)로 전달합니다. 이 엔드포인트는 페이로드를 **Redis Stream에 `XADD`** 로 적재합니다(키 `diconai:ws:alarms`, `MAXLEN ~10000`으로 폭주 시 가장 오래된 알람부터 근사 트리밍).

소비 측인 fastapi의 **`alarm_flush_loop`** 은 자신의 커서(`last_id`, 부팅 시 `"$"` = 이후 신규만)를 들고 **`XREAD BLOCK`** 으로 커서 이후 누적된 알람을 배치로 읽습니다. 커서를 소비 루프가 직접 보유하므로, 여러 replica가 각자의 커서로 스트림 전체를 읽는 **fan-out**이 되어 모든 replica가 모든 알람을 받습니다. 배치로 받은 알람을 순회하며 각각 broadcast하고, 커서는 배치 마지막 entry ID로 전진시킵니다.

> 별도의 `broadcast_loop`은 센서 통합 데이터(가스+전력+위치 스냅샷)를 주기적으로 같은 `/ws/sensors/` 채널에 송신하는 역할이며, **알람 스트림은 읽지 않습니다.** 알람의 즉시 전달은 오직 `alarm_flush_loop`이 단독 담당합니다.

##### 중복 차단 — fingerprint dedup

Celery retry 등으로 같은 알람이 여러 번 push되어 스트림에 중복 적재되는 것을 막기 위해, `XADD` 직전 단계에서 **`alarm:push:dedup:*` 키에 `SET NX EX 30s`** idempotency 게이트를 둡니다. fingerprint는 4분기(룰 이벤트 `event:*` / AI `ai:*` / 정상화 `clear:*` / 커버 `cover:*`)로 계산해 첫 도착자만 통과시키고 후속 retry는 silently drop합니다. AI 알람의 반복 발화는 별도로 `ai_fired:{device}:{channel}:{rule_level}` 키(TTL 60s)로 mute합니다.

##### ⑦ 브라우저 전달 — WebSocket

`alarm_flush_loop`이 broadcast하면, `/ws/sensors/`에 연결된 모든 브라우저(`sensor_clients`)가 알람을 즉시 수신해 위험 팝업을 띄웁니다. 추가로 **작업자 알람 확장**으로, 가스/전력 DANGER는 해당 시설 소속 작업자에게도 전송됩니다(`target_worker_ids` 기반으로 `worker_clients`에 분배 → `/ws/worker/{user_id}/`). 과거 지오펜스 전용이던 작업자 라우팅이 가스·전력 위험까지 포괄하도록 확장된 것입니다. 대시보드 화면·실시간 채널의 상세는 **5장**에서 다룹니다.

##### Discord 연동 (opt-in)

DRF의 `apps/notifications/services/discord_service.py`를 통해 알람을 Discord로도 전달할 수 있습니다. 관리자 webhook은 전체 broadcast, 작업자 webhook은 지오펜스 개인 멘션과 가스·전력 DANGER 시 `@here` 대피 안내를 보냅니다. 기본값은 `DISCORD_ALARM_ENABLED=OFF`로, 명시적으로 켜는 opt-in 방식입니다.

#### 비동기 격리 — Celery 큐 분리

알람 처리와 메트릭 수집은 같은 코드베이스(DRF 이미지)를 쓰되 실행 명령으로 워커를 분리했습니다.

| 워커 | 큐 / 동시성 | 담당 | 분리 이유 |
|---|---|---|---|
| `celery-worker-alarm` | `-Q alarm` / c=2 | 알람 생성·발송 | 알람은 지연 불가 → 전용 워커 즉시 처리 |
| `celery-worker-metric` | `-Q metric` / c=1 | 주기 메트릭 수집 | 무거운 집계가 알람을 막지 않도록 격리 |
| `celery-beat` | - | 스케줄러 | "매 N초마다 실행" 트리거. 중복 실행 방지 위해 항상 1개만 |

#### 공유 상태 — `websocket/state.py` (프로세스 메모리)

실시간 브로드캐스트에 필요한 **WebSocket 연결 목록만** fastapi 프로세스 메모리에 둡니다.

```python
# fastapi-server/websocket/state.py
sensor_clients: list[WebSocket] = []        # /ws/sensors/ 연결 (대시보드 브라우저)
worker_clients: dict[int, WebSocket] = {}   # /ws/worker/{user_id}/ 연결 (작업자 1:1)
```

연결 목록은 각 프로세스가 자기 연결만 관리하면 되므로 메모리에 두는 것이 올바릅니다. 반면 broadcast에 쓰이는 센서 스냅샷(가스·전력·위치)과 알람 큐는 Redis로 외부화되어, 연결 목록과 공유 데이터의 책임이 분리되어 있습니다.

#### URL 분리 원칙 — 페이지 / API / 어드민 패널

요청 종류를 URL 프리픽스로 명확히 구분해, 라우팅만 보고도 응답 형식(HTML/JSON)과 호출 주체를 알 수 있게 했습니다.

| 구분 | 프리픽스 | 반환 | 예시 |
|---|---|---|---|
| **페이지** | 루트 경로 | HTML | `/dashboard/`, `/dashboard/monitoring/realtime/` |
| **API** | `/api/` (필수) | JSON | `/api/auth/login/`, `/api/admin/gas-data/` |
| **어드민 패널** | `/admin-panel/` | HTML 셸 | `/admin-panel/alerts/policies/` |
| **내부 전용** | `/internal/` · `/api/internal/` | JSON | `/internal/alarms/push/` (localhost / 서비스 토큰) |
| **WebSocket** | `/ws/` | WS | `ws://:8001/ws/sensors/`, `/ws/worker/{user_id}/` |

- 경로는 `kebab-case`, API 컬렉션은 복수형(`/api/gas-data/`)을 따릅니다.
- 백오피스는 Django 기본 `/admin/`과 **별도로** `/admin-panel/` 프리픽스를 쓰며, **커스텀 어드민 21메뉴**로 구성됩니다. 단일 라우터(`config/admin_panel_urls.py`)가 `TemplateView`로 페이지 셸(+`active_nav`)만 내려주고, 실제 데이터는 JS가 `/api/admin/...`을 fetch하며, 권한은 API단의 `IsSuperAdmin`에서 검증합니다. 백오피스의 전체 구조는 **8장**에서 다룹니다.

#### 관측성 (Observability)

두 서버 모두 `/metrics`로 Prometheus 메트릭을 노출하고, Prometheus(:9090)가 이를 주기 수집해 Grafana(:3000)의 **대시보드 6종**(overview / sensor / alarm / power-ai / gas-ai / db-redis)으로 시각화합니다. Prometheus 메트릭은 총 19종(`POWER_AI_*` 6 / `GAS_AI_*` 4 / `AI_*` 3 / 인프라·WS·E2E)이며, 알람 E2E 지연(`E2E_ALARM_LATENCY`)과 스트림 lag(`ALARM_STREAM_LAG`)도 포함됩니다. 운영 모니터링의 상세는 **9장**에서 다룹니다.

---

### 증빙자료 ⭐⭐⭐⭐⭐

> 아래 항목은 캡처/다이어그램 placeholder입니다. 실제 이미지는 추후 채워 넣습니다.

| 증빙 | 캡처 / 다이어그램 대상 | 추천 제목 |
|---|---|---|
| [증빙 1: ___] | 전체 아키텍처 다이어그램 (2-tier + 10 컨테이너) — `docs/img/시스템구조도.png` 활용 | `[그림 3-1] 디코나이 통합 관제 플랫폼 전체 아키텍처` |
| [증빙 2: ___] | `docker compose ps` 출력 — 10개 컨테이너 모두 healthy | `[그림 3-2] Docker Compose 10 컨테이너 실행 결과` |
| [증빙 3: ___] | 본 장 E2E 데이터 흐름 다이어그램 → Mermaid/Lucidchart 변환 | `[그림 3-3] 센서 → DB → AI → Redis Stream → 알람 → 대시보드 흐름` |
| [증빙 4: ___] | `redis-cli XINFO STREAM diconai:ws:alarms` 또는 `XLEN` 출력 (스트림 적재 확인) | `[그림 3-4] Redis Stream 알람 큐 적재 상태` |
| [증빙 5: ___] | `celery-worker-alarm` 로그 — `/internal/alarms/push/` 수신·XADD 처리 | `[그림 3-5] Celery alarm 큐 + alarm_flush_loop 처리 로그` |
| [증빙 6: ___] | 브라우저 DevTools — `/ws/sensors/` WebSocket 프레임에 `alarms[]` 수신 | `[그림 3-6] WebSocket 실시간 알람 수신 (네트워크 프레임)` |
| [증빙 7: ___] | URL 분리 — 동일 리소스의 페이지(`/admin-panel/...`) vs API(`/api/admin/...`) 응답 대비 | `[그림 3-7] 페이지/API/어드민 패널 URL 분리 예시` |
| [증빙 8: ___] | Grafana overview 대시보드 (6종 중 1) | `[그림 3-8] Grafana 통합 모니터링 대시보드` |

> [팀원 확인: Discord 연동 실제 발송 캡처를 증빙에 포함할지 — `DISCORD_ALARM_ENABLED` opt-in 상태에서 시연 시점에 켤지 여부]

---

# 4장. 데이터 계약 및 데이터베이스 설계

### 이 장의 핵심 목적

```
센서가 보내는 JSON의 형식(데이터 계약)과 그것이 저장되는 DB 스키마를
한 장에 정리한다. 두 서버(fastapi 수신 / drf 영속화)가 같은 데이터를
서로 다른 표현으로 다루므로, "수신 시점의 계약(Pydantic)"과
"저장 시점의 스키마(Django 모델)"를 분리해 기술한다.
또한 가스·전력·알람·AI 핵심 테이블은 필드 단위로 상세히,
백오피스 마스터/운영 도메인은 '도메인별 테이블 목록 + 한 줄 역할'로 묶어
전체 데이터 자산의 지도를 제공한다.
```

> 데이터가 흐르는 큰 그림(서버 분리·라우팅·WebSocket)은 **3장**에서, 이 데이터를 소비하는 위험 판단·알람 로직은 **6장**, AI 추론 파이프라인은 **7장**에서 다룬다. 이 장은 그 사이의 **계약과 저장 구조**에 집중한다.

---

### 무엇을 수행하는가?

팀은 IoT 게이트웨이가 보내는 센서 페이로드를 **Pydantic 스키마로 입력 검증(fastapi-server)** 한 뒤, **PostgreSQL 16 테이블로 영속화(drf-server)** 하는 2단 데이터 파이프라인을 설계했다. 이 장에서 정의·정리하는 산출물은 다음과 같다.

| 구분 | 산출물 |
|---|---|
| (a) 데이터 계약 | 가스/전력(watt·current·voltage·onoff)/위치 JSON 페이로드 + Pydantic 검증 규칙 |
| (b) 핵심 도메인 테이블 | 센서 raw(`GasData`·`PowerData`), 알람/이벤트(`AlarmRecord`·`Event`·`EventLog`·`EventAcknowledgement`·`AlertPolicy`·`HazardType`), AI(`MLAnomalyResult`·`MLModel`) |
| (c) 백오피스 마스터/운영 도메인 | accounts·facilities·geofence·reference·safety·training·operations 등 16개 앱의 테이블 개요 |
| (d) 데이터 수명·결측 정책 | Raw 7~14일 / Event 영구 / ML 별도의 3계층 + null 의미 분기 |

전체 규모는 **16개 Django 앱 / 약 47개 테이블**이며, 그중 이 장에서 필드 단위로 상세히 다루는 핵심은 센서 2종 + 알람·이벤트 6종 + AI 2종이다.

---

### 왜 필요한가?

산업 안전 관제 데이터는 다음 세 가지 특성을 **동시에** 만족해야 한다.

1. **실시간성** — 가스·전력 모두 1Hz(초당 1 payload)로 끊임없이 들어오며, 단 1초의 위험 신호도 손실 없이 수신·저장되어야 한다.
2. **영속성·감사 추적성** — 알람·이벤트는 법규상 "언제 무엇이 발생해 누가 어떻게 조치했는가"를 사후에 추적할 수 있어야 한다. 따라서 일부 테이블은 수정·삭제가 불가능한 **APPEND-ONLY**로 강제된다.
3. **확장성** — 센서 종류(가스 9종/전력 16채널)와 AI 알고리즘이 늘어나도 스키마 변경 없이 흡수할 수 있어야 한다.

이 세 가지가 충돌하기 때문에, 팀은 단일 평면 테이블이 아니라 **역할별로 분리된 테이블 군(raw / 알람 lifecycle / AI 결과 / 마스터)** 으로 설계했다. 핵심 분리 결정은 다음과 같다.

- **수신 계약(Pydantic)과 저장 스키마(Django)를 분리** — 펌웨어 페이로드 형식(`slave01~slave72`, `255/0` ON/OFF, `-1` 통신불능)을 그대로 DB에 박지 않고, fastapi 라우터에서 도메인 표현(채널 1~16, bool, `null`)으로 변환한다. 펌웨어 프로토콜이 바뀌어도 DB 스키마는 보호된다.
- **판정(`AlarmRecord`)과 업무 워크플로우(`Event`)를 분리** — "센서가 임계치를 넘었다"는 순간적 사실과 "이 사건을 누가 확인하고 조치했다"는 업무 상태를 다른 테이블이 책임진다.
- **AI 결과(`MLAnomalyResult`)를 측정값 테이블과 분리** — 센서 종류가 늘어도 FK 변경 없이 문자열 식별자로 연결한다.

---

### 어떻게 수행했나?

#### (a) 센서 JSON 데이터 계약 + Pydantic 검증

모든 센서 페이로드는 fastapi-server의 도메인별 Pydantic 스키마(`gas/schemas`, `power/schemas`, `positioning/schemas`)를 통과해야 한다. 검증 실패 시 FastAPI가 **422 Unprocessable Entity**로 표준 응답하므로, 잘못된 데이터가 DRF 저장 단계까지 가지 않는다.

**가스 — `POST /api/sensors/gas` (`GasDataPayload`)**

```
{
  "timestamp": "2026-06-02T01:00:00Z",   # UTC. naive면 validator가 UTC로 간주
  "device_id": "GAS-001",
  "device_name": "...",
  "location": { "x": 120.0, "y": 340.0 },  # 지오펜스 연산용 도면 픽셀 좌표
  "o2": 20.9,                             # % (정상 18.0~23.5), ge=0 le=100
  "co": 0, "co2": 0, "h2s": 0,            # ppm, ge=0
  "lel": 0,                               # 폭발하한계 % — 임계치 미정의, 수집만
  "no2": 0, "so2": 0, "o3": 0, "nh3": 0, "voc": 0,  # ppm, ge=0
  "status": "normal",                     # 수신값 무시, 서버가 재계산
  "anomaly_type": null                    # 더미 IF 학습 라벨 (운영센서 미전송)
}
```

핵심 검증 규칙:
- `o2`는 `ge=0 le=100`(%), 나머지 가스는 `ge=0`(ppm) 음수 차단.
- `timestamp`는 `field_validator`로 timezone-aware 강제(naive면 UTC로 보정) — `USE_TZ=True` 환경의 시계열 오염 방지.
- `status`는 클라이언트 전송값을 **무시**하고 `model_validator(mode="after")`가 9종 가스값을 `calculate_gas_status()`로 재평가해 덮어쓴다. → 위험도의 단일 진실 공급원은 항상 서버.
- `anomaly_type`은 `Literal["co_leak","h2s_leak","fire","chemical_spill"] | None`로 화이트리스트 제한 — 임의 문자열은 fastapi 단에서 컷.

**전력 — `POST /api/power/{watt|current|voltage}` (`PowerWattPayload` 등) / `POST /api/power/onoff` (`PowerOnOffPayload`)**

전력은 측정 종류(W/A/V)별 엔드포인트가 나뉘며, 페이로드는 펌웨어 프로토콜 그대로 `slave01~slave72`의 16개 키를 가진다.

```
# watt/current/voltage 공통 (_PowerMeasurementBase)
{
  "device_id": "PWR-001",
  "slave01": 7500.0, "slave02": -1, ... "slave72": 1000.0,  # ge=-1
  "anomaly_labels": { "1": "overload" }   # 더미 IF 학습 라벨 (옵션)
}

# onoff (PowerOnOffPayload): 255=ON, 0=OFF
{ "device_id": "PWR-001", "slave01": 255, "slave02": 0, ... }
```

핵심 검증·변환 규칙(fastapi 라우터에서 수행):
- 측정값은 `ge=-1`. **`-1`은 "해당 포트 통신 불능"의 프로토콜 규정값**이며, `to_channel_values()`가 이를 `None`으로 변환해 DB에 저장한다. 집계 쿼리는 반드시 `value != -1`(또는 `value IS NOT NULL`) 조건을 둔다.
- `slave01~slave72` 키 → **채널 1~16**으로 정규화(`SLAVE_TO_CHANNEL`). 즉 DB 스키마는 펌웨어 키 이름에 의존하지 않는다.
- ON/OFF는 `255 → True / 0 → False`로 변환되어 `PowerEvent.snapshot`(`{"1": bool, ...}`)에 저장된다.
- `risk_level`은 페이로드에 없고, fastapi가 임계치 기준으로 계산한다.

**위치 — `POST /api/positioning/receive` (`WorkerPositionPayload`)**

```
{ "worker_positions": [
    { "worker_id": 1, "worker_name": "...", "facility_id": 1,
      "x": 12.5, "y": 30.0,           # ge=0
      "movement_status": "moving", "measured_at": "...Z",
      "node_id": "NODE-001" }         # 측정 앵커 노드 (없으면 null)
]}
```

모든 페이로드는 **수집 주기 1Hz**를 전제로 설계되었다.

#### (b) 핵심 도메인 테이블

**① 센서 raw**

`GasData` — 가스 9종을 개별 컬럼으로 두는 **wide table(고정 컬럼형)**. 시계열 집계·임계치 비교·AI 학습이 모두 컬럼 기반에서 자연스럽기 때문이다. (`db_table = gas_data`)

| 필드 | 타입 | 설명 |
|---|---|---|
| `gas_sensor` | FK(PROTECT) | 측정 센서. 센서 삭제 차단(이력 보존) |
| `co … voc` (9개) | FloatField null=True | 가스별 측정값(ppm, o2는 %). **null=미측정/결측** |
| `co_risk … voc_risk` (9개) | Char(choices) null=True | 가스별 위험도(normal/warning/danger). raw값으로 `Threshold` DB 기반 재계산 |
| `max_risk_level` | Char | 9종 중 최고 위험도 캐시(대시보드 빠른 필터) |
| `is_anomaly` / `anomaly_type` | Bool / Char(choices) | 더미 IF 학습 라벨(co_leak/h2s_leak/fire/chemical_spill) |
| `raw_payload` | JSON null | 원본 페이로드(디버깅 전용, 집계 미사용) |
| `measured_at` / `received_at` | DateTime | 측정 시각 / 수신 시각(통신 지연 산출) |

- `save()`가 `recalculate_risks_from_thresholds()`를 호출해 raw값으로부터 `*_risk`·`max_risk_level`을 **DRF의 `Threshold` DB 기준으로 재계산**한다 → fastapi/DRF 임계치 분기 위험 제거.
- 결측 사유는 별도 `GasDataError` 테이블(`MISSING`/`SENSOR_FAULT`)에 1:N으로 기록 — 한 측정 시점에 여러 가스가 동시 결측 가능하기 때문.

`PowerData` — 전력은 가스와 달리 **채널별 행(long-format) 정규화** 저장. 1장비 × 16채널 × 3종(전류/전압/전력)을 컬럼으로 펼치면 채널 수 변경에 대응할 수 없기 때문이다. (`db_table = power_data`)

| 필드 | 타입 | 설명 |
|---|---|---|
| `power_device` | FK(PROTECT) | 전력 장비 |
| `channel` | PositiveSmallInt | 채널 번호 1~16 |
| `data_type` | Char(choices) | `current`(A) / `voltage`(V) / `watt`(W) |
| `value` | Float null=True | 측정값. **통신 불능(-1)은 null로 저장** |
| `sensor_status` | Char(choices) | `active` / `comm_failure` |
| `risk_level` | Char(choices) | 임계치 기준 위험도 |
| `is_anomaly` / `anomaly_type` | Bool / Char(choices) | 더미 라벨(overload/voltage_drop/spike/phase_loss/degradation/**night_abnormal**/**motor_stuck**) |
| `measured_at` / `received_at` | DateTime | 측정 / 수신 시각 |

- 복합 UNIQUE `(power_device, channel, data_type, measured_at)`로 동일 시각 중복 저장 차단.
- ON/OFF 상태 스냅샷은 측정값과 분리해 `PowerEvent`(monitoring 앱) 테이블이 별도로 보관한다.

**② 알람 / 이벤트**

팀은 **"판정의 순간(`AlarmRecord`)"과 "업무 워크플로우(`Event`)"를 분리**하는 것을 알람 도메인의 핵심 설계로 삼았다. 한 사건에 같은 신호가 반복되면 N개의 `AlarmRecord`가 1개의 `Event`에 묶인다(N:1 merge 정책).

`AlarmRecord` — 자동 판정 1건의 **불변(immutable) 기록**. `save()`/`delete()` 오버라이드로 수정·삭제 차단(예외: `event`·`ml_anomaly_result` 사후 연결만 허용). (`db_table = alarm_record`)

| 필드 | 타입 | 설명 |
|---|---|---|
| `facility` | FK(PROTECT) | 발생 시설 |
| `event` | FK(SET_NULL) null | 묶인 Event(병합 직후 연결) |
| `sensor` / `power_device` / `geofence` / `worker` | FK(SET_NULL) null | **발생원 FK(alarm_type별 선택적 사용)** |
| `ml_anomaly_result` | FK(SET_NULL) null | AI 알람 시 `MLAnomalyResult` PK join |
| `alarm_type` | Char(choices) | `gas_threshold`/`power_overload`/`geofence_intrusion`/`sensor_fault`/`power_anomaly_ai`/`gas_anomaly_ai` 등 |
| `gas_type` | Char(choices) | 가스 종류(GAS_THRESHOLD 시) |
| `channel` | PositiveSmallInt null | PowerDevice 16채널 중 알람 채널 |
| `measured_value` / `threshold_value` | Float null | 측정값 / 초과 임계치 |
| `risk_level` | Char(choices) | normal/warning/danger |
| **`algorithm_source`** | Char | AI 알람의 알고리즘 출처(`isolation_forest`/`arima`/`combined`/`night_abnormal`/`zscore`/`change_point`). 룰 알람은 빈 문자열/NULL |
| **`source`** | Char(choices) | 검출 주체(`ai` / `static_cover_*` / `static_no_ai_available` / `static_legacy`). `algorithm_source`와 **직교 차원** |

> `algorithm_source`(AI 내부 어느 축이 잡았나)와 `source`(AI냐 정적룰이냐)는 독립된 두 축이다. 이 둘의 결정 로직(fastapi 단일 결정자 `decide_alarm` 6 매트릭스)과 운영자 친화 문구 매핑은 **6장**에서 상세히 다룬다.

`Event` — 여러 `AlarmRecord`를 묶는 업무 워크플로우 단위·상태머신. (`db_table = event`)

| 필드 | 타입 | 설명 |
|---|---|---|
| `facility` | FK(PROTECT) | 발생 시설 |
| `event_type` / `risk_level` | Char(choices) | 유형 / 위험도 |
| `status` | Char(choices) | `active → acknowledged → in_progress → resolved` 상태 전환 |
| `source_sensor` / `source_power_device` / `source_geofence` | FK(SET_NULL) null | **정확히 하나만 NOT NULL**(`clean()` 강제, 4차에 PostgreSQL CHECK 추가 예정) |
| `source_label` | Char | 발생 당시 장비/구역 이름 캐시(이름 변경돼도 과거 표시 일관) |
| `policy` | FK(SET_NULL) null | 트리거된 `AlertPolicy`(이력 추적) |
| `first_detected_at` / `last_detected_at` | DateTime | 병합 윈도우(최대 12시간) 추적 |
| `acknowledged_by/at` / `resolved_by/at` | FK/DateTime | 조치 추적 |

- 발생원 3종(센서/전력/지오펜스)에 대해 각각 **부분 인덱스**(`condition=Q(...__isnull=False)`)를 두어 병합 시 활성 Event 조회를 빠르게 한다.

`EventLog` — Event 상태 전환 **APPEND-ONLY 감사 로그**. 커스텀 QuerySet/Manager로 bulk update·delete까지 차단하고, `save()`도 수정 시 예외를 던진다(4차에 PostgreSQL 트리거로 DB 레벨 강제 예정). Action 5종(`created`/`confirmed`/`status_changed`/`note_added`/`resolved`), `actor`는 SET_NULL로 관리자 탈퇴 후에도 이력 보존. (`db_table = event_log`)

`EventAcknowledgement` — **사용자별(user-scoped) ack** join 테이블. `Event.status=ACKNOWLEDGED`는 글로벌 단일 상태라 한 운영자가 확인하면 모두에게 "확인됨"으로 보이는 문제가 있었다. `(event, user)` 쌍별 ack를 별도 저장(UniqueConstraint)해 "본 사람만 안 보이고 나머지에겐 계속 뜨는" 재팝업 정책을 구현했다. ack 시각은 `BaseModel.created_at`으로 조회(필드 중복 회피), Event/User 삭제 시 CASCADE. (`db_table = event_acknowledgement`)

`AlertPolicy` — "어떤 이벤트가 → 누구에게 → 어떤 채널로" 알림 정책. (`db_table = alert_policy`)

| 필드 | 타입 | 설명 |
|---|---|---|
| `event_type` | Char(choices) | 대상 AlarmType |
| `policy_kind` | Char(choices) | `stateful`/`immediate`/`scheduled` |
| `target_facility` | FK(CASCADE) null | NULL=전사 정책 |
| `target_user_types` / `target_sensor_ids` / `target_device_ids` / `target_geofence_ids` | JSON | 대상 범위 |
| `channels` | JSON | `popup`/`sms`/`email` 등 발송 채널 |
| `message_template` | Text | Django Template 문법 렌더(빈 값이면 `Event.summary` fallback) |
| `recommended_actions` | JSON | risk_level별 권고 조치 단계 리스트 |

`HazardType` / `HazardTypeGroup` — 코드 enum `AlarmType`의 **운영자 어드민 UI 메타(1:1)**. `AlarmType`은 코드 분기의 1차 진실 공급원이고, `HazardType`은 라벨·표시 색상 토큰·지도 표시 여부 등 화면 편집용. `type_code`는 `AlarmType.values`와 1:1 일치해야 하며 CI 정합성 테스트가 어긋남을 차단한다. (`db_table = hazard_type`)

**③ AI**

`MLAnomalyResult` — IF/ARIMA 등 1 추론 = 1 row. 측정값 테이블과 FK로 직결하지 않고 **`sensor_identifier` 문자열로 느슨 연결**(가스/전력 외 센서 추가 시 스키마 변경 불필요). (`db_table = ml_anomaly_result`)

| 필드 | 타입 | 설명 |
|---|---|---|
| `ml_model` | FK(SET_NULL) null | 추론 모델 |
| `model_version_snapshot` | PositiveInt | 모델 삭제돼도 추론 시점 버전 보존 |
| `sensor_type` / `sensor_identifier` | Char | `power`/`gas` / 예: `power:device_1:ch3:watt`, `gas:co` |
| `anomaly_score` | Float | IF `decision_function`/`score_samples`(음수=이상) |
| `prediction` | Char(choices) | `normal` / `anomaly` |
| **`risk_classified`** | Char(choices) | **결합 위험도 5단계** |
| `feature_snapshot_json` | JSON | 입력 피처 스냅샷(재현·디버깅) |
| `measured_at` / `evaluated_at` | DateTime | 측정 시각 / 추론 실행 시각 |

> `RiskClassified`는 **5단계**: `NORMAL`(정상) / `CAUTION`(주의) / `PREDICT_WARN`(예측경고) / `WARNING`(경고) / `DANGER`(위험). fastapi의 `combine_risk_5axis`와 vocab을 동기화하며, 누락 시 DRF forward가 400으로 실패하므로 강결합 계약이다.

`MLModel` — 학습된 모델 메타(학습 1회 = row 1건 + `.pkl` 파일 1개). (`db_table = ml_model`)

| 필드 | 타입 | 설명 |
|---|---|---|
| `version` | PositiveInt | 매칭 단위 안에서 1부터 순차 증가 |
| `sensor_type` | Char(choices) | `power`/`gas` |
| `algorithm` | Char(choices) | `isolation_forest` / `arima` |
| `sensor_identifier` | Char(blank) | 단일 시계열 식별자(ARIMA 등). 빈 값이면 sensor_type 단위 공유(IF 기본) |
| `file_path` / `feature_columns` / `params_json` | Char/JSON | `.pkl` 경로 / 피처 컬럼 / 하이퍼파라미터 |
| `training_*` | DateTime/Int | 학습 데이터 범위·샘플 수 |
| `is_active` | Bool | 활성 모델 1건 제약 |

- **UNIQUE 제약 2개**: `(sensor_type, algorithm, sensor_identifier, version)` 전체 유일 + 부분 UNIQUE `(sensor_type, algorithm, sensor_identifier) WHERE is_active=True` → 채널별 IF 1건 + ARIMA 1건이 같은 sensor_type 안에서 각각 활성 가능. 이 구조가 채널별·알고리즘별 모델 추적·rollback·staleness 모니터링의 인프라가 된다.

> 전력 AI는 위 모델 위에서 **5축**(Threshold / Isolation Forest / ARIMA / Z-score / ChangePoint)에 night_abnormal 휴리스틱을 더해 결합하고, 가스 AI는 **3축**(다변량 IsolationForest / ARIMA / ChangePoint)을 advisory로 운영한다. 두 도메인의 결합 매트릭스·알고리즘 우선순위·운영 정책은 **7장**에서 상세히 다룬다. 활성 4채널은 ch1 압연기(7.5kW), ch9 메인전력반(15kW 3상), ch14 공조(5.5kW), ch15 조명(1kW)이다.

#### (c) 백오피스 마스터/운영 도메인 테이블 개요

위 핵심 외에, 운영자가 `/admin-panel/`(커스텀 어드민 21메뉴)에서 다루는 마스터·운영 데이터가 도메인별로 존재한다. 각 도메인은 '테이블 목록 + 한 줄 역할'로 정리한다(필드 상세는 생략).

| 도메인(앱) | 테이블 | 한 줄 역할 |
|---|---|---|
| **accounts** | `CustomUser` | 인증 주체(super_admin/facility_admin/worker/viewer) |
| | `Company` / `Department` / `UserDepartment` | 회사·부서(트리) 마스터 + User↔Department M:N(주/겸직) |
| | `Position`(+`PositionCategory`) / `RoleProfile` | 직급·직책 분류 / 사용자 정의 역할 |
| | `LoginLog` | 로그인·로그아웃 이력(APPEND-ONLY) |
| **facilities** | `Facility` | 공장/시설 마스터 |
| | `GasSensor` / `PowerDevice`(+추상 `DeviceBase`) | 가스 센서·전력 장비 마스터(device_id 유일, 도면 좌표, `channel_meta` JSON) |
| | `PositionNode` | 작업자 위치 측정 앵커 노드(UWB/BLE) |
| | `Equipment` | Facility↔PowerDevice 1:1 매핑(`FAC-{id:03d}` 자동 코드) |
| | `Threshold` / `ThresholdGroup` | **임계치 단일 진실 공급원**(facility 우선순위 + apply_scope·condition_type) |
| | `GasSensorInspection` / `PowerDeviceInspection` | 센서·장비 점검 기록 |
| **geofence** | `GeoFence` | 작업자 진입 감지용 위험구역 폴리곤 |
| **reference** | `CodeGroup` / `CommonCode` | 공통 코드 그룹(GAS_TYPE 등) + 하위 코드값(어드민 편집) |
| **safety** | `SafetyCheckItem` / `SafetyStatus` / `SafetyCheckSection` / `SafetyCheckSession` / `SafetyChecklistRevision` | 안전 체크리스트(항목·상태·섹션·1일 1세션·발행 스냅샷) |
| **training** | `VRTrainingContent` / `VRTrainingRevision` | VR 교육 콘텐츠(대상별 단일 정책) + 교체 이력 |
| **notices** | `Notice` / `NoticeAttachment` | 시설/전사 공지 + 첨부(10MB·확장자 화이트리스트) |
| **notifications** | `Notification` | 실제 발송 이력(popup/push/sms/email, `policy` FK + retry) |
| **operations** | `AppLog` / `IntegrationLog` | Python logging 영속화 / FastAPI→DRF 연동 호출 기록(둘 다 APPEND-ONLY) |
| | **`DataRetentionPolicy`** | 시계열 자동 정리 정책(DataCategory 15종 + DeviceType 5종) |
| **dashboard** | `Menu` / `RoleMenuVisibility` | DB 기반 메뉴 마스터 + 역할별 노출 제어 |
| **core** | `BaseModel`(추상) / `RiskLevelStandard` / `SystemLog` | 공통 부모(created_at/updated_at/updated_by) / RiskLevel 메타 / 통합 로그(ActionType 24종) |
| **positioning** | `WorkerPosition` | 작업자 좌표 이력(`received_node` FK로 측정 노드 추적) |
| **monitoring** | `PowerEvent` | 전력 ON/OFF 이벤트(snapshot) — `GasData`/`PowerData`와 함께 monitoring 앱 |

> `/admin-panel/`은 Django 기본 admin이 아니라 **커스텀 어드민 21메뉴**다. 단일 라우터(`config/admin_panel_urls.py`)가 페이지 셸(TemplateView + active_nav)만 내리고, 실제 데이터는 JS가 `/api/admin/...`을 fetch하며 권한은 API단 `IsSuperAdmin`에서 강제한다. 화면·운영 인터페이스는 **8장**에서 다룬다.

> ⚠️ 표의 일부 테이블 분류·필드는 git 미추적 수동 문서(`skill/DB/`)를 참조해 정리했다. 백오피스 마스터 도메인(safety·training·notices 등)의 세부 스키마는 해당 도메인 담당 영역이므로, 정확한 필드 목록은 [팀원 확인: 백오피스 마스터 도메인 테이블 필드 상세 — accounts/facilities를 제외한 safety·training·notices의 실제 마이그레이션 대조]가 필요하다.

#### (d) 데이터 수명 3계층 + 결측치 정책

**데이터 수명 3계층 원칙** — 데이터 성격에 따라 보존 정책이 다르며, `operations.DataRetentionPolicy`가 이를 DB로 관리한다(Celery 보관 배치가 순회·삭제).

| 계층 | 대상 | 보존 정책 |
|---|---|---|
| **Raw(단기)** | `GasData`·`PowerData`·`WorkerPosition` 원천 시계열 | 7~14일 후 정리(폭증 방지). 집계 테이블(GasDataHourly·PowerDataHourly)은 4차 신설 예정 |
| **Event(영구)** | `Event`·`EventLog`·`AlarmRecord` | 법규 추적성 — 사실상 영구 보존, APPEND-ONLY |
| **ML(별도)** | `MLAnomalyResult`·`MLModel`·`.pkl` | 별도 카테고리(`ml_result`/`ml_model`). 비활성 모델은 `raw_retention_days` 초과 시 파일까지 정리 |

> 이 3계층 분리는 SQLite 시절 raw 데이터 폭증 인시던트(12GB)에서 도출된 원칙이며, PostgreSQL 16 전환(2026-05-22 완료) 이후에도 유지된다. raw 시계열의 대용량 효율화를 위한 **TimescaleDB 도입만 4차 과제로 잔존**하고, PostgreSQL 전환 자체는 완료되었다.

**결측치 정책 — `None` vs `0` 구분** — 센서 데이터에서 `0`은 유효한 측정값(예: o2 외 가스가 0ppm)이므로, 결측 판별은 반드시 `None`으로 한다. 더 나아가 팀은 **null의 의미를 가스 종류별로 분기**한다.

| 상황 | 의미 | 처리 |
|---|---|---|
| **`o2` null** | 산소 측정 실패 = **산소 결핍 위급**(밀폐공간 질식 위험) | 위급 상황으로 취급 — 정상으로 오인 금지 |
| **기타 가스 null** | 해당 가스 미검출 = **검출 한계 이하**(일반적으로 안전 측) | 결측으로 기록(`GasDataError`), `*_risk`도 null 유지 |
| **전력 value `-1`→null** | 포트 통신 불능 | `value=None` 저장 + `sensor_status=comm_failure`, 집계 제외 |

이 비대칭은 "산소는 없을수록 위험, 다른 가스는 있을수록 위험"이라는 도메인 본질을 스키마/처리 정책에 반영한 것이다.

---

### 증빙자료 ⭐⭐⭐⭐⭐

- 전체 ERD(핵심 테이블 + FK 관계, django-extensions `graph_models`) → `[증빙 1: ___]`
- 알람·이벤트 서브 ERD(`AlarmRecord` ↔ `Event` ↔ `EventLog` ↔ `EventAcknowledgement` ↔ `AlertPolicy` 관계 강조) → `[증빙 2: ___]`
- AI 서브 ERD(`MLModel` 4축 UNIQUE ↔ `MLAnomalyResult` `sensor_identifier` 느슨 연결) → `[증빙 3: ___]`
- 센서 JSON 페이로드 ↔ Pydantic 스키마 대응표 캡처(가스/전력/위치) → `[증빙 4: ___]`
- Pydantic 422 검증 실패 응답 예시(o2 범위 초과·timestamp naive 보정) → `[증빙 5: ___]`
- DB 저장 결과 캡처(`AlarmRecord` + `Event` 동시 생성, N:1 merge 확인) → `[증빙 6: ___]`
- `MLModel` 활성 UNIQUE 제약 검증(채널별 IF 1건 + ARIMA 1건 공존) → `[증빙 7: ___]`
- `DataRetentionPolicy` 어드민 화면(15종 카테고리 보존 기간) → `[증빙 8: ___]`
- 결측치 정책 시나리오 캡처(o2 null=위급 vs 기타 가스 null=검출한계) → `[증빙 9: ___]`

---

# 5장. 실시간 모니터링 대시보드

> **담당**: 정휘훈. 본 장은 운영자가 보는 실시간 화면(가스/전력/작업자/이벤트) 구성과 WebSocket 반영을 다룬다. 알람 팝업 UX는 6장, 데이터 흐름은 3장 참조.

### 5.1 대시보드 구성 [팀원: 정휘훈 작성 예정]
- 메인 통합 대시보드(가스·전력·작업자·알람 한 화면) 레이아웃
- 가스 시스템 / 전력 시스템 / 작업자 현황 / 이벤트 페이지별 UI·기능
- 지도 기반 작업자 위치·지오펜스 시각화

### 5.2 실시간 반영 [팀원: 정휘훈 작성 예정]
- WebSocket `/ws/sensors/` 구독 → 센서 통합 데이터 주기 수신·렌더링
- 위험도 색상 표시(정상/주의/위험), 채널별 상태

### 증빙자료 ⭐⭐⭐⭐⭐
- 메인 대시보드 캡처(3상태) → `[증빙 1: ___]`
- 전력/가스 시스템 화면 캡처 → `[증빙 2: ___]`

---

# 6장. 위험 판단 및 알람 시스템

> **담당**: 최재용(전체 집필). 본 장은 위험 판단·알람 도메인의 정적 임계 평가, FastAPI 단일 결정자, 알람 큐·중복 제거, 실시간 전달, 운영자 UX(모달/토스트/다중 ack), 작업자 대피 통보·Discord 미러까지를 한 흐름으로 정리한다. DB 스키마(`AlarmRecord`/`Event`/`EventAcknowledgement`)는 4장, 아키텍처·데이터 흐름 전반은 3장, AI 5축 추론 내부는 7장을 참조한다.

### 이 장의 핵심 목적

```
가스·전력·작업자 위치의 위험을 "판단 → 발화 → 전달 → 확인 → 정상화" 한 줄로
꿰는 알람 파이프라인을 설명한다. 팀이 세운 두 가지 설계 원칙이 장 전체를 관통한다.

  1. 단일 결정자  — 한 채널의 알람 발화 여부를 FastAPI 한 곳에서만 결정한다
                    (AI와 정적룰이 각자 발화하던 race를 구조적으로 차단).
  2. 정적룰이 최종 안전망 — AI는 "있으면 좋은 것"이지 "없으면 안 되는 것"이 아니다.
                    AI가 침묵·실패·워밍업 중이어도 정적 임계가 책임지고 알람을 띄운다.
```

### 무엇을 수행하는가?

팀이 구축한 알람 시스템은 다음 6개 단계가 직렬로 이어진 파이프라인이다.

| 단계 | 컴포넌트 | 위치 | 역할 |
|---|---|---|---|
| ① 정적 평가 | `threshold_eval` / DRF `threshold_service` | FastAPI · DRF | 정격 대비 % 환산으로 normal/warning/danger 판정 |
| ② 단일 결정 | `decide_alarm` 6매트릭스 | FastAPI `power/services` | AI state × 정적 결과 → 알람 source 1개 결정 |
| ③ 큐 적재 | `push_alarm` (Redis Stream XADD) | FastAPI `websocket/services` | fingerprint dedup 4분기로 중복 차단 후 스트림 적재 |
| ④ AI mute | `ai_fired:*` Redis 키 | FastAPI·DRF 공유 | AI 발화 시 같은 채널 룰 알람 60s suppress |
| ⑤ 실시간 전달 | `alarm_flush_loop` (XREAD broadcast) | FastAPI `ws_router` | 스트림을 replica별 fan-out으로 읽어 브라우저로 즉시 전달 |
| ⑥ 운영자 UX | 모달/토스트 + `EventAcknowledgement` | 프론트 + DRF | danger=모달 / warning=토스트, 다중 관리자 ack 시그널 |

추가로 발화 신뢰성을 높이는 게이트 3종과 외부 통보 2종이 파이프라인에 얹혀 있다.

- **발화 게이트**: danger 2틱 confirm(`DANGER_CONFIRM_TICKS=2`), WARNING 5초 지속(`WARNING_DURATION_SEC=5`), 전력 채널-aware clear.
- **외부 통보**: 작업자 DANGER 대피 통보(`target_worker_ids` → `worker_clients` 개인 전송), Discord 미러(관리자=broadcast / 작업자=`@here` 대피, opt-in).

### 왜 필요한가?

산업 현장 알람의 운영 요구는 단순히 "임계를 넘으면 띄운다"가 아니다. 팀이 재설계 과정에서 마주한 핵심 문제는 세 가지였다.

**1) 두 발화 주체의 충돌.** 재설계 전에는 FastAPI(AI 추론)와 DRF Celery(정적룰)가 같은 채널을 각자 평가해 둘 다 발화할 수 있었다. 같은 위험에 알람이 2건 뜨면 운영자가 신뢰를 잃고, 어느 쪽이 진짜인지 판단할 수 없다. → **FastAPI가 5축 추론과 정적 평가를 같은 프로세스에서 모두 가지므로, 결정을 한 곳(`decide_alarm`)에 모아 race 자체를 없앴다.**

**2) "누가 잡았는가"의 추적 불가.** AI가 잡은 알람인지, 정적룰이 보완으로 띄운 것인지 구분되지 않으면 알고리즘 신뢰도를 측정할 수 없다. → **`source` 6종 + `algorithm_source` 6종**으로 검출 주체와 알고리즘 출처를 직교 분리해 운영자·엔지니어 양쪽이 추적 가능하게 했다.

**3) 단일 틱 스파이크의 false danger.** 모터 인러시(기동 돌입 전류)나 센서 순간 스파이크가 1틱만 임계를 넘어도 danger 모달이 떠 운영자를 피로하게 만든다. → **danger는 연속 2틱 초과 시에만 발화**(`DANGER_CONFIRM_TICKS`)하고, **WARNING은 5초 지속**돼야 발화하도록 게이트를 두었다.

### 어떻게 수행했나?

#### 6.1 정적 임계 평가 — 정격 % SoT

위험 판단의 출발점은 정적 임계다. 전력은 채널마다 정격(rated)이 다르므로(압연기 7.5kW vs 조명 1kW), 절대값이 아닌 **정격 대비 %**로 환산해 평가한다. 임계 단일 진실 공급원(SoT)은 DRF `Threshold` 시드 `power_facility_default`의 % 값과 채널별 `channel_meta` 정격이며, FastAPI `threshold_eval`이 같은 룰을 복제해 in-memory로 판정한다.

| 축 | warning | danger | 방향 |
|---|---|---|---|
| watt | ≥ 80% | ≥ 100% | 단방향 |
| current | ≥ 80% | ≥ 100% | 단방향 |
| voltage | [95%, 105%] 밖 | [90%, 110%] 밖 | 양방향 |

전력은 한 채널의 watt·current·voltage 3축을 평가한 뒤 **종합 위험도 = max(3축)**로 채널당 1알람을 유지한다(`_aggregate_risk`). 가스는 9종 가스 각각의 농도를 임계와 비교한다. 정격% SoT의 검증 및 차트 동기화 세부는 7장(AI·임계 정책)을 참조한다.

> **[팀원 확인: 가스 도메인 담당(이성현)]** 가스 임계 정의서(SoT)·9가스 단위·threshold 시드 운영 절차는 가스 도메인 담당 확인 필요.

#### 6.2 FastAPI 단일 결정자 — `decide_alarm` 6매트릭스

`decide_alarm`은 I/O 없는 순수 함수로, **AI 추론 5-state × 정적 평가 결과**를 받아 알람 `source` 하나를 결정한다. 핵심은 "AI가 못 잡았거나(미탐)·실패했거나·아직 준비 중일 때도, 정적이 위험하다고 보면 알람을 띄우되 출처를 구분한다"는 점이다.

| AI 상태 | 정적 결과 | source | 의미 |
|---|---|---|---|
| `FIRED` | * | `ai` | AI가 직접 발화 |
| `INFERRED_NORMAL` | fired | `static_cover_miss` | AI 미탐 의심 — 정적이 보완 |
| `INFERRED_FAILED` | fired | `static_cover_inference_fail` | AI 추론 실패 — 정적 폴백 |
| `WARMING_UP` | fired | `static_cover_warmup` | AI 윈도우 빌드 중 — 정적 보완 |
| `DISABLED` | fired | `static_no_ai_available` | AI 비활성 채널 — 정적이 주 신호 |
| `None`(Redis 장애·만료) | fired | `static_no_ai_available` | fail-safe(DISABLED 동등) |
| * | not fired | `None` | 알람 없음 |

```python
# decide_alarm.py — AI 5-state × 정적 fired → source 분기 (핵심)
if ai_state == AIInferenceState.FIRED:
    return AlarmDecision(source="ai", alarm_type="power_anomaly_ai", ...)
if not static_fired:
    return None                      # 정적도 발화 안 하면 알람 없음
# 이하 정적 fired 전제 — AI state에 따라 cover source 분기
```

설계 의도는 **fail-safe**다. `ai_state`가 `None`(Redis 장애)이어도 `DISABLED`와 동등하게 취급해 정적 결과를 따른다 — AI 인프라가 죽어도 정적 임계가 알람을 책임지므로, AI는 "없으면 안 되는 것"이 아니다. AI 5-state 머신의 마킹·조회 내부는 7장 참조.

#### 6.3 알람 큐 — Redis Stream XADD + fingerprint dedup 4분기

`decide_alarm`/Celery가 만든 알람은 `push_alarm`을 거쳐 Redis Stream `diconai:ws:alarms`에 `XADD`(MAXLEN ~10000)로 적재된다.

> **설계 변천**: 초기 구현은 메모리 list + `asyncio.Event`였고, 이후 멀티-replica 대비로 List+BRPOP을 거쳐 **Stream+XREAD fan-out**으로 전환됐다. BRPOP은 경쟁 소비(한 알람을 한 replica만 pop)라 replica가 늘면 일부 브라우저가 알람을 못 받는다. Stream은 각 replica가 자기 커서로 스트림 전체를 읽어 **모든 replica가 모든 알람을 받는** fan-out이 된다(Consumer Group은 경쟁 분배라 미사용).

`push_alarm` 진입부에서 **fingerprint dedup**으로 Celery retry 중복·매초 평가 폭주를 막는다. payload 형태에 따라 4분기로 idempotency 키를 계산하고, `SET NX EX 30s`로 첫 도착자만 통과시킨다.

| 분기 | fingerprint 형식 | 막는 중복 |
|---|---|---|
| 룰 알람 | `event:{event_id}:{risk_level}` | Celery retry(같은 event_id) |
| AI 알람 | `ai:{alarm_type}:{device_id}:{channel}:{risk_level}` | 매 sample 평가 재push |
| 정상화 | `clear:{alarm_type}:{source_label}` | 9가스 동시 clear → 패널 1줄 |
| 정적 cover | `cover:{source}:{source_label}:{risk_level}` | 모든 채널 매초 평가 폭주 |

TTL 30s는 의도된 마진이다 — Celery retry 총 시간(5s×3=15s)보다 길고, Event 재알림 cooldown(60s)보다 짧아 1분 후 정상 재발화를 막지 않는다. `SET NX EX`를 `XADD`보다 먼저 두는 이유는, 자주 발생하는 retry 중복 차단 효과가 희소한 XADD 부분 실패(누락) 위험보다 명백히 크기 때문이다. dedup으로 차단된 횟수는 `alarm_push_dedup_hits_total`로 관측한다.

#### 6.4 AI mute — `ai_fired:*` 키로 룰 알람 suppress

AI와 정적룰이 같은 채널을 동시에 띄우지 않도록, AI 발화 순간 `ai_fired:{device}:{channel}:{rule_level}` 키를 TTL 60s로 마킹한다(FastAPI `ai_mute.py`). DRF 측 룰 가드 `is_ai_mute_active`가 같은 raw redis 키를 읽어 룰 fire를 suppress한다.

**격상 bypass**가 핵심 설계다. 마킹은 발화 level "이하" 키만 set한다(AI=warning이면 normal·warning 키만, danger 키 부재). 따라서 AI가 warning을 띄운 사이 룰이 danger를 감지하면, danger 키가 없어 가드를 자연 통과한다 — "더 높은 위험은 AI mute를 뚫는다". suppress된 룰 fire는 `RULE_FIRE_SUPPRESSED_BY_AI_TOTAL`로 카운트한다.

#### 6.5 실시간 전달 — `alarm_flush_loop` XREAD broadcast

`alarm_flush_loop`은 스트림을 `XREAD BLOCK`으로 읽어 접속 브라우저(`sensor_clients`)에 즉시 broadcast한다. 센서 데이터를 주기 전송하는 `broadcast_loop`(5초)와는 **별개 루프**로, 알람만 즉시 전달한다.

```python
# ws_router.py — alarm_flush_loop 골격
last_id = "$"                        # 부팅 이후 신규 알람만 (과거 무한 replay 방지)
while True:
    new_last_id, payloads = await read_alarms_blocking(last_id, timeout=1)
    # payloads를 sensor_clients 전체에 broadcast
    last_id = new_last_id            # 배치 마지막 entry ID로 커서 전진
```

커서 `last_id`는 루프가 메모리로 보유하며, 부팅 직후 `"$"`에서 시작해 과거 알람 무한 replay를 막는다. 배치로 N건을 받아 순서대로 broadcast하고 커서를 배치 마지막 ID로 전진시킨다. 스트림 말단과 커서의 시간차(stream lag)는 `ALARM_STREAM_LAG` 게이지로 측정해 Redis 병목을 조기 감지한다.

#### 6.6 운영자 UX — 모달/토스트 + 다중 ack + `algorithm_source` 워딩

전달된 알람은 위험도에 따라 표현을 나눈다.

- **danger → 모달**: 화면 중앙 차단형. 운영자가 인지·대응을 강제당한다.
- **warning → 토스트**: 비차단 토스트. 작업 흐름을 끊지 않는다.
- **정상화 → 회색 토스트**: clear 알림은 톤을 약화해 "해소됨"을 전달한다.

`source`가 cover 계열(`static_cover_*`)이면 운영자 톤을 1단계 약화한다(노랑 + cover 배지). AI 직접 발화·정적 단독은 기존 risk 톤(빨강/노랑) 그대로다.

**다중 관리자 ack.** 관리자가 여러 명인 환경에서 운영자 A가 이미 "확인 중"인 알람이 운영자 B에게 재발화하면, B의 토스트에 "(A 확인 중)" 시그널을 표시한다. push payload의 `event_ack_users`에 활성 Event의 `EventAcknowledgement` 사용자명을 실어 보낸다. ack와 dedup은 분리 유지(안전망)하고 시그널만 보강한다.

**`algorithm_source` 6종 한글 워딩.** ML 용어(IF/ARIMA/Z-score)를 운영자에게 그대로 노출하지 않고, 알고리즘 동작을 반영한 한국어로 변환한다. DRF·FastAPI 양쪽이 단일 동기화한다.

| algorithm_source | 운영자 워딩 | 알고리즘 본질 |
|---|---|---|
| `isolation_forest` | 이상 수치 탐지 | 분포 outlier |
| `arima` | 이상 패턴 탐지 | 시계열 예측 잔차 |
| `combined` | 이상 수치·패턴 동시 탐지 | IF+ARIMA 동시 발화(최고 신뢰도) |
| `zscore` | 통계 이상 수치 | sliding window 통계 |
| `change_point` | 패턴 변화 탐지 | 변화점 검출 |
| `night_abnormal` | 야간 이상 가동 | 운영 시간 외 baseline 초과 |

#### 6.7 발화 신뢰성 게이트 3종

**danger 2틱 confirm.** danger를 단일 틱에 발화하면 인러시·스파이크가 false danger를 만든다. 연속 2틱(`DANGER_CONFIRM_TICKS=2`) 초과 시에만 발화하도록 `confirm_consecutive`로 카운트한다. 전력은 한 사이클에 3축이 각각 평가되므로 stale 캐시로 인한 조기 발화를 막기 위해 **watt 축에서만** 카운트한다(`current`/`voltage`는 skip, 종합 위험도는 watt 도착 시 3축 최신값 반영). `DANGER_CONFIRM_TICKS=1`이면 첫 틱 즉시 발화(기존 동작). 게이트 통과/보류/리셋은 `POWER_DANGER_CONFIRM_TOTAL{outcome}`로 관측한다.

```python
# power_alarm.py — danger 2틱 confirm (watt 축 한정)
if axis_name != "watt":
    continue
gate_passed = confirm_consecutive(dcount_key, settings.DANGER_CONFIRM_TICKS, _CACHE_TTL)
if not gate_passed:
    POWER_DANGER_CONFIRM_TOTAL.labels(outcome="held").inc()  # 단일 틱 억제
    continue
```

**WARNING 5초 지속.** WARNING은 즉시 발화하지 않고 `apply_async(countdown=5)`로 5초 타이머를 건다. 5초 안에 normal/danger로 바뀌면 타이머를 `revoke`해, 임계 부근 일시 진동의 과발화를 억제한다.

**전력 채널-aware clear.** 한 디바이스의 채널들은 Event를 공유한다. 한 채널이 정상 복귀했다고 공유 Event를 곧장 RESOLVE하면, 아직 위험한 다른 채널의 Event까지 닫혀 다음 발화가 **새 event_id**로 생성되고, 프론트 60s dedup(event_id 키)을 통과해 폭주한다(가스 `cleared_gases`가 막는 race의 전력판). `has_other_active_channel`로 **마지막 활성 채널이 정상화될 때만** `auto_resolve_active_events`를 호출하도록 게이팅한다.

#### 6.8 작업자 DANGER 대피 통보 + Discord 미러

**작업자 대피 통보.** 가스/전력 DANGER는 관리자 대시보드뿐 아니라 소속 시설 작업자에게도 대피 알림을 보낸다. DRF가 시설 기준으로 `target_worker_ids`를 계산해 push payload에 싣고, FastAPI `alarm_router`가 이 목록 중 접속한 작업자의 `worker_clients[user_id]`에만 개인 전송한다(전체 broadcast 아님). 이 목록은 브라우저 broadcast 스트림에는 싣지 않고 pop해 id 노출·payload bloat를 막는다. 지오펜스 진입 알람은 `worker_id` 단건으로 해당 작업자에게 전송한다.

> **[작업자 확인: 디바이스]** 작업자 알람 수신 디바이스 종류·UX는 미정 상태로, 현재는 WS 개인 전송으로 시연을 충족한다. 디바이스 확정 후 라우팅 재설계 필요.

**Discord 미러(opt-in).** `_push_to_ws` 성공 tick 1회만 Discord webhook으로 미러한다(retry 중복 회피, Discord엔 dedup 없음). 관리자 채널은 모든 알람 broadcast(멘션 없음), 작업자 채널은 지오펜스=개인 멘션 / 가스·전력 DANGER=`@here 즉시 대피`. `DISCORD_ALARM_ENABLED=False`거나 webhook 미설정이면 동작하지 않는다.

#### 데이터 흐름 요약

```
IoT → FastAPI 수신 → ① 정적 평가(정격%) + AI 5축 추론(7장)
                   → ② decide_alarm 6매트릭스 → source 1개
                   → ③ push_alarm: fingerprint dedup 4분기 → Redis Stream XADD
   (DRF Celery 룰 경로) → ④ AI mute(ai_fired:*) 가드 → fire_*_task → DB(AlarmRecord/Event) → /internal/alarms/push/
                   → ⑤ alarm_flush_loop XREAD → sensor_clients broadcast
                                              + worker_clients 개인 대피 통보
                                              + Discord 미러(opt-in)
                   → ⑥ danger=모달 / warning=토스트 / EventAck "(N 확인 중)"
```

### 증빙자료 ⭐⭐⭐⭐⭐

- 알람 파이프라인 시퀀스 다이어그램(router → 정적/AI → decide_alarm → push → Stream → flush_loop → 브라우저) → `[증빙 1: 전체 흐름도]`
- `decide_alarm` 6매트릭스 시각화(위 표 + source 6종 색상 톤) → `[증빙 2]`
- 알람 모달 캡처(danger, `algorithm_source="이상 수치·패턴 동시 탐지"` 표시) → `[증빙 3]`
- 알람 토스트 캡처(warning, `source_label="압연기A"` + 측정값) → `[증빙 4]`
- 회색 정상화 토스트 캡처(clear) → `[증빙 5]`
- "(N 확인 중)" `EventAcknowledgement` 다중 ack 시그널 캡처 → `[증빙 6]`
- Redis Stream 모니터링(`redis-cli XLEN diconai:ws:alarms` + `alarm:push:dedup:*` KEYS) → `[증빙 7]`
- Grafana 패널: `alarm_push_dedup_hits_total` / `RULE_FIRE_SUPPRESSED_BY_AI_TOTAL` / `POWER_DANGER_CONFIRM_TOTAL{outcome}` / `ALARM_STREAM_LAG` → `[증빙 8]`
- Discord 미러 캡처(관리자 broadcast + 작업자 `@here` 대피) → `[증빙 9]`
- 운영 시나리오 영상(정상 → 전력 과부하 danger 2틱 confirm → 모달 + 작업자 대피 통보 → ack → 채널-aware clear → 회색 토스트) → `[증빙 10]`

---

# 7장. AI 분석 및 예측

## 7.1 개요 — 가스·전력 2 도메인 AI 구조

### 이 장의 핵심 목적

```
디코나이의 AI 분석 계층은 "임계치에 도달한 뒤" 가 아니라 "도달하기 전" 의
조기 위험 신호를 잡는 것을 목표로 한다. 본 장은 전력 도메인의 5축 정책 엔진,
가스 도메인의 다변량 IF 추론을 중심으로, AI 모델 그 자체보다 입력·결합·도메인
의존 결정·운영 연계가 어떻게 설계되었는지를 정리한다.
```

### 무엇을 수행하는가?

팀은 두 도메인을 서로 다른 AI 구조로 구현하였다. 사고의 시간 척도가 다르기 때문이다.

| 도메인 | 사고 시간 척도 | AI 구조 | 운영 정책 |
|---|---|---|---|
| 전력 | 시간~일 단위 점진 변화 | **5축** (Threshold / IF / ARIMA / Z-score / ChangePoint) + night_abnormal | 발화 알람 (decide_alarm) |
| 가스 | 분 단위 즉시 위험 | **3축** (다변량 IF / ARIMA / ChangePoint) | advisory (정적 룰 보조) |

추론은 모두 fastapi-server 안에서 실시간으로 수행된다 (엣지 게이트웨이 → fastapi → 알람). 데이터 흐름·아키텍처는 3장(아키텍처), 알람 결정 매트릭스의 운영 측면은 6장(위험 판단·알람)을 참조한다.

### 왜 필요한가?

산업 안전 AI 의 핵심 가치는 "절대값 초과 후 대응" 이 아니라 "임계 직전 조기 경고" 이다. 이를 위해 잡아야 하는 위험 패턴은 단일 모델로는 모두 포착할 수 없다.

| 잡아야 하는 패턴 | 담당 축 (전력) |
|---|---|
| 절대값 초과 (정격 100%) | Threshold |
| 학습 분포 밖 단발 spike (인러시·서지) | Isolation Forest |
| 점진 부하 증가 (베어링 마모 등 drift) | ARIMA trend break |
| 평소 대비 통계적 튐 (조기 경고) | Z-score |
| 가동 모드 전환 시점 (패턴 변화) | Change Point |
| 야간 비정상 가동 | night_abnormal 휴리스틱 |

어떤 모델도 모든 패턴을 잡지 못하므로, 도메인 특성에 맞춰 **직교한 축을 결합**해 robustness 와 운영자 추적성(어느 축이 잡았는지)을 동시에 확보한다.

### 어떻게 수행했나?

본 장은 다음 순서로 구성된다.

- 7.2 전력 5축 정책 엔진 — 5축 독립 계산과 `combine_risk_5axis` 우선순위 결합
- 7.3 night_abnormal 휴리스틱 — 야간 비정상 가동 격상
- 7.4 algorithm_source 6 종 — 발화 driver 라벨링과 운영자 워딩
- 7.5 un-downgrade architecture — 가스 격하 vs 전력 동급의 의도된 비대칭
- 7.6 활성 4채널 운영 전략
- 7.7 학습 파이프라인과 영속화 (MLModel / MLAnomalyResult)
- 7.8 가스 AI 분석 [팀원: 이성현 작성 예정]

### 증빙자료 ⭐⭐⭐⭐⭐

- 가스·전력 AI 구조 비교 다이어그램 → `[증빙 1: 전력 5축 / 가스 3축 + 운영 정책(발화 vs advisory)]`

---

## 7.2 전력 5축 정책 엔진

### 이 장의 핵심 목적

```
전력 활성 채널의 watt 측정값에 대해 5개 축을 독립 계산한 뒤, 우선순위 결합으로
단일 위험도를 산출하는 정책 엔진(combine_risk_5axis)의 설계를 정리한다.
```

### 무엇을 수행하는가?

활성 4채널의 watt 값이 들어오면, 슬라이딩 윈도우가 찬 채널에 대해 다음 5축을 독립 계산한다.

| 축 | 입력 | 산출 | 위치 |
|---|---|---|---|
| 1. Threshold | watt vs 정격 % | `normal` / `warning`(80%) / `danger`(100%) | `threshold_eval.calculate_power_risk` |
| 2. Isolation Forest | 4피처 row | `normal` / `anomaly` + score | `ai/router._get_or_load` |
| 3. ARIMA | window → 1-step forecast | `arima_violation` (95% CI 위반) | `ai/router._arima_forecast` |
| 4. Z-score | 윈도우 평균 대비 `\|z\|>=3σ` | `z_score_anomaly` + z 값 | `zscore_anomaly._zscore_check` |
| 5. Change Point | two-window(60틱) 비교 | `change_point` (STABLE→SHIFT) | `change_point_service.detect_change_point` |

IF 의 4피처는 단변량 시계열을 풍부화한 `(value, roll_mean, roll_std, diff)` 이다.

### 왜 필요한가?

5축은 서로 다른 위험 패턴을 책임진다(직교성). 한 축이 놓치는 패턴을 다른 축이 잡는다.

| 축 | 잡는 패턴 | 잡지 못하는 패턴 |
|---|---|---|
| Threshold | 절대값 초과 | 임계 직전 조기 경고 |
| IF | 학습 분포 밖 (point anomaly) | 시간 의존성 (contextual) |
| ARIMA | trend break / 점진 drift | 단발 spike (빠른 적응으로 CI 추종) |
| Z-score | 통계 spike (3σ) | trend break 시점 |
| Change Point | 패턴 변화 시점 | 단발 spike, 절대값 위험 |

→ **어떤 단일 모델도 전부 잡지 못하므로** 5축 직교 결합이 robust 하다.

### 어떻게 수행했나?

5축을 결합하는 핵심은 `fastapi-server/ai/risk_combine.py` 의 우선순위 엔진이다. 48-cell dict 를 펼치지 않고, base 3축 결과에 Z/CP 를 조건부로 격상시키는 방식을 택했다.

```python
def combine_risk_5axis(threshold, if_pred, arima, z, cp) -> tuple[str, str]:
    base = combine_risk_3axis(threshold, if_pred, arima)  # 12-cell 매트릭스
    if base != "normal":
        return base, ""               # AI 발화 중 → Z/CP 격상 안 함 (중복 방지)
    if change_point:
        return "predict_warn", "change_point"
    if z_score_anomaly:
        return "predict_warn", "zscore"
    return "normal", ""
```

**설계 결정**

- **base 를 3축에 위임** — `combine_risk_3axis` (threshold × IF × ARIMA, 12-cell 매트릭스) 결과를 그대로 사용한다. 5축 추가가 기존 3축 동작을 회귀시키지 않도록 가드한다.
- **Z/CP 는 base=normal 일 때만 격상** — base 가 이미 발화 등급(caution/predict_warn/warning/danger)이면 ML·threshold 를 우선하고 Z/CP 는 무시한다. false positive 회피이자, 라벨이 실제 driver 와 어긋나는 것을 막는다.
- **escalation_source 반환** — `(combined, escalation_source)` 튜플로, Z/CP 가 실제 격상에 기여했을 때만 그 라벨("zscore"/"change_point")을 돌려준다. 이 값이 뒤의 `algorithm_source` 결정(7.4)에서 driver 라벨 일관성을 보장한다.

base 3축 매트릭스는 "두 AI(IF·ARIMA) 가 동의할 때만 한 단계 격상" 하도록 보수적으로 설계되어 있다. 예컨대 `("warning", "anomaly", arima=False)` 는 `warning` 에 머무르고(IF 단독), `("warning", "anomaly", arima=True)` 일 때만 `danger` 로 격상된다.

> **단발 스파이크 억제**: 인러시·서지 같은 단일 틱 스파이크가 곧바로 danger 로 격상되는 것을 막기 위해, 알람 단계에서 `DANGER_CONFIRM_TICKS=2`(danger 2틱 confirm), WARNING 5초 게이트를 둔다(상세는 6장).

### 증빙자료 ⭐⭐⭐⭐⭐

- 5축 결합 다이어그램 → `[증빙 2: Threshold + IF + ARIMA + Z + CP → combine_risk_5axis → (combined, escalation_source)]`
- IF feature 4개 시각화 (value / roll_mean / roll_std / diff) → `[증빙 3]`
- ARIMA forecast + 95% CI 시계열 그래프 → `[증빙 4]`
- 추론 로그 샘플 (`[anomaly_inference]` / `[zscore]` / `[change_point]`) → `[증빙 5]`

---

## 7.3 night_abnormal 휴리스틱

### 이 장의 핵심 목적

```
야간 시간대(KST 22-05)에 정격 대비 과한 가동이 감지되면 위험도를 한 단계
격상하는 시각 컨텍스트 휴리스틱의 설계와 임계 결정 근거를 정리한다.
```

### 무엇을 수행하는가?

5축 결합 직후, watt 채널에 한해 야간 격상을 평가한다. `measured_at` 이 KST 야간이고 측정값이 정격의 30% 를 초과하면 `combined` 를 한 단계 격상한다.

```python
if data_type == "watt" and _is_night_kst_iso(measured_at):
    if value > rated_w * _NIGHT_THRESHOLD_RATIO:   # 0.30
        escalated = _NIGHT_ESCALATION.get(combined, combined)
        # normal → caution, caution → warning, predict_warn → warning
```

위치: `fastapi-server/power/services/night_escalation.py`.

### 왜 필요한가?

야간에는 평소 부하 자체가 낮아야 정상이다. 정격 30% 초과는 "야간인데 평소 야간 대비 2배 가동" → 비정상 가동 의심 신호로 본다. 학습형 모델(SARIMA·STL)은 일·주 단위 계절성을 자동 학습할 수 있으나 1~2주 데이터 누적과 모델 수 증가가 선행되어, 시연 단계에서는 학습 cost 0 의 휴리스틱을 택했다.

| 임계 후보 | 의미 | 선택 |
|---|---|---|
| 정격 15% | 야간 평균 baseline 추정 | ❌ 상시 가동 장비에서 false positive 다수 |
| **정격 30%** | 야간 baseline 의 2배 | ✅ 휴리스틱 채택 |
| 정격 50% | 보수적 — 거의 미발화 | ❌ 조기 경고 가치 ↓ |

### 어떻게 수행했나?

- **KST 게이트 (UTC 안전 fallback)**: `measured_at` 이 naive 면 UTC 로 간주하고 `(utc_hour + 9) % 24` 로 KST 시를 구한다. 야간은 `22 <= kst_hour OR kst_hour < 5`. 파싱 실패 시 False 를 반환해 격상을 적용하지 않는다(안전 fallback).
- **격상 후 마킹**: 격상이 실제로 일어나면 `night_escalated=True` 로 표시하고, `[night_abnormal]` 로그를 남긴다. 이 플래그는 7.4 algorithm_source priority 의 최상위로 들어간다.
- **향후**: D+30~D+90 운영 데이터 누적 후 채널별 야간 baseline 학습으로 전환할 수 있다(정격 % 일률 → baseline 대비 격상).

### 증빙자료 ⭐⭐⭐⭐⭐

- `[anomaly_inference]` 야간 격상 로그 (`combined=...->...`) → `[증빙 6]`

---

## 7.4 algorithm_source 6 종 — 발화 driver 라벨링

### 이 장의 핵심 목적

```
발화가 일어났을 때 "어느 축이 잡았는지" 를 6 종 라벨로 결정하고, 운영자
친화 워딩으로 변환해 추적성을 확보하는 흐름을 정리한다.
```

### 무엇을 수행하는가?

발화 등급(`combined ∈ {caution, predict_warn, warning, danger}`)이 나오면, 다음 priority 로 단일 driver 라벨을 결정한다.

```python
if night_escalated:                                algorithm_source = "night_abnormal"
elif prediction == "anomaly" and arima_violation:  algorithm_source = "combined"
elif escalation_source == "change_point":          algorithm_source = "change_point"
elif arima_violation:                              algorithm_source = "arima"
elif escalation_source == "zscore":                algorithm_source = "zscore"
elif prediction == "anomaly":                      algorithm_source = "isolation_forest"
else:                                              algorithm_source = ""
```

→ priority: **night > combined > change_point > arima > zscore > IF** (강한 신호 우선).

### 왜 필요한가?

운영자는 "AI 가 잡았다" 만으로는 신뢰·대응 판단을 할 수 없다. **어느 알고리즘이** 잡았는지를 명시해야 알고리즘별 신뢰도를 측정하고 임계치를 조정할 수 있다. 또한 Z/CP 는 base 가 발화 중일 때 라벨이 실제 driver 와 어긋날 수 있어, `escalation_source` 가 일치할 때만 채택한다(7.2 설계 결정과 연동).

### 어떻게 수행했나?

라벨 코드는 운영자 친화 워딩으로 변환되어 모달 summary 에 노출된다. fastapi 의 `_ALGORITHM_SOURCE_PHRASE` 와 DRF `constants.ALGORITHM_SOURCE_PHRASE` 가 **단일 동기**된다.

| algorithm_source | 운영자 워딩 |
|---|---|
| `isolation_forest` | 이상 수치 탐지 |
| `arima` | 이상 패턴 탐지 |
| `combined` | 이상 수치·패턴 동시 탐지 |
| `zscore` | 통계 이상 수치 |
| `change_point` | 패턴 변화 탐지 |
| `night_abnormal` | 야간 이상 가동 |

발화 분포는 `POWER_AI_AXIS_FIRED_TOTAL` (라벨: if/arima/zscore/change_point/night) 과 `POWER_AI_ALARM_FIRED_TOTAL` (algorithm_source 라벨) 카운터로 추적되어, 특정 축이 과도하게 발화하면 임계 조정 신호가 된다. AI 발화 시 fastapi 는 `mark_ai_recent` 로 DRF 의 `ai_fired:{device}:{channel}:{rule_level}` (TTL 60s) 키를 찍어 rule 알람과의 중복을 차단한다(상세는 6장).

### 증빙자료 ⭐⭐⭐⭐⭐

- algorithm_source 6 종 라벨 분포 캡처 → `[증빙 7]`
- 5축 발화 분포 Grafana 패널 (`POWER_AI_AXIS_FIRED_TOTAL`) → `[증빙 8]`
- 운영자 모달의 워딩 표시 캡처 → `[증빙 9]`

---

## 7.5 un-downgrade architecture — 가스 격하 vs 전력 동급

### 이 장의 핵심 목적

```
ARIMA 가 가스에서는 IF 의 입력 피처로 격하(downgrade)되고, 전력에서는 IF 와
동급의 독립 축으로 유지(un-downgrade)되는 의도된 비대칭의 근거를 정리한다.
```

### 무엇을 수행하는가?

같은 ARIMA 라도 두 도메인에서 위상이 다르다.

| 도메인 | ARIMA 위상 | 결합 시 역할 |
|---|---|---|
| 가스 | **격하** — IF 입력 피처로 흡수 | 잔차가 IF 의 한 차원 |
| 전력 | **un-downgrade** — IF 와 동급 독립 축 | `arima_violation` 으로 독립 격상 기여 |

### 왜 필요한가?

도메인의 사고 시간 척도가 ARIMA 의 본질 가치를 결정한다.

| 도메인 | 사고 척도 | ARIMA 도메인 필요성 | 채택 |
|---|---|---|---|
| 가스 | 분 단위 즉시 위험 | 낮음 — 잔차가 크면 IF 가 즉시 잡음 | **격하** (IF 피처) |
| 전력 | 시간~일 단위 점진 변화 | 높음 — "예측 정비(predictive maintenance)" framing | **un-downgrade** (IF 동급) |

가스는 즉시 위험 도메인이라 "예측" 의 리드타임 가치가 낮고, IF 다변량이 이미 즉각 이상을 잡는다. 전력은 점진 drift(베어링 마모 등)를 ARIMA trend break 로 미리 잡는 것이 정비 framing 상 가치가 크다. 이 비대칭은 결함이 아니라 도메인 의존 설계 결정이다.

### 어떻게 수행했나?

전력 측은 ARIMA 결과를 `arima_violation` 불리언으로 받아 base 3축 매트릭스에 독립 입력한다. ARIMA 가 학습되지 않은 채널은 `arima_violation=False` 로 호출되어 IF 단독 fallback 으로 동작하되, 2축이 아닌 보수적 3축 결과를 그대로 적용한다(단일 AI 발화 시 한 단계 낮음).

### 증빙자료 ⭐⭐⭐⭐⭐

- 도메인 의사결정 매트릭스 (가스 격하 / 전력 동급) → `[증빙 10]`

---

## 7.6 활성 4채널 운영 전략

### 이 장의 핵심 목적

```
16채널 중 AI 추론을 활성화한 4채널의 선정 기준(부하 종류 다양성)과 확장
로드맵을 정리한다.
```

### 무엇을 수행하는가?

watt 채널에 한해, 다음 4채널만 IF·ARIMA 추론을 활성화한다 (`_INFERENCE_ENABLED_CHANNELS`).

| 채널 | 부하 종류 | 정격 |
|---|---|---|
| ch1 | 압연기 | 7.5 kW |
| ch9 | 메인 전력반 | 15 kW (3상) |
| ch14 | 공조 | 5.5 kW |
| ch15 | 조명 | 1 kW |

나머지 채널과 current/voltage/onoff 데이터는 정적 임계 평가만 수행한다 (watt 만 AI 추론 호출).

### 왜 필요한가?

채널 수가 아니라 **부하 프로파일 다양성**을 검증 기준으로 삼았다. 회전 기계(압연기), 종합 부하(메인 전력반), 주기성 부하(공조), 상시 저부하(조명) 4종으로 5축이 서로 다른 부하 특성에서 동작하는지 확인한다. 16채널 전부 활성화하면 채널당 IF+ARIMA 모델 메모리·추론 cost 가 선형 증가하므로, PoC 단계에서는 다양성 우선으로 4채널을 택했다.

### 어떻게 수행했나?

- 비활성 채널은 `DISABLED` state 로 마킹되고 정적 임계가 알람을 책임진다 (decide_alarm cover, 6장).
- 채널 확장은 `_INFERENCE_ENABLED_CHANNELS` set 추가 + 해당 채널 IF/ARIMA 학습으로 이뤄진다.
- D+30 운영 데이터 누적 후 16채널 확장 여부를 결정한다(메모리·추론 부담 측정 기반).

### 증빙자료 ⭐⭐⭐⭐⭐

- 활성 4채널 부하 프로파일 + 정격 표 → `[증빙 11]`

---

## 7.7 학습 파이프라인과 영속화

### 이 장의 핵심 목적

```
채널별 IF·ARIMA 모델의 학습 명령, MLModel 4축 매칭, fastapi 의 TTL 캐시 로드,
추론 결과의 MLAnomalyResult 영속화까지 모델 라이프사이클을 정리한다.
```

### 무엇을 수행하는가?

학습은 DRF management command 로 수행하고, 산출물(.pkl)과 MLModel row 를 등록한다.

| 모델 | 명령 | 산출물 | sensor_identifier |
|---|---|---|---|
| 전력 IF (4피처) | `train_anomaly_model --sensor-type power` | `power_if_v{N}.pkl` | `""` (sensor_type 단위) |
| 전력 ARIMA (1,1,1) | `train_arima_power_model --device-id .. --channel ..` | `power_arima_v{N}_..._chN_watt.pkl` | `power:device_{mac}:chN:watt` (채널 단위) |

`MLModel` 은 4축 unique constraint 로 관리된다.

| 차원 | 의미 |
|---|---|
| `sensor_type` | "gas" / "power" |
| `algorithm` | "isolation_forest" / "arima" |
| `sensor_identifier` | `""` (sensor_type 단위) 또는 `power:device_{mac}:chN:watt` (채널 단위) |
| `version` | 재학습 시 증가 |

### 왜 필요한가?

채널별로 부하 특성이 달라 ARIMA 는 채널 단위로 분리 학습해야 한다(`sensor_identifier` 가 매칭 키). IF 는 4피처로 단변량을 풍부화하므로 sensor_type 단위 한 모델로 충분하다. 학습 버전·기간을 MLModel row 로 남겨 운영 추적이 가능하다. ARIMA 의 (p,d,q)=(1,1,1) 은 하드코딩으로, auto-arima 는 D+30 sprint 후속 과제다.

### 어떻게 수행했나?

- **로드**: fastapi 의 `_get_or_load` / `_get_or_load_arima` 가 DRF `/api/ml/models/active/` 를 조회해 .pkl 을 joblib 으로 로드하고 `(sensor_type, algorithm, sensor_identifier)` 키로 캐시한다. TTL 은 `ML_MODEL_CACHE_TTL_SEC`(기본 300초). `POST /ai/reload` 로 수동 evict 가능하다. [팀원 확인: LRU cap 미적용 — 다채널 확장 시 메모리 폭증 가드는 후속 과제]
- **영속화**: 추론 결과는 decide_alarm 결과와 무관하게 항상 `MLAnomalyResult` 로 forward 된다(운영 추적). payload 는 `anomaly_score`, `prediction`, `risk_classified`(combined 5단계), 그리고 4피처 + ARIMA forecast/CI 를 담은 `feature_snapshot_json` 을 포함한다.
- **품질 가드**: 통신 단절(`value is None`), overflow, stuck(윈도우 전부 동일값)은 추론 전에 skip 되고 `POWER_AI_QUALITY_SKIP_TOTAL` 로 집계된다.

### 증빙자료 ⭐⭐⭐⭐⭐

- MLModel 4축 row 목록 (IF / ARIMA 채널별) → `[증빙 12]`
- MLAnomalyResult 저장 결과 (`feature_snapshot_json` 포함) → `[증빙 13]`
- TTL 캐시 / `/ai/reload` 동작 로그 → `[증빙 14]`

---

## 7.8 가스 AI 분석 [팀원: 이성현 작성 예정]

> 이 절은 가스 도메인 담당(이성현)이 작성한다. 아래 항목 스켈레톤만 남긴다.

- **다변량 Isolation Forest (3가스 상관)** — CO / H2S / CO2 를 동시에 입력하는 다변량 IF(12 또는 15피처)로 3가스 간 상관 이상을 탐지하는 구조. 알람 UI 단일 라벨을 위해 대표 가스(CO) 고정 처리.
- **ARIMA + Change Point 게이트** — 모듈 import 시 3가스 ARIMA pkl 사전 로드(전력은 lazy 로드와 대비), CP 를 cheap pre-filter 로 두어 3가스가 모두 평탄하면 다변량 IF 추론을 skip 하는 비용 절감 게이트.
- **advisory 운영 정책** — 가스 AI 는 정적 룰을 대체하지 않고 보조(advisory)하는 정책. AI 발화 시 30s rate limit 과 3가스 각각의 Redis mute(`mark_gas_ai_recent`) 동기.
- **가스 AI 메트릭 4종** — 가스 추론·발화·skip·mute 관련 Prometheus 메트릭 4종 (구체 항목은 가스 담당 확정).

### 증빙자료 ⭐⭐⭐⭐⭐

- 가스 다변량 IF 3가스 상관 시각화 → `[증빙 15: 팀원 작성]`
- 가스 AI advisory 흐름도 → `[증빙 16: 팀원 작성]`

---

# 8장. 백오피스 / 운영자 관리 인터페이스

## 8.0 백오피스 공통 아키텍처

diconai의 백오피스는 `/admin-panel/` 단일 프리픽스 아래 21개 메뉴로 구성된 **슈퍼관리자 전용** 운영 인터페이스다. 페이지 라우팅은 `config/admin_panel_urls.py` 한 곳에 모여 있으며, 모든 페이지 View는 `TemplateView`를 상속해 ① 렌더할 템플릿(`template_name`) ② 사이드바 활성 표시 토큰(`active_nav`) ③ (선택) 필터 드롭다운용 비변동 메타(부서·직급·공장 등)만 책임진다. 실제 테이블·트리·CRUD 데이터는 페이지 로드 후 JS가 `/api/admin/...` 엔드포인트를 fetch해 렌더링한다 — 즉 **HTML 셸(페이지)과 JSON 데이터(API)를 물리적으로 분리**한 구조다. 페이지 셸 자체에는 권한 가드를 두지 않고, 데이터를 공급하는 API 단에서 `IsSuperAdmin`(일부 `IsSuperAdminOrFacilityAdmin`)으로 접근을 강제한다. 사이드바(`templates/components/admin_sidebar.html`)는 21개 항목을 단일 컴포넌트로 제공하고, 각 페이지의 `active_nav` 토큰으로 현재 위치를 하이라이트한다.

이 장은 운영자가 시스템의 **판단 기준 자체를 코드 배포 없이 바꿀 수 있게 하는** 백오피스를 다룬다. 그중 8.1은 위험 판단·알람의 정책 계층(알림정책·임계치·데이터 보존)을 집필하고, 8.2는 계정·조직·장비 등 나머지 운영 화면을 각 담당자가 작성한다.

---

## 8.1 알림정책·임계치·데이터 보존 [최재용]

### 이 절의 핵심 목적

운영자가 **누구에게 / 어떤 채널로 / 어떤 권고 조치와 함께 알람을 보낼지**(알림정책), **어떤 수치를 위험으로 볼지**(임계치 기준), **데이터를 얼마나 보관할지**(보존 정책)를 코드 수정·재배포 없이 백오피스에서 직접 관리하고, 변경이 **즉시 런타임에 반영**되게 한다.

### 무엇을 수행하는가?

| 화면 | 메뉴 | API 프리픽스 | 권한 |
|---|---|---|---|
| 알림/이벤트 관리 | `알림/이벤트 관리` | `/api/admin/alerts/policies/` | `IsSuperAdmin` |
| 임계치 기준 관리 | `임계치 기준 관리` | `/api/admin/threshold-groups/`, `/api/admin/thresholds/` | `IsSuperAdmin` |
| 데이터 보관 정책 | `데이터 보관 정책` | `/api/admin/retention-policies/` | `IsSuperAdminOrFacilityAdmin` |

세 화면 모두 페이지 셸은 `config/admin_panel_urls.py`의 `TemplateView`가 제공하고(`AlertPolicyAdminPageView` / `ThresholdAdminPageView` / `DataRetentionPolicyAdminPageView`), 데이터·CRUD는 위 API가 담당한다.

### 왜 필요한가?

위험 판단·알람의 모든 파라미터를 하드코딩하면, 현장 조건이 바뀔 때마다 개발자가 코드를 고치고 재배포해야 한다. 산업 안전 관제는 공장·계절·설비 교체에 따라 "무엇이 위험인가"와 "누구에게 알릴 것인가"가 계속 바뀐다. 백오피스는 이 결정권을 운영자에게 넘기되, 변경이 **다음 알람부터 즉시** 반영되도록 캐시 무효화를 보장해야 한다(아래 시연 시나리오 C의 핵심).

### 어떻게 수행했나?

#### (1) 알림정책 편집 + recommended_actions

`AlertPolicy` 모델은 "어떤 이벤트(event_type)가 / 어떤 범위(전사 또는 특정 facility + 센서/전력장치/지오펜스)에서 발생하면 / 누구(target_user_types)에게 / 어떤 채널(channels: popup·push·sms·email)로 알림"을 1행으로 표현한다. 목록·상세·등록·수정 4개 화면은 각자 다른 schema를 쓰므로 시리얼라이저를 4종으로 분리했다(`alert_policy_admin.py`).

- **목록**(`AlertPolicyListSerializer`): 정책명·이벤트·채널·수신대상·사용여부 + `condition_summary`(조건을 운영자 친화 한글 1줄로 요약, 예: `"전사 / 가스 경보 / 관제 실시간 알림·SMS"`). 이 요약은 DB 캐시 컬럼이며, 비어 있으면 즉석 계산한다.
- **쓰기**(`AlertPolicyWriteSerializer`): Create/Update 공용. `partial=True`로 PATCH를 처리하고, 저장은 모델 `save()`를 직접 부르지 않고 `policy_matcher.save_policy()` 서비스 진입점을 경유한다 — view에 비즈니스 로직을 두지 않는 컨벤션(view → service → model)을 지키면서 `condition_summary` 동기화와 캐시 무효화를 한곳에서 보장한다.

**recommended_actions**는 위험 등급별 권고 조치 단계를 담는 `JSONField`다. 키는 `danger` / `warning` / `default`만 허용하고 값은 문자열 리스트여야 하며, 이 규칙을 시리얼라이저 `validate_recommended_actions`에서 강제한다.

```python
# alert_policy_admin.py — recommended_actions 검증 (요지)
allowed_keys = {"danger", "warning", "default"}
# 값은 항상 list[str] — 아니면 ValidationError
```

런타임에서는 Event가 연결된 정책의 권고 조치를 **자신의 risk_level로 룩업**해 화면·통보에 싣는다. 정책 미연결이거나 값이 없으면 빈 리스트를 반환해 프론트의 fallback 매트릭스로 graceful degradation 한다.

```python
# serializers/event.py — get_recommended_actions (요지)
actions = obj.policy.recommended_actions
return actions.get(obj.risk_level) or actions.get("default") or []
```

#### (2) 정책 캐시 즉시 invalidate = 시연 시나리오 C

`AlertPolicy`는 운영자가 바꾸기 전까지 값이 불변이고, 알람이 발화될 때마다 DB를 조회하면 lock 경합이 커진다. 그래서 `policy_matcher`는 event_type 단위로 활성 정책 목록을 **5분 TTL 캐시**(`alert_policies:{event_type}`)에 담는다. 문제는 캐시 때문에 운영자가 정책을 바꿔도 최대 5분간 옛 값이 적용된다는 점이다.

해결은 **정공법(signal) + fallback(명시 호출)** 의 이중 안전망이다.

| 경로 | 무효화 트리거 |
|---|---|
| 정공법 | `apps/alerts/signals.py`의 `post_save`/`post_delete` receiver — Django admin·DRF view·shell 등 **모델이 어디서 변경돼도 자동 발화** |
| fallback | `save_policy()` 서비스 진입점 + DRF `AlertPolicyAdminDetailView.delete`의 명시 `invalidate_policy_cache()` 호출 — signal 누락 대비 안전망 |

```python
# policy_matcher.save_policy — 저장 직후 동일 event_type 캐시 삭제
policy.condition_summary = compute_condition_summary(policy)
policy.save()
invalidate_policy_cache(policy.event_type)  # 다음 알람부터 즉시 반영
```

이 즉시 반영이 **시연 시나리오 C(어드민에서 알림 정책을 바꾸면 그 변경이 다음 알람부터 즉시 적용)** 의 백엔드 근거다. 단, `QuerySet.update()`·`bulk_update()`·raw SQL은 `post_save`를 발화시키지 않으므로 운영 흐름에서는 쓰지 않는다(어드민은 항상 `serializer.save()` 경로).

#### (3) 임계치 기준 관리

임계치는 `ThresholdGroup`(그룹) → `Threshold`(항목)의 2계층 트리다(`threshold_admin.py`).

- 그룹 목록/생성/수정/삭제, 그룹별 임계치 목록/생성/수정/삭제, 다건 일괄 미사용 전환(`bulk-deactivate`)을 제공한다.
- **삭제 가드**: 하위 임계치가 있는 그룹은 삭제를 차단한다(`PROTECT` 정책 반영, 400 반환) — 운영 중 기준이 통째로 사라지는 사고를 막는다.
- **facility 정책**: 현재 어드민은 `facility=null`(전사 기준)만 조회·생성한다. 공장별 예외 기준은 Phase 2 범위로 미루었다.

> 참고: 전력 임계치의 실효 기준(% + 채널 정격) 및 위험 판단 로직은 6장(알람), AI 5축 판단은 7장을 참조한다. 본 절은 "기준값을 백오피스에서 편집한다"는 관리 인터페이스 관점만 다룬다.

#### (4) 데이터 보관 정책

`DataRetentionPolicy`는 `(device_type, data_category)` 조합당 1행으로, **원천 보관 기간**(`raw_retention_days`) / **이력 보관 기간**(`history_retention_days`) / **삭제 주기**(`delete_cycle`) / 활성 여부를 관리한다. `history >= raw`(이력은 원천보다 오래 보관)를 모델 `clean()`에서 강제한다. 데이터 수명은 Raw 단기 / Event·이력 장기 / ML 별도의 3계층 원칙을 따른다.

운영 안전을 위한 핵심은 **삭제 전 미리보기와 줄임 즉시 적용**이다(`retention_policy_views.py`).

| 엔드포인트 | 역할 |
|---|---|
| `GET .../{id}/` | 단건 조회 + 현재 기준 삭제 예정 행 수(`affected_rows`)를 편집 모달 상단에 노출 |
| `GET .../{id}/preview/?raw_days=N` | 저장 없이 입력값 기준 삭제 예정 행 수만 계산 — 입력 변경 시 debounce 호출 |
| `PATCH .../{id}/` | 보관 기간 수정. **기간이 줄었으면** 저장 즉시 초과분 실제 삭제 후 삭제 행 수 반환 |
| `POST .../run/` | 배치 즉시 실행(`dry_run` 지원) |

미리보기·즉시 삭제 모두 실제 배치 태스크의 `_delete_for_policy()`를 재활용한다(`dry_run` 플래그로 count만 또는 실삭제 분기). `SimpleNamespace` mock으로 저장 없이 동일 쿼리 로직을 태우므로, 미리보기 숫자와 실제 삭제 결과가 어긋나지 않는다.

> 보존 정책의 **실제 삭제 배치 실행**(Celery 스케줄·`delete_cycle` 체크)은 9장 운영·모니터링을 참조한다.

#### 경계 — 커스텀 UI가 없는 영역

위험 유형 분류 체계인 **HazardType / HazardTypeGroup은 별도 `/admin-panel/` 커스텀 UI가 없다.** 오직 Django 기본 Admin(`apps/alerts/admin.py`)에 등록되어 그 화면에서만 관리한다(`type_code`는 `AlarmType` enum과 1:1로 강제되어 readonly). 이 절의 백오피스 범위에 포함되지 않는다.

### 증빙자료 ⭐⭐⭐⭐⭐

- [증빙 1: 알림정책 목록 화면 — condition_summary 한글 요약 컬럼 포함]
- [증빙 2: 알림정책 등록/수정 모달 — recommended_actions(danger/warning) 입력 폼]
- [증빙 3: 정책 변경 → 다음 알람에서 즉시 반영(시연 C) — 변경 전/후 알람 비교]
- [증빙 4: 임계치 그룹/항목 2계층 화면 + 하위 항목 있는 그룹 삭제 차단(400)]
- [증빙 5: 데이터 보관 정책 편집 모달 — 보관 기간 변경 시 삭제 예정 행 수 미리보기]
- [증빙 6: HazardType은 Django Admin에서만 관리(커스텀 UI 부재) 캡처]

---

## 8.2 계정·조직·장비·지오펜스·공지·로그·체크리스트·VR 등 [팀원: 각 담당 작성 예정]

아래 항목들은 사이드바(`admin_sidebar.html`) 메뉴 순서대로 나열한다. 각 담당자가 본인 영역을 본문으로 채운다. 공통 아키텍처(페이지 셸 `TemplateView` + `/api/admin/` JS fetch + `IsSuperAdmin`)는 8.0을 따른다.

| # | 메뉴 | 페이지 라우트 | active_nav |
|---|---|---|---|
| 1 | 계정 관리 | `/admin-panel/accounts-management/` | `account` |
| 2 | 조직 관리 | `/admin-panel/organizations/` | `org` |
| 3 | 전력 시스템 | `/admin-panel/facility/` | `power_system` |
| 4 | 장비 관리(가스 센서) | `/admin-panel/gas-sensors/` | `gas_sensor` |
| 5 | 지도/구역(지오펜스) | `/admin-panel/geofence/` | `geofence` |
| 6 | 지도 편집 | `/admin-panel/map-editor/` | `map_editor` |
| 7 | 가스 데이터 | `/admin-panel/data/gas/` | `data` |
| 8 | 전력 데이터 | `/admin-panel/data/power/` | `power_data` |
| 9 | 데이터 보관 정책 | `/admin-panel/data/retention-policy/` | `retention_policy` | ※ 본문은 8.1 참조 |
| 10 | 로그 — 시스템 로그 | `/admin-panel/logs/system/` | `system_log` |
| 11 | 로그 — 사용자 활동 로그 | `/admin-panel/logs/activity/` | `activity_log` |
| 12 | 로그 — 연동 로그 | `/admin-panel/logs/integration/` | `integration_log` |
| 13 | 로그 — 지도 편집 로그 | `/admin-panel/logs/map-edit/` | `map_edit_log` |
| 14 | 공지사항 | `/admin-panel/notices/` | `notice` |
| 15 | 알림/이벤트 관리 | `/admin-panel/alerts/policies/` | `alert_policy` | ※ 본문은 8.1 참조 |
| 16 | 이벤트 이력 조회 | `/admin-panel/events/history/` | `event_history` |
| 17 | 공통코드 관리 | `/admin-panel/common-codes/` | `common_code` |
| 18 | 임계치 기준 관리 | `/admin-panel/thresholds/` | `threshold` | ※ 본문은 8.1 참조 |
| 19 | 위험 기준 관리 | `/admin-panel/risk-standards/` | `risk_standard` |
| 20 | 안전 정책/기준 관리(체크리스트) | `/admin-panel/safety/checklist/` | `policy` |
| 21 | VR 교육 관리 | `/admin-panel/safety/vr-training/` | `vr_training` |

### 8.2.1 계정·조직 [팀원: 작성 예정]
- 계정 관리: 사용자 목록·필터(부서/직급/공장 드롭다운), 계정 CRUD·권한
- 조직 관리: 부서/직급/조직 트리

### 8.2.2 장비·전력 시스템 [팀원: 작성 예정]
- 전력 시스템(`facility`): 전력 장치/채널 메타 관리
- 장비 관리(가스 센서): 센서 등록·상태

### 8.2.3 지도·지오펜스 [팀원: 작성 예정]
- 지도/구역(지오펜스): 위험구역 정의
- 지도 편집: 도면/노드 배치 에디터

### 8.2.4 데이터 조회 [팀원: 작성 예정]
- 가스 데이터 / 전력 데이터: 원천 데이터 조회·필터(장비·기간)

### 8.2.5 로그 [팀원: 작성 예정]
- 시스템 / 사용자 활동 / 연동 / 지도 편집 로그 4종 조회

### 8.2.6 공지·이벤트 이력 [팀원: 작성 예정]
- 공지사항: 등록/수정/상세
- 이벤트 이력 조회: 읽기 전용, 날짜·구분(AlarmType)·상태(EventStatus) 필터

### 8.2.7 공통코드·위험 기준 [팀원: 작성 예정]
- 공통코드 관리: CodeGroup → CommonCode 2계층
- 위험 기준 관리: RiskLevelStandard 3개 레코드(등급별 색상·알림강도) 편집

### 8.2.8 안전 점검·VR 교육 [팀원: 작성 예정]
- 안전 점검 체크리스트: 섹션별 항목 편집 + 반영 이력/저장
- VR 교육 관리: facility별 단일 콘텐츠 조회/교체

---

# 9장. 운영 구조 및 모니터링

## 9.0 이 장의 핵심 목적

이 장은 diconai가 **"센서 데이터를 받아 위험을 판단하고 알람을 전달하는 시스템"을 어떻게 끊김 없이·관찰 가능하게 운영하는가**를 다룬다. 위험 판단 로직 자체(6장)나 AI 알고리즘(7장)이 아니라, 그 결과가 운영 환경에서 **지연·유실·중복 없이 흐르도록 지탱하는 비동기 처리·큐·메트릭 계층**이 주제다.

운영/모니터링은 세 담당으로 나뉜다.

| 영역 | 담당 | 범위 |
|---|---|---|
| 9.1 비동기 알람 처리·메트릭 | **최재용** | Celery 알람 태스크·큐 분리, Redis Stream 알람큐, dedup·AI mute·AI 추론 메트릭 정의 |
| 9.2 Grafana 시각화 | 정휘훈 | 6대시보드 구성·패널 (스켈레톤) |
| 9.3 컨테이너·배포·CI | 이성현 | Docker Compose 10컨테이너·k8s·GitHub Actions (스켈레톤) |

> 시스템 전체 데이터 흐름과 2서버 구조는 3장(아키텍처), 알람 발화 규칙은 6장, AI 추론 5축/3축은 7장을 참조한다. 이 장은 그 흐름이 **운영 중 관찰·복원 가능하게** 만드는 계층에 집중한다.

---

## 9.1 비동기 알람 처리·메트릭 [최재용]

### 이 절의 핵심 목적

알람은 산업 안전 시스템의 최종 산출물이며, **늦거나 빠지거나 겹치면 안 된다.** 이 절은 팀이 알람 발화를 동기 처리에서 분리해 (1) 센서 수신을 막지 않고, (2) 일시 장애에도 유실되지 않으며, (3) 폭주 시에도 운영자에게 중복으로 쏟아지지 않도록 만든 **비동기 처리 파이프라인과, 그 파이프라인을 Grafana만 보고 진단할 수 있게 하는 메트릭 계층**을 설명한다.

### 무엇을 수행하는가?

팀은 알람 경로를 네 개의 독립 컴포넌트로 구성했다.

1. **Celery 알람 태스크** (`apps/alerts/tasks.py`) — 가스/전력의 danger·warning, 지오펜스 진입, 정상화(clear)를 각각 별도 태스크로 발화. DB에 `AlarmRecord`/`Event`를 기록한 뒤 FastAPI로 WS 푸시.
2. **Celery 큐 분리** — 실시간 알람(`alarm`)과 주기 메트릭 수집(`metric`)을 별도 큐·별도 워커로 분리해, 메트릭 태스크가 알람을 밀어내지 못하게 함.
3. **Redis Stream 알람큐** (`diconai:ws:alarms`) — DRF→FastAPI로 넘어온 알람을 Stream에 적재하고, FastAPI replica별 XREAD 커서가 fan-out으로 소비.
4. **Prometheus 메트릭 계층** — dedup 차단·AI mute·E2E latency·스트림 lag·AI 추론 구간을 정량 노출.

### 왜 필요한가?

| 요구 | 동기 처리 시 문제 | 비동기 분리로 해결 |
|---|---|---|
| 센서 수신 비차단 | 알람 DB 쓰기·WS 푸시가 수신 요청을 블로킹 | Celery 태스크로 위임, 수신은 즉시 ACK |
| 일시 장애 유실 방지 | FastAPI/Redis 순간 장애 시 알람 영구 소실 | Stream은 휘발 안 됨 + Celery retry(5s×3) |
| 폭주 시 중복 억제 | retry·매초 재평가가 같은 알람을 N번 푸시 | fingerprint dedup choke point |
| 진단 가능성 | "왜 알람이 안 떴나"를 로그 grep으로만 추적 | 구간별 메트릭으로 원인 구간 특정 |

### 어떻게 수행했나?

#### (1) Celery 알람 태스크 — 4종 × 2도메인

`apps/alerts/tasks.py`의 모든 태스크는 **DB 쓰기와 WS 푸시를 별도 try 블록으로 분리**한다. WS 푸시 실패 시 `self.retry`가 DB 쓰기를 재실행하면 `AlarmRecord`가 중복 생성되기 때문이다 — DB 쓰기 성공 후 WS 푸시 실패는 retry 없이 경고만 남기고, 알람은 DB에 보존되므로 유실되지 않는다.

| 태스크 | 발화 시점 | retry |
|---|---|---|
| `fire_danger_alarm_task` / `fire_power_danger_task` | 즉시 | DB 실패만 retry |
| `fire_warning_alarm_task` / `fire_power_warning_task` | `countdown=WARNING_DURATION_SEC(5s)` 지속 후 | DB 실패만 retry |
| `fire_geofence_alarm_task` | 위험구역 진입 즉시 | DB 실패 retry |
| `fire_clear_notification_task` / `fire_power_clear_task` | 정상화 즉시 | `raise_on_failure=False` (중복보다 손실 허용) |

정상화 태스크는 **채널-aware clear**가 핵심이다. 전력 한 채널이 정상 복귀해도 디바이스를 공유하는 다른 채널이 위험 지속 중이면 `has_other_active_channel`로 Event를 유지한다. 이 게이팅이 없으면 공유 Event가 조기 RESOLVE되고 다음 발화가 새 `event_id`로 생성돼 프론트 60s dedup(event_id 키)을 통과 → 폭주한다.

#### (2) Celery 큐 분리 — alarm / metric

`CELERY_TASK_ROUTES`(`config/settings/base.py`)로 태스크를 큐에 라우팅한다.

```python
CELERY_TASK_ROUTES = {
    "apps.alerts.tasks.*": {"queue": "alarm"},     # 실시간 알람
    "apps.operations.tasks.*": {"queue": "metric"}, # 주기 수집
}
```

`celery-worker-alarm`(`-Q alarm`, concurrency=2)과 `celery-worker-metric`(`-Q metric`, concurrency=1)이 각 큐만 소비한다. 데이터 보관·DB health·큐 길이 수집 같은 무거운 주기 태스크가 알람 워커를 점유하지 못하게 하는 것이 목적이다. (컨테이너 정의 자체는 9.3 이성현 담당.)

#### (3) Redis Stream 알람큐 — `diconai:ws:alarms`

LIST+BRPOP에서 **Stream+XREAD**로 전환했다. BRPOP은 한 알람을 한 소비자만 pop하는 경쟁 소비라 멀티레플리카 fan-out이 불가능했다.

```python
# push_alarm — XADD MAXLEN ~ 10000 (approximate trim)
await r.xadd(ALARM_QUEUE_KEY, {"data": json.dumps(payload)},
             maxlen=MAX_QUEUE_LEN, approximate=True)
```

```python
# alarm_flush_loop — replica별 독립 커서로 스트림 전체를 fan-out 소비
last_id = "$"  # 부팅 이후 신규만 (과거 무한 replay 방지)
new_last_id, payloads = await read_alarms_blocking(last_id, timeout=1)
```

| 특성 | 설계 | 효과 |
|---|---|---|
| 적재 | `XADD MAXLEN ~10000 approximate` | 폭주 시 가장 오래된 알람부터 drop, 별도 트리밍 불필요 |
| 소비 | replica별 `XREAD BLOCK` + 메모리 커서 | 모든 replica가 모든 알람 수신 (fan-out) |
| 재시작 내성 | Stream은 휘발 안 됨 | FastAPI 재시작 시 커서만 `$` 리셋, 큐 보존 |
| 센서와 분리 | `broadcast_loop`(센서 통합 데이터)와 `alarm_flush_loop`(알람)이 별개 루프 | 알람이 센서 broadcast 주기에 묶이지 않음 |

**fingerprint dedup** — Celery retry가 같은 payload를 `/internal/alarms/push/`로 여러 번 보내 큐에 중복 적재되는 것을, push의 choke point에서 `SET NX EX 30s`로 차단한다. fingerprint는 4분기로 안정 idempotency key를 만든다.

| payload 종류 | fingerprint key |
|---|---|
| 룰 알람 | `event:{event_id}:{risk_level}` (RESOLVED는 `:resolved` 분리) |
| AI 알람 | `ai:power_anomaly_ai:{device}:{channel}:{risk_level}` |
| 정상화 | `clear:{alarm_type}:{source_label}` (가스 9종 동시 push를 1줄로) |
| power_overload cover | `cover:{source}:{source_label}:{risk_level}` |

TTL 30s는 Celery retry 총 시간(5s×3=15s)보다 길고, 재알림 cooldown(60s)보다 짧게 잡아 1분 후 정상 재발화를 막지 않는다.

#### (4) AI mute — 룰 알람과의 발화 중복 방지

AI 추론 알람이 발화하면 같은 `(device, channel)`의 룰 알람을 60s 동안 mute한다. FastAPI가 `ai_fired:{device}:{channel}:{rule_level}` 키를 raw Redis로 set하고, DRF 룰 가드가 같은 키를 EXISTS로 읽는다. mute로 skip된 룰 fire 횟수는 `RULE_FIRE_SUPPRESSED_BY_AI_TOTAL`로 추적해 "왜 룰이 안 떴나"를 즉시 확인한다. (격상 케이스 — AI=warning, 룰=danger — 는 발화 level 이하 키만 set하므로 자연 통과.)

#### (5) Prometheus 메트릭 정의

팀이 추가한 비즈니스 메트릭 중 **알람·AI 운영 진단용 핵심 메트릭**은 다음과 같다. 설계 원칙은 일관된다 — **"알람이 안 떴다/늦었다"는 신고가 오면 Grafana만 보고 원인 구간을 특정한다.**

**FastAPI (`fastapi-server/core/metrics.py`, `alarm_queue.py`)**

| 메트릭 | 타입 | 레이블 | 진단 용도 |
|---|---|---|---|
| `alarm_push_dedup_hits_total` | Counter | — | retry 폭주로 차단된 중복 push 추세 |
| `fastapi_alarm_queue_length` | Gauge | — | Stream 적체(XLEN). 꾸준히 쌓이면 flush 병목 |
| `fastapi_alarm_stream_lag_seconds` | Gauge | — | 스트림 말단↔커서 시간차. replica별 뒤처짐 식별 |
| `e2e_alarm_latency_seconds` | Histogram | `risk_level` | IoT 수신→WS 전송 전구간. danger p95 ≤ 1.5s SLO |
| `redis_command_duration_seconds` | Histogram | `command` | XADD 지연 → Redis 병목 판단 근거 |
| `ai_inference_duration_seconds` | Histogram | `model_type` | IF/ARIMA 추론 지연 |
| `ai_inference_failed_total` | Counter | `model_type`,`reason` | AI silent fail 즉시 감지 |

**전력 AI 5축 메트릭** (`POWER_AI_*`)

| 메트릭 | 레이블 | 진단 용도 |
|---|---|---|
| `power_ai_axis_fired_total` | `axis`(if/arima/zscore/change_point/night) | 어느 축이 과탐지하는지 |
| `power_ai_combined_total` | `combined` | 최종 판정 분포 → 재학습 시점 판단 |
| `power_ai_alarm_fired_total` | `algorithm_source`(6종) | 실제 큐 도달 발화 수 |
| `power_ai_quality_skip_total` | `reason` | 센서 불량으로 조용히 멈춘 상태 |
| `power_ai_rate_limited_total` | — | "알람 1번만 왔다" 신고 원인 |
| `power_ai_inference_total` | — | 추론 실행 횟수 (skip 비율) |

**가스 AI 3축 메트릭** (`GAS_AI_*`) — `gas_ai_inference_total`, `gas_cp_detected_total`, `gas_ai_rate_limited_total`, `gas_ai_alarm_fired_total`(`gas_type`,`risk_level`).

**DRF (`drf-server/apps/core/metrics.py`)** — 알람 발화·Celery·게이트 메트릭

| 메트릭 | 레이블 | 진단 용도 |
|---|---|---|
| `alarm_fired_total` | `alarm_type`,`risk_level` | WS 발송된 알람 수(dedupe 통과 후) |
| `rule_fire_suppressed_by_ai_total` | `device_id`,`channel`,`level` | AI mute로 skip된 룰 fire |
| `power_danger_confirm_total` | `outcome`(held/confirmed/reset) | danger 2틱 confirm 게이트 — 스파이크 걸러낸 비율 |
| `celery_task_duration_seconds` | `task_name` | 태스크 로직 지연(C1) |
| `celery_task_queued_seconds` | `task_name` | 큐 대기 → worker 증설 신호(C2) |
| `celery_queue_length` | `queue` | alarm/metric 큐 적체 |
| `celery_task_failed_total` / `_retried_total` | `task_name` | 알람 미발송 추적 시작점 |

이 메트릭들이 **하나의 진단 체인**을 이룬다: `e2e_alarm_latency`가 급등하면 → `celery_task_duration`(로직 느림?) → `db_save_duration`(DB 락?) → `redis_command_duration`(Redis 병목?) → `ai_inference_duration`(AI 느림?) 순으로 좁혀 원인 구간을 단일 화면에서 특정한다.

#### (6) 작업자 DANGER 대피·Discord 연동

danger 알람 payload에는 `target_worker_ids`(소속 시설 작업자)가 실려, FastAPI가 전체 broadcast가 아닌 `worker_clients`로만 개인 대피 통보를 분배한다. 동시에 `_push_to_ws` 성공 tick 1회에 한해 Discord로 미러링하며, 관리자 채널은 broadcast, 작업자 채널은 가스/전력 DANGER에 `@here` 대피 멘션(opt-in)을 발송한다. Discord 실패는 알람 본류를 막지 않는다(silent fail).

### 증빙자료 ⭐⭐⭐⭐⭐

- [증빙 1: ___] Grafana 알람 대시보드 — `e2e_alarm_latency` danger p95 패널 + 진단 체인 패널
- [증빙 2: ___] `celery-worker-alarm` / `celery-worker-metric` 분리 워커 로그 (큐별 태스크 소비)
- [증빙 3: ___] `redis-cli XLEN diconai:ws:alarms` + `KEYS alarm:push:dedup:*` 실행 결과 (Stream 적재·dedup 키)
- [증빙 4: ___] dedup 동작 — 동일 event_id 재푸시 시 `alarm_push_dedup_hits_total` 증가 + `dedup hit` 로그
- [증빙 5: ___] `power_danger_confirm_total{outcome="reset"}` — 단일 틱 스파이크가 걸러진 시계열
- [증빙 6: ___] 작업자 DANGER 대피 — `worker_clients` 개인 통보 + Discord `@here` 대피 메시지

---

## 9.2 Grafana 시각화 [팀원: 정휘훈] 작성 예정

> 본 절은 정휘훈 담당 영역으로, 아래 항목 스켈레톤만 남긴다.

- 6대시보드 구성 (overview / sensor / alarm / db-redis / power-ai / gas-ai) 패널 설계
- 9.1에서 정의한 Prometheus 메트릭 19종의 시각화 매핑 (p95 패널·rate·heatmap)
- 알람 임계 룰(alert rule) 설정 — 큐 길이·E2E latency·DB 락 임계
- Prometheus 스크랩 타깃·데이터소스 프로비저닝
- [팀원 확인: 미설정 alert rule·미차트 메트릭 점검 결과 반영 여부]

---

## 9.3 컨테이너·배포·CI [팀원: 이성현] 작성 예정

> 본 절은 이성현 담당 영역으로, 아래 항목 스켈레톤만 남긴다.

- Docker Compose 10컨테이너 구성 (drf / fastapi / postgres(PG16) / redis / celery-worker-alarm / celery-worker-metric / celery-beat / redis_exporter / prometheus / grafana)
- PostgreSQL 16 전환 — SQLite 대비 동시 쓰기·운영 효과
- k8s manifest (minikube 실험) — 멀티레플리카 fan-out 검증 환경
- GitHub Actions CI — ruff/ruff-format lint, 테스트 파이프라인
- redis_exporter 운영 — Redis 메트릭 스크랩
- 컨테이너 healthcheck·의존성 순서(`depends_on` + `service_healthy`)
```

---

# 10장. 프로젝트 관리 및 협업 방식 (PM)

## 10.1. 이 장의 핵심 목적

이 장은 diconai 프로젝트가 **"어떤 코드를 만들었는가"가 아니라 "그 코드를 만들기까지 무엇을 어떤 순서로 결정했는가"**를 설명한다. 산업 안전 관제 시스템은 가스·전력·작업자 위치라는 서로 다른 도메인이 하나의 알람 흐름으로 수렴하는 구조라(6장·7장 참조), 기능 단위로 각자 개발하면 도메인 경계마다 스키마 불일치·우선순위 충돌·중복 구현이 발생하기 쉽다.

팀은 이를 막기 위해 **요구사항 정리 → 갭 식별 → 기능 인벤토리 대조 → 우선순위 트리아지 → 설계 결정 → 개발 → 시연 시나리오 검증**으로 이어지는 단일 관리 축을 세웠다. 이 축의 정의·운영·문서화는 최재용이 PM으로서 전체를 집필·주도했으며, 이 장은 그 운영 방식을 프로세스 관점에서 기록한다.

> **이 장에서 다루는 6개 관리 활동**
>
> | # | 활동 | 산출물 |
> |---|---|---|
> | 1 | 요구사항 분석 · PRD/화면설계서 갭 식별 | 화면설계서 이슈 분석 + 정의서 우선 원칙 |
> | 2 | 기능 인벤토리 · 누락 영역 양방향 대조 | 엑셀 v7 ↔ 어드민 21페이지 대조표 |
> | 3 | 수정사항 우선순위 트리아지 (60건) | P0~P3 분류 + BE/FE 분배표 |
> | 4 | 단계별 설계 의사결정 주도 | Phase 3 단독 결정문 (30+ 결정) |
> | 5 | 개발 프로세스 정립 (4단계) | 기능정의서 → 스키마 → 데이터흐름 → 코딩 |
> | 6 | 시연 시나리오 A/B/C 정의 | 도메인별 시연 동선 |

---

## 10.2. 무엇을 수행하는가?

이 장이 다루는 PM 활동은 **코드를 짜는 일이 아니라, 코드가 짜여야 할 대상과 순서와 기준을 확정하는 일**이다. 구체적으로는 다음을 수행했다.

- **요구사항 문서 4종의 위계를 정리한다.** 연구개발계획서 → 요구사항정의서 → 화면설계서(피그마) → 기능정의서(엑셀)는 작성 주체와 목적이 다르고 서로 충돌할 수 있다. 충돌 시 무엇을 우선할지의 규칙을 세운다.
- **화면설계서와 실제 코드의 갭을 식별한다.** 피그마 지적사항이 이미 코드에 반영됐는지(outdated), 모델은 있는데 UI만 없는지, 아예 미구현인지를 30여 개 화면에 대해 판정한다.
- **기능 인벤토리를 양방향으로 대조한다.** 엑셀 기능정의서 v7의 26개 어드민 그룹과 실제 구현된 어드민 21메뉴를 양쪽 방향으로 맞춰보며 누락·초과를 찾는다.
- **수정사항을 우선순위로 트리아지한다.** 화면설계서에서 도출된 60건을 시연 영향도 기준으로 P0~P3로 나누고, 작업량을 재추정해 담당(BE/FE)을 배분한다.
- **단계별 설계 결정을 문서로 고정한다.** 모델 변경·마이그레이션 전략·FK 정책 등 30개 이상의 설계 선택을 옵션·장단점·대안과 함께 결정문으로 남긴다.
- **개발 프로세스를 표준화한다.** 모든 기능이 동일한 4단계(기능정의 → 스키마 → 데이터흐름 → 코딩)를 거치도록 규칙을 만든다.
- **시연 시나리오를 정의한다.** 가스·전력·어드민 세 축의 시연 동선(A/B/C)을 확정해 시연 품질을 보장한다.

---

## 10.3. 왜 필요한가?

### 10.3.1. 요구사항 문서가 4종이고 서로 충돌하기 때문

diconai는 중소기업 기술개발 지원사업 연구개발 과제로, 요구사항이 **단일 문서가 아니라 위계가 다른 4종 문서에 분산**되어 있다.

| 문서 | 작성 주체 | 성격 | 변경 가능성 |
|---|---|---|---|
| 연구개발계획서 | 과제 기획 | 프로젝트 존재 이유·기본 전제 | 거의 없음 |
| 요구사항정의서 | diconai | 1차 기능 리스트 | **높음** (연구개발이라 확정 X) |
| 화면설계서 (피그마) | 디자이너 | 화면별 UX·기능 배치 | 중간 |
| 기능정의서 (엑셀 v7) | 기획 | 메인 대시보드 기준 기능 명세 | 중간 |

연구개발 특성상 요구사항정의서·화면설계서는 "사용자 경험상 이 화면에서 무엇이 중요한가"에 따라 **개발 중에도 바뀔 수 있다**. 따라서 어떤 문서를 진실 공급원(SoT)으로 삼을지, 충돌 시 무엇을 우선할지를 PM이 먼저 정하지 않으면 팀원마다 다른 문서를 근거로 작업하게 된다.

### 10.3.2. 화면설계서 지적이 이미 해소됐거나 반대로 누락됐기 때문

화면설계서(1534줄, 30여 개 화면)의 지적사항을 그대로 작업 큐에 넣으면 **이미 코드에 반영된 항목을 다시 만들거나, 실제로 없는 기능을 있다고 착각**한다. 예를 들어 화면설계서는 "viewer 권한 옵션 누락", "LEGAL_THRESHOLDS 하드코딩"을 지적하지만, 코드에는 이미 `UserType.VIEWER`가 정의돼 있고 임계치도 DB로 이관 완료된 상태다(4장 참조). 반대로 "조직 변경 이력 audit 화면", "VR 이수 이력 모델"은 모델조차 없는 진짜 미구현이다.

즉 화면설계서는 **작업 큐가 아니라 갭 분석의 입력**이며, 코드 실사를 거쳐 ✅구현됨 / ⚠️일부 / ❌미구현 / 🔧작업필요로 재분류해야 실제 작업 대상이 나온다.

### 10.3.3. 작업량 추정이 부풀려져 있어 우선순위 없이는 시연을 못 맞추기 때문

시연(2026-06-14)을 앞두고 화면설계서에서 도출된 수정사항은 60건이었고, 초기 추정으로 P0(시연 필수)만 22~36시간이었다. 그러나 코드를 직접 `grep`해보면 채널 디스패처·`AdminPagination`·`SOURCE_TYPE_LABEL` 분기·`Event.worker` FK 같은 인프라가 **이미 다 있어서**, 신규 작성이 아닌 "연결"만 필요한 항목이 대부분이었다. 추정을 코드 기준으로 다시 잡지 않으면 없는 일감에 시연 일정을 맞추려다 실제 P0를 놓친다.

### 10.3.4. 도메인 경계마다 설계 충돌이 잠재하기 때문

알람 흐름은 fastapi 단일 결정자(`decide_alarm` 6매트릭스)로 수렴하지만(6장 참조), 그 위의 모델 계층(Event·Notification·SafetyCheck·WorkerPosition)은 FK 정책·마이그레이션 순서·UNIQUE 제약이 서로 얽혀 있다. "Event 삭제 시 알림을 CASCADE할 것인가 SET_NULL할 것인가" 같은 결정은 한쪽만 보고 정하면 감사 이력 손실이나 패턴 불일치를 낳는다. 이런 결정을 **회의 없이도 일관되게** 내리려면, 옵션과 장단점을 펼쳐 근거를 남기는 결정 문서가 선행돼야 한다.

### 10.3.5. 사람마다 개발 순서가 다르면 데이터 흐름이 깨지기 때문

생성형 AI로 코딩하는 팀 환경에서 각자 바로 코드부터 짜면, 같은 기능이 사람마다 다른 스키마·다른 데이터 흐름으로 구현된다. 모든 기능이 **동일한 사고 순서**(기능정의 → 스키마 → 데이터흐름 → 코딩)를 거치도록 강제해야, IoT → fastapi → drf/WebSocket으로 이어지는 데이터 흐름이 일관되게 유지된다.

---

## 10.4. 어떻게 수행했나?

### 10.4.1. 요구사항 분석 · PRD/화면설계서 갭 식별 · 정의서 우선 원칙

팀은 먼저 요구사항 문서 4종의 **위계와 우선 규칙**을 명문화했다.

**정의서 우선 원칙** — 피그마(화면설계서)와 기능정의서(센서/데이터 정의 포함)가 충돌하면 **정의서를 우선**한다. 화면설계서는 UX와 화면 배치의 진실 공급원이지만, 백엔드 데이터 스키마·센서 수신 필드의 진실 공급원은 정의서다. 따라서 화면에 어떤 컬럼이 그려져 있더라도, 정의서에 없는 센서 수신 데이터 컬럼을 선제적으로 추가하지 않는다.

다음으로 화면설계서 이슈 분석(30여 개 화면)을 **코드 실사 기반으로 재판정**했다. 디자이너 영역(작업자 모바일 앱 화면, 순수 시각 UX, 차트 색상)은 큐레이션에서 제외하고, 백엔드·어드민 패널이 직접 작업 가능한 항목만 추출해 4개 배지로 분류했다.

| 배지 | 의미 | 예시 |
|---|---|---|
| ✅ 구현됨 | 코드엔 이미 있음, UI 노출만 필요 — 원본 지적은 outdated | viewer 권한, LEGAL_THRESHOLDS DB 이관 |
| ⚠️ 일부 | 모델/로직은 있으나 어드민 페이지 미구현 또는 검증 누락 | 코드 그룹 삭제, 위험 유형 코드 노출 |
| 🔧 작업 필요 | 어드민 UX 개선·검증 추가 등 명확한 작업 | 0명 선택 시 버튼 비활성, MAC 형식 검증 |
| ❌ 미구현 | 모델·API·페이지 모두 신규 | 조직 변경 audit 화면, VR 이수 이력 모델 |

이 분류를 통해 **팀 합의가 선행돼야 하는 항목**(enum→DB 이관 정책, VR 영상 저장소 인프라, 작업자 위치 개인정보 보호 정책 등)을 별도로 묶어, "백엔드 작업만으로 해결되는 것"과 "스테이크홀더 결정이 먼저인 것"을 분리했다.

> **[증빙 1: 화면설계서 이슈 분석 — 백엔드/어드민 적용 가능 항목 큐레이션 문서 (배지 4종 분류 + §10 팀 합의 필요 항목)]**

> **[증빙 2: 정의서 우선 원칙 — 피그마와 센서 정의서 충돌 시 정의서를 SoT로 삼는 규칙]**

### 10.4.2. 기능 인벤토리 · 누락 영역 양방향 대조

팀은 4-agent 코드 실사를 통해 어드민 21메뉴(`/admin-panel/`, `IsSuperAdmin` 권한)의 실제 구현 현황을 인벤토리화한 뒤, **엑셀 기능정의서 v7의 26개 어드민 그룹과 양방향으로 대조**했다. 양방향이란 "정의서엔 있는데 인벤토리엔 없는 것"(누락)과 "인벤토리엔 있는데 정의서엔 없는 것"(초과)을 동시에 본다는 뜻이다.

각 누락 영역은 단순 목록이 아니라 **모델·Django Admin·운영자 UI·현재 작동 방식 + 발표 예상 Q&A 답안**까지 정리해, 평가자 질문에 방어 가능한 형태로 만들었다.

| # | 영역 | 판정 | 모델 | Django Admin | 운영자 UI | 비고 |
|---|---|---|---|---|---|---|
| A.1 | 메뉴 관리 | ⚠️ 부분 | ✅ | ✅ | ❌ | UI만 빠짐 |
| A.2 | 공통 코드 | ⚠️ 부분 | ✅ | ✅ | ❌ | UI만 빠짐 |
| A.4 | 설비 관리 | ❌ 미구현 | ✅(고립) | ❌ | ❌ | PowerDevice 종속 — 모델 재설계 선행 |
| A.5 | 위치 노드 | 🔄 흡수 | ✅ | — | 🔄 지도 편집 통합 | **의도된 통합 (강점)** |
| A.9 | 이벤트 이력 | ❌ 미구현 | ✅(EventLog) | ? | ❌ | 시연 후 우선 |
| A.11 | 수집 항목 | ❌ 미구현 | ❌ | ❌ | ❌ | **사양 자체 미정** |

이 대조에서 세 가지 결론을 도출했다.

1. **"기능이 없다"가 아니라 "운영자 노출 단계만 남았다"** — A.1·A.2·A.3·A.6·A.7·A.8 6개 영역은 모델과 Django Admin이 갖춰져 있어 즉시 추가 가능한 상태다. 임계치·위험 기준 같은 안전 직결 영역은 RBAC·변경 이력 체계 정리 후 운영자 UI를 도입하기로 하고, 의도적으로 Django Admin에 위임된 상태임을 명확히 했다.
2. **위치 노드의 지도 편집 통합은 강점** — 위치 노드를 별도 CRUD 페이지로 만들지 않고 지도 편집기(B-6)에서 가스 센서·전력 장치와 함께 드래그·일괄 저장하도록 통합한 것은, 좌표 숫자가 아닌 시각적 맥락에서 작업하게 한 의도된 UX 결정이다.
3. **사양 갱신 권고** — 정의서 v7 이후 신규 구현된 "지도 편집 로그"는 인벤토리 단독 추가 페이지이고, "수집 항목"은 사양 자체가 미정이다. 이 둘은 **사양서 v8로 갱신 권고**해, 무리한 구현보다 사양 결정을 선행하기로 했다.

> **[증빙 3: 엑셀 기능정의서 v7 26개 그룹 ↔ 어드민 21메뉴 양방향 대조표 (A.0 분류 요약)]**

> **[증빙 4: 누락 영역별 모델·Admin·운영자 UI·예상 Q&A 디테일 카드 (A.1~A.11)]**

### 10.4.3. 수정사항 우선순위 트리아지 (60건) 및 BE/FE 분배

화면설계서·인벤토리에서 도출된 수정사항 60건을 **시연 영향도 기준으로 4티어**로 트리아지했다.

| 티어 | 정의 | 건수 |
|---|---|---|
| **P0** | 시연 화면에 노출 → 발표 품질 직접 영향 | 6건 (실작업 5건) |
| **P1** | 시연 전 권장 (시간 남으면) | 10건 |
| **P2** | 시연 후 즉시 (사양 결정 불필요, 코드만) | 17건 |
| **P3** | 사양 결정 선행 (스테이크홀더 협의 후 코드) | 24건 |
| **해소** | PR로 이미 처리됨 + 문서 stale 판명 | 3건 |
| **합계** | | **60건** |

이 트리아지의 핵심은 **코드 grep 후 작업량 재추정으로 P0를 22~36h → 5~10h로 압축**한 것이다. 기존 인프라(`AdminPagination`, `SOURCE_TYPE_LABEL`, `Event.worker` FK, popup/push/sms delivery 모듈, `AlertPolicy.channels`)가 이미 있어, 신규 작성이 아닌 "연결"만 필요한 항목이 대부분이었기 때문이다.

| # | 위치 | 항목 | 영역 | 재추정 |
|---|---|---|---|---|
| 2 | 가스·전력 현황 | 그래프 자동 재구성 (`suggestedMax`→`max` 한 줄) | FE | **10~30분** |
| 3 | 이벤트 현황 | 페이지네이션 (`AdminPagination` 패턴 재활용) | BE+FE | 30분~1h |
| 4 | 이벤트 상세 | 연관 모니터링 sensor 상태 (하드코딩 제거) | BE+FE | 1~2h |
| 6 | 알림 정책 | 채널 라우팅 (`resolve_channels` 정책 분기) | BE | 1~2h |
| 1 | 메인 대시보드 | Chart CSS 가독성 | FE | 2~4h |

또한 **"해소" 3건**을 분리한 것이 트리아지의 정확도를 높였다. "연관 작업자 미연동"으로 보고된 항목은 코드 grep 결과 `Event.worker` FK·`worker_id` 매핑·serializer 노출이 모두 이미 동작 중인 **문서 stale**로 판명돼, 작업 큐에서 제거하고 검증만으로 종료했다.

P3 24건은 **지금 손대지 말 것**으로 명시했다. 회원가입 CRUD 도입 여부, 직위-권한 매핑 정의, 데이터 백업 정책 등은 스테이크홀더 협의가 선행돼야 하므로, 시연 후 사양 회의 1회로 일괄 결정하기로 했다.

작업 영역 분배는 다음과 같이 한 화면에 정리해 팀이 합의했다.

| 영역 | P0(실작업 5건) | P1 | P2 | 합 |
|---|---|---|---|---|
| BE | 2 | 3 | 3 | 8 |
| FE | 1 | 5 | 8 | 14 |
| BE+FE | 2 | 2 | — | 4 |

> **[증빙 5: 수정사항 우선순위 트리아지 표 (P0~P3 + 해소 + TL;DR 작업량 압축 22~36h→5~10h)]**

> **[증빙 6: P0 5건 작업 권장 순서 + BE/FE 분배표]**

### 10.4.4. 단계별 의사결정 주도 — Phase 3 단독 결정문 (30+ 설계 결정)

회의가 어려운 학습용 팀 프로젝트 환경에서, 모델 확장 단계(Phase 3)의 설계 결정 30여 건을 **옵션 / 채택 / 장단점 / 대안** 구조의 단독 결정문으로 고정했다. 각 결정은 채택안만 적는 게 아니라 **선택하지 않은 대안의 장단점까지** 함께 기록해, 후속 팀원이 코드를 보지 않고도 "왜 이렇게 됐는가"를 추적할 수 있게 했다.

결정 영역은 5개 모델 확장(3a~3e)과 7개 횡단 결정으로 나뉜다.

| 영역 | 대표 결정 | 채택 | 핵심 근거 |
|---|---|---|---|
| 3a WorkerPosition.received_node | fastapi 페이로드 갱신 책임 | 본인이 양측 동시 갱신 | schema 불일치 위험 0 |
| 3b SafetyCheckSection | 공장별 vs 전사 | **공장별 (facility FK)** | 권한 격리 일관 |
| 3b Section 삭제 정책 | PROTECT/CASCADE/SET_NULL | **PROTECT** | 데이터 손실 0 |
| 3c Session 식별 키 | (worker,date)/(worker,rev) | **(worker, date, revision)** | 개정 전후 충돌 방지 + 일자 추적 |
| 3c UNIQUE 마이그레이션 | 5단계 vs 단일 | **5단계 분할** | 각 단계 독립 검증·롤백 |
| 3d Event-AlertPolicy FK | CASCADE/SET_NULL/PROTECT | **SET_NULL** | 정책 삭제해도 Event 이력 보존 |
| 3e Notification.event FK | CASCADE → SET_NULL | **SET_NULL + nullable** | 비-Event 알림 모델링 |

설계 결정과 함께 **실행 순서(PR 분할)**도 위험도 기준으로 격리했다.

| PR | 포함 | 위험도 | 격리 사유 |
|---|---|---|---|
| PR1 | 3a (received_node) | 중 | fastapi schema 동시 변경 필요 → 분리 |
| PR2 | 3b+3d+3e (Section·Event·Notification 확장) | 저 | 저위험·독립적 → 함께 진입 |
| PR3 | 3c (Session+Revision+UNIQUE 5단계) | 고 | 다단계 마이그레이션 → 별도 격리 |

횡단 결정에는 마이그레이션 전 `pg_dump` 1회 백업, `RunPython` reverse 코드 필수 + 로컬 reverse 테스트 통과 후 머지, 로컬 DB 복제 dry-run 같은 **안전 절차**까지 포함해, 학습 환경이라도 운영 환경에서 통용되는 마이그레이션 패턴을 그대로 따르도록 했다.

> **[증빙 7: Phase 3 단독 결정문 — 결정 요약 1페이지 (3a~3e + 횡단 A~G)]**

> **[증빙 8: 설계 결정 상세 (옵션/채택/장단점/대안 구조) + PR 분할 최종안]**

### 10.4.5. 개발 프로세스 정립 — 4단계

팀은 모든 기능이 동일한 사고 순서를 거치도록 **4단계 개발 프로세스**를 표준화했다.

```
1) 기능정의서 형태로 1차 작성
   - 기능 목적·사용자 시나리오·예외/에러 처리를 먼저 명문화
   - "이 기능이 왜 있는가"와 "네트워크 오류/데이터 없음" 처리까지 체크

2) 필요한 데이터(스키마) 정의
   - 요청/응답 스키마를 프론트↔백 기준으로 명시
   - 새 모델 필드·인덱싱은 정말 필요할 때만, 마이그레이션 시 팀 공유

3) 데이터 흐름 구조 고려
   - 송수신 각 지점에 logging 부착 (어디서 문제 발생했는지 추적)
   - 동기/비동기 처리 여부 기록
   - View 비대화 → Service 분리 + Serializer 검증 명시

4) 위 내용을 토대로 코딩 시작
   - 완료 기준 체크리스트(테스트 항목) 포함
```

이 프로세스의 핵심은 **2단계(스키마 정의) 전에 전체 모델·ERD를 인지**하도록 강제한 점이다. 예컨대 작업자 현황 패널(MN-04)은 요청 스키마(`facility_id`)와 응답 스키마(`total_workers`, `status_summary`, `current_user`, `is_empty`)를 먼저 확정한 뒤, View → Service → Serializer 흐름으로 분리해 구현했다. 이 4단계는 프로젝트 레이어 규칙(view는 service만 호출, 비즈니스 로직 금지 — 3장 아키텍처 참조)과 그대로 맞물린다.

> **[증빙 9: 개발 진행 방식 4단계 문서 + MN-04 적용 예시 (기능정의 → 스키마 → 데이터흐름 → 코딩)]**

### 10.4.6. 시연 시나리오 A/B/C 정의

시연 품질을 보장하기 위해 **도메인별 시연 동선 3종**을 정의했다. 각 시나리오는 서로 다른 핵심 가치를 보여주도록 설계해, 시연 중 한 도메인의 narrative가 다른 도메인으로 번지지 않게 했다.

| 시나리오 | 도메인 | 핵심 가치 (main course) |
|---|---|---|
| **A** | 가스 | 다변량 IF + ARIMA + CP 3축 advisory, 위험도 격상 모달, cleared_gases 비대칭 처리 |
| **B** | 전력 | 5축 라벨(Threshold/IF/ARIMA/Z/CP) + night_abnormal, AI mute, 데이터 흐름 |
| **C** | 어드민 | **알람 정책 변경 즉시 반영** (AlertPolicy 수정 → 실시간 알람 동작 변화) |

시나리오 분리에는 **narrative 가드**를 함께 정의했다. 위험도 격상 모달은 가스 한정 패턴이므로 전력 시연에 차용하지 않으며, 전력 시연의 main course는 5축 라벨·AI mute·데이터 흐름이다. AI/ML 출처 같은 엔지니어링 디테일은 운영자 멘탈 모델을 단순하게 유지하기 위해 시연 표면이 아닌 엔지니어 채널로 분리했다.

> **[증빙 10: 시연 시나리오 A/B/C 정의 + 도메인별 narrative 가드 (전력=5축/AI mute, 가스=격상모달, 어드민=정책 즉시 반영)]**

---

## 10.5. PM 관리 활동 통합 흐름

위 6개 활동은 독립적이지 않고 **하나의 관리 파이프라인**으로 이어진다.

```
요구사항 4종 (계획서/정의서/피그마/엑셀)
   │  ① 정의서 우선 원칙으로 위계 정리
   ▼
화면설계서 갭 식별 (코드 실사 → ✅⚠️❌🔧 4배지)
   │  ② 엑셀 v7 ↔ 어드민 21메뉴 양방향 대조 (누락 11 + 초과 1)
   ▼
수정사항 60건 도출
   │  ③ P0~P3 트리아지 + grep 재추정 (22~36h→5~10h) + BE/FE 분배
   ▼
P0 5건 시연 전 / P3 24건 사양 회의로 분리
   │  ④ 모델 변경은 Phase 3 단독 결정문 (30+ 결정, PR 3분할)
   ▼
4단계 개발 프로세스 (기능정의→스키마→데이터흐름→코딩)
   │  ⑤ 모든 기능 동일 순서 강제
   ▼
시연 시나리오 A/B/C 검증
   │  ⑥ 도메인별 동선 + narrative 가드
   ▼
시연 (2026-06-14)
```

이 파이프라인의 설계·운영·문서화는 최재용이 PM으로 전 단계를 집필·주도했으며, 각 단계의 산출물(갭 분석·대조표·트리아지·결정문·프로세스·시나리오)이 다음 단계의 입력이 되도록 연결한 것이 diconai 프로젝트 관리의 핵심이다.

> **[증빙 11: PM 관리 파이프라인 6단계 통합도 — 요구사항에서 시연까지의 산출물 연결 흐름]**

---

## 10.6. 이 장의 증빙자료 ⭐⭐⭐⭐⭐

| # | 증빙 항목 | 캡처 대상 |
|---|---|---|
| 1 | 화면설계서 이슈 분석 큐레이션 (배지 4종 + 팀 합의 항목) | [증빙 1] |
| 2 | 정의서 우선 원칙 | [증빙 2] |
| 3 | 엑셀 v7 ↔ 어드민 21메뉴 양방향 대조표 | [증빙 3] |
| 4 | 누락 영역 디테일 카드 (모델·Admin·UI·예상 Q&A) | [증빙 4] |
| 5 | 수정사항 우선순위 트리아지 표 (P0~P3 + 해소) | [증빙 5] |
| 6 | P0 작업 순서 + BE/FE 분배표 | [증빙 6] |
| 7 | Phase 3 단독 결정문 요약 1페이지 | [증빙 7] |
| 8 | 설계 결정 상세 (옵션/장단점/대안) + PR 분할안 | [증빙 8] |
| 9 | 개발 4단계 + MN-04 적용 예시 | [증빙 9] |
| 10 | 시연 시나리오 A/B/C + narrative 가드 | [증빙 10] |
| 11 | PM 관리 파이프라인 통합도 | [증빙 11] |

> 1~4장(개요·팀역할 / 요구사항 / 아키텍처 / DB)에서 정의한 요구사항 위계·레이어 구조·모델 스키마는 본 장의 의사결정 근거이며, 상세는 각 장을 참조한다. 알람 결정 매트릭스와 AI 5축은 각각 6장·7장, 어드민 21메뉴 상세는 8장 참조.

---

# 11장. 트러블슈팅 · 한계 · 향후 계획

### 이 장의 핵심 목적

```
디코나이 운영 과정에서 실제로 발견·진단·해결한 6개 사례를
"문제 / 원인 / 해결 / 효과" 4단으로 정리합니다.

이 장의 가치는 "다 만들었다"가 아니라, 1초 주기 다채널 실시간 시스템에서
필연적으로 드러나는 중복·폭주·false positive·데이터 비대 문제를
팀이 어떻게 데이터·로그·메트릭으로 진단하고, 어디까지 정공법으로 해결하고,
어디부터를 한계로 인정해 다음 단계로 분리했는지를 보여주는 데 있습니다.
```

### 무엇을 수행하는가?

```
실시간 알람·AI·데이터 영속화 3개 축에서 발생한 6개 운영 사례를 다룹니다.

[알람 신뢰성 — fastapi/DRF 결정 경로]
  ① T3 fingerprint dedup        — Celery retry 로 인한 중복 push 차단 (중복 push 0%)
  ② AI vs rule 중복             — fastapi(AI) + DRF(rule) 동시 발화 차단 (ai_fired mute 0%)
  ③ 전력 알람 폭주               — clear 의 device-wide resolve churn → 채널-aware clear
  ④ danger 단일틱 false danger   — 1틱 스파이크/인러시 → 2틱 confirm

[AI 한계 — 모델 특성 구분]
  ⑤ ARIMA(1,1,1) 단발 spike 한계 — "의도된 한계 vs 버그" 명시 + 4축 보완

[데이터 영속화 — 운영 인프라]
  ⑥ SQLite 12GB 폭증            — PG16 전환 + DataRetentionPolicy

이후 "한계(정직)" 표 + "향후 계획(D-day / D+30 / D+90 / 장기)" 로 마무리합니다.
③·④ 는 현재 작업 브랜치(feature/0602_power_alarm_flood)에 반영된 최신 사례입니다.
```

### 왜 필요한가?

```
산업 안전 관제 시스템에서 "알람이 운영자에게 도달했다"는 것만으로는 부족합니다.
같은 사건이 3번 울리거나, AI 와 룰이 동시에 울리거나, 단일 틱 스파이크가 즉시
danger 가 되면 — 운영자는 알람을 신뢰하지 않게 되고 결국 무시합니다. 알람 시스템의
가치는 "발화 여부"가 아니라 "신뢰할 수 있는 발화"에서 나옵니다.

따라서 팀은 다음 4가지 운영 품질 문제를 직접 진단·해결했습니다:

- 중복 제거 (같은 신호가 여러 번 도달하지 않을 것)
- 단일 결정자 (AI 와 룰이 한 채널에서 동시에 울리지 않을 것)
- 폭주 억제 (다채널이 임계 부근을 들락날락해도 event_id 가 churn 하지 않을 것)
- false positive 억제 (1틱 블립/인러시가 즉시 경보가 되지 않을 것)

또한 AI 의 한계(ARIMA 단발 spike)를 "버그"로 오인하지 않고 "모델 특성"으로 구분해
다른 축으로 보완하는 판단, 그리고 데이터 영속화(SQLite→PG16) 인프라 안정화까지
포함해, 이 시스템이 데모용이 아닌 "운영 가능한 시스템"임을 증명합니다.
```

### 어떻게 수행했나?

각 사례를 "문제 → 원인 → 해결 → 효과" 4단으로 정리합니다.

---

#### 사례 ① — T3 fingerprint dedup (Celery retry 중복 push 0%)

| 단계 | 내용 |
|---|---|
| **문제** | 알람 push 경로의 Celery task retry(최대 3회)가 같은 payload 를 최대 3번 Redis Stream(`diconai:ws:alarms`)에 적재. 운영자에게 같은 알람이 2~3번 표시됨. |
| **원인** | choke point 부재. push 진입부에 멱등성(idempotency) 보장이 없어 retry 마다 새 XADD 가 발생. 알람의 "논리적 동일성"을 식별하는 키가 없었음. |
| **해결** | `push_alarm` 진입부에 fingerprint dedup(`alarm:push:dedup:*`, `SET NX EX 30s`) 4분기 도입. 첫 도착자만 Stream 에 적재, 후속 retry 는 silent drop + `alarm_push_dedup_hits_total` Counter 증가. |
| **효과** | 운영 중복 push 0% (Prometheus 카운터로 추적 가능). retry 안전성과 멱등성을 동시에 확보. |

fingerprint 4분기 (알람 성격별로 동일성 정의를 다르게):

```
룰     : event:{event_id}:{risk_level}
AI     : ai:{alarm_type}:{device_id}:{channel}:{rule_level}
정상화 : clear:{alarm_type}:{source_label}
정적 cover: cover:{source}:{source_label}:{risk_level}
```

> 같은 사건은 같은 fingerprint 로 수렴하므로 retry·중복 경로 모두 첫 1건만 통과. 위험 판단·알람 결정 구조 전반은 **6장 참조**.

---

#### 사례 ② — AI vs rule 중복 (ai_fired mute 0%)

| 단계 | 내용 |
|---|---|
| **문제** | 같은 채널에서 AI 알람(fastapi 추론)과 rule 기반 알람(DRF Celery)이 동시 발화. 운영자에게 같은 위험 신호가 2개로 보임. |
| **원인** | fastapi(AI 추론 후 결정)와 DRF Celery(정적 rule task)가 같은 신호에 각자 발화. 두 결정 경로 사이에 sync 가 없었음. |
| **해결** | AI 발화 시 fastapi 가 Redis 에 `ai_fired:{device}:{channel}:{rule_level}` 키(TTL 60s)를 마킹 → DRF Celery rule task 가 `is_ai_mute_active` 가드로 mute. AI 가 잡은 채널은 룰이 침묵. |
| **효과** | AI 발화 중인 채널의 rule 알람 0%. AI 1순위 원칙(AI 가 잡으면 룰은 양보) 확립. AI mute hits 메트릭으로 추적. |

이 사례는 "fastapi 단일 결정자(`decide_alarm` 6매트릭스)" 설계의 일부입니다. AI state 가 INFERRED_NORMAL/FAILED/DISABLED/WARMING_UP 인 경우 정적 임계가 cover 하므로, AI 는 "있으면 좋은 것"이지 "없으면 안 되는 것"이 아니라는 운영 안전망도 함께 보장됩니다. (decide_alarm 매트릭스 전체는 **6장 참조**)

---

#### 사례 ③ — 전력 알람 폭주: clear 의 device-wide resolve churn (현 브랜치)

**발견 경위**: 팀원 피드백 — "전력 DANGER/WARNING 알람이 비정상적으로 폭주한다(가스에선 안 보임). 팝업 '확인' 버튼을 누르면 다음 알람이 0초 만에 울린다." 코드 직접 확인 + 독립 검증으로 단일 뿌리임을 확정.

| 단계 | 내용 |
|---|---|
| **문제** | 전력만 알람이 폭주. 가스에서는 동일 부하에서도 발생하지 않음. 운영자가 팝업을 ack 하자마자 새 팝업이 즉시 등장. |
| **원인** | **clear 처리의 가스/전력 비대칭.** 전력은 `(device, channel)` 단위로 발화하지만 Event 병합은 `(facility, event_type, device)` 단위 — 채널을 무시해 16채널이 디바이스당 Event 하나를 공유. 한 채널이 잠깐 정상 복귀하면 `fire_power_clear_task` 가 디바이스 전체 Event 를 RESOLVE → 다른 채널이 아직 위험해도 닫힘 → 다음 위험이 **새 event_id** 로 생성 → 프론트 dedup(event_id 키)을 통과 → 60초 throttle 무력화 → 폭주. 가스는 `cleared_gases` 로 "모든 가스가 정상일 때만 RESOLVE"하게 이미 막아둔 race 였으나, 전력은 그대로 안고 있었음. |
| **해결** | 전력 clear 를 **채널-aware** 로 전환. `has_other_active_channel(device_id, exclude_channel, channel_count)` 헬퍼로 "다른 채널이 하나라도 WARNING/DANGER 상태인지" 검사 → 마지막 활성 채널이 정상화될 때만 `auto_resolve_active_events` 호출. 다른 채널이 위험하면 `resolved=0` 으로 Event 유지. |
| **효과** | 한 채널 정상복귀가 공유 Event 를 통째 닫는 churn 제거 → event_id 가 안정 유지 → 프론트 60초 dedup·ack store 가 정상 동작 → "ack 하자마자 재발화" 연쇄 차단. 가스가 `cleared_gases` 로 막은 race 의 전력판을 동일 원리로 정합. |

핵심 코드 (`apps/monitoring/services/power_alarm.py`):

```python
def has_other_active_channel(device_id, exclude_channel, channel_count=16) -> bool:
    keys = [_state_key(device_id, ch)
            for ch in range(1, channel_count + 1) if ch != exclude_channel]
    if not keys:
        return False
    states = cache.get_many(keys)
    return any(s in (RiskLevel.WARNING, RiskLevel.DANGER) for s in states.values())
```

```python
# fire_power_clear_task — 게이팅
if has_other_active_channel(device_id, channel, channel_count):
    resolved = 0  # 다른 채널 위험 지속 → Event 유지 (마지막 채널이 닫는다)
else:
    resolved = auto_resolve_active_events(
        event_type_prefix="power", power_device_id=device_id)
```

> 보조로, 팝업 수동 ack 간격을 700ms 로 두고 비프음을 throttle 해 "연쇄 click → 연쇄 비프"의 체감 폭주도 완화했습니다(`alarm-popup.js`).

---

#### 사례 ④ — danger 단일틱 false danger → 2틱 confirm (현 브랜치)

| 단계 | 내용 |
|---|---|
| **문제** | 단일 틱 센서 스파이크(가스 블립) 또는 전력 인러시(inrush, 기동 돌입 전류)가 1틱만 임계를 넘어도 즉시 DANGER 발화 → false danger. 1초 주기 송신에서 우발적 1틱 튐이 곧장 경보가 됨. |
| **원인** | danger 분기가 "현재 틱이 danger 인가"만 평가하고 지속성(persistence)을 보지 않음. 산업 부하의 정상적 transient(모터 기동, 센서 노이즈)를 실재 위험과 구분하지 못함. |
| **해결** | **danger 2틱 confirm** 도입. `confirm_consecutive(count_key, threshold, ttl)` 로 연속 danger 틱을 카운트, `DANGER_CONFIRM_TICKS`(기본 2) 도달 시에만 발화. 위험도가 danger 가 아니게 되면(warning/normal 전이) 카운터 리셋. WARNING 타이머는 3→5초로 함께 조정. 전력은 축별 중복 카운트를 막기 위해 **watt 축에서만** 카운트(current/voltage 는 stale watt 캐시로 조기 발화 가능 → skip). `aggregate` 는 watt 도착 시 3축 최신값을 반영하므로 누락 없음. |
| **효과** | 1틱 블립/인러시가 경보를 만들지 않음. `DANGER_CONFIRM_TICKS=1` 환경변수로 되돌리면 기존 즉시 발화 동작 복원 — 시연 직전 즉시성 우선 시 env 한 줄로 전환. 가스·전력 양쪽 danger 분기에 동일 적용. |

핵심 코드 (`apps/alerts/services/alarm_dedupe.py`):

```python
def confirm_consecutive(count_key, threshold, ttl) -> bool:
    """연속 발생 카운터를 1 증가, threshold 도달 시 True.
    표준 cache.get/set 사용(LocMemCache 테스트 호환). threshold<=1 이면 첫 틱 True."""
    count = (cache.get(count_key) or 0) + 1
    cache.set(count_key, count, ttl)
    return count >= threshold
```

```python
# trigger_power_alarms — DANGER 분기 (watt 축만 카운트)
if axis_name != "watt":
    continue
if not confirm_consecutive(dcount_key, settings.DANGER_CONFIRM_TICKS, _CACHE_TTL):
    continue
```

> **설계 트레이드오프**: 2틱 confirm 은 "false danger 억제 ↑ / 첫 발화 latency ≈송신주기×1틱 ↑"의 교환입니다. 산업 부하의 정상 transient 가 잦은 전력 도메인에서 신뢰도 이득이 latency 비용보다 큽니다. env 토글로 도메인·상황별 재조정 가능.

---

#### 사례 ⑤ — ARIMA(1,1,1) 단발 spike 한계 (의도된 한계 vs 버그 구분)

| 단계 | 내용 |
|---|---|
| **문제** | un-downgrade 검증 중, 8000W(정격 7500W 의 107%) 강제 주입 시 ARIMA `violation=False`. 기대 `(danger, anomaly, True)` vs 실제 `(danger, anomaly, False)`. |
| **원인** | ARIMA(1,1,1)의 **빠른 적응 특성**. `apply(endog=values)` 호출 시 마지막 1~3틱 spike 가 입력에 포함되어 forecast 의 95% 신뢰구간이 spike 근처로 따라감 → actual 이 CI 안에 들어와 violation=False. |
| **해결** | ARIMA 단독으로 단발 spike 를 잡으려 하지 않음. **"의도된 모델 한계 vs 버그"를 명시적으로 구분**하고 4축으로 역할 분담. |
| **효과** | 8000W 케이스에서 threshold=danger ✓ + IF=anomaly ✓ 가 잡아 `combine_risk_3axis(danger, anomaly, False)=danger` ✓ — 시스템 전체는 정확히 작동. ARIMA 가 못 잡아도 다른 축이 cover. |

축별 책임 분담 (어떤 모델도 모든 패턴을 잡지 못함 → 직교 결합):

| 패턴 | 잡는 축 | ARIMA(1,1,1) |
|---|---|---|
| 단발 spike (1~3틱) | IF + Threshold | ❌ (빠른 적응으로 CI 따라감) |
| 점진 trend break | **ARIMA** | ✓ |
| 통계적 튐 (3σ) | Z-score | — |
| 패턴 변화 시점 | Change Point | — |
| seasonal (시각 사이클) | night_abnormal 휴리스틱 | ❌ (non-seasonal) |
| 학습 분포 변화 | 재학습 cadence | — |

> 핵심 교훈: **모델의 강점·한계를 미리 알고 다른 축으로 보완**. ARIMA violation=False 는 버그가 아니라 모델 특성이며, 전력 5축 결합 구조 전체는 **7장 참조**.

---

#### 사례 ⑥ — SQLite 12GB 폭증 → PG16 전환 + DataRetentionPolicy

| 단계 | 내용 |
|---|---|
| **문제** | 더미 3종(가스·전력·위치) 동시 송출 시 `/dashboard/` 알람 누락·응답 멈춤. DB 파일 12GB. Celery `database is locked` 무한 retry, fastapi→drf `action=timeout` 폭주. |
| **원인** | **3겹 직렬 병목.** ① SQLite 다중 writer + `BEGIN DEFERRED` → `SQLITE_BUSY_SNAPSHOT` 즉시 실패(busy_timeout 으로 재시도 안 됨). ② IF 학습용 백필 데이터(373만 행)가 운영 시계열과 같은 `power_data` 테이블에 혼재 → 인덱스 6개 포함 9GB, 단발 INSERT 최대 8초. ③ retention cron(03:00 KST)이 개발 PC 꺼진 시간대라 미발사. |
| **해결** | 1단계(응급): busy_timeout 5→30s + `transaction_mode=IMMEDIATE` + gunicorn `threads=4`. 2단계: 학습 자산 parquet 분리 + 운영 DB truncate + `DataRetentionPolicy`(raw 7~14일 TTL) + retention 스케줄 09:30 KST 이동. 이후 **PG16 전환** 완료. |
| **효과** | DB 11.19GiB → 0.16GiB(99% 절감, 76배). Celery 락 에러 0건, 태스크 처리 5초+ → 10~25ms. INSERT max latency -42%(꼬리 발작 강도 감소). retention 3정책 36.5ms 완료. 현재 PG16 컨테이너로 운영. |

> 진단에서 얻은 운영 원칙 2가지: ① **PRAGMA·기본 설정 확인을 0단계로**(WAL 활성 여부를 모르고 오진한 자기정정 사례). ② **원인과 증폭기는 다르다** — 12GB 자체가 락의 원인이 아니라(원인=다중 writer+DEFERRED), 락 보유 시간을 늘린 증폭기. 슬림화·구조 둘 다 처방. DB 스키마·데이터 수명 정책 전반은 **4장 참조**.

---

#### 11.x [팀원: 가스 AI 담당] 작성 예정

> 본 장은 알람·전력 AI·데이터 영속화 트러블슈팅 위주이며, 아래 가스 도메인 사례는 담당 팀원이 채웁니다.

- 가스 다변량 IF 학습 풀 데이터 누수(9.1%) 정제 — IF v4 재학습 전후 정확도 변화
- 가스 IF feature mismatch (학습/추론 피처 불일치) 진단·교정
- 가스 ARIMA 격하(downgrade) 정책에서의 false positive 패턴
- (해당 시) 가스 시나리오 A 안정화 과정의 트러블슈팅

#### 11.y [팀원: 프론트/대시보드 담당] 작성 예정

> 실시간 대시보드·WebSocket 클라이언트 측 트러블은 담당 팀원이 채웁니다.

- `monitoring-realtime.js` WebSocket 재연결·메시지 유실 사전 버그
- 대시보드 16채널 동시 렌더링 성능 (브라우저 측)
- (해당 시) 차트·패널 렌더링 트러블슈팅

---

### 한계 (정직)

| 한계 | 영향 | 후속 plan |
|---|---|---|
| 16채널 중 활성 4채널만 AI 추론 (ch1 압연기 7.5kW / ch9 메인전력반 15kW 3상 / ch14 공조 5.5kW / ch15 조명 1kW) | 나머지 채널은 정적 임계만 의존 | D+30 — 16채널 확장 |
| SARIMA seasonal 미적용 | 시각 사이클 자동 학습 부재 (night_abnormal 휴리스틱으로 우회) | D+30 — 운영 데이터 1~2주 누적 후 |
| ARIMA (p,d,q)=(1,1,1) 고정 | auto-arima 미적용 — 채널별 최적 order 미탐색 | D+30 — pmdarima auto_arima |
| danger 2틱 confirm latency | 첫 danger 발화가 ≈송신주기×1틱 지연 | env(`DANGER_CONFIRM_TICKS`)로 도메인별 재조정 |
| ARIMA 단발 spike 미포착 | 의도된 한계 — IF+threshold 가 cover | D+30 — multi-step forecast 검토 |
| 실 IoT 게이트웨이 미연동 | dummy 시뮬레이터로 구조 검증 | 장기 — 실 IoT 단계 |
| 가스 AI advisory 운영 (격하 정책) | 가스 ARIMA 는 IF 보조 (un-downgrade 미적용) | 도메인 의존 결정 — 유지 |

> 정직성 원칙: 위 한계는 "못 만든 것"이 아니라 "단계로 분리한 것"입니다. 동작 중인 시스템(현 4채널·5축·채널-aware clear·2틱 confirm)은 시연·운영에 충분하며, 확장은 운영 데이터 누적 후 정당성을 검증해 진행합니다.

### 향후 계획 (D-day / D+30 / D+90 / 장기)

| 단계 | 주요 작업 |
|---|---|
| **D-day (~2026-06-14)** | 시연 안정화 — 추가 모델 변경 금지. 채널-aware clear·2틱 confirm 검증, 알려진 P1·P2 수정만. 필요 시 `DANGER_CONFIRM_TICKS=1` 로 즉시성 복원 옵션 확보 |
| **D+1 ~ D+30 (정확도)** | FFT/ACF 분석 + SARIMA 도입 · IF feature 확장(hour/day_of_week/자기상관) · auto-arima · ARIMA confusion matrix 측정으로 un-downgrade 가중치 검증 |
| **D+30 ~ D+90 (확장성)** | 활성 4채널 → **16채널 확장** · 모델 캐시 LRU cap(N device 메모리 가드) · CUSUM + Change Point 결합 · 디바이스 클러스터링 PoC · 가스 ARIMA MLModel 통합 |
| **장기 (4차 본격)** | **실 IoT 게이트웨이 연동**(dummy → 실 센서) · **TimescaleDB** 전환(PG16 → 시계열 최적화) · 추론 서버 분리(3-tier) · Online ARIMA · 알람 큐 multi-replica XREAD consumer group 정합 |

> 본 시스템은 시연(2026-06-14)으로 끝이 아니라, 검증된 PoC 위에서 4차 R&D 본격 단계(16채널·실 IoT·TimescaleDB)로 이어지는 architecture 검증 단계입니다. 각 한계마다 후속 단계와 진입 조건(운영 데이터 누적량 등)이 명시되어 있습니다.

### 증빙자료 ⭐⭐⭐⭐⭐

- **사례별 Before/After 비교표** (아래)
- `alarm_push_dedup_hits_total` Grafana 카운터 캡처 → `[증빙 1: T3 dedup 차단 건수 추이]`
- AI mute(`is_ai_mute_active`) 차단 카운터 캡처 → `[증빙 2: AI vs rule 중복 차단]`
- 채널-aware clear 전/후 event_id churn 비교 (전력 폭주 → 안정) → `[증빙 3: 폭주 전후 알람 타임라인]`
- danger 2틱 confirm 검증 (1틱 블립 무발화 / 2틱 발화) 로그 → `[증빙 4: DANGER_CONFIRM_TICKS 동작 로그]`
- 8000W 강제 주입 ARIMA violation=False 검증 로그 → `[증빙 5: ARIMA 단발 spike 한계]`
- SQLite 폭증 인시던트 그래프 (12GB → 0.16GB, 76배) → `[증빙 6: DB 슬림화 전후]`
- 향후 계획 4단계 로드맵 다이어그램 → `[증빙 7: D-day/D+30/D+90/장기]`

#### 사례별 Before / After 비교표

| 사례 | Before | After |
|---|---|---|
| ① T3 dedup | Celery retry × 3 → 같은 push 최대 3회 중복 | `NX EX 30s` fingerprint 4분기 → 중복 push 0% |
| ② AI vs rule | 같은 채널 AI + rule 동시 발화 | `ai_fired:*` TTL 60s mute → 중복 0% |
| ③ 전력 폭주 | 한 채널 복귀가 디바이스 Event 통째 RESOLVE → event_id churn → 폭주 | 채널-aware clear(`has_other_active_channel`) → 마지막 채널만 RESOLVE → churn 제거 |
| ④ danger false | 1틱 스파이크/인러시 즉시 DANGER | 2틱 confirm(watt 축 카운트) → 1틱 블립 무발화 |
| ⑤ ARIMA spike | (의도된 한계 — 모델 특성) | 4축 보완으로 시스템 전체 정상 (combined=danger) |
| ⑥ SQLite 폭증 | Raw+학습 혼재 12GB → lock busy, timeout 폭주 | PG16 전환 + DataRetentionPolicy → 0.16GB, 락 0건 |

---

# 12장. 결론

> **담당**: 최재용(초안 작성 예정). 본 장은 프로젝트 성과·기술적 의미·한계·향후 방향을 요약한다. 상세 트러블슈팅·향후 계획은 11장 참조.

### 12.1 [최재용 작성 예정]
- 전체 성과 요약(가스·전력·위치 실시간 + 다축 AI + 알람 단일결정자 + 백오피스 + 10컨테이너 운영)
- 팀이 적용한 의사결정 패턴(PoC→확장 / 도메인 의존 architecture / 정적 안전망 / 운영 데이터 누적 후 검증)
- 4차 R&D 본격 단계 연결(TimescaleDB·16채널·실 IoT)
