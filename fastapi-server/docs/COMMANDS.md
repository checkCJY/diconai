**/home/cjy/diconai/fastapi-server/docs/COMMANDS.md**

### 공통 명령어
uv venv
source .venv/bin/activate
deactivate


### FastAPI 실행 명령어
uvicorn main:app --reload --port 8001
uvicorn websocket:app --reload --port 8001

### 더미데이터 들어오는것 확인
.venv/bin/python legacy/test_schemas.py
