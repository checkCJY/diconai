# Wave 1 — 정합·로깅 리팩토링 실행 보고서

> **브랜치**: `feature/0508_refactory_code`
> **작업일**: 2026-05-09
> **분석 베이스**: [docs/codereviews/2026_05_09/](../../../codereviews/2026_05_09/), [docs/refactor/js/2026_05_09/](../../js/2026_05_09/)
> **상태**: ✅ 완료
> **검증**: pytest 84/84 통과, ruff lint+format 통과

## 1. 작업 개요

### 1.1 목표
이전 분석에서 식별한 **가장 안전·시급한 16개 항목**을 일괄 적용. 모두 1~10줄 수준 변경으로 회귀 위험을 최소화하면서 운영 가시성·정합성·코드 품질을 즉시 향상시키는 것이 목적.

### 1.2 범위
- 백엔드 5건 (B1~B5)
- JS 11건 (J1~J11)
- 신규 파일 1개 (`apps/core/authentication.py`)
- 환경변수 1개 추가 (`INTERNAL_SERVICE_TOKEN`)

### 1.3 영향 파일 (16개)

| 분류 | 파일 |
|---|---|
| **백엔드 신규** | `drf-server/apps/core/authentication.py` |
| **백엔드 수정** | `drf-server/apps/positioning/views/position_views.py`, `drf-server/apps/alerts/views/alarm_record.py`, `drf-server/apps/alerts/tasks.py`, `drf-server/apps/monitoring/views/gas_data.py`, `drf-server/apps/monitoring/views/power_data.py`, `drf-server/config/settings.py` |
| **fastapi 수정** | `fastapi-server/internal/routers/alarm_router.py`, `fastapi-server/core/config.py` |
| **JS 수정** | `drf-server/static/js/shared/{util,config,ws-client,layout,auth,app-sub}.js`, `drf-server/static/js/dashboard/app.js`, `drf-server/static/js/detail/safety_history.js` |

## 2. 변경 항목 상세

각 항목은 다음 5섹션으로 정리:
**(A) 무엇이 바뀌었나** · **(B) 왜 바뀌었나 (분석 근거)** · **(C) 적용된 기능** · **(D) Before / After** · **(E) 다른 방법 trade-off**

---

### B1. `print()` → `logger.exception` ([positioning/views/position_views.py:102](../../../../drf-server/apps/positioning/views/position_views.py#L102))

**(A) 변경 내용**
- 모듈 상단에 `import logging` + `logger = logging.getLogger(__name__)` 추가
- 위치 데이터 저장 실패 시 `print(...)` → `logger.exception(...)` 변경 + bare exception variable `as e` 제거 (logger.exception이 traceback 자동 포함)

**(B) 왜 바뀌었나**
- CLAUDE.md 컨벤션 위반: "print() 금지 → logging 사용"
- 분석 근거: [07_geofence_positioning.md G3](../../js/2026_05_09/) (실제로는 도메인 리뷰 07 G3 항목)
- `print()`는 stdout으로 직접 출력 → Django 로그 시스템에 안 잡힘 → 운영 환경에서 로그 수집 도구(Sentry 등)에 전파 안 됨

**(C) 적용된 기능**
- Python 표준 logging 인프라 사용 → log level 필터·핸들러·외부 전송 모두 가능
- `logger.exception()`은 traceback을 자동으로 ERROR 레벨로 기록

**(D) Before / After**
```python
# Before
except Exception as e:
    print(f"[positioning] 저장 오류: {e}")

# After
except Exception:
    logger.exception("[positioning] 저장 오류 (item ignored)")
```

**(E) 다른 방법 trade-off**

| 옵션 | 장점 | 단점 | 채택 여부 |
|---|---|---|---|
| ✅ `logger.exception` | traceback 포함 / 운영 로그 수집 가능 | logger 인스턴스 import 필요 | **채택** |
| `logger.error(msg, exc_info=True)` | 동일한 결과 | 코드 길어짐 | 미채택 |
| `logger.warning` | exception이 아니라는 의미 | traceback 누락, 디버깅 어려움 | 미채택 |
| `raise` (예외 전파) | 호출자가 처리 | 위치 배열의 부분 실패가 전체 실패로 → UX 영향 | 미채택 (B7 권고로 이전) |

---

### B2. `AlarmPayload.extra="ignore"` ([alarm_router.py:18](../../../../fastapi-server/internal/routers/alarm_router.py#L18))

**(A) 변경 내용**
- Pydantic `model_config`의 `"extra"` 값을 `"allow"` → `"ignore"` 변경
- 미정의 필드가 페이로드에 포함되어도 모델이 받지 않음 (silent drop)

**(B) 왜 바뀌었나**
- 분석 근거: [04_alerts_events.md D5](../../../codereviews/2026_05_09/04_alerts_events.md)
- `"allow"`는 임의 키를 통과시켜 다운스트림(브라우저)에 의도치 않은 정보 노출 가능
- DRF Celery 측이 명시 필드만 보내야 contract 정확

**(C) 적용된 기능**
- Pydantic의 미정의 필드 자동 제거 — 송신자가 잘못된 키 보내도 받는 쪽이 안전
- OpenAPI 스키마 정확성 향상 (스키마 정의 외 필드 비공개)

