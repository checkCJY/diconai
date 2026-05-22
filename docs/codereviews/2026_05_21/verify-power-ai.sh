#!/bin/bash
# verify-power-ai.sh — Power AI 다채널 적용 확인 스크립트
#
# 사용법:
#   ./verify-power-ai.sh                현 상태 4가지 검증
#   ./verify-power-ai.sh CH VALUE       특정 채널에 단발 watt 주입 + 추론 결과 확인
#
# 예시:
#   ./verify-power-ai.sh                전체 검증
#   ./verify-power-ai.sh 9 14500        ch9 에 14500W (정격 15000 의 97%) 주입
#   ./verify-power-ai.sh 15 950         ch15 에 950W (정격 1000 의 95%) 주입
#
# 전제: docker compose 가동 중 + 더미가 fastapi 컨테이너 안에서 실행 중
#       (docker exec -d diconai-fastapi-1 python -m dummies.power_dummy)

set -e

DEVICE_MAC="63200c3afd12"
FASTAPI_BASE="http://localhost:8001"
CONTAINER="diconai-fastapi-1"

# 색상
G='\033[32m'; R='\033[31m'; Y='\033[33m'; B='\033[34m'; N='\033[0m'

# channel → slave key 매핑 (SLAVE_TO_CHANNEL 의 역방향)
declare -A CH_TO_SLAVE=(
  [1]=slave01 [2]=slave02 [3]=slave11 [4]=slave12
  [5]=slave21 [6]=slave22 [7]=slave31 [8]=slave32
  [9]=slave41 [10]=slave42 [11]=slave51 [12]=slave52
  [13]=slave61 [14]=slave62 [15]=slave71 [16]=slave72
)

# ─────────────────────────────────────────────────────────────
# 모드 1: 현 상태 검증
# ─────────────────────────────────────────────────────────────
verify_status() {
  echo -e "${B}=== Power AI 4채널 적용 상태 검증 (3분 윈도우) ===${N}"
  echo ""

  # 1. 모델 로드 라인 (IF 4 + ARIMA 4 = 8)
  echo -e "${B}[1] 모델 로드 라인 (IF + ARIMA 8개 기대)${N}"
  loaded=$(docker compose logs fastapi --since 5m 2>&1 | grep -E "IF loaded|ARIMA loaded" | sort -u)
  count=$(echo "$loaded" | grep -c "loaded" || true)
  echo "$loaded" | sed 's/^/  /'
  if [ "$count" -eq 8 ]; then
    echo -e "${G}  ✓ 8개 로드 라인 확인${N}"
  else
    echo -e "${R}  ✗ ${count}개 발견 (8 기대) — STEP 6 cache evict 재시도${N}"
  fi
  echo ""

  # 2. 채널별 추론 활동
  echo -e "${B}[2] 채널별 추론 활동 (3분)${N}"
  for ch in 1 9 14 15; do
    total=$(docker compose logs fastapi --since 3m 2>&1 | grep -c "ch=${ch} watt" || true)
    if [ "$total" -gt 50 ]; then
      printf "  ${G}✓${N} ch%-3s: %s건\n" "$ch" "$total"
    else
      printf "  ${R}✗${N} ch%-3s: %s건 (50건 미만)\n" "$ch" "$total"
    fi
  done
  echo ""

  # 3. ARIMA ci 폭 분포
  echo -e "${B}[3] ARIMA CI 폭 분포 (폭 0 비율 0% 기대)${N}"
  docker compose logs fastapi --since 3m 2>&1 \
    | grep -oE "arima_fc=[0-9.]+ ci=\[[0-9.]+,[0-9.]+\]" \
    | head -100 \
    | awk -F'[][,= ]' '
      { w=$6-$5; if(w<0.1) z++; else nz++; sum+=w }
      END {
        ratio = (z+nz>0) ? (z*100/(z+nz)) : 0
        printf "  ci 폭 0:    %d 건\n  ci 폭 > 0: %d 건\n  평균 폭:    %.0f\n  폭 0 비율:  %.1f%%\n",
               z+0, nz+0, (z+nz>0?sum/(z+nz):0), ratio
      }'
  echo ""

  # 4. DRF forward 400 카운트
  echo -e "${B}[4] DRF forward 400 카운트 (0건 기대)${N}"
  err=$(docker compose logs fastapi --since 3m 2>&1 | grep -c "anomaly_forward_ml.*non_success.*status=400" || true)
  if [ "$err" -eq 0 ]; then
    echo -e "  ${G}✓ 0건${N}"
  else
    echo -e "  ${R}✗ ${err}건 — migration 0003 미적용 또는 vocab 매핑 누락${N}"
  fi
  echo ""

  echo -e "${B}=== 통과 기준: 4개 모두 ✓ ===${N}"
}

