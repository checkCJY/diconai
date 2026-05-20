# SKILL: dev-convention
## DESCRIPTION
산재 예방 통합 관제 시스템 개발팀(4인)을 위한 통합 컨벤션 가이드. Python(Django/FastAPI) · Frontend(JS/HTML/CSS) · 인프라(Dockerfile/Compose/k8s/GH Actions/Shell) 모든 파일의 코딩 스타일, 네이밍, 주석/docstring, 아키텍처 규약을 정의한다.

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

## 6. COMMENTS, DOCSTRINGS & LOGGING

> **§6 의 원칙은 언어 무관 — Python · JS · HTML · CSS, 그리고 인프라 파일(Dockerfile · docker-compose · k8s manifest · GH Actions · Shell)에 모두 적용한다.**
> 주석/docstring 의 **문법만** 각 언어에 매핑되고, 작성 원칙(행동 중심 · 데이터 흐름 명시 · sprint 마커 금지 · WHY 4종 · 안티패턴 5종 · 깔끔하면서도 충분)은 동일하다.
> Python 은 PEP8 §주석 + PEP257 docstring 표준을 따른다.

> **두 줄 기준 (모든 절에 공통)**
> 1. **깔끔** — 군더더기 없이 짧게. sprint 마커(`T1/T3/2026-05-19`), 작업 이력, 검토 결정 과정 코드 밖으로.
> 2. **충분** — 코드 본문을 안 봐도 주석/docstring 만으로 **이 파일/클래스/함수가 어떤 행동을 어떤 데이터 흐름으로 하는지** 파악 가능해야 한다.

### 6.0 언어별 문법 매핑

| 항목 | Python | JS | HTML | CSS | YAML / Dockerfile / Shell |
|---|---|---|---|---|---|
| 1줄 주석 | `# ...` | `// ...` | `<!-- ... -->` | `/* ... */` | `# ...` |
| 블록 주석 | `# ` 연속 | `/* ... */` | `<!-- ... -->` | `/* ... */` 다줄 | `# ` 연속 |
| 모듈/파일 헤더 | `# <경로>/<file.py> — 역할` 블록 | `// <경로>/<file.js> — 역할` 블록 | `<!-- <file.html> — 역할 -->` 블록 | `/* <file.css> — 역할 ... */` 블록 | `# Dockerfile — 역할` 블록 |
| 클래스/함수 docstring | `"""..."""` (PEP257) | `/** ... */` JSDoc | — | — | — |

### 6.1 모듈/파일 헤더 — 데이터 흐름 명시 ★

> **모든 비즈니스 로직·진입점 파일은 헤더에 데이터 흐름(IN/OUT)을 명시한다.**
> 파일이 어떤 데이터를 받아 어디로 넘기는지가 가장 먼저 보여야 한다.

**형식**:
1. 첫 줄: `<상위경로>/<file.확장자> — 역할 한 줄`
2. 빈 주석 줄
3. `데이터 흐름:` 섹션 — `IN:` / `OUT:` 각 1~3줄
4. (선택) `구성 요소:` 또는 짧은 나열 / 외부 의존

**필수 대상 (데이터를 받아 어딘가로 넘기는 파일)**:
- Python: `services/`, `views/`, `routers/`, `tasks.py`, `selectors/`, `signals.py`, WebSocket handlers
- JS: 페이지별 진입 JS, `*-mapper.js`, `alarm-popup.js` 같은 글로벌 핸들러
- HTML: 페이지 템플릿 (`{% extends %}` 직후 또는 최상단)
- CSS: 컴포넌트 단위 stylesheet
- 인프라: Dockerfile, docker-compose.yml, GH Actions yaml, k8s manifest, 운영 shell

**비대상 (데이터 흐름 없음)**: `models/`, `utils/`, `exceptions.py`, `constants.py`, base CSS — 클래스/상수 docstring 으로 충분.

**표준 예시 — Python**:
```python
# alerts/tasks.py — 가스 알람 Celery 태스크
#
# 데이터 흐름:
#   IN  : Celery 큐의 alarm_data dict (fastapi gas_service 가 enqueue)
#         { gas_type, value, sensor_identifier, alarm_level, ... }
#   OUT : 1) DB — AlarmRecord / Event / EventLog 기록
#         2) FastAPI POST /internal/alarms/push/ — WS broadcast 큐 추가
#
# 3종 태스크:
#   fire_danger_alarm_task       : DANGER 즉각
#   fire_warning_alarm_task      : WARNING 30s 지속 후 (countdown=30)
#   fire_clear_notification_task : 정상화
```

