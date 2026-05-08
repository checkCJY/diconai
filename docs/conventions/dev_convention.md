# SKILL: dev-convention
## DESCRIPTION
산재 예방 통합 관제 시스템 개발팀(4인)을 위한 Python, Django, FastAPI 통합 코딩 스타일, 네이밍, 주석, 아키텍처 컨벤션 가이드.

## TRIGGER CONDITIONS
- "컨벤션/코드 스타일 가이드 알려줘/보여줘"
- "네이밍 규칙이 뭐야?", "변수명/함수명 어떻게 지어?"
- "Django 모델명/FastAPI 라우터 파일명 규칙이 뭐야?"
- "주석 어떻게 달아?"
- 새 파일/함수 생성 및 코드 리뷰(code-review 스킬 연계) 시

## 1. PYTHON BASIC STYLE

> **자동 강제 — pre-commit (ruff + ruff-format)**
> `[.pre-commit-config.yaml](../../.pre-commit-config.yaml)`이 `drf-server/`, `fastapi-server/` 하위 `.py` 파일에 대해 §1.1을 자동 적용한다.
> commit 시 양식이 어긋나면 ruff-format이 파일을 **자동 수정 → commit 거부**하므로, `git add` 후 다시 commit 해야 통과한다.
> 별도 ruff 설정 파일이 없으므로 ruff **기본값**으로 동작한다 (line-length=88, double-quote, lint=E4/E7/E9/F).

### 1.1 ruff·ruff-format 자동 적용 (양식)
- **들여쓰기**: 스페이스 4칸 (Tab 금지).
- **줄 길이**: 최대 **88자** (`ruff-format` 기본값, Black 호환). 79자 PEP 8 권장값보다 완화된 값 — 더 짧게 써도 ruff가 88자 안에서 한 줄로 합칠 수 있다.
- **문자열 인용부호**: 큰따옴표(`"`) — 작은따옴표는 자동 변환됨.
- **빈 줄(Blank Lines)**:
  - 클래스 및 최상단 함수 위아래: 2줄
  - 클래스 내부 메서드 사이: 1줄
- **trailing comma**: 다중 인자·리스트·dict 마지막 요소에 자동 추가.
- **trailing whitespace / 파일 끝 줄바꿈**: 자동 정리 (`pre-commit-hooks`).
- **lint 기본 활성**: `F`(Pyflakes — 미사용 import·정의되지 않은 변수), `E4/E7/E9`(import 위치·문장·런타임 오류). `args: [--fix]`로 자동 수정 가능한 항목은 수정.

### 1.2 작성자 책임 (ruff가 강제하지 않음)
- **문자열 포매팅**: `f-string`만 사용 (`%`, `.format()` 금지).
- **Import 순서**: 그룹 간 빈 줄 1개, 그룹 내 알파벳 정렬. *(ruff `I` 룰 미활성 — 자동 정렬 안 됨)*
  1. 표준 라이브러리 (ex: `os`, `datetime`)
  2. 서드파티 (ex: `fastapi`, `pydantic`)
  3. 내부 모듈 (ex: `app.schemas`)
- **네이밍 (§2)**: ruff `N` 룰 미활성 — 컨벤션은 §2를 따른다.
- **줄 길이 lint**: ruff `E501` 미활성 — `ruff-format`이 자동 줄바꿈해 주지만, 문자열·주석은 88자 초과해도 lint 에러가 나지 않으므로 작성자가 끊는다.

## 2. NAMING CONVENTIONS
- **변수 (Variables)**: `snake_case`. 의미를 담을 것 (ex: `gas_value` O, `v` X).
  - Boolean: `is_`, `has_`, `can_` 접두어 사용 (ex: `is_danger`).
- **함수 (Functions)**: `snake_case`. "동사 + 목적어" 형태 (ex: `get_sensor_by_id`, `calculate_gas_risk`).
  - *주요 동사*: `get`(조회), `create`(생성), `update`(수정), `delete`(삭제), `calculate`(계산), `validate`(검증), `send`(전송), `check`(확인).
- **클래스 (Classes)**: `PascalCase` (단수형).
- **상수 (Constants)**: `UPPER_SNAKE_CASE`.
- **파일명 (Files)**: `snake_case` (ex: `gas_sensor.py`).
- **URL 경로**: `kebab-case`, 복수형 (ex: `/api/gas-data/`).

## 3. DJANGO / DRF SPECIFIC
- **Models (`models.py`)**:
  - 클래스명: 단수형 `PascalCase` (ex: `GasSensor`).
  - 필드명: `snake_case`.
  - 시간/날짜 필드: `_at` 접미어 (ex: `created_at`).
  - 관계 역참조(`related_name`): 복수형 `snake_case` (ex: `gas_sensors`).
  - Meta 속성: `db_table`은 `snake_case` 지정.
