#!/usr/bin/env bash
# 기능별-curl.sh — 기능정의서 기능ID별 실행증명 curl (각 기능 1~2개)
#
# 목적: 관리자페이지+메인대시보드의 API 보유 기능을, 엑셀 '증명' 칼럼에 붙일
#       curl 실행증명으로 1~2개씩 제공. 모든 경로는 코드(urls.py) 실측 확정.
# 검증: 2026-06-05 / 브랜치 devleop / 인증 = JWT(SimpleJWT)
#
# 사용법:
#   1) 스택 가동 확인 (docker compose ps — drf running)
#   2) 아래 ADMIN_USER/ADMIN_PW 를 super-admin 계정으로 채움
#   3) bash 기능별-curl.sh           # 읽기(GET)만 실행 — 안전
#      WRITE=1 bash 기능별-curl.sh   # 쓰기(POST/PATCH/DELETE)까지 — ⚠️ DB 변경
#
# 규칙: 읽기 블록은 무조건 실행, 쓰기 블록은 WRITE=1 일 때만. {ID} 류는 실데이터로 교체.

set -uo pipefail
BASE="${BASE:-http://localhost:8000}"
ADMIN_USER="${ADMIN_USER:-admin}"
ADMIN_PW="${ADMIN_PW:-xptmxm123!}"
WRITE="${WRITE:-0}"

# ── LGN-05  로그인 = 모든 curl 의 전제(JWT access 발급) ──────────────────
echo "== LGN-05 POST /api/auth/login/ =="
ACCESS=$(curl -s -X POST "$BASE/api/auth/login/" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"$ADMIN_USER\",\"password\":\"$ADMIN_PW\"}" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("access",""))')
if [ -z "$ACCESS" ]; then echo "로그인 실패 — 계정 확인"; exit 1; fi
AUTH="Authorization: Bearer $ACCESS"
JSON='Content-Type: application/json'
g(){ echo "== $1 =="; shift; curl -s -H "$AUTH" "$@" | head -c 600; echo; echo; }       # GET
w(){ if [ "$WRITE" = "1" ]; then echo "== $1 (WRITE) =="; shift; curl -s -H "$AUTH" -H "$JSON" "$@" | head -c 600; echo; echo; else echo "-- $1 (skip: WRITE=1 필요) --"; fi; }

# 동적 이벤트 ID — 이벤트는 시점별 id 가 바뀌므로 목록 첫 행을 사용 (MEVD 용)
EVID=$(curl -s -H "$AUTH" "$BASE/alerts/api/events/" | python3 -c 'import sys,json;r=json.load(sys.stdin).get("results") or [];print(r[0]["id"] if r else 1)')

###############################################################################
# 관리자페이지 (admin-panel)
###############################################################################

# ── USR 사용자 관리 ──
g "USR-01 사용자 목록"            "$BASE/api/admin/accounts/?page=1&page_size=20"
w "USR-03 사용자 등록"            "$BASE/api/admin/accounts/" -X POST -d '{"username":"qa_demo","password":"Qa!demo1234","name":"QA데모"}'

# ── ORG 조직 관리 ──
g "ORG-01 조직 트리"              "$BASE/api/admin/organizations/tree/"
g "ORG-05 부서 상세"             "$BASE/api/admin/departments/3/"

# ── POS 직위 관리 ── (전용 어드민 API 미구현 — 증명 대상 아님)

# ── EQP 설비 관리 ── (※ 페이지 미연결, API 는 완비 → 백엔드 증명용)
g "EQP-01 설비 목록"             "$BASE/api/equipments/"
w "EQP-03 설비 등록"             "$BASE/api/equipments/" -X POST -d '{"facility":1,"name":"QA설비"}'

# ── CMM 공통 코드 ── (2026-06-05 @extend_schema 보강 완료)
g "CMM-01 코드그룹 목록"          "$BASE/api/admin/code-groups/"
w "CMM-02 코드 생성"             "$BASE/api/admin/code-groups/1/codes/" -X POST -d '{"code":"QA","name":"QA코드","sort_order":99}'

# ── GAS 유해가스 센서 ──
g "GAS-01 센서 목록"             "$BASE/api/gas-sensors/"
g "GAS-04 센서 상세"             "$BASE/api/gas-sensors/1/"

# ── SPW 스마트전력시스템 ──
g "SPW-01 전력장치 목록"          "$BASE/api/power-devices/"
w "SPW-07 연결 확인(TCP)"         "$BASE/api/power-devices/check-connection/" -X POST -d '{"ip_address":"127.0.0.1","port":502}'

# ── LOC/MAP 위치노드·지도편집 ──
g "LOC-01 지도객체 조회"          "$BASE/api/map-editor/objects/?facility_id=1"
w "MAP-06 운영 반영(저장)"        "$BASE/api/map-editor/save/" -X POST -d '{"facility_id":1,"objects":[]}'

# ── THR 임계치 ── (2026-06-05 @extend_schema 보강 완료)
g "THR-01 임계치그룹 목록"        "$BASE/api/admin/threshold-groups/"
w "THR-02 임계치 수정"           "$BASE/api/admin/thresholds/1/" -X PATCH -d '{"warning_value":30}'