**표준 예시 — JS**:
```javascript
// shared/alarm-popup.js — 알람 토스트/모달 렌더링
//
// 데이터 흐름:
//   IN  : WS 메시지 (alarm-router → broadcast)
//         { alarm_type, event_id, alarm_level, sensor_name, event_resolved_at, ... }
//   OUT : DOM — 토스트 스택 + 모달 popup
//         localStorage — _AckStore (확인 상태) + _DedupStore (60s TTL)
//
// 외부 의존: AlarmMapper.normalize() — WS 메시지 → 정규화 객체
```

**표준 예시 — CSS**:
```css
/* alarm-popup.css — 알람 토스트/모달 스타일
 *
 * 데이터 흐름:
 *   IN  : alarm-popup.js 가 .alarm-toast-stack, .alarm-modal 클래스 부착
 *   OUT : 화면 우상단 토스트 스택 + 중앙 모달
 *
 * 색상 토큰: danger=#e74c3c, warning=#f39c12, clear=#27ae60
 */
```

**표준 예시 — HTML**:
```html
<!-- monitoring/dashboard.html — 실시간 가스/전력 대시보드
 |
 | 데이터 흐름:
 |   IN  : drf view context (sensors, workers, recent_alarms)
 |         + WS /ws/sensors/ (실시간 값 갱신)
 |   OUT : 차트·맵·알람 패널 DOM
 |
 | 외부 의존: monitoring-realtime.js, chart-renderer.js
 -->
```

**표준 예시 — Dockerfile**:
```dockerfile
# drf-server/Dockerfile — Django REST 서버 이미지
#
# 데이터 흐름:
#   IN  : requirements.txt + drf-server/ 소스
#   OUT : Gunicorn :8000 + manage.py migrate (entrypoint)
#
# 베이스: python:3.12-slim
# 볼륨  : /app/db (SQLite), /app/media
```

### 6.2 클래스/컴포넌트 Docstring

> **클래스 본문을 안 봐도 docstring 만으로 "무엇을 위한 클래스이고 어떤 도메인 약속을 따르는지" 파악 가능해야 한다.**

- **깔끔**: 첫 줄 imperative 1줄 요약(마침표). 군더더기 어구(`이 클래스는...`) 제거. sprint 마커 첫 줄 금지.
- **충분**: 단순 wrapper 가 아니면 본문에 다음 섹션 태그로 의도·도메인 맥락을 묶는다.
  - `[설계 원칙]` — 이 모델/클래스를 만든 이유와 wide table 등 구조 결정의 근거
  - `[가스 종류 출처]`, `[임계치 출처]` — 외부 명세서·법규 참조
  - `[null 처리]` — `None`/`0` 구분 등 도메인 규약
  - `[관계 의도]` — FK·related_name·역참조의 의도

**필수 대상**: `models/` 의 모든 모델 클래스, 외부에서 import 되는 모든 클래스, JS 의 전역 컨트롤러/싱글톤.

**Python 표준 예시**: `drf-server/apps/monitoring/models/gas_data.py:8-22`, `drf-server/apps/alerts/models/event.py:8-35`.

**JS (JSDoc) 표준 예시**:
```javascript
/**
 * AlarmPopup — 알람 모달 컨트롤러.
 *
 * 단일 인스턴스. WS 메시지가 도착하면 alarm_level 에 따라
 * 모달을 열거나 토스트로 격하 표시한다.
 *
 * 도메인 규약:
 *   - event_resolved_at 박힌 메시지는 모달 close + 회색 토스트.
 *   - localStorage 의 _AckStore 와 sync 하여 확인 상태 영속화.
 */
```

### 6.3 함수 Docstring

> **함수 본문을 안 봐도 docstring 만으로 "무엇을 · 어떤 단계로 · 어떤 계약으로" 하는지 파악 가능해야 한다.**

- **깔끔**: 첫 줄 imperative 1줄(마침표). "이 함수는 ~한다" → "~한다". sprint 마커 첫 줄 금지.
- **충분**: 외부 호출용(view·service·API·외부 import) 함수는 다음 4종 중 해당되는 것 모두 포함.
  1. **단계별 동작** (`1./2./3.`) — 비즈니스 로직 함수 필수
  2. **Args / Returns** — 자명하지 않은 파라미터·반환값
  3. **계약** — 트랜잭션 경계, 락, 외부 호출 실패 정책, 멱등성
  4. **도메인 맥락** — 임계치 출처, 특수 처리 근거 (`O2 의 0 은 유효값` 등)