**(D) Before / After**
```python
# Before
class AlarmPayload(BaseModel):
    model_config = {"extra": "allow"}  # 필드가 추가되어도 유연하게 수용

# After
class AlarmPayload(BaseModel):
    # 미정의 필드는 통과시키지 않음 — DRF Celery 측이 명시 필드만 보내야 함
    model_config = {"extra": "ignore"}
```

**(E) 다른 방법 trade-off**

| 옵션 | 장점 | 단점 | 채택 여부 |
|---|---|---|---|
| ✅ `"ignore"` | 미정의 필드 자동 제거 / 호환성 유지 | 송신자가 키 오타·정의 누락 시 silent | **채택** |
| `"forbid"` | 미정의 키 시 즉시 422 에러 — 디버깅 명확 | 백엔드 응답 형식 변경 시 모든 운영 알람 차단 → 위험 | 미채택 |
| `"allow"` (유지) | 유연성 | 보안·정합성 위험 | 변경 전 |

선택 이유: `forbid`가 가장 엄격하지만 운영 영향 큰 변경. `ignore`로 안전성·호환성 균형.

---

### B5. `WorkerSummaryView` permission_classes 클래스화 ([alarm_record.py:119](../../../../drf-server/apps/alerts/views/alarm_record.py#L119))

**(A) 변경 내용**
- `permission_classes`에 `IsSuperAdminOrFacilityAdmin` 추가
- view body의 `if user_type not in ... raise PermissionDenied` 제거
- import 정리: `PermissionDenied` 제거, `IsSuperAdminOrFacilityAdmin` 추가

**(B) 왜 바뀌었나**
- 분석 근거: [04_alerts_events.md D4](../../../codereviews/2026_05_09/04_alerts_events.md)
- 권한 체크가 view body에 인라인되면 발견·테스트 어려움
- DRF의 표준 권한 클래스 패턴이 일관성 보장

**(C) 적용된 기능**
- 401/403 자동 응답 (DRF 표준)
- OpenAPI 스키마에 권한 정보 자동 노출
- 단위 테스트 시 view body 실행 전에 차단됨 → 테스트 성능

**(D) Before / After**
```python
# Before
class WorkerSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.user_type not in ("facility_admin", "super_admin"):
            raise PermissionDenied("접근 권한이 없습니다.")
        facility = request.user.facility
        ...

# After
class WorkerSummaryView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdminOrFacilityAdmin]

    def get(self, request):
        # 권한 체크는 permission_classes(IsSuperAdminOrFacilityAdmin)가 처리
        facility = request.user.facility
        ...
```

**(E) 다른 방법 trade-off**

| 옵션 | 장점 | 단점 | 채택 여부 |
|---|---|---|---|
| ✅ `permission_classes`에 추가 | DRF 표준 / 테스트·문서 자동 | `IsSuperAdminOrFacilityAdmin` import 필요 | **채택** |
| view body raise 유지 | 변경 없음 | 일관성 결여 / OpenAPI 부정확 | 미채택 |
| 데코레이터 (`@user_passes_test`) | Django 전통 패턴 | DRF와 mismatch | 미채택 |

---

### B3 + B4. 서비스 토큰 인증 (Phase 5) — 신규 [apps/core/authentication.py](../../../../drf-server/apps/core/authentication.py) + 5개 view + Celery + fastapi alarm_router

**(A) 변경 내용**
1. **신규**: `apps/core/authentication.py::ServiceTokenAuthentication` — DRF BaseAuthentication 클래스
2. **drf settings**: `INTERNAL_SERVICE_TOKEN` env 추가
3. **drf views 4개**: `GasDataCreateView`, `PowerEventIngestView`, `PowerDataBulkIngestView`, `WorkerPositionReceiveView` 모두 `authentication_classes = [ServiceTokenAuthentication]` 적용
4. **drf Celery (alerts/tasks.py)**: `_push_to_ws()`가 `Authorization: Bearer <token>` 헤더 부착
5. **fastapi config.py**: `INTERNAL_SERVICE_TOKEN` env 추가
6. **fastapi alarm_router**: `/internal/alarms/push/` 진입에서 토큰 검증

**(B) 왜 바뀌었나**
- 분석 근거: [04_alerts_events.md D1](../../../codereviews/2026_05_09/04_alerts_events.md), [06_monitoring_ingest.md F1](../../../codereviews/2026_05_09/06_monitoring_ingest.md)
- 가스/전력/위치 ingest 엔드포인트가 무인증 — 외부 노출 시 측정값 위변조 가능
- alarm-push가 localhost 검증만으로 부족 — 같은 호스트의 다른 프로세스가 임의 알람 push 가능
- 코드에 "Phase 5에서 보호 추가 예정" 주석이 명시되어 있던 항목

**(C) 적용된 기능**
- **옵트인 토큰 인증**: `INTERNAL_SERVICE_TOKEN` 미설정 시 기존 무인증 동작 유지, 설정 시 자동 활성화
- 양방향 인증: fastapi → drf (이미 토큰 송신 중) + drf Celery → fastapi (신규 토큰 송신)
- DRF `ServiceTokenAuthentication`이 `(None, None)` 반환 → 시스템 호출이라 User 객체 없이 통과
- fastapi 측은 localhost 검증 + (옵트인) 토큰 검증 이중 보호

**(D) Before / After**

```python
# Before — drf views (예: gas_data.py)
class GasDataCreateView(APIView):
    authentication_classes = []
    permission_classes = []

# After — drf views
class GasDataCreateView(APIView):
    authentication_classes = [ServiceTokenAuthentication]
    permission_classes = [AllowAny]
```

