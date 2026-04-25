**/home/cjy/diconai/fastapi-server/docs/COMMANDS.md**

### 공통 명령어
uv venv
source .venv/bin/activate
deactivate


# 리팩토링 이후 명령어

## 서버실행
uvicorn app:app --reload --port 8001

## 더미 데이터 전송 (터미널 하나당 더미 데이터 한개씩)
##### 가스 / 전력 순서

python -m dummies.gas_dummy
python -m dummies.power_dummy
