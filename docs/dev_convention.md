# SKILL: dev-convention
## DESCRIPTION
산재 예방 통합 관제 시스템 개발팀(4인)을 위한 Python, Django, FastAPI 통합 코딩 스타일, 네이밍, 주석, 아키텍처 컨벤션 가이드.

## TRIGGER CONDITIONS
- "컨벤션/코드 스타일 가이드 알려줘/보여줘"
- "네이밍 규칙이 뭐야?", "변수명/함수명 어떻게 지어?"
- "Django 모델명/FastAPI 라우터 파일명 규칙이 뭐야?"
- "주석 어떻게 달아?"
- 새 파일/함수 생성 및 코드 리뷰(code-review 스킬 연계) 시

## 1. PYTHON BASIC STYLE (PEP 8)
- **들여쓰기**: 스페이스 4칸 (Tab 금지).
- **줄 길이**: 최대 79자. 긴 문자열/인자는 줄바꿈 적용.
- **문자열**: 큰따옴표(`""`) 기본 사용. 문자열 포매팅은 `f-string`만 사용.
- **빈 줄(Blank Lines)**:
  - 클래스 및 최상단 함수 위아래: 2줄
  - 클래스 내부 메서드 사이: 1줄
- **Import 순서**: 그룹 간 빈 줄 1개, 그룹 내 알파벳 정렬.
  1. 표준 라이브러리 (ex: `os`, `datetime`)
  2. 서드파티 (ex: `fastapi`, `pydantic`)
  3. 내부 모듈 (ex: `app.schemas`)

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
- **Docstring**: `"""` 사용. 클래스 및 외부 호출용 함수에 필수 작성. `Args`와 `Returns` 명시.
- **인라인/블록 주석**: 코드의 "무엇"이 아닌 **"왜(이유, 목적)"**를 설명.
  - 법적 근거, 비즈니스 규칙 출처 명시 (ex: 산업안전보건법 기준).
- **TODO**: 담당자와 기한 명시 (ex: `# TODO(재용): ...`).
- **로깅 (Logging)**: `print()` 금지. 내장 `logging` 모듈 사용.
  - 포맷: `logger.LEVEL(f"[CATEGORY] key=value")`
  - 레벨: `DEBUG`(상세), `INFO`(정상완료), `WARNING`(주의/재시도), `ERROR`(실패).

## 7. PRE-PR CHECKLIST (자주 하는 실수 방지)
1. 변수명 의미 명확성 (`tmp`, `data` 배제).
2. 함수명 "동사 + 목적어" 규칙 준수.
3. Import 순서 (표준 -> 서드파티 -> 내부).
4. 신규 함수 Docstring 작성 여부.
5. `None`과 `0`의 구분 (센서 데이터에서 `0`은 유효값).
6. 하드코딩된 비밀번호/API 키 부재 확인.
7. `print()` 대신 `logging` 사용 여부.
8. 단일 함수 30줄 초과 여부 (초과 시 분리 고려).
