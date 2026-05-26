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
        health metrics targets clean prune \
        logs-drf logs-fastapi logs-celery logs-beat logs-all \
        logs-locks logs-timeouts logs-errors logs-ai logs-retention \
        logs-err logs-err-fastapi logs-err-all logs-app logs-app-fastapi logs-stat \
        dummies-start dummies-stop dummies-list dummies-restart \
        db-size db-pragma db-counts \
        scenario scenario-set scenario-reset scenario-clean demo-prep demo-check

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
	@printf "      make logs                            $(DIM)# 7개 서비스 전체 (stdout, 휘발성)$(RESET)\n"
	@printf "      make logs s=fastapi                  $(DIM)# 한 서비스만$(RESET)\n"
	@printf "      make logs-err-all                    $(DIM)# 양 서버 ERROR 영속 파일 실시간 (시연·사고 추적 1순위)$(RESET)\n\n"
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


##@ 📋 서비스별 로그 (개발 일상)

logs:         ## 로그 실시간 (Ctrl+C). s=서비스명 미지정이면 전체 7개 서비스
	docker compose logs -f --tail=100 $(s)

logs-drf:     ## drf 단독 (gunicorn access + Django request/ERROR)
	docker compose logs -f --tail=100 drf

logs-fastapi: ## fastapi 단독 (uvicorn access + IoT 인입 + WS)
	docker compose logs -f --tail=100 fastapi

logs-celery:  ## celery-worker 단독 (알람 태스크 처리 + ML forward)
	docker compose logs -f --tail=100 celery-worker

logs-beat:    ## celery-beat 단독 (retention 등 주기 태스크 스케줄링)
	docker compose logs -f --tail=100 celery-beat

logs-all:     ## drf + fastapi + celery 4개 통합 (요청→저장→알람 흐름 한 화면)
	docker compose logs -f --tail=50 drf fastapi celery-worker celery-beat


##@ 📁 파일 로그 (RotatingFileHandler — 영속·시연용)

# 배경·결정 근거: skill/study/2026-05-26_파일_로깅_도입_배경.md
# stdout(make logs)은 컨테이너 재시작 시 휘발. 영속 로그는 */logs/*.log 파일에서 본다.
# error.log = ERROR 전용 (100MB × 10), app.log = INFO+ (50MB × 5). 자동 회전.

logs-err:     ## drf-server/logs/error.log 실시간 (ERROR 전용)
	tail -f drf-server/logs/error.log

logs-err-fastapi: ## fastapi-server/logs/error.log 실시간
	tail -f fastapi-server/logs/error.log

logs-err-all: ## 양 서버 error.log 합쳐 보기 (시연·사고 추적 1순위)
	tail -f drf-server/logs/error.log fastapi-server/logs/error.log

logs-app:     ## drf-server/logs/app.log 실시간 (INFO+; retention·AI·임계치 변경)
	tail -f drf-server/logs/app.log

logs-app-fastapi: ## fastapi-server/logs/app.log 실시간 (IoT 페이로드 파싱 등)
	tail -f fastapi-server/logs/app.log

