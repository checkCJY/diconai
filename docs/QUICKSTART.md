# 빠른 시작 (QUICKSTART)

> **처음 보는 사람이 클론부터 가동까지 이 한 파일로 끝낼 수 있도록** 정리한 문서.
> Docker 통합 환경 기준이며, 로컬(uv) 개발 방식은 [README §실행 방법](../README.md#-실행-방법)을 참고.

소요 시간: 첫 빌드 ~5분 + 시드/접속 ~2분.

---

## 0. 한눈에 보는 흐름

```
clone → .env.docker 작성 → make up → make seed → make super → 접속
                              (자동: migrate + collectstatic)
```

| 단계 | 명령 | 비고 |
|---|---|---|
| 1. 클론 | `git clone … && cd diconai` | |
| 2. 환경변수 | `cp .env.docker.example .env.docker` + 값 채움 | 토큰 3종 생성 |
| 3. 기동 | `make up` | 12개 서비스, migrate·collectstatic 자동 |
| 4. 상태 확인 | `make ps` / `make health` | 모두 healthy/ok |
| 5. 시드 | `make seed` | 마스터 데이터 (Worker×4 등) |
| 6. 슈퍼유저 | `make super` | **반드시 시드 이후** |
| 7. (선택) 더미 | `make dummies-start` | 실시간 데이터 송출 |

---

## 1. 사전 요구사항 (Prerequisites)

- **Docker Desktop** + WSL2 통합 (Windows) / Docker Engine (Linux·macOS)
- **git**, **make**
- 그 외 Python·uv·Redis·PostgreSQL은 **컨테이너 안에 모두 포함** — 호스트 설치 불필요

```bash
docker --version    # 동작 확인
make --version
```

---

## 2. 클론

```bash
git clone https://github.com/checkCJY/diconai.git
cd diconai
```

---

## 3. 환경변수 작성 (`.env.docker`)

```bash
cp .env.docker.example .env.docker
```

`.env.docker`에서 **최소 다음 값**을 채운다 (나머지는 기본값으로 가동 가능):

```bash
# 시크릿 3종 생성
python -c "import secrets; print(secrets.token_urlsafe(50))"   # DJANGO_SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"   # 토큰/JWT 키
```

| 변수 | 채울 값 |
|---|---|
| `DJANGO_SECRET_KEY` | 위 50자 생성값 |
| `INTERNAL_SERVICE_TOKEN` | 32자 생성값 |
| `DRF_SERVICE_TOKEN` | **`INTERNAL_SERVICE_TOKEN`과 같은 값** ⚠️ |
| `JWT_SIGNING_KEY` | 32자 생성값 (위 토큰과 별개) |
| `POSTGRES_PASSWORD` | 임의 값 (팀 환경은 팀장 문의) |

> ⚠️ **`INTERNAL_SERVICE_TOKEN` ≠ `DRF_SERVICE_TOKEN`이면** fastapi 가스 더미가 전부 HTTP 502(drf 401)로 실패한다.
> 진단: [docs/troubleshooting.md §4](troubleshooting.md), [docs/infra/docker_setup.md §10 ⑥](infra/docker_setup.md).

전체 변수 설명: [docs/env-guide.md](env-guide.md).

---

## 4. 기동

```bash
make up        # 이미지 없으면 자동 빌드 + 12개 서비스 백그라운드 기동
```

기동되는 서비스(12종): `redis` · `postgres` · `drf`(:8000) · `fastapi`(:8001) ·
`celery-worker-alarm` · `celery-worker-metric` · `celery-beat` ·
`redis_exporter` · `postgres_exporter` · `node_exporter` · `prometheus`(:9090) · `grafana`(:3000)

> drf 컨테이너의 entrypoint가 **migrate + 시퀀스 리셋 + collectstatic을 자동 실행**한다.
> 수동 마이그레이션은 필요 없다 (명시적으로 하려면 `make migrate`).

---

## 5. 상태 확인

```bash
make ps        # 모든 서비스 STATUS가 healthy / Up 인지
make health    # 양 서버 /health/ → {"status":"ok"}
make targets   # Prometheus scrape 대상이 모두 health=up
```

---

## 6. 마스터 데이터 시드 + 슈퍼유저

```bash
make seed      # Worker×4 / GasSensor / PowerDevice 등 (재실행 안전)
make super     # 슈퍼유저 생성 (대화형 입력)
```

> ⚠️ **순서 주의 — `seed`를 먼저, `super`를 나중에.**
> 시드가 worker `id=1~4`를 점유해야 슈퍼유저가 `id=5+`로 부여되어 위치 더미와 충돌하지 않는다.

---

## 7. 접속

| URL | 설명 | 인증 |
|---|---|---|
| http://localhost:8000/dashboard/ | 메인 대시보드 | 슈퍼유저 로그인 |
| http://localhost:8001/docs | FastAPI Swagger (IoT 수신 API) | — |
| http://localhost:8000/api/schema/swagger-ui/ | DRF Swagger (REST API) | — |
| http://localhost:9090/targets | Prometheus (모두 UP 확인) | — |
| http://localhost:3000 | Grafana 대시보드 | admin / `GRAFANA_PASSWORD` |

---

## 8. (선택) 실시간 데이터 보기

더미 센서를 송출하면 대시보드에 실시간 값·알람이 흐른다.

```bash
make dummies-start          # 가스+전력+위치 3종 송출 시작
make dummies-list           # 실행 중인 더미 확인
make dummies-stop           # 정상 종료

# 시연 시나리오 (자동 1 사이클)
make demo-cycle             # 가스(co_leak) + 전력(overload) ~2분 30초
make scenario-reset         # normal 복귀 (시연 안전 상태)
```

시나리오 모드 상세: [docs/specs/url-structure.md §2.3](specs/url-structure.md).

---

## 9. 가동 검증 체크리스트

- [ ] `make ps` — 12개 서비스 모두 `healthy`/`Up`
- [ ] http://localhost:8000/dashboard/ — 로그인 후 대시보드 렌더링
- [ ] http://localhost:9090/targets — 모든 target `state="up"`
- [ ] `make dummies-start` 후 대시보드에 가스/전력/작업자 값 갱신
- [ ] `make demo-gas` → 대시보드에 위험 알람 팝업 (Celery·Redis·WS 흐름 정상)

---

## 10. 정지 / 정리

```bash
make stop      # 컨테이너 정지 (다음에 빠르게 재기동)
make down      # 컨테이너 제거 (DB/메트릭 볼륨은 유지)
make clean     # 컨테이너 + 볼륨 모두 제거 ⚠️ Redis/Prometheus/Grafana 데이터 삭제
```

---

## 11. 자주 막히는 지점

| 증상 | 원인 / 해결 |
|---|---|
| 가스 더미만 HTTP 502 | `INTERNAL_SERVICE_TOKEN ≠ DRF_SERVICE_TOKEN` → 같은 값으로 → `make restart` |
| `/dashboard/` 정적 파일 깨짐 | `make exec s=drf cmd="python manage.py collectstatic --noinput"` → `make restart s=drf` |
| Prometheus target down | 해당 서비스 미기동 → `make ps`로 확인 후 `make start s=<svc>` |
| 마이그레이션 미적용 | `make showmigrations` 확인 → `make migrate` |

전체 트러블슈팅: [docs/troubleshooting.md](troubleshooting.md), [docs/infra/docker_setup.md §10](infra/docker_setup.md).

---

## 더 알아보기

- 전체 명령어: `make help` / [docs/conventions/COMMANDS.md](conventions/COMMANDS.md)
- 아키텍처·기술 구조: [README.md](../README.md)
- 디렉토리 구조: [docs/specs/directory-structure.md](specs/directory-structure.md)
- URL·API 구조: [docs/specs/url-structure.md](specs/url-structure.md)
- 환경변수 전체: [docs/env-guide.md](env-guide.md)
- Docker 심화(메트릭 흐름·일상 워크플로우): [docs/infra/docker_setup.md](infra/docker_setup.md)
</content>