# ─────────────────────────────────────────────────────────────
# 모드 2: 단발 주입 + 결과 확인
# ─────────────────────────────────────────────────────────────
inject_channel() {
  local CH=$1
  local VALUE=$2
  local SLAVE=${CH_TO_SLAVE[$CH]}

  if [ -z "$SLAVE" ]; then
    echo -e "${R}잘못된 채널: $CH (1~16 사용)${N}"
    exit 1
  fi

  echo -e "${B}=== ch$CH ($SLAVE) 에 ${VALUE}W 단발 주입 ===${N}"
  echo ""

  # 16채널 페이로드 — 대상 채널만 VALUE, 나머지는 baseline 100W
  payload=$(cat <<EOF
{
  "device_id": "$DEVICE_MAC",
  "slave01": 100, "slave02": 100, "slave11": 100, "slave12": 100,
  "slave21": 100, "slave22": 100, "slave31": 100, "slave32": 100,
  "slave41": 100, "slave42": 100, "slave51": 100, "slave52": 100,
  "slave61": 100, "slave62": 100, "slave71": 100, "slave72": 100
}
EOF
)
  # 대상 채널 값 교체
  payload=$(echo "$payload" | sed "s/\"$SLAVE\": 100/\"$SLAVE\": $VALUE/")

  echo "전송 페이로드 (요약):"
  echo "  device=$DEVICE_MAC | $SLAVE (ch$CH) = ${VALUE}W | 그 외 16채널 = 100W"
  echo ""

  # 주입 시점 마커 — 이후 grep 으로 시점 이후 추론 필터
  mark=$(date +%s)
  echo "$payload" | docker compose exec -T fastapi curl -sS -w "HTTP=%{http_code}\n" \
    -X POST -H "Content-Type: application/json" \
    -d @- "$FASTAPI_BASE/api/power/watt" | tail -1
  echo ""

  echo -e "${Y}10초 대기 (window 30 누적 + 추론 trigger)...${N}"
  sleep 10
  echo ""

  echo -e "${B}=== ch$CH 의 최근 추론 결과 (주입 후) ===${N}"
  docker compose logs fastapi --since 15s 2>&1 \
    | grep "ch=$CH watt" \
    | grep -oE "value=[0-9.]+ threshold=[a-z_]+ pred=[a-z]+ arima_v=[A-Za-z]+ z=[A-Za-z]+ cp=[A-Za-z]+ combined=[a-z_]+ score=-?[0-9.]+ arima_fc=[0-9.]+ ci=\[[0-9.,]+\]" \
    | tail -5 | sed 's/^/  /'
  echo ""

  echo -e "${B}=== 같은 시간 window 의 night_abnormal 격상 (KST 22~05 일 때만)${N}"
  docker compose logs fastapi --since 15s 2>&1 \
    | grep "night_abnormal.*ch=$CH" \
    | tail -3 | sed 's/^/  /'
  echo ""

  echo -e "${B}=== ch$CH 의 알람 push (rate-limit 통과한 발화)${N}"
  docker compose logs fastapi --since 15s 2>&1 \
    | grep "push_alarm" \
    | grep -v "dedup hit" \
    | grep -iE "ch$CH|chN${CH}|채널 ${CH}|채널${CH}" \
    | tail -3 | sed 's/^/  /'
}

# ─────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────
if [ $# -eq 0 ]; then
  verify_status
elif [ $# -eq 2 ]; then
  inject_channel "$1" "$2"
else
  echo "사용법:"
  echo "  $0                 현 상태 4가지 검증"
  echo "  $0 CH VALUE        ch=CH 에 VALUE W 단발 주입 + 추론 결과 확인"
  exit 1
fi