- **내부 헬퍼**(`_` 접두): 1줄로 충분. 단, 그 1줄이 호출자가 이해할 수 있게 self-contained 여야 함.

**Python 표준 예시**: `drf-server/apps/alerts/services/event_service.py:31-37`.
```python
def create_alarm_and_event(...):
    """AlarmRecord + Event 를 생성하거나 활성 Event 에 병합한다.

    1. 병합 대상 활성 Event 검색 (select_for_update)
    2. 존재: AlarmRecord 만 생성, Event 업데이트
    3. 없음: Event 생성 + AlarmRecord 생성 + EventLog(CREATED)

    동시성: select_for_update 로 동일 facility 동시 생성 race 방지.
    """
```

**JS (JSDoc) 표준 예시**:
```javascript
/**
 * 활성 Event 의 EventAck 사용자명 목록을 반환한다.
 *
 * 다중 관리자 환경에서 토스트에 "(N 확인 중)" 시그널을 표시하기 위해 호출된다.
 *
 * @param {object} data - WS 메시지 (alarm-router 정규화 후)
 * @returns {string[]} — 빈 배열이면 시그널 미표시
 */
```

### 6.4 인라인 주석 — WHY 4종 분류 ★

인라인 주석은 아래 **4종 중 하나**에 해당할 때만 작성한다. 그 외에는 주석 없이 코드 자체로 의미를 드러낸다.
주석 한 줄은 **self-contained** — 다른 줄을 안 봐도 이 한 줄로 의도가 잡혀야 한다.

| 분류 | 적용 대상 | 예시 |
|---|---|---|
| **상수·매직넘버** | 임계치, 타이머, 쿨다운, 배치 크기 등 숫자 상수 | `RENOTIFY_COOLDOWN_MINUTES = 5  # 동일 이벤트 재알림 최소 간격 — 알람 폭주 방지` |
| **동시성·트랜잭션** | `select_for_update`, `asyncio.Event`, lock, atomic | `# select_for_update — 동일 facility 동시 알람 생성 race 방지` |
| **도메인 특수성** | 직관과 다른 처리, 의외의 분기 | `# O2 는 0 이 유효값 — None 만 결측 처리 (산소 결핍 0% 측정 가능)` |
| **외부 시스템 계약** | 실패 정책, 재시도, 타임아웃 의도 | `# WS 푸시 실패해도 태스크 성공 — DB 기록이 진실의 원천` |

### 6.5 안티패턴 5종 — 작업 이력 dumping 금지 ★

다음 패턴은 **코드/주석/docstring 어디에도 박지 않는다.** 작업 이력은 PR 본문 · plan 문서 · changelog 에 둔다.

| 안티패턴 | 잘못된 예 (실제 코드에서 발견) | 처리 방침 |
|---|---|---|
| ① sprint 코드/날짜 마커 | `# T3 (2026-05-19) — 활성 Event 의 EventAck...`, `# 2026-05-15 알람 재설계:` | sprint 코드·날짜는 외부 문서. 코드엔 의도만. |
| ② 검토 결정 이력 | `# 30s 하향 검토 후 60s 유지 결정 — "폭주 회피"` | "왜 60s 인가" 1줄. 검토 과정은 PR 본문. |
| ③ 동일 주석 중복 | 5개 `fire_*_task` 함수에 같은 3줄 블록 복붙 | 헬퍼 docstring 1회 또는 코드 자체로 표현. |
| ④ docstring 첫 줄 sprint 마커 | `"""T3 (2026-05-19) — 활성 Event 의 ..."""` | PEP257 위반. imperative 1줄 요약으로 교체. |
| ⑤ 인접 주석 누적 | 상수 1개 위 5~6줄 주석 블록 (의도+검토+이력+제외사항) | 의도 1~2줄로 압축. 상세는 모듈 헤더 또는 외부 문서. |

### 6.6 좋은 예 / 나쁜 예

**docstring 첫 줄 (PEP257)**:

| 나쁜 예 | 좋은 예 |
|---|---|
| `"""T3 (2026-05-19) — EventAck 사용자명 list."""` (sprint 마커) | `"""활성 Event 의 EventAck 사용자명 list 를 반환한다."""` |
| `"""사용자 이름을 반환한다."""` (호출 맥락 부재) | `"""활성 Event 의 EventAck 사용자명 list 를 반환한다. 다중 관리자 환경 토스트의 '(N 확인 중)' 시그널 표시용."""` |
| `"""이 함수는 알람을 생성한다."""` (군더더기 + WHAT) | `"""DANGER 알람을 즉각 발화한다."""` |