logs-stat:    ## 로그 파일 크기·회전 백업 현황 (운영 점검)
	@ls -lh drf-server/logs/*.log* fastapi-server/logs/*.log* 2>/dev/null || echo "  (로그 파일 아직 없음 — 서버 기동 후 다시 확인)"


##@ 🔍 로그 필터 (이슈 추적·트러블슈팅)

logs-locks:   ## Celery 'database is locked' 감시 (1단계 락 폭주 회귀 확인)
	docker logs -f diconai-celery-worker-1 2>&1 | grep -E --line-buffered "database is locked|retry"

logs-timeouts: ## fastapi 'action=timeout' 감시 (DRF 응답 지연 추적)
	docker logs -f diconai-fastapi-1 2>&1 | grep -E --line-buffered "action=timeout|ERROR"

logs-errors:  ## DRF 4xx/5xx + ERROR + Forbidden 감시
	docker logs -f diconai-drf-1 2>&1 | grep -E --line-buffered " 4[0-9]{2} | 5[0-9]{2} |ERROR|Forbidden"

logs-ai:      ## AI 추론 로그 (anomaly_inference + 가스 IF 추론 실패)
	docker logs -f diconai-fastapi-1 2>&1 | grep -E --line-buffered "anomaly_inference|AI 추론"

logs-retention: ## retention task 발사·실행 로그 (매일 09:30 KST)
	docker logs -f diconai-celery-worker-1 2>&1 | grep -E --line-buffered "retention|run_data_retention"


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


##@ 🎭 더미 송출 (개발·시연 부하 테스트)

# Python procps 미설치 (slim 이미지). /proc 직접 순회로 PID 추적.
# cmdline args 단위로 정확히 매치 (args[1]=='-m' and args[2].startswith('dummies.'))
# — `python -c` 한 줄 명령 안에 'dummies.' 문자열이 있어도 오탐 안 함.
define _DUMMIES_IS_DUMMY
def _is_dummy(p):
    try:
        args = open(p).read().split(chr(0))
    except Exception:
        return None
    if (len(args) >= 3 and args[0].endswith('python')
            and args[1] == '-m' and args[2].startswith('dummies.')):
        return args
    return None
endef

define _DUMMIES_LIST_PY
import glob
$(_DUMMIES_IS_DUMMY)
found = False
for p in glob.glob('/proc/[0-9]*/cmdline'):
    args = _is_dummy(p)
    if args:
        print(p.split('/')[2], ' '.join(args[:3]), sep='\t')
        found = True
if not found:
    print('  (실행 중인 더미 없음)')
endef
export _DUMMIES_LIST_PY

define _DUMMIES_STOP_PY
import os, signal, glob
$(_DUMMIES_IS_DUMMY)
only = os.environ.get('ONLY', '').strip()
target_module = f'dummies.{only}_dummy' if only else None
n = 0
for p in glob.glob('/proc/[0-9]*/cmdline'):
    args = _is_dummy(p)
    if not args:
        continue
    if target_module and args[2] != target_module:
        continue
    os.kill(int(p.split('/')[2]), signal.SIGINT)
    n += 1
label = f' ({only}_dummy only)' if only else ''
print(f'  killed {n} processes{label}')
endef
export _DUMMIES_STOP_PY

dummies-start:    ## 더미 송출 시작. s=gas|power|position 단일, 미지정 시 3종 전체
	@if [ -n "$(s)" ]; then \
	  docker exec -d diconai-fastapi-1 python -m dummies.$(s)_dummy; \
	  echo "  started: $(s)_dummy"; \
	else \
	  docker exec -d diconai-fastapi-1 python -m dummies.power_dummy; \
	  docker exec -d diconai-fastapi-1 python -m dummies.gas_dummy; \
	  docker exec -d diconai-fastapi-1 python -m dummies.position_dummy; \
	  echo "  started: power_dummy gas_dummy position_dummy"; \
	fi
	@sleep 1
	@$(MAKE) -s dummies-list

dummies-list:     ## 실행 중인 더미 프로세스 확인
	@docker exec diconai-fastapi-1 python -c "$$_DUMMIES_LIST_PY"

dummies-stop:     ## 더미 정상 종료 (SIGINT). s=gas|power|position 단일, 미지정 시 전체
	@docker exec -e ONLY="$(s)" diconai-fastapi-1 python -c "$$_DUMMIES_STOP_PY"

dummies-restart:  ## 더미 재기동 (stop → 2초 → start). s= 인자 동일하게 전파
	@$(MAKE) -s dummies-stop s=$(s)
	@sleep 2
	@$(MAKE) -s dummies-start s=$(s)


##@ 💾 SQLite DB 상태 (운영 점검·디버깅)

define _DB_PRAGMA_PY
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from django.contrib.auth import get_user_model
list(get_user_model().objects.all()[:1])
from django.db import connection
with connection.cursor() as c:
    for pragma in ('journal_mode', 'busy_timeout', 'synchronous', 'foreign_keys'):
        c.execute(f'PRAGMA {pragma}')
        print(f'  {pragma:<20}: {c.fetchone()[0]}')
print(f'  transaction_mode    : {connection.transaction_mode}')
endef
export _DB_PRAGMA_PY

define _DB_COUNTS_PY
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from django.db import connection
TABLES = [('power_data', 'measured_at'), ('gas_data', 'measured_at'),
          ('worker_position', 'measured_at'), ('alarm_record', 'detected_at'),
          ('event', 'detected_at'), ('ml_anomaly_result', 'occurred_at'),
          ('integration_log', 'created_at')]
