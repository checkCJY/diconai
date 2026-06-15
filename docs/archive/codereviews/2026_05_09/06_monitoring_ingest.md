# 06. 모니터링·데이터 수집 (Gas/Power Ingest · Thresholds · Admin Browse)

## 1. 범위

### 1.1 API 엔드포인트
| 서버 | URL | 메서드 | 뷰/핸들러 | 권한 |
|---|---|---|---|---|
| **fastapi** | `/api/sensors/info` | POST | receive_device_info | (무인증) |
| **fastapi** | `/api/sensors/gas` | POST | receive_gas_data | (무인증) |
| **fastapi** | `/api/power/onoff` | POST | recv_onoff | (무인증) |
| **fastapi** | `/api/power/current` | POST | recv_current | (무인증) |
| **fastapi** | `/api/power/voltage` | POST | recv_voltage | (무인증) |
| **fastapi** | `/api/power/watt` | POST | recv_watt | (무인증) |
| **drf** | `/api/monitoring/gas/` | POST | GasDataCreateView | **무인증 (의도적)** |
| **drf** | `/api/monitoring/power/data/` | POST | PowerDataBulkIngestView | **무인증 (의도적)** |
| **drf** | `/api/monitoring/power/event/` | POST | PowerEventIngestView | **무인증 (의도적)** |
| **drf** | `/api/monitoring/power/thresholds/` | GET, POST | PowerThresholdView | (확인 필요) |
| **drf** | `/api/admin/gas-data/` | GET | GasDataAdminListView | IsSuperAdmin |
| **drf** | `/api/admin/gas-data/export/` | GET | GasDataAdminExportView | IsSuperAdmin |
| **drf** | `/api/admin/gas-data/sensors/` | GET | GasDataAdminSensorListView | IsSuperAdmin |
| **drf** | `/api/admin/power-data/` | GET | PowerDataAdminListView | IsSuperAdmin |
| **drf** | `/api/admin/power-data/export/` | GET | PowerDataAdminExportView | IsSuperAdmin |
| **drf** | `/api/admin/power-data/devices/` | GET | PowerDataAdminDeviceListView | IsSuperAdmin |

### 1.2 백엔드 파일
- **drf 인입**:
  - [drf-server/apps/monitoring/views/gas_data.py](../../../../drf-server/apps/monitoring/views/gas_data.py) — 100줄, 무인증 ingest
  - power 인입 view들 (PowerDataBulkIngestView, PowerEventIngestView)
- **drf 어드민 조회**:
  - [drf-server/apps/monitoring/views/gas_data_admin.py](../../../../drf-server/apps/monitoring/views/gas_data_admin.py) — 308줄
  - [drf-server/apps/monitoring/views/power_data_admin.py](../../../../drf-server/apps/monitoring/views/power_data_admin.py) — 260줄
- **drf 모델/임계치**:
  - [drf-server/apps/monitoring/models/](../../../../drf-server/apps/monitoring/models/) — GasData, PowerData, PowerEvent
  - [drf-server/apps/facilities/models/thresholds.py](../../../../drf-server/apps/facilities/models/thresholds.py) — Facility별 임계치 (PR-G 추가)