```python
# Before — drf Celery (tasks.py)
httpx.post(FASTAPI_INTERNAL_URL, json=alarm_data, timeout=3.0)

# After — drf Celery
headers = {}
token = getattr(settings, "INTERNAL_SERVICE_TOKEN", "") or ""
if token:
    headers["Authorization"] = f"Bearer {token}"
httpx.post(FASTAPI_INTERNAL_URL, json=alarm_data, headers=headers, timeout=3.0)
```

```python
# Before — fastapi alarm_router
async def push_alarm(request: Request, alarm: AlarmPayload):
    client_host = request.client.host if request.client else ""
    if client_host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(status_code=403, ...)

# After — fastapi alarm_router
async def push_alarm(request: Request, alarm: AlarmPayload):
    client_host = request.client.host if request.client else ""
    if client_host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(status_code=403, ...)

    # Phase 5: 옵트인 토큰 검증
    expected_token = settings.INTERNAL_SERVICE_TOKEN
    if expected_token:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="서비스 토큰이 필요합니다.")
        if auth_header[7:].strip() != expected_token:
            raise HTTPException(status_code=403, detail="유효하지 않은 서비스 토큰입니다.")
    ...
```

**(E) 다른 방법 trade-off**

| 옵션 | 장점 | 단점 | 채택 여부 |
|---|---|---|---|
| ✅ **옵트인 토큰 (env 빈 값이면 비활성)** | 기존 환경 즉시 호환 / 단계적 활성화 | 운영자가 토큰 설정 잊으면 보호 안 됨 | **채택** |
| 강제 활성화 (토큰 부재 시 503 응답) | 보안 강제 | 기존 운영·개발 환경 즉시 깨짐 → 큰 회귀 | 미채택 |
| IP 화이트리스트만 | 토큰 관리 불필요 | 같은 호스트 내 위변조 차단 못 함 / 컨테이너 IP 동적 변동 | 미채택 |
| mTLS (mutual TLS) | 가장 강력 | 인증서 관리 인프라 필요 / 큰 작업 | 다음 sprint 또는 보류 |
| 단일 환경변수 `INTERNAL_SERVICE_TOKEN` 양 서비스 동일 | 운영 단순 / 한 곳 변경 | 양 서비스 동시 갱신 필요 (롤링 배포 시 잠시 양쪽 모두 비활성 권장) | **채택** |
| 양 서비스 별도 변수 | 명시적 분리 | 운영 복잡도 증가 / 키 동기화 부담 | 미채택 |

**선택 이유**: 옵트인 + 단일 변수가 운영 단순성·안전성·점진적 활성화 모두 만족.

---

### J1. `levelLabel` dead code 제거 ([util.js:51](../../../../drf-server/static/js/shared/util.js))

**(A) 변경 내용**
- `levelLabel = { danger: '위험', caution: '주의', safe: '정상' }` 한 줄 제거

**(B) 왜 바뀌었나**
- 분석 근거: [06_utils_config.md R1](../../js/2026_05_09/06_utils_config.md), [08_admin_panel_pages.md H1](../../../codereviews/2026_05_09/08_admin_panel_pages.md)
- grep 결과 호출자 0건 → **dead code 확인**
- 백엔드 enum (`danger`/`warning`/`normal`)과 키 불일치 (`caution`/`safe`) → 사용했어도 silent UI 깨짐 가능

**(C) 적용된 기능**
- 없음 (코드 제거 — dead code clean up)

**(D) Before / After**
```js
// Before
/** 차트 최대 보관 포인트 수 */
const MAX_POINTS = 30;

/** 위험도 한글 레이블 (danger·caution·safe 공통) */
const levelLabel = { danger: '위험', caution: '주의', safe: '정상' };

// After
/** 차트 최대 보관 포인트 수 */
const MAX_POINTS = 30;
```

**(E) 다른 방법 trade-off**

| 옵션 | 장점 | 단점 | 채택 여부 |
|---|---|---|---|
| ✅ 제거 (dead code clean) | 코드 간결 / 미래 혼동 방지 | 만약 향후 사용 의도 있다면 재추가 필요 | **채택** |
| 백엔드 정합 (`{danger, warning, normal}`로 키 변경) | 사용 시 정확 | 호출자 없으니 의미 없음 | 미채택 |
| 유지 + 키 변경 + 호출자 추가 | 라벨 표준화 | scope 초과 | 미채택 |

**근거**: `grep -rn 'levelLabel' static/ templates/` → 0건. 안전한 제거.

---

### J2. `pushData` 검증 추가 ([util.js:37-50](../../../../drf-server/static/js/shared/util.js))

**(A) 변경 내용**
- chart 객체 null 가드 추가
- `values.length > datasets.length` 시 `console.warn`
- forEach 내부에서 `chart.data.datasets[i]` 존재 여부 확인 후 push

**(B) 왜 바뀌었나**
- 분석 근거: [06_utils_config.md R2](../../js/2026_05_09/06_utils_config.md)
- Chart.js 라이브러리 사용처가 늘어날수록 dataset/values 길이 mismatch 가능성
- silent NPE 발생 시 디버깅 어려움

**(C) 적용된 기능**
- 잘못된 호출 시 `console.warn` 출력 → 빠른 디버깅
- 부분 push 가능 (datasets 부족 시에도 가능한 만큼 push)

