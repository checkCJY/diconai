# 코드 리뷰 종합 보고서 — 2026-05-09

> **대상 브랜치**: `feature/0508_refactory` (Phase 1~4 + B 운영 트랙 PR-A~H 누적)
> **작성 목적**: 머지 전 품질·아키텍처·보안 관점 1회 종합 점검
> **리뷰 범위**: drf-server (Django/DRF) + fastapi-server (FastAPI) + 프론트엔드 (templates, static/js)

## 1. 시스템 한눈에 보기

| 서버 | 포트 | 역할 |
|---|---|---|
| `drf-server/` | 8000 | 인증·HTML 렌더링·DB 영속성·REST API·Celery 트리거 |
| `fastapi-server/` | 8001 | IoT 센서 수신·WebSocket 브로드캐스트·DRF 브리지 |

**데이터 흐름 요약**:
```
IoT 센서 ─HTTP/WS→ fastapi-server (검증·임계치) ─HTTP→ drf-server (DB 저장)
                                                       │
                                                       ↓ Celery 태스크
                                  POST /internal/alarms/push/ ←┘
                                       │
                                       ↓ active_alarms 큐
                       fastapi alarm_flush_loop ─WS 브로드캐스트→ 브라우저 (sensor_clients)
```

## 2. 도메인 그룹 인덱스

| # | 도메인 | 핵심 API/흐름 | 파일 |
|---|---|---|---|
| 01 | 인증/인가 | JWT 발급·LoginLog·permission_classes | [01_auth_access.md](01_auth_access.md) |
| 02 | 조직 관리 | 부서·구성원·리더 할당 | [02_organization.md](02_organization.md) |
| 03 | 대시보드/안전 | 메뉴·VR·체크리스트·실시간 패널 | [03_dashboard_safety.md](03_dashboard_safety.md) |
| 04 | 알람/이벤트 | Celery↔FastAPI 브리지·alarm-popup | [04_alerts_events.md](04_alerts_events.md) |
| 05 | 설비/장치 | 시설·가스센서·전력장치·맵에디터 | [05_facilities_devices.md](05_facilities_devices.md) |
| 06 | 모니터링 수집 | gas/power 인입·임계치·CSV | [06_monitoring_ingest.md](06_monitoring_ingest.md) |
| 07 | 지오펜스/포지셔닝 | 지오펜스·작업자 위치 (HTTP+WS) | [07_geofence_positioning.md](07_geofence_positioning.md) |
| 08 | 어드민 패널 공통 | 공유 JS·템플릿 컴포넌트·layout | [08_admin_panel_pages.md](08_admin_panel_pages.md) |
| 09 | 실시간 횡단 | state.py·broadcast loops·동시성 | [09_realtime_websocket.md](09_realtime_websocket.md) |
| 99 | 보안 종합 | OWASP 매핑·인증 매트릭스 | [99_security_summary.md](99_security_summary.md) |

## 3. 핵심 소견 요약

### 01 인증/인가
JWT 인증·LoginLog·잠금 카운터 등 핵심 흐름은 동작하나, **블랙리스트 미설정 + access 토큰 24h**로 탈취 시 30일 노출. `apps/accounts/services/`는 빈 폴더 — view에 인증 로직 인라인. JS의 `_refresh` 동시성 미보호로 다중 401 시 race.

### 02 조직 관리
**629줄 모놀리식 org_views.py**, view에서 직접 ORM 호출, 구성원 일괄 작업에 트랜잭션 부재로 부분 실패 시 데이터 불일치. 사용자 도메인은 SystemLog 누락 (조직 도메인은 잘 적용됨). 100년 뒤 timestamp로 무기한 잠금을 표현하는 hacky 패턴.

