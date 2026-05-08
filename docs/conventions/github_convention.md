# Git 컨벤션 가이드

> 작성일: 2026-04-12
>
>
> 대상: 산재 예방 통합 관제 시스템 개발팀 (4인)
>
> Git 워크플로에 익숙하지 않은 상태를 고려하여 작성하였습니다.
>

---

## 1. 브랜치 전략

### 브랜치 구조 — 딱 2종류만 기억

```
main ─────────────────────────────────────────── 완성본 (배포 가능한 상태만)
  │
  └── develop ────────────────────────────────── 개발 중인 코드가 모이는 곳
        │
        ├── feature/가스센서-CRUD ──────────── 기능 하나를 만드는 작업 공간
        ├── feature/JWT-인증 ───────────────── 기능 하나를 만드는 작업 공간
        └── feature/대시보드-차트 ──────────── 기능 하나를 만드는 작업 공간
```

- **main** = "완성된 보고서"를 보관하는 서랍. 중간 작업물은 절대 넣지 않는다.
- **develop** = "작업 중인 보고서"가 모이는 책상. 팀원들이 각자 쓴 부분을 여기에 합친다.
- **feature/기능명** = "내가 쓰고 있는 부분"의 개인 메모장. 다 쓰면 develop 책상에 올린다.

---

### 브랜치 이름 규칙

```
feature/기능을-설명하는-짧은-이름
```

| 예시 | 설명 |
| --- | --- |
| `feature/가스센서-CRUD` | DRF 가스센서 모델 + API |
| `feature/JWT-인증` | 로그인/토큰 발급 기능 |
| `feature/수집서버-전처리` | FastAPI 데이터 검증 로직 |
| `feature/대시보드-차트` | 프론트엔드 실시간 차트 |

규칙:

- 한글 사용 가능 (팀 내 의사소통 우선)
- 띄어쓰기 대신 (하이픈) 사용
- 너무 길지 않게, 무엇을 만드는지 알 수 있을 정도로

---

### 머지 방식 — 두 구간을 다르게 적용합니다다

| 구간 | 머지 방식 | 왜? |
| --- | --- | --- |
| feature → develop | **Squash & Merge** | feature에서 "일단 커밋", "수정", "또 수정" 같은 잡다한 커밋이 쌓여도, develop에는 **1개의 깔끔한 커밋**으로 합쳐서 들어감 |
| develop → main | **일반 Merge** | develop의 히스토리를 그대로 보존. 스쿼시로 하면 develop과 main의 커밋 해시가 달라져서 이후 충돌이 반복됨 |

---

### 실제 작업 흐름 — 단계별 명령어

## 1️⃣ Feature 브랜치 생성

```c
# develop 브랜치로 이동
git checkout develop

# 최신 코드 받기
git pull origin develop

# 내 작업 브랜치 생성
git checkout -b feature/가스센서-CRUD
```

## 2️⃣ 작업 및 커밋

```c
git add .
git commit -m "feat(drf): 가스센서 모델 및 시리얼라이저 작성"
```

> 💡 여러 번 자유롭게 커밋해도 됩니다 (나중에 Squash로 합쳐짐)
>

## 3️⃣ develop 최신화 및 충돌 해결

```c
git checkout develop
git pull origin develop
git checkout feature/가스센서-CRUD
git merge develo
```

> ⚠️ 충돌 발생 시 로컬에서 해결
>

## 4️⃣ 원격 저장소에 Push

```c
# 내 브랜치를 원격에 올리기
git push origin feature/가스센서-CRUD`
```

## 5️⃣ GitHub PR 생성 (feature → develop)

- PR 머지 방식: **Squash and merge** ✅
- 결과: feature 브랜치의 모든 작업이 1개 커밋으로 develop에 기록
- 머지 버튼 클릭 시 **"Squash and merge"** 선택
- 머지 후 해당 feature 브랜치는 삭제

## 6️⃣ 배포 PR 생성 (develop → main)

```c
develop의 최신 상태 확인 후 GitHub에서 PR 생성
```

- PR 머지 방식: **Create a merge commit** (일반 Merge) ✅
- 결과: develop 히스토리 보존, 커밋 해시 유지

---

### 충돌이 발생했을 때

가장 흔한 상황: 내가 작업하는 동안 다른 팀원이 develop에 코드를 합친 경우

```bash
# 내 feature 브랜치에서
git checkout feature/내-기능