**(D) Before / After**
```js
// Before
function pushData(chart, label, ...values) {
  chart.data.labels.push(label);
  values.forEach((v, i) => chart.data.datasets[i].data.push(v));
  if (chart.data.labels.length > MAX_POINTS) { ... }
  chart.update('none');
}

// After
function pushData(chart, label, ...values) {
  if (!chart || !chart.data || !chart.data.datasets) return;
  if (values.length > chart.data.datasets.length) {
    console.warn('[pushData] values.length > datasets.length',
      { values: values.length, datasets: chart.data.datasets.length });
  }
  chart.data.labels.push(label);
  values.forEach((v, i) => {
    const ds = chart.data.datasets[i];
    if (ds) ds.data.push(v);
  });
  if (chart.data.labels.length > MAX_POINTS) { ... }
  chart.update('none');
}
```

**(E) 다른 방법 trade-off**

| 옵션 | 장점 | 단점 | 채택 여부 |
|---|---|---|---|
| ✅ console.warn + 부분 push | 호출자에 즉시 피드백 / 일부 데이터 보존 | warn 무시하면 silent 가까움 | **채택** |
| throw Error | 명확한 에러 | 차트 갱신 멈춤 → UI 정지 | 미채택 |
| silent (현재) | 차트 영향 0 | 디버깅 매우 어려움 | 변경 전 |

---

### J3. WS_BASE 운영 가드 ([config.js:6-22](../../../../drf-server/static/js/shared/config.js))

**(A) 변경 내용**
- `window.AppConfig` 미정의 시 fallback 직전 `console.warn` 추가
- 추가 가드: WS_BASE가 localhost인데 페이지 호스트가 localhost가 아니면 `console.error`

**(B) 왜 바뀌었나**
- 분석 근거: [06_utils_config.md R3](../../js/2026_05_09/06_utils_config.md)
- `app_config.html` 로드 누락 시 fallback이 dev URL — 운영에서 silent로 모든 WS 연결 실패
- 기존 코드는 fallback 자체가 silent → 발견 어려움

**(C) 적용된 기능**
- `console.warn`: AppConfig 미정의 시 fallback 사용 명시
- `console.error`: 운영 환경에서 localhost WS_BASE 사용 시 즉시 가시화

**(D) Before / After**
```js
// Before
window.AppConfig = window.AppConfig || {
  API_BASE: "",
  WS_BASE:  "ws://127.0.0.1:8001"
};

// After
if (!window.AppConfig) {
  console.warn('[AppConfig] not defined by template, using localhost fallback (dev only)');
  window.AppConfig = {
    API_BASE: "",
    WS_BASE:  "ws://127.0.0.1:8001"
  };
}

// 운영 환경 가드: localhost가 아닌 host에서 WS_BASE가 localhost면 경고
if (window.AppConfig.WS_BASE &&
    window.AppConfig.WS_BASE.includes('127.0.0.1') &&
    window.location.hostname !== 'localhost' &&
    window.location.hostname !== '127.0.0.1') {
  console.error('[AppConfig] WS_BASE points to localhost in non-local environment:',
    window.AppConfig.WS_BASE);
}
```

**(E) 다른 방법 trade-off**

| 옵션 | 장점 | 단점 | 채택 여부 |
|---|---|---|---|
| ✅ console.warn + console.error 가드 | 1초만에 원인 파악 / 운영 환경 자동 감지 | console에만 표시 → Sentry 도입 시 의미 큼 | **채택** |
| `throw Error` (운영에서 페이지 차단) | 사고 방지 강제 | 정상 dev 환경도 영향 | 미채택 |
| 빌드 시점 검증 | 가장 안전 | 빌드 인프라 부재 | 다음 sprint |

---

### J4. `safety_history.js` pad 로컬 재정의 제거 ([safety_history.js:4](../../../../drf-server/static/js/detail/safety_history.js))

**(A) 변경 내용**
- IIFE 내부의 `function pad(n) { return String(n).padStart(2, '0'); }` 제거
- 주석 추가: "pad는 shared/util.js의 글로벌 함수 사용"

**(B) 왜 바뀌었나**
- 분석 근거: [06_utils_config.md R5](../../js/2026_05_09/06_utils_config.md)
- `util.js`의 `pad` 글로벌 함수와 중복
- 사전 검증: `templates/snb_details/safety_history.html`에서 util.js(177)이 safety_history.js(184)보다 먼저 로드 확인 → 안전

**(C) 적용된 기능**
- 단일 진실 원천 (util.js의 pad)
- 향후 pad 로직 변경 시 1곳만 수정

**(D) Before / After**
```js
// Before
(function () {
  function pad(n) { return String(n).padStart(2, '0'); }
  const today = new Date();
  ...
})();

// After
(function () {
  // pad는 shared/util.js의 글로벌 함수 사용
  const today = new Date();
  ...
})();
```

**(E) 다른 방법 trade-off**

| 옵션 | 장점 | 단점 | 채택 여부 |
|---|---|---|---|
| ✅ 제거 + 글로벌 사용 | 단일 출처 | 로드 순서 의존 | **채택** (사전 검증) |
| 유지 (모듈 격리) | IIFE 외부 의존성 0 | 중복 / 정책 변경 시 누락 위험 | 미채택 |
| ES Modules import | 명시적 의존성 | 빌드 도구 도입 필요 | 다음 sprint |

---

### J5. WSClient `_resolveUrl` console.warn ([ws-client.js:28-50](../../../../drf-server/static/js/shared/ws-client.js))

