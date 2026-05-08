# API 응답 봉투 표준 (Response Convention)

> 기준일: 2026-05-04
> 목적: drf-server / fastapi-server 양쪽 API 응답 구조를 통일하여
> 프론트엔드의 응답 처리 코드를 단일화한다.

---

## 0. 적용 범위

- **drf-server**: `/api/**` 모든 JSON 엔드포인트
- **fastapi-server**: `/api/**`, `/internal/**` JSON 엔드포인트
- **WebSocket 메시지**: 본 문서 적용 안 함 (별도 페이로드 스키마)
- **HTML 페이지 응답**: 본 문서 적용 안 함

---

## 1. HTTP 상태 코드 (필수 준수)

| 상황 | 코드 |
|---|---|
| 조회 성공 | `200 OK` |
| 생성 성공 | `201 Created` |
| 비동기 수락 (Celery 큐잉 등) | `202 Accepted` |
| 본문 없는 성공 (DELETE 등) | `204 No Content` |
| 입력 검증 실패 | `400 Bad Request` |
| 인증 실패 (토큰 없음/만료) | `401 Unauthorized` |
| 권한 부족 (인증은 됨, 접근 거부) | `403 Forbidden` |
| 리소스 없음 | `404 Not Found` |
| 메서드 불일치 | `405 Method Not Allowed` |
| 비즈니스 룰 위반 (중복, 충돌) | `409 Conflict` |
| 서버 내부 오류 | `500 Internal Server Error` |
| 외부 의존성 장애 (DRF↔FastAPI 통신 실패) | `502 Bad Gateway` |
| 임시 사용 불가 (서비스 중단) | `503 Service Unavailable` |

**금지:** 에러 응답에 200을 사용하지 않는다 (`{"ok": false}` 같은 200 에러 패턴 X).

---

## 2. 단일 객체 응답 (조회/생성/수정)

성공 응답은 **객체를 그대로** 반환한다 (래핑 없음).

```json
{
  "id": 12,
  "name": "GAS-001",
  "is_active": true,
  "created_at": "2026-05-04T10:30:00+09:00"
}
```

- 키 이름: `snake_case` (Python·JS 모두에서 일관)
- 시간: ISO 8601 with timezone offset
- Boolean: `is_*`, `has_*`, `can_*` 접두어
- `null` vs `0`: 센서 값에서 `0`은 유효값, 미측정은 `null`

---

## 3. 페이지네이션 응답 (목록 조회)

**모든 목록 API는 다음 5개 키를 반드시 포함**한다.

```json
{
  "results": [
    { "...": "..." }
  ],
  "total": 137,
  "page": 1,
  "page_size": 20,
  "has_next": true
}
```

| 키 | 타입 | 설명 |
|---|---|---|
| `results` | `array` | 페이지에 해당하는 객체 배열 (빈 페이지면 `[]`) |
| `total` | `integer` | 전체 항목 수 |
| `page` | `integer` | 현재 페이지 번호 (1-based) |
| `page_size` | `integer` | 페이지당 항목 수 |
| `has_next` | `boolean` | 다음 페이지 존재 여부 |

**금지된 변형:**
- `records`, `items`, `data`, `list` — 모두 `results`로 통일
- `count` (DRF 기본값) — `total`로 통일
- `next`/`previous` URL — 본 표준에서는 사용 안 함 (`has_next`만)

**쿼리스트링:** `?page=1&page_size=20` 표준. 기본값은 `page=1`, `page_size=20`. 최대 `page_size=100`.

---

## 4. 에러 응답 (4xx / 5xx)

```json
{
  "error": {
    "code": "validation_failed",
    "message": "필수 필드가 누락되었습니다.",
    "details": {
      "name": ["이 필드는 필수입니다."],
      "threshold": ["0보다 큰 정수여야 합니다."]
    }
  }
}
```

| 키 | 타입 | 설명 |
|---|---|---|
| `error.code` | `string` | 기계 식별용 에러 코드 (snake_case) |
| `error.message` | `string` | 사용자 노출 가능한 한글 메시지 (1줄) |
| `error.details` | `object?` | 필드 단위 검증 오류 등 추가 정보 (옵션) |

### 표준 에러 코드

| code | 발생 상황 | HTTP |
|---|---|---|
| `validation_failed` | 입력 검증 실패 | 400 |
| `authentication_required` | 토큰 없음/만료 | 401 |
| `invalid_credentials` | 로그인 실패 | 401 |
| `permission_denied` | 권한 부족 | 403 |
| `not_found` | 리소스 없음 | 404 |
| `conflict` | 중복 생성, 상태 충돌 | 409 |
| `internal_error` | 서버 내부 오류 | 500 |
| `upstream_unavailable` | DRF↔FastAPI 통신 실패 | 502 |

**금지:**
- 에러 응답에 200 사용
- `{"ok": false, "msg": "..."}` 같은 평면 구조 (`error` 객체로 감쌀 것)
- 스택트레이스 노출 (개발 환경에서도 `details`에는 검증 오류만)

---

## 5. 비동기 수락 응답 (202)

Celery 태스크 큐잉, 배치 처리 등.

```json
{
  "task_id": "5a8f...",
  "status": "queued",
  "submitted_at": "2026-05-04T10:30:00+09:00"
}
```

---

## 6. 적용 우선순위 (마이그레이션 순서)

본 표준은 Phase 2 PR에서 drf-server admin-panel API 14곳을 일괄 적용하고,
Phase 3에서 프론트가 이 표준에 맞춰 응답을 처리한다.

1. **Phase 2 (drf-server):**
   - `apps.core.pagination.AdminPagination` 응답 구조를 본 표준으로 조정
   - 4xx/5xx 응답을 본 표준 `{error: {code, message, details?}}` 구조로 변환할 글로벌 예외 핸들러는 **Phase 4**에서 도입 — Phase 2는 코드 변경 없는 항목(키 이름)만 통일
2. **Phase 3 (프론트):**
   - `Auth.apiFetch`가 응답 키를 본 표준으로 가정하고 처리
   - 이전 응답 형식과의 호환 코드 제거
3. **Phase 4 (drf-server):**
   - 글로벌 예외 핸들러로 `{error: {...}}` 자동 변환
   - drf-spectacular로 본 표준이 OpenAPI에 반영
4. **Phase 5 (fastapi-server):**
   - `response_model` + 전역 예외 핸들러로 동일 표준 적용

---

## 7. 검증 체크리스트

PR 머지 전 다음을 확인:

- [ ] 새/수정 엔드포인트 모두 본 문서의 HTTP 상태 코드 표 준수
- [ ] 목록 조회는 `{results, total, page, page_size, has_next}` 5키 포함
- [ ] 에러 응답이 `{error: {code, message}}` 구조
- [ ] 키 이름이 `snake_case`
- [ ] 시간 필드가 ISO 8601 with timezone
- [ ] 검증 오류는 `error.details`에 필드별로
- [ ] 200 + 에러 메시지 패턴 부재 (반드시 4xx/5xx)

---

## 변경 이력

- 2026-05-04: 초안 작성 (Phase 1)