### 03 대시보드/안전
**451줄 모놀리식 views.py**에 페이지 뷰 11개 + API 6개 혼재. VR/안전 API가 **AllowAny + 세션 키** — 같은 브라우저에서 다른 사용자 로그인 시 진도가 섞임. 안전확인 진실 원천이 세션과 DB로 이중화 → 사용자 사고 가능. cross-domain 모델 import로 도메인 경계 침범.

### 04 알람/이벤트
**alerts는 selectors/services 분리 모범 사례**. 단, view가 selectors 활용 안 함. `/internal/alarms/push/`가 localhost 검증만으로 충분치 않음 (호스트 내 위변조). `AlarmPayload.extra="allow"`로 미정의 필드 통과. **alarm-ws.js의 키 리네이밍**(risk_level→alarm_level 등)이 contract fragility 핵심.

### 05 설비/장치
**1818줄 분산** (4개 파일, 최대 668줄). selectors/services 폴더 정의되어 있으나 view가 활용 안 함. `/api/{gas-sensors,power-devices}/check-connection/`은 SSRF 가능성. map-editor/save는 트랜잭션 부재로 부분 실패 시 지도 깨짐. 4개 admin 페이지 JS가 90% 동일 → 공유 베이스 부재.

### 06 모니터링 수집
**무인증 ingest 엔드포인트** (의도적, "Phase 5에서 보호 예정" 주석). **fastapi gas_thresholds.py가 정적 전역 dict** — drf의 facility별 임계치(PR-G)와 분기. 같은 측정값이 두 서버에서 다르게 평가됨. `_alarms` 매직 attribute 패턴, raw_payload 대량 저장 비용. CSV export 기간 제한 부재.

### 07 지오펜스/포지셔닝
**positioning은 service 활용 모범**. 단 `print()` 사용으로 컨벤션 위반. `/ws/worker/{user_id}/` 인증 부재 — 임의 user_id로 타인 알람 가로채기 가능. `/ws/position/` IoT 무인증 — 가짜 위치 주입으로 안전 사고 직결. 4개 JS 파일에 지도 렌더링 로직 분산.

### 08 어드민 패널 공통
**ws-client.js는 모범 사례** (캐시·재연결·다중 핸들러). util.js의 `levelLabel` 키 매핑이 백엔드 enum과 불일치 (`caution`/`safe` vs `warning`/`normal`) — silent 깨짐. 5+ admin 페이지가 동일 패턴인데 공유 베이스 부재. SVG 아이콘 인라인. innerHTML 패턴으로 향후 XSS 위험.

### 09 실시간 횡단
**state.py 9개 mutable globals — 다중 워커 시 100% 깨짐**. broadcast의 `level` 필드와 `ai_*` 4개 필드가 `random.random()` 더미 — 운영 페이로드의 신뢰성 침해. `_send_to_all`이 순차 await으로 슬로우 클라이언트 1명이 전체 broadcast 차단. WS contract가 코드로만 표현됨 — 명세 문서 부재.

### 99 보안 종합
**WS 인증 부재가 가장 큰 위험** (3개 채널). JWT 블랙리스트 미설정 + access 24h. localStorage 토큰 보관 + XSS 다층 방어 부재. 무인증 ingest 엔드포인트의 외부 노출 위험. `1주 내 4개 PR (S1~S4)`로 보안 시급 항목 80% 해소 가능 — 99 문서 §8 참조.

## 4. 우선순위 Top 10

각 도메인의 우선순위 [상] 항목을 종합한 Top 10. 보안·신뢰성·정합성·코드 정리 순.