**(A) 변경 내용**
- AppConfig.wsUrl 미정의 시 `console.warn`
- attachToken 옵션이지만 Auth 모듈 미로드 시 `console.warn`
- attachToken 옵션이지만 토큰 부재 시 `console.warn`

**(B) 왜 바뀌었나**
- 분석 근거: [02_ws_infrastructure.md R4](../../js/2026_05_09/02_ws_infrastructure.md)
- 기존 silent fallback이 디버깅 어려움
- 향후 WS 인증 도입(다음 sprint) 시 토큰 누락이 모든 WS 연결 실패의 silent 원인이 될 수 있음

**(C) 적용된 기능**
- 3가지 silent 시나리오 각각 구분된 메시지 출력
- 빠른 원인 파악

**(D) Before / After**
```js
// Before
function _resolveUrl(path, opts) {
  let base;
  if (window.AppConfig && typeof window.AppConfig.wsUrl === 'function') {
    base = window.AppConfig.wsUrl(path);
  } else {
    base = path;
  }
  if (opts && opts.attachToken && typeof Auth !== 'undefined') {
    const token = Auth.getAccessToken();
    if (token) { /* token 부착 */ }
  }
  return base;
}

// After
function _resolveUrl(path, opts) {
  let base;
  if (window.AppConfig && typeof window.AppConfig.wsUrl === 'function') {
    base = window.AppConfig.wsUrl(path);
  } else {
    console.warn('[WSClient] AppConfig.wsUrl unavailable, using same-origin fallback for', path);
    base = path;
  }
  if (opts && opts.attachToken) {
    if (typeof Auth === 'undefined') {
      console.warn('[WSClient] attachToken requested but Auth module not loaded');
    } else {
      const token = Auth.getAccessToken();
      if (!token) {
        console.warn('[WSClient] attachToken requested but no token in storage');
      } else { /* token 부착 */ }
    }
  }
  return base;
}
```

**(E) 다른 방법 trade-off**

| 옵션 | 장점 | 단점 | 채택 여부 |
|---|---|---|---|
| ✅ 분기별 console.warn | 정확한 원인 식별 | 정상 운영 시 출력 0 (조건부) | **채택** |
| 단일 console.warn | 단순 | 어떤 경우인지 모호 | 미채택 |
| throw Error | 강제 가시화 | 정상 fallback도 차단 | 미채택 |

---

### J6. `Menu.iconMap` 미정의 console.warn ([layout.js:50-58](../../../../drf-server/static/js/shared/layout.js))

**(A) 변경 내용**
- `const icon = this.iconMap[menu.icon] || '•';` 한 줄 → 분기 + console.warn 추가
- menu.icon이 truthy인데 iconMap에 없을 때만 warn (icon 자체가 없는 메뉴는 OK)

**(B) 왜 바뀌었나**
- 분석 근거: [04_layout_menu_header.md R4](../../js/2026_05_09/04_layout_menu_header.md)
- 새 메뉴 아이콘 추가 시 silent fallback (`'•'`) → 디자인 깨짐 발견 늦음

**(C) 적용된 기능**
- 새 아이콘 키 추가 시 즉시 경고
- 의도된 누락(menu.icon=undefined)은 silent 통과

**(D) Before / After**
```js
// Before
const icon = this.iconMap[menu.icon] || '•';

// After
let icon = this.iconMap[menu.icon];
if (!icon) {
  if (menu.icon) console.warn('[Menu] icon not defined:', menu.icon);
  icon = '•';
}
```

**(E) 다른 방법 trade-off**

| 옵션 | 장점 | 단점 | 채택 여부 |
|---|---|---|---|
| ✅ console.warn (icon 키 있을 때만) | 의도된 누락 silent | 운영 환경에서도 console에 표시 | **채택** |
| throw Error | 강제 명시 | 페이지 진입 차단 | 미채택 |
| 빌드 시점 검증 | 자동 | 인프라 부재 | 다음 sprint |

---

### J7. `ROLE_LABEL` 모듈 상수화 + 미정의 console.warn ([layout.js:107-115, 199-211](../../../../drf-server/static/js/shared/layout.js))

**(A) 변경 내용**
- `Header.renderUser` 내부에 함수 호출마다 새로 만들어지던 객체를 모듈 상단의 `Object.freeze` 상수로 추출
- role 값이 ROLE_LABEL에 없을 때 `console.warn`

**(B) 왜 바뀌었나**
- 분석 근거: [04_layout_menu_header.md R7](../../js/2026_05_09/04_layout_menu_header.md)
- 함수 호출마다 동일 객체 재생성 (미세하지만 불필요)
- 새 role 추가 시 silent `'-'` 폴백

**(C) 적용된 기능**
- 모듈 상수 + Object.freeze로 immutable
- 미정의 role 즉시 경고

