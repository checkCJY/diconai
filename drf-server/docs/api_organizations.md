# 조직 관리 API 명세

> **Base URL** : `/api/admin/`
> **인증** : `Authorization: Bearer {access_token}` (슈퍼관리자 전용)
> **Content-Type** : `application/json`

---

## 목차

1. [조직도 트리 조회](#1-조직도-트리-조회)
2. [부서 생성](#2-부서-생성)
3. [부서 상세 조회](#3-부서-상세-조회)
4. [부서 수정](#4-부서-수정)
5. [부서 삭제](#5-부서-삭제)
6. [구성원 목록 조회](#6-구성원-목록-조회)
7. [구성원 추가](#7-구성원-추가)
8. [부서 이동](#8-부서-이동)
9. [소속 제외](#9-소속-제외)
10. [조직장 임명](#10-조직장-임명)

---

## 1. 조직도 트리 조회

```
GET /api/admin/organizations/tree/
```

회사 목록과 각 회사의 부서 트리, 조직 없음 인원 수를 반환합니다.

**Response `200`**
```json
{
  "companies": [
    {
      "id": 1,
      "name": "(주)가림이앤지",
      "departments": [
        {
          "id": 1,
          "name": "경영지원팀",
          "code": "001",
          "leader_id": 3,
          "leader_name": "홍길동",
          "children": [
            {
              "id": 5,
              "name": "기획파트",
              "code": "001-1",
              "leader_id": null,
              "leader_name": null,
              "children": []
            }
          ]
        }
      ]
    }
  ],
  "no_dept_count": 3
}
```

---

## 2. 부서 생성

```
POST /api/admin/departments/
```

**Request Body**
| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `name` | string | ✅ | 부서명 |
| `code` | string | ✅ | 부서 코드 (unique) |
| `company` | integer | - | 회사 ID |
| `parent` | integer | - | 상위 부서 ID |

```json
{ "name": "신규팀", "code": "999", "company": 1 }
```

**Response `201`**
```json
{
  "id": 10,
  "name": "신규팀",
  "code": "999",
  "company_id": 1,
  "company_name": "(주)가림이앤지",
  "parent_id": null,
  "leader_id": null,
  "leader_name": null,
  "created_at": "2026-04-29T10:00:00Z",
  "updated_at": "2026-04-29T10:00:00Z",
  "updated_by_name": "홍길동"
}
```

---

## 3. 부서 상세 조회

```
GET /api/admin/departments/{id}/
```

**Response `200`**
```json
{
  "id": 1,
  "name": "경영지원팀",
  "code": "001",
  "company_id": 1,
  "company_name": "(주)가림이앤지",
  "parent_id": null,
  "leader_id": 3,
  "leader_name": "홍길동",
  "created_at": "2025-03-11T11:04:00Z",
  "updated_at": "2025-03-11T11:04:00Z",
  "updated_by_name": "홍길동"
}
```

---

## 4. 부서 수정

```
PATCH /api/admin/departments/{id}/
```

**Request Body** (변경할 필드만 전송)
| 필드 | 타입 | 설명 |
|------|------|------|
| `name` | string | 부서명 |
| `code` | string | 부서 코드 |

```json
{ "name": "경영기획팀" }
```

**Response `200`** — 수정된 부서 상세 (3번과 동일 구조)

---

## 5. 부서 삭제

```
DELETE /api/admin/departments/{id}/
```

소프트 삭제(`is_active=False`). 구성원 데이터는 유지됩니다.

**Response `204`** — No Content

---

## 6. 구성원 목록 조회

```
GET /api/admin/departments/{id}/members/
GET /api/admin/departments/none/members/    ← 조직 없음
```

조직장이 목록 최상단에 위치합니다.

**Query Parameters**
| 파라미터 | 타입 | 기본값 | 설명 |
|---------|------|--------|------|
| `q` | string | - | 이름 또는 아이디 검색 |
| `page` | integer | 1 | 페이지 번호 |
| `page_size` | integer | 20 | 페이지 크기 (최대 100) |

**Response `200`**
```json
{
  "results": [
    {
      "id": 3,
      "name": "홍길동",
      "username": "super.admin",
      "position": "대표이사",
      "status": "active",
      "is_leader": true
    },
    {
      "id": 7,
      "name": "김한국",
      "username": "hankook",
      "position": "이사",
      "status": "locked",
      "is_leader": false
    }
  ],
  "total": 28,
  "page": 1,
  "page_size": 20
}
```

**`status` 값**
| 값 | 설명 |
|----|------|
| `active` | 사용 |
| `locked` | 잠금 |
| `inactive` | 비활성 |

---

## 7. 구성원 추가

```
POST /api/admin/departments/{id}/members/add/
```

**Request Body**
| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `user_ids` | integer[] | ✅ | 추가할 사용자 ID 목록 |
| `keep_previous` | boolean | - | `true`: 겸직(기존 소속 유지), `false`: 주소속 변경 (기본 `false`) |

```json
{ "user_ids": [1, 2, 3], "keep_previous": false }
```

**Response `200`**
```json
{ "ok": true, "added": 3 }
```

---

## 8. 부서 이동

```
POST /api/admin/departments/{id}/members/move/
```

현재 부서(`{id}`)의 구성원을 다른 부서로 이동합니다.

**Request Body**
| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `user_ids` | integer[] | ✅ | 이동할 사용자 ID 목록 |
| `target_dept_id` | integer | ✅ | 이동 대상 부서 ID |
| `keep_previous` | boolean | - | `true`: 겸직, `false`: 주소속 변경 (기본 `false`) |

```json
{ "user_ids": [1, 2], "target_dept_id": 5, "keep_previous": false }
```

**Response `200`**
```json
{ "ok": true, "moved": 2 }
```

---

## 9. 소속 제외

```
POST /api/admin/departments/{id}/members/remove/
```

해당 부서에서 구성원을 제외합니다. 다른 소속 부서가 없으면 자동으로 **조직 없음** 상태가 됩니다.

**Request Body**
| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `user_ids` | integer[] | ✅ | 제외할 사용자 ID 목록 |

```json
{ "user_ids": [1, 2, 3] }
```

**Response `200`**
```json
{ "ok": true, "removed": 3 }
```

---

## 10. 조직장 임명

```
POST /api/admin/departments/{id}/members/assign-leader/
```

단일 사용자만 조직장으로 임명 가능합니다.

**Request Body**
| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `user_id` | integer | ✅ | 조직장으로 임명할 사용자 ID |

```json
{ "user_id": 3 }
```

**Response `200`**
```json
{
  "ok": true,
  "leader": { "id": 3, "name": "홍길동" }
}
```

---

## 공통 에러 응답

| 상태 코드 | 설명 |
|-----------|------|
| `400` | 요청 데이터 오류 |
| `401` | 인증 토큰 없음 또는 만료 |
| `403` | 슈퍼관리자 권한 없음 |
| `404` | 대상 리소스 없음 |

```json
{ "error": "에러 메시지" }
```

---

## 감사 로그 (SystemLog)

모든 쓰기 작업은 `system_log` 테이블에 자동 기록됩니다.

| API | `action_type` |
|-----|--------------|
| 부서 생성 | `dept_create` |
| 부서 수정 | `dept_update` |
| 부서 삭제 | `dept_delete` |
| 구성원 추가 | `member_add` |
| 부서 이동 | `member_move` |
| 소속 제외 | `member_remove` |
| 조직장 임명 | `leader_assign` |
