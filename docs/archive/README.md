# docs/archive — 시점성 작업기록 아카이브

완료된 작업의 시점별 산출물을 모아둔 곳입니다. **현행 레퍼런스가 아니라 "당시 결정·변경의 근거"를 추적하기 위한 동결 기록**입니다. 현행 문서는 [docs/](../) 상위 폴더를 보세요.

> 아카이브 문서 내부의 코드 파일 링크 일부는 작성 당시 기준이라 현재 코드 구조와 어긋날 수 있습니다. 코드의 진실 공급원은 항상 실제 소스입니다.

## 구성

| 폴더 | 내용 | 시기 |
|---|---|---|
| [changelog/](changelog/) | PR·머지 단위 변경 이력 (트랙별 서브폴더) — [changelog/README.md](changelog/README.md) | 2026-04 ~ 05 |
| [phases/](phases/) | Phase 1~4 plan·report + Post-Phase 4 B-track + 회귀 점검 | 2026-05-08 ~ 09 |
| [codereviews/](codereviews/) | 날짜별 코드리뷰·데이터 흐름 분석 (알람·전력 5축 등) | 2026-05-09 ~ 21 |
| [refactor/](refactor/) | 2026-05-09 대규모 리팩토링 분석 (JS 함수 단위 `js/`, 웨이브 `waves/`) | 2026-05-09 |
| [plan/](plan/) | 폐기·대체된 계획서 (PG 마이그레이션 구 체크리스트, 미실행 초안) | — |

## 타임라인 개요

1. **2026-04** — DRF/FastAPI 초기 리팩토링 (`changelog/early_2026-04/`)
2. **2026-05-07~09** — Phase 1~5 백엔드 리팩토링 + 도메인별 코드리뷰 + JS/웨이브 정리 (`changelog/phase1-5_refactoring/`, `codereviews/2026_05_09/`, `refactor/`)
3. **2026-05-13~15** — ML 이상탐지 인프라 + 알람 신뢰성 (`changelog/ml/`, `changelog/alarm_reliability/`)
4. **2026-05-15~21** — 알람 시스템 재설계·증상 진단 (`codereviews/2026_05_15` ~ `2026_05_21`)
5. **2026-05-22** — PostgreSQL 전환 (현행 가이드는 [../migration/](../migration/))