- **Serializers (`serializers.py`)**: `[모델명]Serializer`. 용도별(목록/상세/생성) 분리 권장.
- **Views (`views.py`)**: `[모델명]ViewSet`. 비즈니스 로직은 배제.
- **App 이름**: 복수형 `snake_case` (ex: `sensors`).
- **아키텍처/역할 분리**:
  - **`services.py`**: 비즈니스 로직(복잡한 계산, 외부 API 통신 등) 전담. View에서는 호출만 수행.
  - **URL 분리**:
    - 페이지 URL(HTML 반환): 루트 경로 (ex: `/sensors/`).
    - API URL(JSON 반환): 반드시 `/api/` 접두어 사용 (ex: `/api/sensors/`).
  - **정적 파일/템플릿**:
    - 공통 파일: 루트의 `templates/`, `static/`.
    - 앱 전용: `[앱명]/templates/[앱명]/`, `[앱명]/static/[앱명]/`.
    - JS/Axios: 페이지별 JS 분리, Axios 설정은 `api_client.js`로 통합.

## 4. FASTAPI SPECIFIC
- **Routers (`routers/`)**:
  - 파일명: `snake_case` (ex: `gas_data.py`).
  - Prefix: `kebab-case` (ex: `/gas-data`).
  - 라우터 함수명: `snake_case` + 동사 (ex: `receive_gas_data`).
- **Schemas (`schemas/`)**: `Pydantic` 기반.
  - 클래스명: `[용도]Request` / `[용도]Response` (ex: `GasDataRequest`).
  - 속성: `Field`를 사용하여 `description`, `examples` 반드시 작성.
  - 누락 가능 필드: `Optional` + 기본값 `None` 지정.
- **비즈니스 로직 분리**: 전처리(`services/`), AI 추론(`inference.py`) 모듈화.

## 5. FILE & DIRECTORY SPLIT RULES (Common)
- **줄 수 기준**: 단일 파일이 200줄 초과 시 도메인별 폴더로 분리.
- **역할 기준**: 서로 다른 역할(CRUD vs 통계 vs 알림)이 섞이면 파일 분리.
- **폴더 전환 시 패턴**: `__init__.py`를 활용하여 외부 import 경로 유지 (ex: `from .gas import GasSensorSerializer`).

## 6. COMMENTS & LOGGING

> **대원칙**: 주석은 코드의 **"무엇(WHAT)"이 아닌 "왜(WHY)"**를 설명한다.
> 이름이 좋으면 주석은 불필요하다. 다음 4종 — 도메인 근거, 동시성·트랜잭션, 도메인 특수성, 외부 시스템 계약 — 에서만 인라인 주석을 적극 작성한다.

### 6.1 모듈 헤더 주석
- **형식**: `# <앱>/<file.py> — 역할 한 줄`을 첫 줄에 둔다. 이후 빈 주석 줄(`#`)을 두고 다중 태스크/엔드포인트/상태머신을 짧게 나열.
- **필수 대상**: `services/`, `tasks.py`, `routers/`, `selectors/` 등 비즈니스 로직 또는 외부 진입점 모듈.
- **표준 예시**: `drf-server/apps/alerts/tasks.py:1-9` 형식을 그대로 따른다.
  ```python
  # alerts/tasks.py — 가스 알람 Celery 태스크
  #
  # 3종 알람 태스크:
  #   fire_danger_alarm_task  : DANGER 즉각 알람
  #   fire_warning_alarm_task : WARNING 30초 지속 후 알람 (countdown=30)
  #   fire_clear_notification_task : 정상화 알림
  #
  # 각 태스크는 AlarmRecord/Event를 DB에 기록한 뒤,
  # FastAPI /internal/alarms/push/ 엔드포인트로 WS 브로드캐스트 큐에 알람을 추가한다.
  ```

### 6.2 클래스 Docstring
- **형식**: `"""` 사용. 첫 줄은 1줄 요약, 이후 `[설계 원칙]` / `[v3 신설]` 같은 **대괄호 섹션 태그**로 의도·이력을 묶는다.
- **필수 대상**: `models/` 의 모든 모델 클래스, 외부에서 import되는 모든 클래스.
- **대괄호 섹션 태그 권장 목록**:
  - `[설계 원칙]` — 이 모델/클래스를 만든 이유와 wide table 등 구조 결정의 근거
  - `[v3 신설]`, `[v2 변경]` — 버전·이력 변경점
  - `[가스 종류 출처]`, `[임계치 출처]` — 외부 명세서·법규 참조
  - `[null 처리]` — `None`/`0` 구분 등 도메인 규약