| # | 항목 | 도메인 | 우선순위 | 규모 | 단계 |
|---|---|---|---|---|---|
| 1 | WS 인증 통합 (`/ws/sensors/`, `/ws/worker/{id}/`, `/ws/position/`) | 04 D2 / 07 G1·G2 / 09 I4 | 상 | 중 | 1주 내 |
| 2 | 무인증 ingest 토큰 보호 (`/api/monitoring/{gas,power}/`) | 06 F1 | 상 | 중 | 즉시 |
| 3 | `/internal/alarms/push/` 인증 강화 (localhost + 토큰) | 04 D1 | 상 | 소 | 즉시 |
| 4 | broadcast의 random 더미 분리 (`level`, `ai_*`) — 운영 신뢰성 | 09 I1 | 상 | 중 | 즉시 |
| 5 | JWT 블랙리스트 + ACCESS_TOKEN 단축 + `_refresh` 동시성 | 01 A1·A2·A3 | 상 | 중 | 1주 내 |
| 6 | _send_to_all 병렬화 + per-send timeout (slow client 차단) | 09 I3 | 상 | 소 | 즉시 |
| 7 | facility 별 임계치 fastapi 동기화 (PR-G 미완성) | 06 F3 | 상 | 중 | 1~2주 |
| 8 | 일괄 작업 트랜잭션 (구성원·맵에디터·위치) | 02 B2 / 05 E5 / 07 G5 | 상 | 소 | 즉시 |
| 9 | 사용자 도메인 SystemLog 적용 (감사 트레일) | 02 B3 | 상 | 중 | 1주 내 |
| 10 | check-connection SSRF 차단 | 05 E4 | 상 | 소 | 즉시 |

## 5. 공통 권고사항 (도메인 횡단 패턴)

도메인 횡단으로 반복 등장하는 패턴을 모음 — **단일 PR로 처리하면 효율적**.

### 5.1 컨벤션·코드 품질
- **레이어 경계 위반**: 정의된 selectors/services 활용 안 하고 view에서 직접 ORM (01·02·03·04·05·07·08 모두 해당). selectors/services 활용 정착 PR을 도메인별로 쪼개 진행.
- **모놀리식 view 파일 (200줄+)**:
  - facilities/facility_admin.py 668줄
  - accounts/org_views.py 629줄
  - facilities/gas_sensor_admin.py 485줄
  - facilities/power_device_admin.py 453줄
  - dashboard/views.py 451줄
  - alerts/tasks.py 432줄
  - accounts/auth_views.py 368줄
  - monitoring/gas_data_admin.py 308줄
  - alerts/alarm_record.py 296줄
  - accounts/admin_views.py 276줄
  - monitoring/power_data_admin.py 260줄
  - facilities/map_editor.py 212줄
- **광범위 except Exception**: 거의 모든 도메인. 구체 예외로 변경 + 적어도 logger.exception.
- **함수 안 import**: 03 dashboard/views.py 등. 모듈 상단 또는 selectors 위임.
- **inline_serializer 과다**: 01·03·04·05 등. `apps/<x>/schemas.py` 분리.
- **광범위 print() 사용 검색**: 07 positioning에서 발견. `grep -rn 'print(' drf-server/apps fastapi-server`.

### 5.2 보안
- **WS 인증 통합** (마스터 플랜은 99 §2): 모든 WS endpoint가 `Depends(get_current_user_from_ws_token)`. 한 PR에 묶어 처리.
- **JWT 보안 강화** (01 A1+A2+A3): blacklist + lifetime + 동시성 보호. 한 PR에 묶음.
- **트랜잭션 일관성** (02 B2 + 05 E5 + 07 G5): 일괄 작업에 `@transaction.atomic` 일괄 적용. grep으로 후보 식별 후 한 PR.
- **부분 실패 응답 표준화** (02 B7 + 05 E5 + 07 G4): `{success:[ids], failed:[{id, reason}]}` 응답 패턴.

### 5.3 JS 횡단
- **WSClient `attachToken: true` 일관 적용**: WS 인증 통합과 함께.
- **`shared/admin-list-page.js` 베이스 추출** (08 H2 / 05 E9): 5+ admin 페이지 압축.
- **innerHTML → textContent 패턴 정착** (08 H3): 향후 XSS 자동 방지.
- **levelLabel 정합 또는 dead code 제거** (08 H1): 1줄 변경.
- **응답 봉투 정책 통일** (04 D3): 클라이언트 단일 처리.