# develop의 최신 코드를 내 브랜치로 가져오기
git pull origin develop

# 충돌 발생 시 → 에디터에서 충돌 부분 수정 → 저장
git add .
git commit -m "chore: develop 코드 병합 충돌 해결"
```

충돌을 줄이려면: **같은 파일을 동시에 수정하지 않도록 작업 범위를 사전에 나누는 것**이 가장 효과적입니다.

---

## 2. 커밋 메시지 규칙

### 형식

```
기존
타입(스코프): 한 줄 설명

변경
타입 : 한 줄 설명

이유 : 작업하다보면 스코프를 정확히 명시하기 힘들어짐
```

### 타입 목록

| 타입 | 언제 쓰나 | 예시 |
| --- | --- | --- |
| `feat` | 새 기능 추가 | 기존 : `feat(drf): 가스센서 CRUD API 구현`변경 : `feat: 가스센서 CRUD API 구현` |
| `fix` | 버그 수정 | 기존 : `fix(fastapi): Pydantic 검증 누락 필드 처리`변경 : `fix: Pydantic 검증 누락 필드 처리` |
| `refactor` | 동작은 같은데 코드 구조 개선 | 기존 : `refactor(drf): 시리얼라이저 중복 로직 분리`변경 : `refactor: 시리얼라이저 중복 로직 분리` |
| `docs` | 문서 수정 | 기존 : `docs(공통): API 명세서 v2 업데이트`변경 : `docs: API 명세서 v2 업데이트` |
| `chore` | 설정, 의존성, 기타 잡일 | 기존 : `chore(docker): compose 포트 번호 변경`변경 : `chore: compose 포트 번호 변경` |
| `test` | 테스트 코드 | 기존 : `test(drf): 가스 데이터 저장 API 테스트 추가`변경 : `test: 가스 데이터 저장 API 테스트 추가` |
| `style` | 코드 포매팅 (동작 변화 없음) | 기존 : `style(fastapi): 불필요한 import 정리`변경 : `style: 불필요한 import 정리` |

### 스코프 목록 ( 현재 시점에서 사용 X )

> 현재 시점에서 사용하지 않겠습니다.
>

| 스코프 | 의미 |
| --- | --- |
| `drf` | Django REST Framework 서버 |
| `fastapi` | FastAPI 수집+추론 서버 |
| `frontend` | 프론트엔드 (HTML/JS) |
| `docker` | Docker, docker-compose 설정 |
| `공통` | 여러 서버에 걸치는 변경 |

### 커밋 메시지 작성 규칙

1. **한글로 작성** — 팀 내 소통이 최우선
2. **한 줄에 50자 이내** — 길면 핵심만 남기기
3. **"무엇을 했다"가 아니라 "무엇을 한다"** — 현재형으로 작성
4. **하나의 커밋 = 하나의 변경 단위** — "여러 개 한꺼번에 커밋"은 지양
- VS Code의 Commit Message Editor 확장프로그램을 이용해 다음과 같이 메세지 관리 추천

feat : 로그인 기능 완성

- 일반 유저와 관리자 유저 인증권한에 따른 화면 및 기능 설계
- 추후 관리자 권한에 따라서 회원가입 기능 작성해야 합니다.
- 그 외 자유롭게 작성

### 좋은 예시 / 나쁜 예시

```
# 좋은 예시
feat(drf): 가스 임계치 관리 API 추가
fix(fastapi): O2 센서 None 값 처리 누락 수정
refactor(drf): Notification 모델 중복 필드 제거
chore(docker): PostgreSQL 볼륨 마운트 경로 수정