with connection.cursor() as c:
    print(f'  {"table":<22} {"rows":>12}  {"min_time":<20} {"max_time":<20}')
    print(f'  {"-"*22} {"-"*12}  {"-"*20} {"-"*20}')
    for t, col in TABLES:
        try:
            c.execute(f'SELECT COUNT(*) FROM "{t}"')
            n = c.fetchone()[0]
            mn = mx = ''
            if n:
                try:
                    c.execute(f'SELECT MIN({col}), MAX({col}) FROM "{t}"')
                    mn, mx = c.fetchone()
                except Exception:
                    pass
            print(f'  {t:<22} {n:>12,}  {str(mn or ""):<20} {str(mx or ""):<20}')
        except Exception:
            pass
endef
export _DB_COUNTS_PY

db-size:          ## DB 파일 + WAL/SHM 크기 (12GB 비대화 같은 폭증 감지)
	@docker exec diconai-drf-1 sh -c 'ls -lh /app/db.sqlite3* 2>/dev/null || echo "  (DB 파일 없음)"'

db-pragma:        ## PRAGMA 설정 (busy_timeout/journal_mode 검증)
	@docker exec diconai-drf-1 python -c "$$_DB_PRAGMA_PY"

db-counts:        ## 주요 테이블 row count + 시간 범위 (raw 비대화 추적)
	@docker exec diconai-drf-1 python -c "$$_DB_COUNTS_PY"


##@ 🎬 시연 시나리오 (가스 co_leak / 전력 overload 데모용)

scenario:        ## 현재 시나리오 모드 조회
	@curl -s http://localhost:8001/internal/scenario/mode | python3 -m json.tool

scenario-set:    ## 시나리오 모드 변경. mode=co_leak|overload|normal|mixed 등
	@if [ -z "$(mode)" ]; then \
	  echo "❌ mode 인자 필요. 예: make scenario-set mode=co_leak"; exit 1; \
	fi
	@curl -s -X POST http://localhost:8001/internal/scenario/mode \
	  -H 'Content-Type: application/json' -d '{"mode":"$(mode)"}' | python3 -m json.tool

scenario-reset:  ## 시나리오 모드를 normal 로 복귀 (시연 안전 상태)
	@$(MAKE) -s scenario-set mode=normal

scenario-clean:  ## 알람 큐 + dedup/상태 키 일괄 정리 (리허설 사이 초기화)
	@docker compose exec redis redis-cli DEL diconai:ws:alarms > /dev/null
	@for pat in 'alarm:state:*' 'alarm:power:*' 'ai_fired:*' 'alarm:push:dedup:*'; do \
	  docker compose exec redis redis-cli --scan --pattern "$$pat" | \
	    xargs -r -I {} docker compose exec redis redis-cli DEL {} > /dev/null; \
	done
	@echo "✅ Redis 알람 관련 키 모두 정리됨"

demo-prep:       ## 시연 직전 일괄 셋업 (mode=normal + Redis 키 정리)
	@echo "🎬 시연 준비..."
	@$(MAKE) -s scenario-set mode=normal
	@$(MAKE) -s scenario-clean
	@echo "✅ 시연 준비 완료 — 시연 트리거 예: make scenario-set mode=co_leak"

demo-check:      ## 시연 환경 한방 점검 (현재 모드 + env + 큐 길이)
	@echo "📊 현재 시연 환경:"
	@printf "  • 모드: "
	@$(MAKE) -s scenario
	@printf "  • env: "
	@docker compose exec fastapi printenv DUMMY_SEND_INTERVAL_SEC DUMMY_SCENARIO_MODE 2>&1 | tr '\n' ' '; echo
	@printf "  • 알람 큐 길이: "
	@docker compose exec redis redis-cli LLEN diconai:ws:alarms


##@ 🧹 정리

clean:        ## 컨테이너 + 볼륨 모두 제거 ⚠️ Redis/Prometheus/Grafana 데이터 삭제
	docker compose down -v

prune:        ## 댕글링 이미지/볼륨 정리 ⚠️ 전역 (다른 프로젝트도 영향)
	docker image prune -f
	docker volume prune -f
