# diconai 문서 허브

산재 예방 통합 관제 시스템(diconai)의 전체 문서 인덱스입니다. 목적별로 폴더가 나뉘어 있습니다.

> 프로젝트 전체 개요·실행은 루트 [README.md](../README.md), 빠른 시작은 [QUICKSTART.md](QUICKSTART.md)부터 보세요.

---

## 무엇을 보려면 어디로

| 목적 | 위치 |
|---|---|
| 클론→가동 빠른 시작 | [QUICKSTART.md](QUICKSTART.md) |
| 시스템 한 페이지 개요 | [architecture.md](architecture.md) |
| 데이터 저장·DB 구조 | [database.md](database.md) |
| 배포·운영 매뉴얼 | [deployment.md](deployment.md) |
| 환경 변수 정리 | [env-guide.md](env-guide.md) |
| API 5분 요약 | [api.md](api.md) (전체 명세는 [specs/api_specification.md](specs/api_specification.md)) |
| 성과 검증 결과 | [results.md](results.md) |
| 트러블슈팅 모음 | [troubleshooting.md](troubleshooting.md) |

## 레퍼런스 (현행 SoT)

| 폴더 | 내용 |
|---|---|
| [conventions/](conventions/) | 코드·Git·API 응답 컨벤션 + [COMMANDS.md](conventions/COMMANDS.md) |
| [specs/](specs/) | API·JSON 필드·URL·디렉토리 구조 명세 |
| [domains/](domains/) | 도메인별 아키텍처 SoT (gas/power/alerts/ai-ml/positioning/websocket) — [domains/README.md](domains/README.md) |
| [ai/](ai/) | AI 이상탐지 의사결정·파이프라인·적용현황 |
| [infra/](infra/) | Docker·Redis/Celery·WebSocket 확장성 가이드 |
| [features/](features/) | 기능정의서 — [features/README.md](features/README.md) |
| [api/](api/) | 자동 생성 OpenAPI 스냅샷 (yaml/json; html은 로컬 생성) |
| [incidents/](incidents/) · [migration/](migration/) | 장애 리포트 · DB 마이그레이션 가이드 |
| [plan/](plan/) | 진행 중 로드맵 (전력 AI 센싱 확장, PG 안정화, multi-replica 검토) |

## 제출 산출물

| 위치 | 내용 |
|---|---|
| [submission/tech-doc.md](submission/tech-doc.md) | 개인 기술문서 (전력 AI·알람) |
| [submission/team-tech-doc.md](submission/team-tech-doc.md) | 팀 기술문서 |
| [submission/templates/](submission/templates/) | 기술문서 템플릿·발표 가이드·자료 인덱스 |

## 아카이브 (시점성 작업기록)

완료된 시점의 작업 산출물은 [archive/](archive/)에 모여 있습니다 — [archive/README.md](archive/README.md) 참고.
changelog · phases · codereviews · refactor · 폐기된 plan.
