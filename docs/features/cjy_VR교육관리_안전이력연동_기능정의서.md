# 기능정의서 — VR 교육 관리 어드민 + 안전 확인 이력 DB 통합

> 작성일: 2026-05-12
> 작성자: CJY
> 브랜치: `feature/admin_safety_check`
> 커밋: `abcf7ba`
> 대상 기능 ID: **VR 교육 관리(어드민) · 작업자 VR 시청 · 안전 확인 이력**

---

## 1. 기능 목록표

| 대분류 | 화면명 | 기능ID | 기능명 | 기능 목적 | 사용자 시나리오 | 백엔드 처리 | 프론트엔드 처리 | 참고사항 |
|:--|:--|:--|:--|:--|:--|:--|:--|:--|
| 안전 확인 관리 | VR 교육 관리 (어드민) | VR-A1 | 단일 콘텐츠 조회 | 공장별 활성 VR 콘텐츠 1건의 메타·재생 시간 노출 | 어드민 진입 → facility별 콘텐츠 조회 | `VRTrainingDetailView`가 `select_related`로 콘텐츠+facility+updated_by 단일 쿼리 | `<video controls>` + 우측 정보 패널 dl | 콘텐츠 미등록 시 `empty=true` 응답 |
| 안전 확인 관리 | VR 교육 관리 (어드민) | VR-A2 | 영상 교체 (multipart) | 단일 콘텐츠 교체 + 자동 재생 시간 추출 | [영상 교체] → 모달 → 파일 선택 → [저장] | `VRTrainingReplaceView` → MEDIA에 파일 저장 → `probe_duration_seconds` → `replace_vr_content` 트랜잭션 | FormData multipart POST `/replace/` | ffmpeg 미설치 시 duration None fallback |
| 안전 확인 관리 | VR 교육 관리 (어드민) | VR-A3 | 메타 수정 (PATCH) | 영상 미수반 이름/설명/운영 메모 수정 | [수정] → 모달 → 텍스트 변경 → [저장] | `VRTrainingMetaUpdateView` → `update_vr_metadata` | JSON PATCH `/<pk>/` | file 누락 시 PATCH 분기 |
| 안전 확인 관리 | VR 교육 관리 (어드민) | VR-A4 | 이전 파일 디스크 삭제 | 영상 교체 시 디스크 용량 누적 차단 | 교체 직후 이전 파일 자동 삭제 | `transaction.on_commit`으로 unlink 예약 + path traversal 가드 | 없음 | DB `VRTrainingRevision`에 메타 스냅샷 보존 |
| 안전 확인 관리 | 작업자 VR 교육 페이지 | VR-W1 | 어드민 콘텐츠 동적 연동 | 작업자 facility의 등록된 영상 재생 | 페이지 진입 → 본인 facility 콘텐츠 자동 로드 | `safety_vr_page`가 context에 `vr_content_id`/`vr_content_url` 주입 | `<source src="{{ vr_content_url }}">` | 미등록 facility → 빈 상태 안내 카드 (static 폴백 제거) |
| 안전 확인 관리 | 작업자 VR 교육 페이지 | VR-W2 | Skip 방지 강화 | 영상 끝까지 시청해야 완료 가능 | seek/키보드/속도 조작 불가 | 없음 | seeking 가드(lastPlayheadTime)·tabindex=-1·ratechange 고정·키보드/우클릭 차단 | controls 표시되나 진행바 클릭만 비활성 |
| 안전 확인 관리 | 작업자 VR 교육 페이지 | VR-W3 | 이어보기 + 가드 | 이탈 후 재진입 시 위치 복원, 단 다른 사용자/영상 누설 차단 | 페이지 재진입 시 동일 (user, content)면 복원 | `VRProgressView` 세션 dict (user_id, content_id, position) | GET 응답의 content_id가 페이지 data-content-id와 일치 시에만 currentTime 적용 | 세션은 브라우저 단위라 user_id 가드 필수 |
| 안전 확인 관리 | 안전 확인 이력 | VR-H1 | 이력 DB 연동 | 메인 카드 ↔ 캘린더 데이터 일치 + 다른 기기 일관성 | 완료 처리 → 이력 캘린더 ✓ 표시 | `MySafetyStatusView.post`가 세션 + `SafetyCheckSession` 두 곳에 dual-write | 없음 (기존 API 호출 그대로) | `SafetyCheckSession.vr_completed_at` 신규 필드 |
| 안전 확인 관리 | 안전 확인 이력 | VR-H2 | 캘린더 데이터 통일 | 한 모델에서 체크리스트·VR 동시 조회 | 월 단위 캘린더 자동 표시 | `SafetyHistoryAPIView`가 `SafetyCheckSession` 단일 쿼리로 두 시리즈 채움 | 기존 캘린더 그대로 | `vr_done: False` 하드코딩 제거 |

