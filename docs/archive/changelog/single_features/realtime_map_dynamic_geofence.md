# 변경 기록서 — 실시간 모니터링 지도 동적 지오펜스 + fit 개선

> 작성일: 2026-05-06
> 브랜치: feature/project_4_refactoring
> 커밋: 4248d8c422ce62fafa12e617473e60c903465625
> 작업 종류: fix + refactor
> 하위 호환성: **non-breaking** — 외부 API/응답/WS 페이로드 형식 변경 없음. 프론트 동작·시각 표현만 변경. 어드민 사이드바 중복 링크 1개 제거(실사용 없음).

---

## 1. 변경 개요

- **목적(Why):** 메인 대쉬보드 / 실시간 모니터링 페이지(`/dashboard/`, `/dashboard/monitoring/realtime/`)의 Leaflet 지도에서 (1) 컨테이너 비율 차이로 좌우 여백이 크게 비거나 SVG 상단이 잘려 보이는 fit 문제, (2) 지오펜스 폴리곤 색상이 어드민 베이스라인 고정이라 센서가 위험을 감지해도 영역 색이 안 바뀌는 부조화, (3) 가스 센서·전력 장치 마커가 WS 위험도 데이터를 받아도 지도 위에선 항상 초록색으로 고정되는 문제, (4) 작업자 마커 색이 어드민 베이스라인을 따라 영역의 실제 동적 위험도와 어긋나는 문제를 한 번에 해결.
- **결과(What):** (1) `MapPanel.recenter()` 헬퍼 + `zoomSnap:0` + `setMaxBounds`로 4개 콜사이트의 fitBounds 호출을 통일하고 fit 후 minZoom 잠금. (2) 데이터 흐름을 **센서/장치 → 지오펜스** 단방향으로 정립 — `_applyDeviceRiskToGeofences()`가 톨러런스 12 SVG 단위 안의 장치 최댓값 위험도로 폴리곤을 동적 재색상. 빈 지오펜스는 어드민 베이스라인 유지. (3) `updateGasSensorFromWS`는 9가스 `*_risk` 필드 스캔으로, `updatePowerDevicesFromWS`는 신규 추가로 각각 마커 아이콘 갱신. (4) 작업자 색상/상태가 layer에 캐싱된 `_currentRiskLevel`(동적 effective risk)을 우선 참조해 폴리곤 색과 일치.
- **영향 범위(Where):** 프론트엔드만 — `drf-server/static/js/dashboard/...`, `drf-server/static/js/detail/map_detail.js`, 관련 템플릿. drf-server 백엔드 / fastapi-server / DB / WS 페이로드 스키마 변경 없음.

## 2. Before / After 비교

