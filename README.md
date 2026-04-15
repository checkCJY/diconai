### 초기 간단한 세팅방법

```
1. 가상환경 종료 준비
deactivate
cd ~

git clone https://github.com/checkCJY/diconai.git
cd diconai
git branch -M main
git remote add origin https://github.com/checkCJY/diconai.git

2. 실행환경 맞추기
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt

# git hook 등록 후 확인
pre-commit install
pre-commit run --all-files

2.1 fastapi 실행환경 맞추기
deactivate

# 프로젝트 루트 폴더에서 시작
cd fastapi-server
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt

실행되는지 간단하게 확인
uvicorn main:app --reload --port 8001

2.2 drf 실행환경 맞추기
deactivate

# 프로젝트 루트 폴더에서 시작
cd drf-server
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt

실행되는지 간단하게 확인
python manage.py makemigrations
python manage.py migrate
python manage.py runserver
```