**(D) Before / After**
```js
// Before
const Header = {
  ...
  renderUser(username, role) {
    const nameEl = document.getElementById('headerUsername');
    const roleEl = document.getElementById('headerRole');
    const roleLabel = {  // 호출마다 재생성
      worker: '작업자', facility_admin: '공장관리자',
      super_admin: '슈퍼관리자', viewer: '열람자',
    };
    if (nameEl) nameEl.textContent = username ? `${username}님 환영합니다` : '-';
    if (roleEl) roleEl.textContent = roleLabel[role] || '-';
  },
};

// After
const ROLE_LABEL = Object.freeze({
  worker: '작업자', facility_admin: '공장관리자',
  super_admin: '슈퍼관리자', viewer: '열람자',
});

const Header = {
  ...
  renderUser(username, role) {
    const nameEl = document.getElementById('headerUsername');
    const roleEl = document.getElementById('headerRole');
    if (nameEl) nameEl.textContent = username ? `${username}님 환영합니다` : '-';
    if (roleEl) {
      const label = ROLE_LABEL[role];
      if (!label && role) console.warn('[Header] unknown role:', role);
      roleEl.textContent = label || '-';
    }
  },
};
```

**(E) 다른 방법 trade-off**

| 옵션 | 장점 | 단점 | 채택 여부 |
|---|---|---|---|
| ✅ 모듈 상수 + freeze + warn | 성능·안전·가시성 | 모듈 scope 추가 | **채택** |
| 함수 안 const + freeze | 외부 노출 X | 호출마다 재생성 | 미채택 |
| Map | 더 명시적 | 약간 무거움 / 호환성 | 미채택 |

---

### J8. `handleRefresh` setTimeout 누적 방지 ([layout.js:118, 152-163](../../../../drf-server/static/js/shared/layout.js))

**(A) 변경 내용**
- `Header._refreshErrTimer: null` 인스턴스 속성 추가
- catch 내부에서 setTimeout 직전 `clearTimeout(this._refreshErrTimer)` 호출

**(B) 왜 바뀌었나**
- 분석 근거: [04_layout_menu_header.md R8](../../js/2026_05_09/04_layout_menu_header.md)
- 빠른 연속 새로고침 실패 시 setTimeout이 누적 → 복원 시점이 어긋남

**(C) 적용된 기능**
- timer가 항상 1개만 활성
- 마지막 실패 시점부터 3초 후 복원 보장

**(D) Before / After**
```js
// Before
} catch {
  if (btn) {
    btn.style.color = 'var(--danger)';
    btn.title = '새로고침 실패 — 잠시 후 다시 시도하세요';
    setTimeout(() => { btn.style.color = ''; btn.title = '새로고침'; }, 3000);
  }
}

// After
} catch {
  if (btn) {
    btn.style.color = 'var(--danger)';
    btn.title = '새로고침 실패 — 잠시 후 다시 시도하세요';
    clearTimeout(this._refreshErrTimer);
    this._refreshErrTimer = setTimeout(() => {
      btn.style.color = ''; btn.title = '새로고침';
    }, 3000);
  }
}
```

**(E) 다른 방법 trade-off**

| 옵션 | 장점 | 단점 | 채택 여부 |
|---|---|---|---|
| ✅ clearTimeout + reassign | 단순 / 정확 | 인스턴스 속성 1개 추가 | **채택** |
| Promise·debounce 라이브러리 | 더 우아 | 의존성 추가 | 미채택 |
| 무시 | 변경 없음 | 부정확 | 변경 전 |

---

### J9. `initApp().catch()` ([dashboard/app.js:49](../../../../drf-server/static/js/dashboard/app.js), [app-sub.js:11](../../../../drf-server/static/js/shared/app-sub.js))

**(A) 변경 내용**
- 두 파일의 `initApp();` → `initApp().catch(err => console.error(...));`

**(B) 왜 바뀌었나**
- 분석 근거: [05_page_init.md R1](../../js/2026_05_09/05_page_init.md)
- async 함수의 await 없는 호출은 unhandled promise rejection 가능
- 사용자에게 빈 화면만 보이고 콘솔 에러도 늦게 노출

**(C) 적용된 기능**
- 명시적 에러 로깅 → 빠른 원인 추적

**(D) Before / After**
```js
// Before (dashboard/app.js)
initApp();

// After
initApp().catch(err => {
  console.error('[app] initialization failed:', err);
});
```

**(E) 다른 방법 trade-off**

| 옵션 | 장점 | 단점 | 채택 여부 |
|---|---|---|---|
| ✅ `.catch(console.error)` | 단순 / 즉시 효과 | 사용자 피드백은 콘솔뿐 | **채택** |
| `.catch` + 사용자 에러 페이지 | UX 개선 | 추가 마크업 / 디자인 결정 | 다음 sprint |
| `window.addEventListener('unhandledrejection', ...)` | 글로벌 처리 | scope 큼 / 다른 비동기에 영향 | 다음 sprint |

---

### J10. `loadMySafetyStatus` catch console.warn ([dashboard/app.js:46](../../../../drf-server/static/js/dashboard/app.js))

**(A) 변경 내용**
- `catch { /* 기본값 유지 */ }` → `catch (e) { console.warn(...); }`

**(B) 왜 바뀌었나**
- 분석 근거: [05_page_init.md R6](../../js/2026_05_09/05_page_init.md)
- 빈 catch는 디버깅 어려움

**(C) 적용된 기능**
- 실패 원인 가시화 (네트워크 / JSON 파싱 / DOM 부재 등)

**(D) Before / After**
```js
// Before
} catch { /* 실패 시 기본값(미완료) 유지 */ }

// After
} catch (e) {
  console.warn('[loadMySafetyStatus] fetch failed:', e);
}
```

**(E) 다른 방법 trade-off**

| 옵션 | 장점 | 단점 | 채택 여부 |
|---|---|---|---|
| ✅ console.warn | 가시성 / 사용자 영향 0 | console에만 | **채택** |
| 사용자 알림 | UX 명확 | 일시적 네트워크 에러도 노출 → 잡음 | 미채택 |