**인라인 주석**:

| 나쁜 예 (WHAT/sprint) | 좋은 예 (WHY/행동) |
|---|---|
| `# 이벤트를 생성한다` | `# 활성 이벤트 부재 또는 12h 윈도우 초과 시 새 Event 생성` |
| `# 5분으로 설정` | `# 5분 — 알람 폭주 vs 위험 재상승 감지의 균형 (운영팀 합의)` |
| `# T3 (2026-05-19): 30s 검토 후 60s 유지` | `# 60s — 같은 센서 알람 폭주 회피 (브라우저·운영자 UX)` |
| `# None 체크` | `# 통신 불능 채널은 0 이 아닌 None — false positive 방지` |
| `# 락 건다` | `# select_for_update — 동시 AlarmRecord 생성 race 방지` |

**모듈 헤더 (JS)**:

| 나쁜 예 | 좋은 예 |
|---|---|
| `// alarm-popup.js — 팝업 처리` (역할 모호·데이터 흐름 부재) | `// shared/alarm-popup.js — 알람 토스트/모달 렌더링` + `IN/OUT` 블록 (§6.1) |

### 6.7 주석 정비 원칙 ★

- **로직·주석 작업 분리**: 주석 정비 PR 에서 코드 로직(분기·임계치·변수명) 수정 금지. 발견하면 별도 PR.
- **추측 금지**: 의도가 불명확하면 주석을 작성하지 않는다. 작성자 확인 또는 `drf-server/docs/known-issues/` 로 인계.
- **sync 의무**: 코드 변경 시 인접 주석/docstring 동기 검토. stale 주석은 즉시 수정 또는 삭제.
- **언어 무관**: Python · JS · HTML · CSS · 인프라 파일 모두 동일 원칙. 문법만 §6.0 매핑 참조.

### 6.8 TODO / FIXME

- **형식**: `# TODO(담당자) [기한]: 설명` (ex: `# TODO(재용) [2026-06-01]: 임계치 외부 설정 분리`)
- **FIXME**: 알려진 버그가 있고 임시 우회 중인 경우만 사용. 같은 형식.
- JS/CSS/HTML 등 다른 언어도 동일 형식, 문법만 §6.0 매핑.

### 6.9 로깅 (Logging)

- **Python**: `print()` 금지, 내장 `logging` 모듈만 사용.
  - **포맷**: `logger.LEVEL(f"[CATEGORY] key=value")`
  - **레벨**: `DEBUG`(상세), `INFO`(정상완료), `WARNING`(주의/재시도), `ERROR`(실패).
- **JS**: 운영 코드의 `console.log` 잔여물 제거. 디버깅 출력 commit 금지.

## 7. PRE-PR CHECKLIST

### 7.1 자동 (pre-commit이 처리)
들여쓰기·88자 줄바꿈·큰따옴표·빈 줄·trailing comma·trailing whitespace·파일 끝 줄바꿈·미사용 import 제거.
> commit 시 ruff-format이 파일을 수정하면 거부됨 → `git add <수정된 파일>` 후 다시 commit.
> 로컬 사전 점검: `pre-commit run --all-files` 또는 `ruff check . && ruff format .`

### 7.2 수동 점검 (작성자 책임)
1. 변수명 의미 명확성 (`tmp`, `data` 배제).
2. 함수명 "동사 + 목적어" 규칙 준수.
3. Import 순서 (표준 → 서드파티 → 내부, 알파벳 정렬). *(ruff `I` 미활성)*
4. **신규 모듈/파일에 §6.1 데이터 흐름 헤더(IN/OUT) 작성 여부.**
5. 신규 함수/클래스 Docstring (§6.2·§6.3) — 깔끔(첫 줄 imperative) + 충분(코드 안 봐도 행동 파악) 둘 다 만족.
6. `None`과 `0`의 구분 (센서 데이터에서 `0`은 유효값).
7. 하드코딩된 비밀번호/API 키 부재 확인.
8. `print()` 대신 `logging` 사용 여부 (§6.9). JS `console.log` 잔여물 부재.
9. 단일 함수 30줄 초과 여부 (초과 시 분리 고려).
10. 인라인 주석이 §6.4 WHY 4종 중 하나에 해당하는지 (그 외엔 코드로 표현).
11. **안티패턴 5종 (§6.5) 부재 — sprint 마커·검토 결정·중복·docstring 첫 줄 sprint·인접 누적 없음.**
