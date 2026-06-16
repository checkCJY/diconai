#!/usr/bin/env bash
# 기능별-curl-writes.sh — 쓰기 실행증명 (안전 모드, 데모 DB 무손상)
#
#  · 생성(POST): create → 캡처 → DELETE 라운드트립 (원상복구, CRUD 양방향 증명)
#  · 수정(PATCH): 현재값 읽어 동일값 PATCH (무변경 200 — 엔드포인트 동작만 증명)
#  · 위험/세션 항목: 사유 남기고 skip
# 검증: 2026-06-05 / 인증 JWT / 모든 경로 urls.py 실측
#
# 사용법: ADMIN_USER/ADMIN_PW 채운 뒤  bash 기능별-curl-writes.sh

set -uo pipefail
BASE="${BASE:-http://localhost:8000}"
ADMIN_USER="${ADMIN_USER:-admin}"
ADMIN_PW="${ADMIN_PW:-xptmxm123!}"

ACCESS=$(curl -s -X POST "$BASE/api/auth/login/" -H 'Content-Type: application/json' \
  -d "{\"username\":\"$ADMIN_USER\",\"password\":\"$ADMIN_PW\"}" \
  | python3 -c 'import sys,json;print(json.load(sys.stdin).get("access",""))')
[ -z "$ACCESS" ] && { echo "로그인 실패 — 계정 확인"; exit 1; }
A="Authorization: Bearer $ACCESS"; J="Content-Type: application/json"

# JSON 경로 추출 — pick: 원시값(id·path용) / pickj: json.dumps(본문 인라인용, bool→true/false)
pick(){ python3 -c "import sys,json
d=json.load(sys.stdin)
for p in '$1'.split('.'):
  d=d[int(p)] if isinstance(d,list) else d.get(p)
  if d is None: print(''); sys.exit()
print(d)"; }
pickj(){ python3 -c "import sys,json
d=json.load(sys.stdin)
for p in '$1'.split('.'):
  d=d[int(p)] if isinstance(d,list) else d.get(p)
print(json.dumps(d))"; }
hc(){ curl -s -o /dev/null -w "%{http_code}" "$@"; }   # HTTP 코드만

echo "############ CREATE → 캡처 → DELETE (가역) ############"

echo "== EQP-03 POST /api/equipments/ (설비 등록) =="
R=$(curl -s -H "$A" -H "$J" -X POST "$BASE/api/equipments/" -d '{"facility":1,"name":"QA증빙설비"}')
echo "$R" | head -c 220; echo
ID=$(echo "$R" | pick id)
[ -n "$ID" ] && echo "  ↩ cleanup DELETE /api/equipments/$ID/ → HTTP $(hc -H "$A" -X DELETE "$BASE/api/equipments/$ID/")"
echo

echo "== CMM-02 POST /api/admin/code-groups/1/codes/ (코드 생성) =="
R=$(curl -s -H "$A" -H "$J" -X POST "$BASE/api/admin/code-groups/1/codes/" -d '{"code":"QA_EVID","name":"증빙용코드","sort_order":99}')
echo "$R" | head -c 220; echo
ID=$(echo "$R" | pick id)
[ -n "$ID" ] && echo "  ↩ cleanup DELETE /api/admin/codes/$ID/ → HTTP $(hc -H "$A" -X DELETE "$BASE/api/admin/codes/$ID/")"
echo

echo "== NTC-02 POST /api/admin/notices/ (공지 등록) =="
R=$(curl -s -H "$A" -H "$J" -X POST "$BASE/api/admin/notices/" -d '{"title":"QA증빙공지","content":"증빙용 본문","category":"general"}')
echo "$R" | head -c 220; echo
ID=$(echo "$R" | pick id)
[ -n "$ID" ] && echo "  ↩ cleanup DELETE /api/admin/notices/$ID/ → HTTP $(hc -H "$A" -X DELETE "$BASE/api/admin/notices/$ID/")"
echo

echo "############ NO-OP PATCH (현재값 그대로 → 무변경 200) ############"

echo "== RSK-04 PATCH /api/admin/risk-standards/1/ (display_color 동일값) =="
CUR=$(curl -s -H "$A" "$BASE/api/admin/risk-standards/" | pickj 0.display_color)
curl -s -H "$A" -H "$J" -X PATCH "$BASE/api/admin/risk-standards/1/" -d "{\"display_color\":$CUR}" | head -c 220; echo; echo

echo "== NOT-02 PATCH /api/admin/alerts/policies/{id}/ (is_active 동일값) =="
PID=$(curl -s -H "$A" "$BASE/api/admin/alerts/policies/" | pick results.0.id)
ACT=$(curl -s -H "$A" "$BASE/api/admin/alerts/policies/" | pickj results.0.is_active)
echo "   대상 policy id=$PID, is_active=$ACT"
curl -s -H "$A" -H "$J" -X PATCH "$BASE/api/admin/alerts/policies/$PID/" -d "{\"is_active\":$ACT}" | head -c 220; echo; echo

echo "== THR-02 PATCH /api/admin/thresholds/{id}/ (is_active 동일값) =="
TID=$(curl -s -H "$A" "$BASE/api/admin/threshold-groups/1/thresholds/" | pick 0.id)
TACT=$(curl -s -H "$A" "$BASE/api/admin/threshold-groups/1/thresholds/" | pickj 0.is_active)
echo "   대상 threshold id=$TID, is_active=$TACT"
curl -s -H "$A" -H "$J" -X PATCH "$BASE/api/admin/thresholds/$TID/" -d "{\"is_active\":$TACT}" | head -c 220; echo; echo

echo "############ 무손상 PROBE ############"
echo "== SPW-07 POST /api/power-devices/check-connection/ (TCP 연결확인, DB 무변경) =="
curl -s -H "$A" -H "$J" -X POST "$BASE/api/power-devices/check-connection/" -d '{"ip_address":"127.0.0.1","port":502}' | head -c 220; echo; echo

echo "############ 안전상 SKIP (사유) ############"
echo "  PRF-08  비밀번호 변경  → 관리자 계정 잠김 위험 (증명 생략)"
echo "  MAP-06  지도 일괄저장  → objects:[] 가 배치 데이터 삭제 위험 (생략)"
echo "  MEVD-11 이벤트 상태전이 → resolved 데모 이벤트 재오픈 위험 (생략)"
echo "  SAF-02  체크리스트 섹션 → 활성 리비전 변경 (생략)"
echo "  USR-03  사용자 생성    → soft-delete 만 가능(완전 가역 X) (생략)"
echo "  DAT-05  보관주기 수정  → 데이터 수명 설정, no-op 생략"
echo "  RTM-09  지오펜스 생성  → polygon 좌표 필요 (생략)"
echo "  CHK-08/VR-08 세션 저장 → 세션 상태(증명 가치 낮음, 생략)"
echo
echo "== 완료 =="