---

### J11. `Auth.getMe` catch console.warn ([auth.js:97-99](../../../../drf-server/static/js/shared/auth.js))

**(A) 변경 내용**
- `catch { return null; }` → `catch (e) { console.warn(...); return null; }`

**(B) 왜 바뀌었나**
- 분석 근거: [01_auth_session.md R7](../../js/2026_05_09/01_auth_session.md)
- 페이지 진입 시 호출되는 핵심 함수의 silent failure

**(C) 적용된 기능**
- 인증 흐름 실패 가시화

**(D) Before / After**
```js
// Before
async getMe() {
  try {
    const res = await this.apiFetch('/api/auth/me/');
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
},

// After
async getMe() {
  try {
    const res = await this.apiFetch('/api/auth/me/');
    if (!res.ok) return null;
    return await res.json();
  } catch (e) {
    console.warn('[Auth.getMe]', e);
    return null;
  }
},
```

**(E) 다른 방법 trade-off**

| 옵션 | 장점 | 단점 | 채택 여부 |
|---|---|---|---|
| ✅ console.warn + null 유지 | 호환성 / 가시성 | console만 | **채택** |
| throw 전파 | 명시적 처리 강제 | 모든 호출자 수정 필요 | 미채택 |

## 3. 적용된 신규 기능 (요약)

### 3.1 `ServiceTokenAuthentication` (DRF 인증 클래스)
**위치**: [drf-server/apps/core/authentication.py](../../../../drf-server/apps/core/authentication.py)
**역할**: 서비스 간 호출(fastapi → drf 인입)을 Bearer 토큰으로 검증.
**옵트인**: `settings.INTERNAL_SERVICE_TOKEN` 빈 값이면 비활성 (다음 인증 클래스로 위임), 값이 있으면 검증.

### 3.2 환경변수 `INTERNAL_SERVICE_TOKEN`
**위치**: drf settings.py + fastapi config.py 양쪽
**용도**:
- drf가 받을 토큰 (fastapi → drf 호출 검증)
- drf Celery가 보낼 토큰 (drf → fastapi alarm-push)
- fastapi가 받을 토큰 (drf Celery → fastapi 검증)
**운영**: 양 서비스에 동일 값 설정. 빈 값이면 인증 비활성 (Phase 5 점진 활성화 준비).

### 3.3 운영 환경 가드 (config.js)
**역할**: 비-localhost 호스트에서 WS_BASE가 localhost를 가리키면 `console.error` 출력 → 배포 누락 즉시 가시화.

### 3.4 `ROLE_LABEL` 모듈 상수
**역할**: 이전 함수 내부 객체 → 모듈 상단 `Object.freeze` 상수. 새 role 추가 시 console.warn.

## 4. 검증 체크리스트

### 4.1 자동 테스트 ✅
- [x] **fastapi-server pytest**: 22 passed (PR-F 22종)
- [x] **drf-server pytest**: 62 passed (e2e 4종 + alarm/event/safety/menu/etc.)
- [x] **ruff lint**: All checks passed (16개 변경 파일)
- [x] **ruff format**: Applied (1 file reformatted)

### 4.2 수동 검증 (권장 — 아직 미수행)

#### 4.2.1 페이지 진입 (콘솔 에러 0)
- [ ] `/accounts/login/` → 로그인 폼 정상 노출
- [ ] 로그인 성공 → `/dashboard/` 리다이렉트
- [ ] 대시보드 진입 (charts·panels·websocket 모두 동작)
- [ ] 서브 페이지 진입 (`/dashboard/monitoring/gas/`, `/dashboard/safety/checklist/` 등)
- [ ] admin 페이지 진입 (`/admin-panel/accounts-management/` 등)
- [ ] 로그아웃 → 토큰 정리 → 로그인 페이지

#### 4.2.2 새 console.warn/error 메시지 의도된 곳에서만 발생
- [ ] 정상 운영 시 콘솔에 warn 0 또는 의도된 메시지만
- [ ] 일부러 잘못된 메뉴 icon 키 사용 시 → `[Menu] icon not defined: ...` 출력
- [ ] 일부러 잘못된 role 사용 시 → `[Header] unknown role: ...` 출력

#### 4.2.3 환경변수 옵트인 검증 (Phase 5 활성화 시)
- [ ] **case 1**: 양쪽 `INTERNAL_SERVICE_TOKEN` 미설정
  - [ ] fastapi → drf 인입 정상 (`/api/monitoring/gas/` 등)
  - [ ] drf Celery → fastapi alarm-push 정상
- [ ] **case 2**: 양쪽 동일 토큰 설정
  - [ ] 정상 통과 확인
  - [ ] 잘못된 토큰으로 직접 curl 호출 시 → 401/403
- [ ] **case 3**: 한쪽만 설정 (운영 사고 시뮬레이션)
  - [ ] 토큰 없는 호출 차단 확인

#### 4.2.4 알람 흐름 회귀 (PR-H 동등)
- [ ] 가스 위험 시뮬레이션 → AlarmPopup 노출
- [ ] 지오펜스 진입 시뮬레이션 → 작업자 단말 worker-ws 알림
- [ ] alarm-push에 미정의 필드 송신 시 → silent ignore (B2 효과)

