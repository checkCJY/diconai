# diconai — Docker 작업 단축 명령어
#
# 사용:  make help    (모든 명령 + 시나리오 보기)
#        make <목표>
#
# 처음이라면 먼저 docs/infra/docker_setup.md §8 신규 환경 세팅을 따라가세요.
# 일상 워크플로우 가이드는 같은 문서 §9.

.DEFAULT_GOAL := help
SHELL := /bin/bash

# 서비스명 인자 (생략 시 전체 또는 명령에 따라 다름)
s ?=
cmd ?=

# 색상
BOLD   := \033[1m
CYAN   := \033[36m
YELLOW := \033[33m
GREEN  := \033[32m
DIM    := \033[2m
RESET  := \033[0m

.PHONY: help up down start stop restart ps build rebuild logs sh exec \
        test test-drf test-fastapi migrate super seed showmigrations shell-drf \
        health metrics targets clean prune

help:  ## 전체 명령어 + 자주 쓰는 시나리오 보기
	@printf "\n  $(BOLD)📦 diconai Docker 단축 명령어$(RESET)\n"
	@printf "  $(DIM)처음 사용한다면 먼저:  docs/infra/docker_setup.md§8 신규 환경 세팅$(RESET)\n"
	@awk 'BEGIN {FS = ":.*?## "} \
	  /^##@/ {printf "\n$(YELLOW)  %s$(RESET)\n", substr($$0, 5)} \
	  /^[a-zA-Z_-]+:.*?## / {printf "    $(CYAN)%-16s$(RESET) %s\n", $$1, $$2}' \
	  $(MAKEFILE_LIST)
	@printf "\n  $(BOLD)🎯 자주 쓰는 시나리오$(RESET)\n"
	@printf "    $(GREEN)최초 환경 띄우기$(RESET)\n"
	@printf "      cp .env.docker.example .env.docker  $(DIM)# 시크릿 채우기$(RESET)\n"
	@printf "      mkdir -p drf-server/media\n"
	@printf "      make build && make up && make ps && make health\n\n"
	@printf "    $(GREEN)코드 수정 후 한 서비스만 재기동$(RESET)\n"
	@printf "      make rebuild s=drf && make up        $(DIM)# Python 코드/requirements 바뀐 경우$(RESET)\n"
	@printf "      make restart s=drf                   $(DIM)# 환경변수만 바뀐 경우$(RESET)\n\n"
	@printf "    $(GREEN)로그 모니터링$(RESET)\n"
	@printf "      make logs                            $(DIM)# 7개 서비스 전체$(RESET)\n"
	@printf "      make logs s=fastapi                  $(DIM)# 한 서비스만$(RESET)\n\n"
	@printf "    $(GREEN)컨테이너 안에서 디버깅$(RESET)\n"
	@printf "      make sh s=drf                        $(DIM)# /bin/sh 진입$(RESET)\n"
	@printf "      make shell-drf                       $(DIM)# Django shell (ORM 조작 가능)$(RESET)\n"
	@printf '      make exec s=drf cmd="python manage.py dbshell"   $(DIM)# 임의 명령$(RESET)\n\n'
	@printf "    $(GREEN)Django DB 작업$(RESET)\n"
	@printf "      make showmigrations                  $(DIM)# 적용 상태 보기$(RESET)\n"
	@printf "      make migrate                         $(DIM)# 수동 적용 (entrypoint도 자동 처리)$(RESET)\n"
	@printf "      make super                           $(DIM)# 슈퍼유저 생성$(RESET)\n"
	@printf "      make seed                            $(DIM)# 더미 데이터$(RESET)\n\n"
	@printf "    $(GREEN)정상 동작 검증$(RESET)\n"
	@printf "      make health                          $(DIM)# /health/ 응답$(RESET)\n"
	@printf "      make metrics                         $(DIM)# /metrics 샘플$(RESET)\n"
	@printf "      make targets                         $(DIM)# Prometheus scrape 상태$(RESET)\n\n"
	@printf "    $(GREEN)정리 / 초기화$(RESET)\n"
	@printf "      make down                            $(DIM)# 컨테이너만 제거 (데이터 유지)$(RESET)\n"
	@printf "      make clean                           $(DIM)# 볼륨까지 제거 (Redis/Grafana 데이터 삭제 주의)$(RESET)\n\n"
	@printf "  $(DIM)인자: s=서비스명(drf|fastapi|redis|celery-worker|celery-beat|prometheus|grafana)$(RESET)\n\n"


##@ 🐳 빌드 / 기동

up:           ## 7개 서비스 전체 기동 (백그라운드). 이미지 없으면 자동 빌드
	docker compose up -d

down:         ## 컨테이너 제거 (볼륨 = DB/메트릭 데이터는 유지)
	docker compose down

start:        ## 정지된 컨테이너 재기동 (이미지 재사용, 빠름). s=서비스명 옵션
	docker compose start $(s)

stop:         ## 컨테이너 정지 (제거 안 함, 다음에 빠르게 재기동). s=서비스명 옵션
	docker compose stop $(s)

restart:      ## 재기동 (환경변수만 바뀐 경우 충분). s=서비스명 옵션
	docker compose restart $(s)

ps:           ## 7개 서비스 상태 표 (STATUS가 healthy/Up인지 확인)
	docker compose ps

build:        ## 이미지 빌드 (캐시 사용, 코드/requirements 변경 시). s=서비스명 옵션
	docker compose build $(s)

rebuild:      ## 캐시 무시 재빌드 (의존성 충돌·이미지 깨짐 의심 시). s=서비스명 옵션
	docker compose build --no-cache $(s)


##@ 📋 로그

logs:         ## 로그 실시간 (Ctrl+C로 빠짐). s=서비스명 미지정이면 전체
	docker compose logs -f --tail=100 $(s)


##@ 🐚 컨테이너 안에서 실행

sh:           ## 컨테이너 쉘 진입 (디버깅·파일 확인). 예: make sh s=drf
	@test -n "$(s)" || (echo "사용: make sh s=drf  (s 필수)" && exit 1)
	docker compose exec $(s) sh

exec:         ## 임의 명령 실행. 예: make exec s=drf cmd="python manage.py dbshell"
	@test -n "$(s)" || (echo '사용: make exec s=drf cmd="..."' && exit 1)
	docker compose exec $(s) $(cmd)

test:         ## drf + fastapi pytest 일괄 실행 (회귀 검증)
	docker compose exec drf pytest -q
	docker compose exec fastapi pytest -q

test-drf:     ## drf-server pytest만 실행 (Django 측 변경 시)
	docker compose exec drf pytest -q

test-fastapi: ## fastapi-server pytest만 실행 (FastAPI 측 변경 시)
	docker compose exec fastapi pytest -q

shell-drf:    ## Django shell 진입 (ORM 조작, 디버깅용)
	docker compose exec drf python manage.py shell


##@ 🗄 Django DB 작업

migrate:      ## 미적용 마이그레이션 수동 실행 (entrypoint가 자동 처리하지만 명시적으로)
	docker compose exec drf python manage.py migrate

showmigrations: ## 마이그레이션 적용 상태 ([X] 적용 / [ ] 미적용)
	docker compose exec drf python manage.py showmigrations

super:        ## 슈퍼유저 생성 (대화형: id/이메일/비밀번호 입력)
	docker compose exec drf python manage.py createsuperuser

seed:         ## 더미 데이터 시드 (Worker × 4, GasSensor, PowerDevice 등)
	docker compose exec drf python manage.py seed_dummy_data


##@ ✅ 정상 동작 검증

health:       ## 양 서버 /health/ 엔드포인트 호출 (가장 빠른 alive 확인)
	@curl -fsS http://localhost:8000/health/ && echo "  ← drf OK"
	@curl -fsS http://localhost:8001/health/ && echo "  ← fastapi OK"

metrics:      ## 양 서버 /metrics 샘플 (http_requests_total 5줄씩)
	@echo "── DRF ──";     curl -s http://localhost:8000/metrics | grep '^http_requests_total' | head -5
	@echo "── FastAPI ──"; curl -s http://localhost:8001/metrics | grep '^http_requests_total' | head -5

targets:      ## Prometheus가 scrape하는 3개 target 상태 (모두 health=up이어야 정상)
	@curl -s 'http://localhost:9090/api/v1/targets?state=active' | python3 -m json.tool | grep -E '"job"|"health"'


##@ 🧹 정리

clean:        ## 컨테이너 + 볼륨 모두 제거 ⚠️ Redis/Prometheus/Grafana 데이터 삭제
	docker compose down -v

prune:        ## 댕글링 이미지/볼륨 정리 ⚠️ 전역 (다른 프로젝트도 영향)
	docker image prune -f
	docker volume prune -f