---

## 2. 요구사항 정의서

### [REQ-VR-A1] 단일 콘텐츠 조회 (어드민)

- **분류**: 신규 기능
- **중요도**: 상
- **기능 목적**: 공장별로 단 1건만 운영하는 VR 콘텐츠의 메타·영상·재생 시간을 어드민에 노출
- **요구사항 상세**:
  - URL: `GET /api/admin/training/vr-training/?facility_id=`
  - 권한: `[IsAuthenticated, IsSuperAdminOrFacilityAdmin]`
  - `_resolve_facility_id` 패턴: super_admin은 쿼리 파라미터, facility_admin은 본인 facility 강제
  - 응답에 `target_type`은 포함하지 않음 (운영 컨벤션상 화면 비노출)
- **모델**:
  - `VRTrainingContent` 부분 UniqueConstraint(`is_active=True`)로 facility당 1건 보장
  - 신규 필드: `duration_seconds (Integer, null)`, `operation_note (Text, blank)`
- **N+1 회피**: `select_related("target_facility", "updated_by")`

### [REQ-VR-A2] 영상 교체 (multipart) — 자동 재생 시간 추출

- **분류**: 신규 기능
- **중요도**: 상
- **기능 목적**: 어드민이 영상 파일을 업로드하면 서버가 재생 시간을 자동 계산해 저장
- **요구사항 상세**:
  - URL: `POST /api/admin/training/vr-training/replace/` (multipart/form-data)
  - 입력: `file` 필수 + `name`/`description`/`operation_note` 선택
  - 파일 검증: 확장자(mp4/webm/mov) + MIME prefix `video/` + 최대 500MB
  - 저장 경로: `MEDIA_ROOT/vr/<uuid4>.<ext>` → `request.build_absolute_uri`로 절대 URL 구성
  - 재생 시간 추출: `ffprobe` 시스템 바이너리 + `subprocess.run` 호출, 15초 타임아웃
- **트랜잭션 + 파일 시스템 원자성**:
  1. 트랜잭션 진입 전 `default_storage.save`로 파일 저장
  2. 트랜잭션 내부에서 DB UPDATE + `VRTrainingRevision` 이력 INSERT
  3. 이전 파일은 `transaction.on_commit`으로 unlink 예약 (롤백 시 보존)
  4. 서비스 호출 중 예외 발생 시 새 파일을 청소 후 예외 재전파
- **인프라**: drf 컨테이너 Dockerfile에 `apt-get install ffmpeg` 추가
- **Fallback**: ffprobe 미설치/타임아웃/파싱 실패 시 `duration_seconds=None` 저장 (업로드는 정상)

### [REQ-VR-A3] 메타 수정 (PATCH)

- **분류**: 신규 기능
- **중요도**: 중
- **기능 목적**: 영상 파일을 건드리지 않고 이름·설명·운영 메모만 수정
- **요구사항 상세**:
  - URL: `PATCH /api/admin/training/vr-training/<int:pk>/`
  - 권한 가드: `pk + facility_id` AND 조회 → 다른 공장 pk PATCH 시도는 404
  - 최소 1개 필드 요구 (`VRMetaUpdateSerializer.validate`)
  - service의 `update_vr_metadata`는 변경된 필드만 `update_fields`로 save

