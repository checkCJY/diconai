**/home/cjy/diconai/fastapi-server/docs/COMMANDS.md**

### 공통 명령어
uv venv
source .venv/bin/activate
deactivate


# 리팩토링 이후 명령어

## 서버실행
uvicorn app:app --reload --port 8001


## 더미 데이터 실행 (터미널 하나당 더미 한 개)

가스 → 전력 → 위치 순으로 각각 별도 터미널에서 실행한다.

```
python -m dummies.gas_dummy
python -m dummies.power_dummy
python -m dummies.position_dummy
```

송출 주기:
- 가스: 1초 (`DUMMY_SEND_INTERVAL_SEC`)
- 전력: 3초 (4개 엔드포인트 순차)
- 위치: 1초


## 시연 시나리오 모드

더미 데이터의 위험도 범위를 강제로 고정해 정상/주의/위험 시나리오를 의도적으로 재현한다.
가스(`gas_dummy`), 전력(`power_dummy`)에 적용되며 위치 더미는 영향 없음.

| 모드 | 동작 |
|---|---|
| `mixed` (기본) | `DUMMY_RISK_PROBABILITY` 확률로 위험 이벤트 주입 |
| `normal` | 모든 가스/전력 채널을 정상 범위에서 생성 |
| `warning` | 모든 가스/전력 채널을 주의 범위에서 생성 (가스 알람은 30초 지연) |
| `danger` | 모든 가스/전력 채널을 위험 범위에서 생성 (즉시 알람) |


### (1) 환경변수로 부팅 시 초기 모드 지정

```
DUMMY_SCENARIO_MODE=danger uvicorn app:app --reload --port 8001
DUMMY_SCENARIO_MODE=warning python -m dummies.gas_dummy
```

또는 `.env` 파일에:
```
DUMMY_SCENARIO_MODE=mixed
```


### (2) 런타임 전환 — 대시보드 시연 패널

대시보드 좌측 하단 "시연 시나리오" 패널의 [혼합/정상/주의/위험] 버튼 클릭으로 즉시 전환.
더미는 1초 캐시로 polling하므로 클릭 후 1~2초 안에 새 모드로 전환된다.


### (3) 런타임 전환 — curl

```
curl http://127.0.0.1:8001/internal/scenario/mode
curl -X POST http://127.0.0.1:8001/internal/scenario/mode \
  -H "Content-Type: application/json" \
  -d '{"mode":"danger"}'
```

응답: `{"mode":"danger"}`


## 영상 녹화용 권장 흐름

```
[혼합] 평상시 동작 5초
  ↓
[정상] 정상 시나리오 5~10초 (알람 없음 — 데이터 흐름만 확인)
  ↓
[위험] 위험 시나리오 5~10초 (즉시 알람 팝업 발화)
  ↓
[정상] 복구 알림 5초 (이전 경보 해제)
```

주의(warning) 시나리오는 가스/전력 모두 30초 지속 후 발화하도록 설계됨
(`alerts/tasks.py:WARNING_DURATION_SEC`). 영상에 포함하려면 30초 대기 필요.