| 구분 | Before | After |
|---|---|---|
| 지도 fit 호출 | `MapPanel.map.fitBounds([[0,0],[600,1300]])` 인라인 4곳에서 중복 + 패딩 없음 | `MapPanel.recenter()` 1개 헬퍼로 통일. 내부에서 `SVG_BOUNDS` 상수 + `FIT_PADDING:[20,20]` 적용 |
| Leaflet 옵션 | `minZoom:-2, maxZoom:2, zoomSnap:기본(1)` — 컨테이너 < SVG일 때 fit 줌이 정수로 스냅돼 과도 축소 / 빈 여백 | `minZoom:-4, maxZoom:2, zoomSnap:0, maxBoundsViscosity:1.0`. 부팅 시 `recenter()` 후 `setMinZoom(getZoom())` + `setMaxBounds(SVG_BOUNDS)`로 패닝/줌 잠금 |
| 지오펜스 색상 | 어드민이 설정한 `risk_level` 베이스라인 색으로 **고정** | 내부 장치(센서/전력) 최댓값 위험도로 **동적**. 비어있으면 베이스라인 유지 |
| 가스 마커 색상 | `wsData.level === '위험'` 체크로만 갱신 — 페이로드에 `level` 필드 없음 → **항상 초록색** | 9가스 `*_risk` 필드 스캔으로 최댓값 위험도 산출 → 모든 가스 마커 갱신 |
| 전력 마커 색상 | 마커 저장 자체가 없음(`L.marker(...).addTo(...)` 직후 참조 손실) → WS 갱신 경로 부재 | `this.powerMarkers[code]` 저장 + `updatePowerDevicesFromWS(equipment)` 신규: 이름 매칭(개별 위험도) 또는 전체 최댓값 폴백 |
| 작업자 마커 색상 | `ZONE_COLOR[inGeofence.risk_level]` (어드민 베이스라인) — 폴리곤 동적 색과 부조화 | `layer._currentRiskLevel`(동적 effective risk) 우선, 없으면 베이스라인 폴백 — 폴리곤 색과 일치 |
| `_pointInPolygon` | Ray Casting 단일 — 경계선 위 점은 부동소수점 흔들림 | `tolerance` 옵션 인자 추가(기본 0). `tolerance>0`이면 변까지 거리 ≤ tolerance도 inside. 작업자 호출은 strict(0) 유지, 지오펜스 ↔ 장치 매칭은 12 SVG 단위 |
| 어드민 사이드바 "데이터" 링크 | `<a href="#">데이터</a>` 자리표시(클릭 시 동작 없음) + 그 아래 "가스 데이터"/"전력 데이터" 실제 링크 중복 | 자리표시 제거. 실제 링크 2개만 노출 |

### 코드 차이 핵심

```js
// Before — map-panel.js init()
this.map = L.map('map', {
  crs: L.CRS.Simple, minZoom: -2, maxZoom: 2,
  zoomControl: false, dragging: true,
  scrollWheelZoom: true, doubleClickZoom: false, touchZoom: false,
});
const bounds = [[0, 0], [600, 1300]];
if (mapUrl) L.imageOverlay(mapUrl, bounds).addTo(this.map);
this.map.fitBounds(bounds);

// After
this.map = L.map('map', {
  crs: L.CRS.Simple, minZoom: -4, maxZoom: 2,
  zoomControl: false, dragging: true,
  scrollWheelZoom: true, doubleClickZoom: false, touchZoom: false,
  maxBoundsViscosity: 1.0, zoomSnap: 0,
});
if (mapUrl) L.imageOverlay(mapUrl, this.SVG_BOUNDS).addTo(this.map);
this.recenter();                              // fitBounds + 20px 패딩
this.map.setMinZoom(this.map.getZoom());      // fit 줌을 minZoom으로 잠금
this.map.setMaxBounds(this.SVG_BOUNDS);       // 패닝 영역 SVG 안으로 제한
```

```js
// Before — updateGasSensorFromWS: 'level' 필드는 페이로드에 없음 → 영원히 0
const level = wsData.level === '위험' ? 2 : 0;

// After — 페이로드 실제 구조 활용 (co_risk, h2s_risk, ...)
let worstLevel = 0;
Object.keys(wsData).forEach(k => {
  if (!k.endsWith('_risk')) return;
  const r = wsData[k];
  if (r === 'danger')       worstLevel = Math.max(worstLevel, 2);
  else if (r === 'warning') worstLevel = Math.max(worstLevel, 1);
});
```

```js
// Before — 작업자 색상: 베이스라인 고정
const newColor = inGeofence
  ? (this.ZONE_COLOR[inGeofence.risk_level] || '#f85149')
  : '#58a6ff';

// After — 폴리곤에 캐싱된 동적 effective risk를 우선 사용
const layer = inGeofence ? this._geofenceLayers[inGeofence.id] : null;
const effectiveRisk = layer?._currentRiskLevel || inGeofence?.risk_level || 'normal';
const newColor = inGeofence
  ? (this.ZONE_COLOR[effectiveRisk] || '#f85149')
  : '#58a6ff';
```

