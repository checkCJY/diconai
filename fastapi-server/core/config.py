# core/config.py — 서버 전역 설정
#
# Pydantic BaseSettings 기반 환경변수 관리.
# 모든 모듈은 os.getenv() 대신 settings 인스턴스를 import해서 사용한다.
# 우선순위: 환경변수 > .env 파일 > 코드 기본값
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """fastapi-server 전역 설정. .env 파일 또는 환경변수로 주입 가능."""

    # ── 로깅 ───────────────────────────────────────────────────
    # core.logging.setup_logging()에 전달. DEBUG/INFO/WARNING/ERROR.
    LOG_LEVEL: str = "INFO"

    # ── DRF 연동 ───────────────────────────────────────────────
    DRF_BASE_URL: str = "http://localhost:8000"
    DRF_SERVICE_TOKEN: str = ""  # 빈 문자열이면 Authorization 헤더 미포함
    DRF_REQUEST_TIMEOUT_SEC: float = 5.0

    # ── Redis (Phase 1 C4) ─────────────────────────────────────
    # 알람 큐(diconai:ws:alarms) + 향후 IF rate limit/메트릭 공유 저장소.
    # 로컬: redis://localhost:6379/0, 도커 컴포즈: redis://redis:6379/0 (compose가 주입).
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── 서비스 간 인증 토큰 (Phase 5) ──────────────────────────
    # /internal/alarms/push/ (Celery → FastAPI) 검증용. 빈 문자열이면 비활성.
    # 운영에서는 drf의 INTERNAL_SERVICE_TOKEN과 동일 값으로 설정.
    INTERNAL_SERVICE_TOKEN: str = ""

    # ── WebSocket JWT 인증 (Phase 5) ──────────────────────────
    # drf SimpleJWT가 발급한 access 토큰을 같은 SIGNING_KEY로 검증.
    # 빈 문자열이면 비활성 (기존 무인증 동작 유지). 운영에서는 drf의 JWT_SIGNING_KEY와 동일 값.
    JWT_SIGNING_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"  # drf SimpleJWT 기본 알고리즘과 일치

    # ── WebSocket 브로드캐스트 ─────────────────────────────────
    # 메인 broadcast 주기. 너무 짧으면 클라이언트 부하 증가.
    BROADCAST_INTERVAL_SEC: float = 5.0
    # 데이터가 이 시간 이상 갱신 안 되면 stale 처리.
    DATA_STALE_THRESHOLD_SEC: float = 8.0

    # ── 전력 임계치 (단위: W, Phase A 기준) ──────────────────────
    # 표시용 fallback. 실제 알람 판정은 DRF가 수행 (단일 진실 공급원: DRF
    # facilities.Threshold(group="power_default", item="power_w")). 어드민에서 변경 시
    # 본 env도 동기화 의무 (운영 진입 시 DRF API fetch 캐시 검토).
    POWER_THRESHOLD_CAUTION: int = 2200
    POWER_THRESHOLD_DANGER: int = 2860

    # ── 더미 송출 (개발/테스트 전용) ─────────────────────────────
    # dummies/*.py 스크립트에서 fastapi-server 본인을 호출할 때 사용.
    DUMMY_TARGET_HOST: str = "127.0.0.1"
    DUMMY_TARGET_PORT: int = 8001
    # 송출 주기(초). 가스/전력/위치 3종 더미가 공유. 0 이하면 1회만 송출.
    DUMMY_SEND_INTERVAL_SEC: float = 3.0
    # 임계치 초과 케이스 발생 확률 (0.0 ~ 1.0).
    DUMMY_RISK_PROBABILITY: float = 0.1
    # 시연 시나리오 모드. mixed=확률 기반, normal/warning/danger=고정.
    # 더미는 부팅 시 이 값을 초기 상태로 사용하고, 이후 FastAPI에 polling.
    DUMMY_SCENARIO_MODE: str = "mixed"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