# ── RSK 위험 기준 ── (시나리오 C 인접: 즉시 반영)
g "RSK-03 위험기준 목록"          "$BASE/api/admin/risk-standards/"
w "RSK-04 위험기준 수정"          "$BASE/api/admin/risk-standards/1/" -X PATCH -d '{"display_color":"#ff3b30"}'

# ── DAT 운영 데이터 ──
g "DAT-01 가스 데이터"            "$BASE/api/admin/gas-data/?page=1"
g "DAT-02 전력 데이터"            "$BASE/api/admin/power-data/?page=1"
g "DAT-04 보관주기 목록"          "$BASE/api/admin/retention-policies/"
w "DAT-05 보관주기 수정"          "$BASE/api/admin/retention-policies/1/" -X PATCH -d '{"retention_days":14}'

# ── EVT 이벤트 이력 (읽기전용) ──
g "EVT-03 이벤트 이력"            "$BASE/api/admin/alerts/events/?page=1"

# ── NOT 알림 정책 ── (시나리오 C: 알림정책 즉시 반영)
g "NOT-01 알림정책 목록"          "$BASE/api/admin/alerts/policies/"
w "NOT-02 알림정책 수정"          "$BASE/api/admin/alerts/policies/1/" -X PATCH -d '{"is_active":true}'

# ── NTC 공지사항 ──
g "NTC-01 공지 목록"             "$BASE/api/admin/notices/"
w "NTC-02 공지 등록"             "$BASE/api/admin/notices/" -X POST -d '{"title":"QA공지","content":"본문"}'

# ── SAF 안전 점검 ──
g "SAF-01 체크리스트 상태"        "$BASE/api/admin/safety/checklist/state/"
w "SAF-02 섹션 추가"             "$BASE/api/admin/safety/sections/" -X POST -d '{"title":"QA섹션"}'

# ── VR 교육 (admin) ──
g "VR-01 VR콘텐츠 조회"           "$BASE/api/admin/training/vr-training/?facility_id=1"

# ── LOG 로그 조회 ──
g "LOG-01 시스템 로그"            "$BASE/api/admin/system-logs/?page=1"
g "LOG-02 활동 로그"             "$BASE/api/admin/activity-logs/?page=1"
g "LOG-03 연동 로그"             "$BASE/api/admin/integration-logs/?page=1"
g "MAP-09 지도편집 로그"          "$BASE/api/admin/map-edit-logs/?page=1"

###############################################################################
# 메인대시보드
###############################################################################

# ── PRF 프로필 ──
g "PRF-01 프로필 로드"            "$BASE/api/auth/profile/"
w "PRF-08 비밀번호 변경"          "$BASE/api/auth/password/change/" -X POST -d '{"current_password":"<현재>","new_password":"<신규>"}'

# ── CHK 안전 확인 체크리스트 ──
g "CHK-01 활성 체크리스트"        "$BASE/api/safety/checklist/active/"
w "CHK-08 완료 확인"             "$BASE/dashboard/api/safety-status/" -X POST -d '{}'

# ── HST 안전 이력 ──
g "HST-01 월간 이력"             "$BASE/dashboard/api/safety-history/"
g "HST-07 전체 작업자 목록"        "$BASE/dashboard/api/workers-list/"

# ── VR 교육 (대시보드) ──
g "VR(dash)-01 VR콘텐츠"         "$BASE/dashboard/api/vr-content/active/"
w "VR(dash)-08 진행 저장"        "$BASE/dashboard/api/vr-progress/" -X POST -d '{"content_id":1,"position":12.5}'

# ── RTM 실시간 모니터링 ──
w "RTM-09 구역 완료(생성)"        "$BASE/api/geofences/" -X POST -d '{"name":"QA구역","facility":1,"polygon":[]}'

# ── MGS / MPW 가스·전력 차트 임계치 ──
g "MGS-09 가스 임계치"            "$BASE/api/monitoring/gas/thresholds/"
g "MPW-09 전력 임계치"            "$BASE/api/monitoring/power/thresholds/"

# ── MEV / MEVD 이벤트 목록·상세 ──
g "MEV-01 이벤트 목록"            "$BASE/alerts/api/events/"
g "MEV-03 조치필요 탭"            "$BASE/alerts/api/events/?status=pending"
g "MEVD-01 이벤트 상세"           "$BASE/alerts/api/events/$EVID/"
w "MEVD-11 상태 전이"            "$BASE/alerts/api/events/$EVID/update_status/" -X PATCH -d '{"status":"in_progress"}'

# ── MNU 메뉴 (조회만 구현) ──
g "MNU-01 메뉴 조회"             "$BASE/dashboard/api/menu/"

# ── WS 실시간 (DSH-14/15·MGS-01·MPW-01·WKR-02·MEV-11·RTM-14) ──
#   /ws/... 는 curl 불가 → 서버측 알람 푸시 로그(IntegrationLog transmit, target=DRF→FastAPI)로 증명.
#   keyword=alarm_type 이 WS 푸시 행만 분리(FastAPI→DRF 수집행 제외). 총 43,261건(success 41,450).
g "WS푸시 증명 (DRF→FastAPI 알람 푸시 로그)" "$BASE/api/admin/integration-logs/?integration_type=transmit&keyword=alarm_type&page_size=5"

echo "== 완료 (WRITE=$WRITE) =="