# 나쁜 예시
수정함                          ← 뭘 수정했는지 모름
feat: 기능추가                   ← 어떤 기능인지, 어느 서버인지 모름
fix(drf): 버그수정했습니다          ← 어떤 버그인지 모름
여러 파일 수정 및 기능 추가          ← 커밋 범위가 너무 넓음
```

---

## 3. Pull Request(PR) 규칙

### PR 제목

커밋 메시지와 동일한 형식을 사용합니다.

```
feat(drf): 가스센서 CRUD API 구현
```

### PR 본문 템플릿

```markdown
## 작업 내용
- 가스센서 모델 생성 (GasSensor, GasData)
- 시리얼라이저 및 ViewSet 구현
- Admin 등록

## 변경 파일
- drf-server/sensors/models.py
- drf-server/sensors/serializers.py
- drf-server/sensors/views.py

## 테스트 방법
1. 서버 실행: `python manage.py runserver`
2. POST /api/sensors/ 로 데이터 전송
3. Django Admin에서 저장 확인

## 참고사항
- GasThreshold 모델은 다음 PR에서 추가 예정
```

### PR 규칙

1. **develop 브랜치로만 PR 생성** — main에 직접 PR 금지
2. **최소 1명 이상 코드 확인 후 머지** — 급할 때도 Slack/카톡으로 알린 뒤 머지
3. **머지 후 feature 브랜치 삭제** — GitHub에서 "Delete branch" 버튼 클릭
4. **충돌이 있으면 PR 생성자가 해결** — 본인 브랜치에서 develop pull 후 충돌 해결

---

## 4. 디렉토리 구조

> 프로젝트 진행하면서 채워나갈 예정이며,  따로 문서화를 진행할 예정
아래 내용은 간단하게 이런식으로 구성될 것이다 라는 예시
>

```

프로젝트 루트/
├── drf-server/          # Django REST Framework 서버
├── fastapi-server/      # FastAPI 수집+추론 통합 서버
├── frontend/            # 프론트엔드 (HTML/JS/CSS) -> React일 경우, 기존은 DRF에 종속속
├── docker-compose.yml   # 컨테이너 통합 실행
├── .env.example         # 환경변수 템플릿 (.env는 .gitignore에 추가)
├── .gitignore
└── README.md
```

---

## 5. .gitignore 필수 항목

```
# 환경변수 (절대 커밋 금지)
.env

# Python
__pycache__/
*.pyc
*.pyo
venv/
.venv/

# Django
db.sqlite3
media/
staticfiles/

# IDE
.vscode/
.idea/
*.swp

# OS
.DS_Store
Thumbs.db

# Docker
*.log
```

---

## 6. 태그 규칙 ( 정보필요 )

> 주요 마일스톤마다 태그를 생성하여 되돌아갈 수 있는 지점을 남깁니다.
현재 시점에서 크게 불필요하다고 판단됩니다.
나중에 Hotfix branch 생성을 통해서 log 관리 또는 각자 개개인의 local branch를 통해서 backup하면 될 것 같지만, 이런 내용은 아마 main - devleop 각각 branch에서 합병 후 문제가 없다고 판단되는 시점에 적용될 수 있을 것이라 판단중입니다
>

```bash
git tag v1.0-3차완료
git tag v2.0-4차완료
```

문제가 생겼을 때 해당 태그 시점으로 롤백할 수 있습니다.

```bash
git checkout v1.0-3차완료
```

---

## 빠른 참조 카드

```
[ 새 기능 시작 ]
git checkout develop → git pull → git checkout -b feature/기능명

[ 작업 중 커밋 ]
git add . → git commit -m "타입(스코프): 설명"

[ 작업 완료 ]
git push origin feature/기능명 → GitHub에서 PR 생성 → Squash & Merge

[ 마일스톤 반영 ]
git checkout main → git merge develop → git tag v버전
```
