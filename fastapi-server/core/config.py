# core/config.py — 서버 전역 설정
#
# Pydantic BaseSettings 기반 환경변수 관리.
# 모든 모듈은 os.getenv() 대신 settings 인스턴스를 import해서 사용한다.
# 우선순위: 환경변수 > .env 파일 > 코드 기본값
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """DRF 연동에 필요한 설정값. .env 파일 또는 환경변수로 주입 가능."""

    DRF_BASE_URL: str = "http://localhost:8000"
    DRF_SERVICE_TOKEN: str = ""  # 빈 문자열이면 Authorization 헤더 미포함

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