- **fastapi 인입**:
  - [fastapi-server/gas/routers/gas_router.py](../../../../fastapi-server/gas/routers/gas_router.py) — 57줄
  - [fastapi-server/gas/services/gas_service.py](../../../../fastapi-server/gas/services/gas_service.py) — 108줄
  - [fastapi-server/gas/schemas/gas.py](../../../../fastapi-server/gas/schemas/gas.py) — Pydantic 검증
  - [fastapi-server/core/gas_thresholds.py](../../../../fastapi-server/core/gas_thresholds.py) — 86줄, **전역 정적 dict**
  - power/* (router·service)

### 1.3 프론트엔드 파일
- 실시간 모니터링:
  - [drf-server/static/js/detail/gas_monitoring.js](../../../../drf-server/static/js/detail/gas_monitoring.js)
  - [drf-server/static/js/detail/websocket_gas.js](../../../../drf-server/static/js/detail/websocket_gas.js)
  - [drf-server/static/js/detail/power_system.js](../../../../drf-server/static/js/detail/power_system.js)
  - [drf-server/static/js/detail/websocket_power.js](../../../../drf-server/static/js/detail/websocket_power.js)
- 어드민 데이터 조회:
  - [drf-server/static/js/admin/gas/gas_data.js](../../../../drf-server/static/js/admin/gas/gas_data.js)
  - [drf-server/static/js/admin/power/power_data.js](../../../../drf-server/static/js/admin/power/power_data.js)
- 템플릿:
  - [drf-server/templates/snb_details/monitoring_{gas,power,realtime}.html](../../../../drf-server/templates/snb_details/)
  - [drf-server/templates/admin_panel/data/{gas,power}_data.html](../../../../drf-server/templates/admin_panel/data/)

## 2. 기능 흐름

### 2.1 가스 센서 1초 인입 (핵심 데이터 흐름)
```
1. IoT 가스 센서 → POST http://fastapi:8001/api/sensors/gas
   payload: {device_id, timestamp, o2, co, co2, h2s, lel, no2, so2, o3, nh3, voc, max_risk_level, ...}
2. gas_router.receive_gas_data:
   ├─ Pydantic GasDataPayload 검증 (타입·범위)
   └─ process_gas_data(payload) 호출
3. gas_service.process_gas_data:
   ├─ calculate_individual_risks(gas_values) — 9개 가스(lel 제외) 위험도 계산
   ├─ POST http://drf:8000/api/monitoring/gas/ {device_id, measured_at, 9 gases, 9 risks, raw_payload}
   │   ├─ DRF GasDataCreateSerializer.is_valid + save()
   │   ├─ post_save signal 또는 service에서 Celery 태스크 트리거
   │   └─ DRF 응답 {id, received, alarms[]}
   ├─ 통신 실패 → HTTPException 503/502/404 (센서 장비에 응답)
   └─ 성공 시 latest_gas_snapshot.update(gas_snapshot) — 공유 상태 직접 갱신
4. fastapi broadcast_loop (5초) 또는 alarm_flush_loop (즉시):
   └─ /ws/sensors/ 클라이언트(브라우저)에 페이로드 broadcast
5. 브라우저 websocket_gas.js / dashboard/websocket.js:
   ├─ data.o2, data.co, ... 측정값 업데이트
   └─ 게이지·차트 렌더
```

### 2.2 전력 4종 인입 (onoff/current/voltage/watt)
```
1. IoT 전력 모듈 → POST /api/power/{onoff|current|voltage|watt} (별도 엔드포인트)
   payload: 16채널 배열
2. power_service.update_power_state(type, channels, measured_at):
   └─ power_latest 공유 상태 갱신 (16채널 × 4 데이터 = 64 슬롯)
3. BackgroundTask로 DRF에 비동기 저장:
   - watt → /api/monitoring/power/data/ + 임계치 초과 판정 → /event/ 저장
   - onoff → /api/monitoring/power/event/ (스냅샷)
4. broadcast 시 build_equipment()가 power_latest 읽어 equipment[] 조립
```

### 2.3 어드민 데이터 조회 (시계열 페이지네이션 + CSV 내보내기)
```
1. /admin-panel/data/gas/ → admin/gas/gas_data.js
2. GET /api/admin/gas-data/?sensor=X&from=Y&to=Z&page=1&page_size=50
   ├─ GasDataAdminListView.get
   ├─ GasData.objects.filter(...) + select_related("sensor")
   └─ 페이지네이션 + 직렬화
3. 필터 파라미터로 GET /api/admin/gas-data/export/ → CSV 응답 (Content-Disposition: attachment)
4. /api/admin/gas-data/sensors/ → 센서 드롭다운 옵션
```

## 3. 백엔드 소견

### 3.1 일반 코드 리뷰
- **[중] gas_thresholds.py가 전역 정적 dict**
  [gas_thresholds.py:14-25](../../../../fastapi-server/core/gas_thresholds.py#L14-L25) `GAS_THRESHOLDS`가 모듈 상수. PR-G에서 facility별 정책(`gas_facility_default`)을 도입했으나 **fastapi 측은 여전히 단일 값 사용**. drf의 facility별 정책과 fastapi의 정적 정책이 분기되면 같은 측정값이 두 서버에서 다르게 평가됨. fastapi가 facility별 임계치를 DRF에서 동기 fetch하거나 Redis 캐시하는 패턴 필요.
- **[중] gas_service의 `gas_data._alarms` 매직 어트리뷰트**
  [gas_data.py:95](../../../../drf-server/apps/monitoring/views/gas_data.py#L95) `getattr(gas_data, "_alarms", [])`. `_alarms`는 GasData 모델 필드 아닌 **GasDataCreateSerializer.save()가 동적으로 부착**하는 attr로 보임. 코드 흐름이 마법적이라 디버깅 어려움. `serializer.save()`가 tuple `(gas_data, alarms)` 반환 또는 service가 dict 반환 권장.
- **[중] raw_payload 저장 비용**
  fastapi가 DRF에 보낼 때 `raw_payload: payload.model_dump(mode="json")` 동봉 — 모든 GasData row가 원본 JSON을 1조각씩 더 보관. 1초 1행, 9~10필드면 한 row당 ~500바이트 추가 → 1년 운영 시 GB 급. 정상적으로 검증된 후엔 raw_payload 보관 정책 검토(retention 30일?).
- **[하] gas_router.py 짧지만 power_router는 본문 미확인**
  power 측은 4개 엔드포인트로 분산. 채널 데이터를 stream별로 분리한 게 IoT 측 요구라면 OK. service에서 일관 처리 패턴 확인 필요.
- **[하] DRF 통신 에러 코드 매핑이 service에**
  [gas_service.py:71-81](../../../../fastapi-server/gas/services/gas_service.py#L71-L81) `if exc.status is None: 503; if 404; else 502`. 같은 패턴이 power/positioning service에도 있을 가능성 — `services/drf_client.py::raise_drf_error_as_http(exc)` 헬퍼로 중복 제거.

### 3.2 아키텍처/레이어
- **[참고] gas/power 도메인 분리 (fastapi side)**
  fastapi-server/gas/, power/ 디렉토리로 분리되어 있음. router·service·schemas 구성도 잘 되어 있음. **drf 측보다 fastapi 측이 더 깔끔**.
- **[중] drf 인입 view와 어드민 view가 같은 monitoring 앱**
  GasDataCreateView (서버 간 ingest)와 GasDataAdminListView (관리자 조회)는 권한·트래픽 패턴·SLA가 완전히 다름. 같은 앱에 있는 건 OK이나 view 분리(`views/ingest/`, `views/admin/`)는 필요.
- **[중] threshold 정책의 두 출처**
  - DRF 측: facilities/models/thresholds.py (facility별, PR-G)
  - fastapi 측: core/gas_thresholds.py (정적 전역)
  → 진실 원천 단일화 필요. **DRF가 마스터, fastapi는 동기화** 패턴 권장.

### 3.3 보안 관점 (요약)
- **[상] 무인증 ingest 엔드포인트의 외부 노출 위험**
  [GasDataCreateView:23-24](../../../../drf-server/apps/monitoring/views/gas_data.py#L23-L24) `authentication_classes = []`. 의도(서버 간)는 명확하고 주석에도 "Phase 5에서 보호 예정"이라 명시. 그러나 **현재 운영 중이라면** reverse proxy 차단·내부 네트워크 격리·서비스 토큰 중 1개라도 즉시 시급. 외부에 노출 시 임의 측정값 위변조 → 알람 폭주 또는 위험 무시 가능.
- **[상] fastapi → drf 호출에는 토큰이 있으나, drf → fastapi의 알람 push에는 토큰 없음 (04에서 다룸)**
- **[중] CSV export 파라미터 검증**
  GET /api/admin/{gas,power}-data/export/는 from/to 등 파라미터에 대량 데이터 추출 가능. 기간 제한·rate limit 없으면 DoS 또는 정보 추출 위험. 1년 치 일괄 추출 가능 여부 확인 필요.
- **[중] device_id 위변조**
  현재 fastapi가 받은 device_id를 그대로 DRF에 전달. **장비 인증 부재** → 임의 device_id로 DRF에 데이터 주입 가능. `/api/sensors/info` 엔드포인트가 "추후 장비 등록·인증 절차 추가 예정"이라 명시 — 시급.

## 4. 프론트엔드(JS/HTML) 소견

### 4.1 백엔드 contract 정합성
- **[상] 페이로드 키 정합성 — gas/power 다수 키**
  fastapi가 broadcast하는 키:
  - gas: o2, co, co2, h2s, lel, no2, so2, o3, nh3, voc + 각 *_risk
  - power: equipment[] (16채널), total_power_kw
  브라우저 websocket_gas.js / websocket_power.js / dashboard/websocket.js가 이 키들을 직접 참조. 한 키 rename 시 silent 누락. **단위 테스트 + TypeScript-like 스키마 검증** 권장 (또는 09에서 종합).
- **[중] 임계치 라벨링 매핑**
  JS에서 `*_risk` 값을 'normal'/'warning'/'danger'로 매핑해 색상 적용. 백엔드의 enum 값과 정확히 일치해야 함. evaluate_single_gas의 반환값과 JS의 case 분기가 어긋나면 silent 노멀 표시.

### 4.2 차트·게이지 렌더링
- **[중] 1초 broadcast로 차트 매번 redraw**
  websocket_gas.js가 매 메시지마다 차트 업데이트하면 1초마다 reflow. 부드러운 스트림 차트 (예: ring buffer + canvas batch)로 최적화 필요. 사용자 PC 성능 낮으면 화면 덜덜.
- **[하] 게이지/차트 라이브러리 의존**
  charts.js가 어떤 라이브러리(Chart.js? D3?) 쓰는지 확인 필요. 의존 라이브러리 버전 고정·번들 크기 확인.

### 4.3 어드민 데이터 조회 UX
- **[중] CSV export 큰 데이터 시 브라우저 freeze**
  서버가 1년 데이터 CSV로 반환하면 브라우저 다운로드는 OK이나 **메모리에 buffering된다면** 메모리 폭주. StreamingHttpResponse(서버) + 다운로드 progress(클라이언트) 권장.

## 5. 개선 제안

### F1. 인입 엔드포인트 보호 (Phase 5 즉시 진행) [상 · 중]
- **왜 필요?**: 무인증 ingest는 임의 위변조 가능. 알람 시스템 자체를 무력화할 수 있음.
- **장점**: 위변조·DoS·내부 네트워크 침투 차단.
- **단점**: fastapi 측 호출 코드에 토큰 헤더 추가 필요 (1줄).
- **변경 위치**:
  - [GasDataCreateView, PowerDataBulkIngestView, PowerEventIngestView](../../../../drf-server/apps/monitoring/views/gas_data.py#L23) `authentication_classes = [ServiceTokenAuthentication]` 도입.
  - [apps/core/auth.py](../../../../drf-server/apps/core/) 또는 별도 — `Authorization: Bearer <DRF_SERVICE_TOKEN>` 검증.
  - fastapi `services/drf_client.py`는 이미 토큰을 보내고 있으니 DRF 측만 검증 추가하면 됨.

### F2. 장비 인증·등록 절차 (장기) [상 · 대]
- **왜 필요?**: 임의 device_id로 측정값 주입 가능. IoT 장비 → 시스템 신뢰 경계 부재.
- **장점**: 장비별 식별·취소 가능 / 데이터 위변조 차단.
- **단점**: 펌웨어·하드웨어 협업 필요. 큰 작업.
- **변경 위치**: `/api/sensors/info` 엔드포인트를 등록 절차로 확장. 장비별 secret/cert 관리. 별도 PR.

### F3. fastapi의 facility별 임계치 동기화 [상 · 중]
- **왜 필요?**: drf의 facility별 임계치(PR-G)와 fastapi의 정적 임계치가 분기. 같은 측정값이 다르게 평가됨.
- **장점**: 진실 원천 단일화 / 정책 변경 1곳.
- **단점**: fastapi가 DRF API 의존 → 시작 시 fetch + 주기적 refresh 또는 캐시 무효화 신호 필요.
- **변경 위치**: [core/gas_thresholds.py](../../../../fastapi-server/core/gas_thresholds.py) — `GAS_THRESHOLDS = {}` (캐시), 시작 시 `GET /api/admin/threshold-policies/`로 로드, 변경 시 SSE/Redis 또는 폴링.

### F4. CSV export 보호 [중 · 소]
- **왜 필요?**: 무제한 기간 export는 DoS·정보 추출 위험.
- **장점**: 시스템 안정성 / 데이터 보호.
- **단점**: 큰 데이터 운영 보고가 필요한 경우 별도 절차 필요.
- **변경 위치**: [GasDataAdminExportView, PowerDataAdminExportView](../../../../drf-server/apps/monitoring/views/gas_data_admin.py) — 최대 기간 90일 검증 + StreamingHttpResponse + rate limit (django-ratelimit).

### F5. raw_payload 보존 정책 [중 · 중]
- **왜 필요?**: 매 row 500바이트 추가 → 1년 GB. 디버깅 외 가치 낮음.
- **장점**: 저장 비용 절감.
- **단점**: 디버깅 시 원본 추적 불가.
- **변경 위치**: GasData 모델에 retention 설정 (예: 30일 후 raw_payload=None로 마스킹). 또는 raw_payload는 별도 archive 테이블/S3.

### F6. `_alarms` 매직 어트리뷰트 제거 [중 · 소]
- **왜 필요?**: serializer.save()가 모델에 동적 attr 붙이는 패턴은 디버깅·테스트 어려움.
- **장점**: 흐름 명시 / 타입 힌트 가능.
- **단점**: 호출 시그니처 변경 (사용처 1곳).
- **변경 위치**: [GasDataCreateSerializer.save](../../../../drf-server/apps/monitoring/serializers/) → tuple 반환 또는 service 호출로 분리.

### F7. ingest vs admin view 폴더 분리 [중 · 소]
- **왜 필요?**: 권한·트래픽·SLA가 다른 view가 같은 폴더에 있어 한꺼번에 import.
- **변경 위치**: [apps/monitoring/views/{ingest,admin}/](../../../../drf-server/apps/monitoring/views/) 분리.

### F8. drf_client 에러 매핑 헬퍼 [하 · 소]
- **왜 필요?**: 503/502/404 매핑이 모든 service에 중복.
- **변경 위치**: [services/drf_client.py](../../../../fastapi-server/services/drf_client.py)에 `raise_as_http(exc)` 헬퍼.

### F9. 차트 1초 redraw 최적화 [하 · 중]
- **왜 필요?**: 1초 redraw는 모바일/저성능 PC에서 끊김 발생 가능.
- **장점**: 부드러운 UX / CPU 사용률 절감.
- **단점**: 라이브러리에 따라 batch update 패턴 학습 필요.
- **변경 위치**: [websocket_gas.js, websocket_power.js](../../../../drf-server/static/js/detail/) — 최근 N개만 ring buffer + requestAnimationFrame.

### F10. CSV 다운로드 streaming + progress [하 · 중]
- **왜 필요?**: 큰 데이터 추출 시 브라우저 freeze 방지.
- **변경 위치**: 서버 StreamingHttpResponse, JS는 `fetch` + `ReadableStream`으로 progress.

## 6. 구현 추천 순서

### 1단계 — 보안 시급 (즉시) ⚡
- **F1** ingest 토큰 보호 (Phase 5 명시 — 시작 시점)
- **F4** CSV export 기간 제한·rate limit
- **이유**: 외부 노출 위험·DoS 직접적. 변경 작은데 효과 큼. F1은 `Phase 5에서 추가 예정` 주석이 있으니 정확히 그 작업.

### 2단계 — 정책 단일화 (1~2주) 🔄
- **F3** fastapi facility별 임계치 동기화
- **F6** _alarms 매직 어트리뷰트 제거 (작은 변경)
- **이유**: PR-G가 도입한 facility 정책이 절반만 적용된 상태 — 완성 필요.

### 3단계 — 장비 신뢰성 (장기) 🔐
- **F2** 장비 등록·인증 (펌웨어 협업 필요, 별도 PR/sprint)
- **F5** raw_payload 보존 정책
- **이유**: 큰 작업이지만 보안·저장소 비용 모두 영향.

### 4단계 — 코드 정리 (여유 시) 🧹
- **F7** ingest/admin view 분리
- **F8** drf_client 에러 매핑 헬퍼

### 5단계 — UX 최적화 (여유 시) ✨
- **F9** 차트 redraw 최적화
- **F10** CSV streaming

### ⚠️ 주의사항 (초보자용)
- **F1 토큰 검증 추가 시 fastapi service 토큰 일치 확인**: `DRF_SERVICE_TOKEN` 환경변수가 fastapi/drf 양쪽에 동일한 값으로 설정되어야 함. 배포 시 둘 다 동시 변경 필요(롤링 배포 시 잠시 호환 양쪽 허용).
- **F3 facility별 임계치는 캐시 무효화 정책이 핵심**: 관리자가 임계치 변경 후 fastapi 측이 5분 동안 옛 값 사용한다면 알람이 잘못 발생/누락 가능. 변경 즉시 반영 메커니즘 필요(예: DRF가 fastapi에 invalidate 신호).
- **F4 CSV 기간 제한은 운영자에게 사전 공지**: 90일로 제한하면 분기/연간 보고서 절차가 깨질 수 있음. 별도 비동기 export 절차(이메일 발송 등) 도입 검토.
- **F2는 펌웨어 협업이라 큰 작업**: 팀 내부 펌웨어 담당자와 일정 합의 필요. 단계적으로 (1) 장비 등록 → (2) 등록 안 된 장비 데이터 거부 → (3) 인증서/secret 도입.