### [REQ-VR-A4] 이전 파일 디스크 삭제 + 이력 보존

- **분류**: 신규 기능
- **중요도**: 상 (디스크 용량 누적 차단)
- **기능 목적**: 단일 콘텐츠 정책상 영상 1건만 유지하되 교체 이력은 감사용으로 보존
- **path traversal 가드**:
  - URL에서 추출한 경로를 `MEDIA_ROOT + os.sep` prefix와 정규화 후 비교
  - 외부 URL이거나 prefix 불일치는 silent skip → 시스템 파일 삭제 시도 차단
- **이력 모델**: `VRTrainingRevision`에 `previous_url`, `previous_name`, `replaced_by`(SET_NULL) 보존
- **실패 허용**: 파일 없음/권한 오류는 로그만 남기고 무시 (디스크 고아 파일은 DB 정합성보다 사소한 비용)

### [REQ-VR-W1] 작업자 VR 페이지 어드민 콘텐츠 동적 연동

- **분류**: 신규 기능
- **중요도**: 상
- **기능 목적**: 어드민이 등록한 영상이 작업자 페이지에 실시간 반영
- **요구사항 상세**:
  - `safety_vr_page` view가 작업자 `facility_id`로 `get_vr_content_for_facility` 호출
  - context: `vr_content_id`, `vr_content_url`, `vr_content_name`
  - 템플릿에서 `<source src="{{ vr_content_url }}">` 직접 렌더
  - `<video data-content-id="{{ vr_content_id }}">` 속성으로 클라이언트 가드 연동
- **빈 상태 처리**:
  - `vr_content_url`이 None이면 `<video>` 자체를 렌더하지 않고 `.video-empty` 안내 카드 노출
  - **이전 버전의 static 폴백(`safety_vr.mp4`)은 제거** → 영상 저장 경로 `media/vr/` 일원화
  - JS는 `if (!video) return;`으로 안전하게 조기 종료
- **facility 폴백 정책**: `user.facility_id || get_default_facility_id()` — 단일 공장 단계 한정. 다중 공장 전환 시 작업자(worker) 폴백 제거 필요 (후속 과제)

### [REQ-VR-W2] Skip 방지 강화

- **분류**: 보안/정책 보강
- **중요도**: 상
- **기능 목적**: 산업 안전 교육의 핵심 — 끝까지 시청해야만 완료 처리
- **다층 가드 (각각 다른 우회 경로 차단)**:
  1. **seeking 가드**: `lastPlayheadTime`과 0.5초 이상 어긋난 모든 currentTime 변경을 직전 위치로 되돌림. 이어보기 복원만 `allowOneSeek` 플래그로 1회 허용.
  2. **CSS pointer-events**: `::-webkit-media-controls-timeline { pointer-events: none; }` → 진행바 클릭 자체 비활성 (Chrome/Edge/Safari)
  3. **재생 속도 고정**: `ratechange` 이벤트로 `playbackRate=1` 강제 → DevTools 조작도 즉시 복귀
  4. **키보드 차단**: video 요소 + document 캡처 단계 이중 등록, `stopImmediatePropagation`으로 native 컨트롤 가로채기 전에 차단. 차단 키: 방향키/PageUp·Down/Home/End/J/L/0~9
  5. **포커스 거부**: `tabindex="-1"` + `focus` → 즉시 `blur` 호출
  6. **우클릭 메뉴**: `contextmenu` preventDefault → "다른 이름으로 저장"/"반복 재생" 등 메뉴 봉쇄
- **시간 표시**: `<video controls controlslist="nodownload noplaybackrate noremoteplayback" disablepictureinpicture>` → 진행률·시간 텍스트는 그대로 노출

### [REQ-VR-W3] 이어보기 + 누설 차단 가드

- **분류**: 신규 기능 + 보안 보강
- **중요도**: 상
- **기능 목적**: 이탈 후 재진입 시 이어보기를 제공하되, 다른 사용자·다른 영상의 위치가 잘못 적용되지 않도록 차단
- **세션 키 구조**:
  ```python
  session["vr_safety_progress"] = {
      "user_id": int | None,
      "content_id": int | None,
      "position": float,
  }
  ```