## 3. 변경 파일 목록

### 신규
해당 없음 — 모두 기존 파일 수정.

### 수정
| 파일 | 변경 요약 |
|---|---|
| `drf-server/static/js/dashboard/panels/map-panel.js` | (1) `SVG_BOUNDS`/`FIT_PADDING`/`GEOFENCE_TOLERANCE` 상수 + `recenter()` / `_distanceToSegment()` / `_applyDeviceRiskToGeofences()` / `updatePowerDevicesFromWS()` 메서드 신규. (2) `_pointInPolygon` tolerance 파라미터 추가. (3) `init()` Leaflet 옵션 변경 + recenter/setMinZoom/setMaxBounds. (4) `_loadDevices`·`_drawDummyDevices` 전력 마커 `this.powerMarkers[code]` 저장. (5) `_loadGeofences` try/catch 양 분기에서 `_geofenceLayers[id]` 저장 + `_applyDeviceRiskToGeofences()` 호출. (6) `updateGasSensorFromWS` 9가스 `*_risk` 스캔 로직으로 재작성, 모든 가스 마커에 적용. (7) `updateWorkerPositions`에서 `layer._currentRiskLevel` 우선 사용 |
| `drf-server/static/js/dashboard/websocket.js` | `MapPanel.updateGasSensorFromWS(data)` 다음 줄에 `if (data.equipment) MapPanel.updatePowerDevicesFromWS(data.equipment);` 추가. 주석 "가스센서·작업자" → "가스센서·전력장치·작업자" 갱신 |
| `drf-server/static/js/detail/map_detail.js` | `_initFocusBtn`("전체 맞춤" 버튼 핸들러)의 인라인 fitBounds → `MapPanel.recenter()` 위임 |
| `drf-server/templates/dashboard/panels/map_panel.html` | ⌂ 버튼 onclick: `MapPanel.map.fitBounds([[0,0],[600,1300]])` → `MapPanel.recenter()` |
| `drf-server/templates/snb_details/monitoring_realtime.html` | "초기화" 버튼 onclick: 동일하게 `MapPanel.recenter()` |
| `drf-server/templates/components/admin_sidebar.html` | 자리표시 `<a href="#">데이터</a>` 1줄 제거 (실제 링크 "가스 데이터"/"전력 데이터"와 중복이라 사용자 혼동 유발) |

### 삭제
- `_applyGeofenceRiskToDevices()` 메서드 — 작업 도중 잠시 도입했던 "지오펜스 → 장치 색상" 역방향 로직. 사용자 요청에 따라 데이터 흐름을 "장치 → 지오펜스" 정방향으로 뒤집으면서 제거. (커밋 시점엔 흔적 없음)

## 4. API / 응답 / 인터페이스 변경

해당 없음. WS 페이로드 키, REST 응답, 어드민 API 모두 변경 없음. 프론트가 기존 키(`*_risk`, `equipment[].risk_level`)를 새로 활용하기 시작했을 뿐.

## 5. 환경변수·설정 변경

해당 없음.

## 6. 마이그레이션 가이드

```bash
# 1. 풀 받기
git pull

# 2. 의존성·DB·env 변경 없음 — 정적 파일만 갱신
# 브라우저 캐시 강제 새로고침(Ctrl+F5) 권장
```

## 7. 결정 근거 (ADR)

