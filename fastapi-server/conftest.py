"""
fastapi-server pytest 공통 fixture (PR-F).

[scope]
- 단위 테스트 위주 (스모크). 외부 DB/HTTP 의존 없음.
- 추후 통합 테스트 도입 시 httpx mock + DRF 응답 fixture 확장.
"""