- **두 가지 가드**:
  - **user_id 가드** (서버): GET 시 세션 user_id ≠ request.user.id면 `{position: 0}` 반환 → 같은 브라우저에서 사용자 전환 후 진행도 누설 차단
  - **content_id 가드** (클라이언트): 페이지의 `data-content-id`와 GET 응답의 `content_id`가 일치할 때만 currentTime 적용 → 어드민이 영상 교체했을 때 이전 위치 점프 방지

### [REQ-VR-H1] 안전 확인 이력 DB 연동

- **분류**: 데이터 일관성 개선
- **중요도**: 상
- **기능 목적**: 메인 대시보드 "완료" 표시와 이력 캘린더 ✓ 표시의 데이터 소스를 하나로 통일
- **이전 문제점**:
  - 메인 대시보드: Django 세션 키 (`safety_checklist_done_date`, `safety_vr_done_date`) — 휘발성
  - 이력 캘린더: DB 조회 — `checklist_done`은 `SafetyStatus` 기반(채워질 일 없음), `vr_done`은 `False` 하드코딩
  - 결과: 메인은 "완료"인데 이력은 영구히 ✗
- **해결**: `SafetyCheckSession`에 `vr_completed_at (DateTime, null)` 1건 추가
  - 체크리스트 완료 → `is_completed=True`, `completed_at=now`
  - VR 완료 → `vr_completed_at=now`
  - 같은 (worker, date, revision) row의 다른 필드를 갱신 → "오늘의 안전 확인 1회" 묶음 의미 유지
- **dual-write**: `MySafetyStatusView.post`가 세션 키 저장과 동시에 `_record_completion_to_db` 호출
- **DB 폴백**: `MySafetyStatusView._is_done_today_in_db`로 세션이 비어있어도 DB에서 오늘자 완료 확인 → 다른 기기 로그인 시에도 메인 대시보드 표시 정확

### [REQ-VR-H2] 이력 캘린더 데이터 통일

- **분류**: 데이터 소스 변경
- **중요도**: 중
- **기능 목적**: 단일 쿼리로 체크리스트·VR 두 시리즈를 동시에 채움
- **이전**: `SafetyStatus`(체크리스트만) + `False`(VR 하드코딩)
- **변경 후**:
  ```python
  sessions = SafetyCheckSession.objects.filter(
      worker=target, date__year=year, date__month=month,
  ).values("date", "is_completed", "vr_completed_at")
  checklist_dates = {s["date"] for s in sessions if s["is_completed"]}
  vr_dates = {s["date"] for s in sessions if s["vr_completed_at"] is not None}
  ```
- **성능**: 월 최대 31 row, set 비교 → 가벼움

---

## 3. 데이터 모델 변경

### 3-1. VRTrainingContent (필드 2건 추가)

```python
duration_seconds = models.IntegerField(
    null=True, blank=True, verbose_name="재생 시간(초)",
)
operation_note = models.TextField(
    blank=True, default="", verbose_name="운영 메모",
)
```

**마이그레이션**: `apps/training/migrations/0002_add_duration_and_operation_note.py` (AddField 2건)

### 3-2. SafetyCheckSession (필드 1건 추가)

```python
vr_completed_at = models.DateTimeField(
    null=True, blank=True, verbose_name="VR 교육 완료 시각",
)
```

**마이그레이션**: `apps/safety/migrations/0012_safetychecksession_vr_completed_at.py` (AddField 1건)

### 3-3. 신규 모델 — 없음

본 작업은 **신규 모델 0건**, 기존 모델 필드 추가 3건만으로 모든 요구사항을 충족.

---

## 4. API 엔드포인트

### 4-1. 신규 어드민 API (`/api/admin/training/`)