| 결정 | 채택안 | 검토했던 대안 | 근거 |
|---|---|---|---|
| 데이터 흐름 방향 | **센서/장치 → 지오펜스 색상 (단방향)** | 지오펜스 → 장치(역방향), 양방향 | 운영 의도상 센서가 데이터를 받는 주체이고 지오펜스는 위험구역 표시용. 역방향이면 "정상 지오펜스 안 위험 센서"가 가려져 안전 위험. 양방향은 색상 결정 우선순위가 모호. |
| 빈 지오펜스 색상 | **어드민 베이스라인 `risk_level` 유지** | 항상 초록(센서 없음=안전) | 접근금지·장시간 작업 위험구역처럼 센서 없이도 위험 표시가 필요한 운영 케이스가 있음. 어드민이 설정한 의도를 보존. |
| 경계선 톨러런스 | **`_pointInPolygon`에 옵션 인자 추가, 기본 0** | 항상 톨러런스 적용 / 별도 함수 분리 | 작업자 위험구역 진입 알람은 strict해야 false positive 회피. 옵션 인자가 호출자별 정책 선택을 깔끔하게 분리. |
| 톨러런스 단위 | **SVG 좌표 단위 12 (`GEOFENCE_TOLERANCE`)** | 화면 픽셀, 폴리곤 변 길이의 % | `L.CRS.Simple`이라 SVG 단위 = 좌표계. 화면 픽셀은 줌 레벨에 따라 흔들림. 12 단위는 fit 줌(0.5x 부근)에서 약 6 화면픽셀 — 시각적으로 자연스럽고 부동소수점 오차 흡수 충분. |
| 마커 색상 캐싱 | **layer에 `_currentColor`/`_currentRiskLevel` 두 필드** | 매번 재계산 / 별도 Map 자료구조 | layer 객체에 직접 부착하면 layer 라이프사이클과 자동 결착. 같은 색 재적용 시 `setStyle` no-op로 DOM 갱신 회피. 별도 Map은 동기화 누수 가능. |
| `recenter()` 헬퍼 추출 | **`MapPanel.recenter()` 1개 메서드** | 인라인 4곳 그대로 / 모듈 export | 4개 콜사이트가 같은 fitBounds+padding을 써야 하므로 단일 진입점. `MapPanel`이 이미 전역이라 추가 export 불필요. |
| `zoomSnap:0` | **분수 줌 허용** | 정수 스냅 유지(`zoomSnap:1` 기본) | 컨테이너와 SVG의 비율 차이로 fit 계산값이 -0.5 같은 분수일 때, 스냅이 -1로 떨어지면 50% 더 축소돼 큰 여백 발생. 분수 허용이 정확한 fit. 픽셀 정렬 손실은 SVG 도면 시각엔 영향 없음. |
| 전력 마커 매칭 전략 | **이름 일치 우선 + 전체 최댓값 폴백** | 이름 일치만 / `code`/`device_id` 매칭 / 전부 폴백 | 지도 마커명("스마트파워")과 WS 설비명("압연기" 등) 체계가 다른 운영 케이스 존재. 폴백 없이는 전력 마커가 영원히 안 바뀜. 폴백 단독은 개별 위치별 위험도 차이를 무시. 이름 일치 시 정밀, 미일치 시 안전 기본값. |
| 가스 단일 페이로드 적용 | **모든 가스 마커에 동일 worstLevel 적용** | 마커별 개별 위험도 | WS 페이로드가 사이트 전체 합산 1세트(센서별 분리 없음)라 마커별 차등이 데이터에 없음. 페이로드 구조 진화 시 재검토. |

## 8. 검증 방법 / 결과

### 자동 검증
JS 변경이라 기존 자동 테스트(`pytest`/lint 대상) 영향 없음. ESLint 등 프론트 lint 미설정 — 수동 검증으로 갈음.

### 수동 검증 체크리스트

**fit / 재배치**
- [x] `/dashboard/` 첫 로드 — SVG가 컨테이너에 ~20px 패딩만 두고 채워짐
- [x] ⌂ 버튼 클릭 — recenter 동작
- [x] 마우스 휠 줌 아웃 시도 — fit 줌 이하로 안 내려감 (minZoom 잠금)
- [x] 줌 인 후 SVG 영역 밖 패닝 시도 — `maxBounds`로 snap-back
- [x] `/dashboard/monitoring/realtime/` "초기화" / "전체 맞춤" 버튼 동일 동작