### 4.3 회귀 위험 0 확인 항목
- [x] WorkerSummaryView 권한 변경: 기존 facility_admin/super_admin 호출 시 정상 (62 테스트에 포함)
- [x] AlarmPayload extra="ignore": 기존 정의 필드 모두 통과
- [x] ServiceTokenAuthentication 옵트인: 토큰 미설정 시 기존 동작 유지

## 5. 알려진 한계 / 후속 작업

### 5.1 이번 Wave에 포함되지 않은 항목
- **WS 인증 통합** (분석 09 I4): 모든 `/ws/*` 채널의 JWT 인증 — Wave 3 또는 다음 sprint
- **alarm-mapper.js 추출** (분석 03 R1): JS 키 매핑 단일화 — Wave 3 후보
- **Menu.render innerHTML → createElement** (분석 04 R1): XSS 패턴 정착 — Wave 3
- **AlarmPopup 큐 정책** (분석 03 R2): 운영팀 합의 후 진행
- **선택 사항 B10**: PasswordChangeView 토큰 블랙리스트 — Wave 2에서 결정

### 5.2 운영 적용 시 주의
1. **`INTERNAL_SERVICE_TOKEN` 양 서비스 동시 설정**: 한쪽만 설정하면 통신 끊김. 롤링 배포 시 잠시 양쪽 모두 비활성 → 동시 재시작 → 양쪽 활성화 권장.
2. **토큰 값 안전 보관**: settings.py · core/config.py 양쪽이 env에서 읽음. .env 파일 git 제외 확인.
3. **새 console.warn 메시지**: 운영 환경에서 콘솔 노이즈 약간 증가. Sentry 등 로깅 도구 도입 시 노이즈 필터 설정 필요.

### 5.3 향후 분석 항목
- 실제 운영 환경에서 `console.warn` 빈도 측정 → 잡음/실제 이슈 비율 확인
- 토큰 활성화 후 fastapi → drf 통신 latency 영향 측정 (보통 영향 0)

## 6. 머지 전 확인 항목

### 6.1 Git
- [ ] 변경 파일 16개 모두 의도된 변경인지 `git diff` 검토
- [ ] 신규 파일 `apps/core/authentication.py` git add 확인
- [ ] commit 분리 권장: `B1`, `B2`, `B5`, `B3+B4`, `J1~J4`, `J5~J8`, `J9~J11` 단위 (cherry-pick 용이)

### 6.2 운영 영향
- [ ] `INTERNAL_SERVICE_TOKEN` 운영 .env 파일에 추가할지 결정 (옵트인이라 미설정도 가능)
- [ ] 운영 모니터링 대시보드에 새 console 메시지 노출 정책 결정

### 6.3 PR 작성 (실험 → 머지 결정 후)
- [ ] PR 제목: `refactor: Wave 1 — 정합·로깅 (16건)`
- [ ] PR 본문: 본 보고서 §2 변경 항목 + §4 검증 결과 요약

## 7. 다음 단계

**Wave 2 — JWT 인증 보안** (분석 베이스: [99_security_summary.md PR-S2](../../../codereviews/2026_05_09/99_security_summary.md), [01_auth_session.md R1](../../js/2026_05_09/01_auth_session.md))

준비된 변경 항목:
- B6~B8: SimpleJWT blacklist 도입 + ROTATE_REFRESH_TOKENS + ACCESS_TOKEN_LIFETIME 단축
- B9: LogoutView refresh 블랙리스트
- B10: PasswordChangeView 토큰 블랙리스트 (선택)
- J12: `Auth._refresh` 싱글톤 동시성 가드
- J13: Logout body에 refresh 동봉

Wave 2 시작 시점에 동일 양식의 보고서 [docs/refactor/waves/2026_05_09/wave_2.md](wave_2.md) 작성 예정.

## 8. 결정 로그 (전체 Wave 1 핵심 의사결정)

### 8.1 옵트인 토큰 인증 (vs 강제 활성화)
**선택**: 옵트인
**이유**: 기존 환경 영향 0 + 단계적 활성화로 회귀 격리 가능. 운영자가 env 한 줄 설정하면 즉시 활성화.

### 8.2 단일 환경변수 (vs 양 서비스 별도)
**선택**: `INTERNAL_SERVICE_TOKEN` 단일
**이유**: 운영 단순성. drf와 fastapi가 같은 토큰을 양방향으로 사용 가능. 별도 변수면 동기화 부담.

### 8.3 console.warn (vs throw / 사용자 알림)
**선택**: 거의 모든 silent failure에 console.warn
**이유**: 사용자 영향 0 + 가시성 확보. 다음 단계에서 Sentry 등 도입 시 자동 수집.

### 8.4 dead code 즉시 제거 (vs 보존 + 정합 변경)
**선택**: J1 levelLabel 즉시 제거
**이유**: grep 결과 0건 호출자 확인 후 결정. 보존은 언제 쓸지 불명확한 상태로 유지 → 미래 혼동.

### 8.5 ServiceTokenAuthentication 위치 (`apps/core/` vs 도메인별)
**선택**: `apps/core/authentication.py`
**이유**: 여러 도메인이 공통 사용 (monitoring, positioning, alerts). core/permissions.py와 동일 위치 패턴.

### 8.6 commit 분리 (vs 단일 커밋)
**선택**: 각 항목별 분리 (B1·B2·B5·B3+B4·J1~J4·J5~J8·J9~J11)
**이유**: cherry-pick 용이, PR 분할 가능, blame 정확.