| Method | Path | 응답 |
|---|---|---|
| GET | `vr-training/?facility_id=` | 단일 콘텐츠 detail 또는 `{empty: true}` |
| POST | `vr-training/replace/` | 200 detail (multipart 업로드) |
| PATCH | `vr-training/<int:pk>/` | 200 detail (메타만) |
| GET | `vr-training/<int:pk>/revisions/` | 이력 배열 (UI 미사용, API 완비) |

### 4-2. 변경된 기존 API

| Method | Path | 변경 사항 |
|---|---|---|
| GET | `/dashboard/api/safety-status/` | 세션이 비어있으면 DB 폴백 |
| POST | `/dashboard/api/safety-status/` | 세션 저장 + `SafetyCheckSession` dual-write |
| GET | `/dashboard/api/vr-progress/` | 응답에 `content_id` 추가, user_id 불일치 시 `{position: 0}` |
| POST | `/dashboard/api/vr-progress/` | 입력에 `content_id` 추가, 세션 키 구조 dict 변경 |
| GET | `/dashboard/api/safety-history/?month=` | `vr_done` 하드코딩 제거, `SafetyCheckSession` 단일 쿼리로 두 시리즈 동시 채움 |

---

## 5. 화면 / URL

| 화면 | URL | 권한 | 사이드바 토큰 |
|---|---|---|---|
| VR 교육 관리 (어드민) | `/admin-panel/safety/vr-training/` | super_admin + facility_admin | `vr_training` |
| 작업자 VR 교육 | `/dashboard/safety/vr/` | 인증 사용자 | — |

사이드바: `templates/components/admin_sidebar.html`의 "안전 정책/기준 관리" 다음 줄에 "VR 교육 관리" 추가.

---

## 6. 주요 정책 결정

| 결정 | 사유 |
|---|---|
| 영상 저장: URLField 유지 + MEDIA 업로드 | FileField 마이그레이션 회피 + 향후 S3 등 외부 저장소 전환 시 URL만 갱신하면 됨 |
| 재생 시간: ffprobe subprocess | Python 라이브러리 의존성 추가 없이 시스템 바이너리 활용. Docker 이미지에 1개 패키지(`ffmpeg`)만 추가 |
| 영상 교체: 같은 행 UPDATE | 부분 UniqueConstraint(`is_active=True`) 충돌 회피 + 코드 단순화. Revision 이력은 별도 모델 |
| 이전 파일 삭제: `transaction.on_commit` | DB 트랜잭션과 파일 시스템 원자성 분리. 롤백 시 파일 보존 |
| target_type 비노출 | 운영 단계에서 화면 요구가 facility 기반이라 type 개념 불필요. 모델은 유지하되 응답/UI에서 숨김 (확장 여지) |
| 새 모델 신설 거부 → 기존 SafetyCheckSession 활용 | 이력 추적 의미가 "안전 확인 1회 = 체크리스트 + VR" 묶음 → 같은 row 활용이 의미적으로 정확 |
| Skip 방지: 6중 가드 | 브라우저별·우회 경로별 사각지대 차단 (CSS pointer-events는 WebKit 전용이지만 JS seeking 가드가 백업) |
| 이어보기: 세션 기반 + 가드 | DB 모델 신설 없이 ~10줄 추가로 user/콘텐츠 누설 차단 가능. 다른 기기 이어보기는 산업 안전 시나리오 외 |

---

## 7. 함정 / 후속 과제

### 운영 시 주의

- **ffmpeg 미설치 시**: duration이 null로 저장되지만 업로드는 정상. 클라이언트 `<video>.loadedmetadata`가 시간 배지를 보강. 정확한 DB 저장이 필요하면 Dockerfile 재빌드 + 컨테이너 재시작.
- **active SafetyChecklistRevision 없을 때**: `SafetyCheckSession` 생성 자체가 실패해 dual-write가 silent skip. 메인 대시보드는 세션으로 일시 표시되나 이력에 ✗로 남음. 어드민이 체크리스트 1회 [반영 저장] 필요.
- **Firefox**: `::-webkit-media-controls-timeline`이 적용 안 되어 진행바 클릭이 가능. JS seeking 가드가 백업으로 잡지만 UX가 어색 (클릭 후 즉시 되돌아감).