### 5.4 진실 원천 (Single Source of Truth)
- **임계치 정책**: drf facility별 vs fastapi 정적 (06 F3) — 한 곳에서.
- **안전확인 상태**: 세션 vs SafetyStatus 모델 (03 C3) — DB가 마스터.
- **검증 정책**: JS vs Python (01 A7) — 한 곳에서 (보류 가능).
- **WS contract**: 코드 vs 명세 (09 I8) — 명세 문서 필요.

## 6. 일정 권고 (PR 묶음)

### 1주 내 — 보안 핵심 묶음 (4개 PR, 99 §8 상세)
- **PR-S1 (1일)**: 즉시 정합·로깅 — print→logger, levelLabel, AlarmPayload, ingest 토큰, alarm-push 토큰
- **PR-S2 (3일)**: JWT 보안 — blacklist + lifetime + _refresh 동시성
- **PR-S3 (5일)**: WS 인증 통합 — websocket/auth.py + 모든 WS + ws-client.js
- **PR-S4 (3일)**: 감사·정합 — 사용자 SystemLog + 일괄 트랜잭션 + VR/안전 IsAuthenticated

### 1~2주 — 신뢰성·정책 통일
- broadcast random 더미 분리 (09 I1) + facility 임계치 동기화 (06 F3)
- _send_to_all 병렬화 (09 I3)
- check-connection SSRF (05 E4) + map-editor 트랜잭션 (05 E5)
- 안전확인 진실 원천 통일 (03 C3)

### 다음 sprint — 아키텍처 정리 (도메인별 PR 쪼개기)
- selectors/services 활용 정착: 01·02·03·05·06 도메인별
- 모놀리식 view 분리: facility_admin → org_views → dashboard → gas/power_admin 순
- shared/admin-list-page.js 베이스 (5+ 페이지 마이그레이션)
- WS contract 명세 문서

### 다음 분기 — 장기 보안·확장
- IoT 장비 인증 절차 (펌웨어 협업)
- 다중 워커 + Redis (트래픽 증가 시점)
- CSP·DOMPurify·SRI XSS 다층 방어
- 의존성 정기 audit 자동화

## 7. 리뷰 방법론

- **표준 템플릿**: 각 도메인 파일은 (1) 범위 (2) 흐름 (3) 백엔드 소견 (4) 프론트엔드 소견 (5) 개선 제안 (6) 구현 추천 순서 6섹션.
- **개선 제안 라벨**: 우선순위 [상/중/하] · 규모 [소/중/대].
- **각 제안의 4가지 정보**: 왜 필요? · 장점 · 단점 · 변경 위치.
- **구현 추천 순서**: 1단계(즉시) ~ 4~5단계(여유 시) + 초보자 주의사항.
- **보안 이슈**: 도메인 파일에는 짧게 표시, 상세 분석은 [99_security_summary.md](99_security_summary.md)에 종합.
- **JS 연결**: 백엔드 API와의 contract, WS 메시지 매칭, 공유 유틸 재사용 관점 포함.

## 8. 다음 단계 — 사용자 선택

이 보고서를 바탕으로 다음 중 선택:

1. **Top 10 우선 처리**: 위 §4의 1~10번을 순차로 PR로 처리.
2. **PR-S1~S4 보안 묶음 진행**: 99 §8의 1주 일정.
3. **특정 도메인 깊이 있게**: 한 도메인을 잡고 그 안의 모든 [상] 항목 처리.
4. **추가 리뷰 영역**: 이 리뷰가 다루지 않은 영역 (예: DB 스키마·인덱스, 의존성 audit, 성능 프로파일, 테스트 커버리지) 추가 진행.

각 도메인 파일의 §6 "구현 추천 순서"가 단계별 작업 흐름을 제시. 선택 후 해당 PR부터 시작 가능.