- **표준 예시**: `drf-server/apps/monitoring/models/gas_data.py:8-22`, `drf-server/apps/alerts/models/event.py:8-35`.

### 6.3 함수 Docstring
- **형식**: `"""` 사용. 첫 줄 1-2줄 요약 + 단계별 동작 설명(`1./2./3.`). `Args`, `Returns` 는 외부 호출용(API view·service·외부 라이브러리에서 import) 함수에 필수.
- **내부 헬퍼 함수**(`_` 접두어)는 1줄 요약만으로 충분.
- **표준 예시**: `drf-server/apps/alerts/services/event_service.py:31-37`.
  ```python
  def create_alarm_and_event(...):
      """
      AlarmRecord + Event 생성/병합 핵심 로직

      1. 병합 대상 활성 Event 검색 (select_for_update)
      2. 존재: AlarmRecord만 생성, Event 업데이트
      3. 없음: Event 생성 + AlarmRecord 생성 + EventLog(CREATED)
      """
  ```

### 6.4 인라인 주석 — WHY 4종 분류 ★
인라인 주석은 아래 **4종 중 하나**에 해당할 때만 작성한다. 그 외에는 주석 없이 코드 자체로 의미를 드러낸다.

| 분류 | 적용 대상 | 예시 |
|---|---|---|
| **상수·매직넘버** | 임계치, 타이머, 쿨다운, 배치 크기 등 숫자 상수 | `RENOTIFY_COOLDOWN_MINUTES = 5  # 동일 이벤트 재알림 최소 간격 — 알람 폭주 방지` |
| **동시성·트랜잭션** | `select_for_update`, `asyncio.Event`, lock, atomic | `# select_for_update — 동일 facility 동시 알람 생성 race 방지` |
| **도메인 특수성** | 직관과 다른 처리, 의외의 분기 | `# O2는 0이 유효값 — None만 결측 처리 (산소 결핍 0% 측정 가능)` |
| **외부 시스템 계약** | 실패 정책, 재시도, 타임아웃 의도 | `# WS 푸시 실패해도 태스크 성공 — DB 기록이 진실의 원천` |

### 6.5 좋은 예 / 나쁜 예

| 나쁜 예 (WHAT) | 좋은 예 (WHY) |
|---|---|
| `# 이벤트를 생성한다` | `# 활성 이벤트 부재 또는 12h 윈도우 초과 시 새 Event 생성` |
| `# 5분으로 설정` | `# 5분 — 운영팀 합의(2026-04 회의), 알람 폭주 vs 위험 재상승 감지의 균형` |
| `# None 체크` | `# 통신 불능 채널은 0이 아닌 None — false positive 방지` |
| `# 락 건다` | `# select_for_update — 동시 AlarmRecord 생성 race 방지` |

### 6.6 TODO / FIXME
- **형식**: `# TODO(담당자) [기한]: 설명` (ex: `# TODO(재용) [2026-06-01]: 임계치 외부 설정 분리`)
- **FIXME**: 알려진 버그가 있고 임시 우회 중인 경우만 사용. 같은 형식.

### 6.7 로깅 (Logging)
- **`print()` 금지**, 내장 `logging` 모듈만 사용.
- **포맷**: `logger.LEVEL(f"[CATEGORY] key=value")`
- **레벨**: `DEBUG`(상세), `INFO`(정상완료), `WARNING`(주의/재시도), `ERROR`(실패).

## 7. PRE-PR CHECKLIST

### 7.1 자동 (pre-commit이 처리)
들여쓰기·88자 줄바꿈·큰따옴표·빈 줄·trailing comma·trailing whitespace·파일 끝 줄바꿈·미사용 import 제거.
> commit 시 ruff-format이 파일을 수정하면 거부됨 → `git add <수정된 파일>` 후 다시 commit.
> 로컬 사전 점검: `pre-commit run --all-files` 또는 `ruff check . && ruff format .`

### 7.2 수동 점검 (작성자 책임)
1. 변수명 의미 명확성 (`tmp`, `data` 배제).
2. 함수명 "동사 + 목적어" 규칙 준수.
3. Import 순서 (표준 → 서드파티 → 내부, 알파벳 정렬). *(ruff `I` 미활성)*
4. 신규 함수 Docstring 작성 여부 (§6.3).
5. `None`과 `0`의 구분 (센서 데이터에서 `0`은 유효값).
6. 하드코딩된 비밀번호/API 키 부재 확인.
7. `print()` 대신 `logging` 사용 여부 (§6.7).
8. 단일 함수 30줄 초과 여부 (초과 시 분리 고려).
9. 인라인 주석이 §6.4 WHY 4종 분류에 해당하는지 (그 외엔 코드로 표현).