### 후속 과제

| 과제 | 우선순위 | 메모 |
|---|---|---|
| 작업자(worker) facility 폴백 제거 | 중 | 다중 공장 전환 시 다른 공장 콘텐츠 노출 위험. `safety_vr_page`와 `_resolve_facility_id` 정리 |
| 신규 비즈니스 로직 테스트 작성 | 중 | `replace_vr_content` / `_safe_unlink_media` / dual-write / 가드 회귀 방지 |
| MIME 검증 화이트리스트 강화 | 하 | `video/*` prefix → `{"video/mp4", "video/webm", "video/quicktime"}` |
| `static/video/safety_vr.mp4` 파일 정리 | 하 | 코드 참조는 끊었음. `git rm`으로 디렉터리 정리 가능 |
| 다른 기기 이어보기 (DB 이동) | 보류 | 산업 안전 시나리오상 필요성 낮음. 요구 시 `VRViewProgress` 모델 신설 |
| 이력 모달 UI 추가 | 보류 | API는 완비됨 (`/api/admin/training/vr-training/<pk>/revisions/`) |

---

## 8. 검증 방법

### 8-1. 도커 환경 배포

```bash
docker compose build drf
docker compose up -d drf celery-worker celery-beat
# entrypoint가 자동으로 마이그레이션 실행
docker compose logs drf | grep "Applying"
# Applying training.0002_add_duration_and_operation_note
# Applying safety.0012_safetychecksession_vr_completed_at
docker compose exec drf ffprobe -version | head -1
```

### 8-2. 어드민 시나리오

1. `/admin-panel/safety/vr-training/` 진입 → 첫 등록 시 `empty=true` 응답 → "[영상 교체] 버튼을 눌러 첫 콘텐츠를 등록해 주세요" 노출
2. [영상 교체] → mp4 업로드 → 응답 JSON에 `duration_seconds`가 정수
3. 우상단 배지에 `mm:ss` 형식 표시 + 우측 정보 패널 "재생 시간"에 `M분 SS초`
4. 다시 한 번 [영상 교체] → 호스트 `drf-server/media/vr/`에 새 파일 1개만 남음 (이전 파일 자동 삭제)
5. `sqlite3 drf-server/db.sqlite3 "select count(*) from vr_training_revision"` → 교체 횟수와 일치

### 8-3. 작업자 시나리오

1. `/dashboard/safety/vr/` 진입 → 어드민이 등록한 영상 재생
2. 키보드 ←/→/L/숫자키 → 모두 무시
3. 진행바 클릭 (미시청 구간) → 즉시 되돌아감
4. DevTools 콘솔에서 `vrVideo.playbackRate=2` → 즉시 1로 복귀
5. 영상 50% 시청 → 다른 페이지 → 돌아오면 그 지점부터 재개
6. 어드민에서 영상 교체 → 작업자 페이지 새로고침 → 0초부터 시작 (content_id 가드)
7. 같은 브라우저에서 다른 계정으로 로그인 → 페이지 진입 → 0초부터 시작 (user_id 가드)

### 8-4. 안전 확인 이력 시나리오

1. 작업자 계정으로 체크리스트 완료 → VR 완료
2. 메인 대시보드 → "안전 확인 체크리스트 완료", "VR 교육 완료" 두 항목 노출
3. `/dashboard/safety/history/` 캘린더 → 오늘 날짜에 ✓ 안전 체크리스트 / ✓ VR 교육
4. 다른 브라우저로 로그인 → 메인 대시보드 → 두 항목 그대로 "완료" 표시 (DB 폴백)

---

## 9. 참고

- 코드 리뷰: `docs/codereviews/` 또는 PR description에 포함된 인라인 리뷰
- 커밋: `abcf7ba`
- 관련 모델: `apps/training/models/vr_training_content.py`, `apps/training/models/vr_training_revision.py`, `apps/safety/models/safety_check_session.py`
- 관련 컨벤션: `docs/conventions/dev_convention.md`, `.claude/CLAUDE.md`