**지오펜스 동적 색상**
- [x] 어드민이 "정상" 베이스라인으로 그린 지오펜스 안에 가스 센서가 들어 있고 가스 데이터가 `*_risk: 'danger'` 한 가지라도 있으면 → 폴리곤이 빨강으로 변경
- [x] 위험 가스 데이터 사라지면 → 폴리곤이 베이스라인 색으로 복귀
- [x] 빈 지오펜스(내부 센서 없음) → 어드민 베이스라인 색 유지
- [x] 경계선에 살짝 걸친 센서(좌표 차 ≤ 12 SVG 단위) → 톨러런스로 inside 인식

**마커 색상**
- [x] 가스 9종 중 `*_risk` 'warning'/'danger' 발생 시 가스 아이콘 노랑/빨강
- [x] WS `equipment` 배열에 'warning'/'danger' 등장 시 전력 ⚡ 아이콘 노랑/빨강 (이름 미매칭이라도 전체 최댓값 폴백)
- [x] 작업자 마커 색상이 폴리곤 색상과 일치 (어드민 베이스라인 아닌 동적 effective risk)

**어드민 사이드바**
- [x] 자리표시 "데이터" 링크 사라지고 실제 링크 2개만 노출

### 검증 미완 (운영 회귀 시점)
- [ ] 다중 지오펜스 중첩/체인 케이스에서 톨러런스로 인한 시각적 부조화 여부
- [ ] 전력 마커 이름이 WS 설비명과 일치하는 운영 환경에서 개별 마커 차등 색상 동작
- [ ] WS 단절·재연결 직후 마커 색상 일관성

## 9. 하위 호환성 / 롤백

### Breaking 영역
없음.

### Non-breaking 영역
- WS 페이로드 / REST 응답 / DB 스키마 / env 모두 동일
- 기존 시각 동작은 더 정확해진 방향(센서가 위험을 알리면 그 영역도 빨개짐)으로 변경
- 어드민 사이드바 "데이터" 자리표시 제거는 실제 사용처 없음

### 롤백
- `git revert 4248d8c4` 단일 커밋 되돌리기로 충분
- 의존성·DB·env 변경 없음

## 10. 후속 작업 / 참고

### 본 작업에서 의도적으로 미룬 것
- **AI 예측 차트 가독성** — 시간축 범위(12시간 예측 vs 실시간 추이), 색상 구분(주황+빨강 따뜻한 톤 겹침), 그리드 부재 등 별도 작업으로 분리 (사용자 결정 대기).
- **전력 마커 ↔ WS 설비명 정합** — 현재 폴백으로 모든 전력 마커가 사이트 전체 최댓값으로 동기화. 운영상 마커별 위험도 차등이 필요해지면 지도 편집기에서 `device_name`을 WS 설비명과 정확히 매칭하도록 어드민 가이드 추가 또는 `code` 매칭 전환.
- **가스 멀티 센서 차등** — WS 페이로드가 센서별로 분리될 때까지 모든 가스 마커가 동일 worstLevel을 표시. 페이로드 진화 시 `gasMarkers[code]`별 개별 데이터 매칭으로 변경.
- **지오펜스 어드민 가이드라인** — 무한히 크거나 극소·중첩 그리기 케이스 대응은 톨러런스로 부분 흡수. UX 가이드(권장 크기, 중첩 회피)는 운영 매뉴얼 수준 별도 문서.
- **레이어 가시성 토글 시 색상 동기화** — 탭 필터로 가스/전력 레이어 OFF 상태에서도 지오펜스 계산엔 그대로 반영(시각만 숨김). 의도된 동작이지만 운영 회귀 시 확인 필요.

### 관련 문서
- 기존 변경 기록: `docs/changelog/phase{1,2,3,4,5}_*.md`
- 마스터 검증 체크리스트: `docs/changelog/00_pr_verification_checklist.md`
- 변경기록 작성 프롬프트: `skill/system_instruction_changelog.md`
