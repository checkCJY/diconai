"""fastapi-server 로깅 설정.

drf-server의 settings.LOGGING과 동일한 포맷·정책을 적용한다.

컨벤션 (docs/dev_convention.md §6):
    - 모듈별 logger: logger = logging.getLogger(__name__)
    - 메시지 포맷: f"[CATEGORY] key=value key=value"
    - 레벨: DEBUG(상세) / INFO(정상완료) / WARNING(주의·재시도) / ERROR(실패)

app.py 진입 시점에 setup_logging()을 1회 호출하면 dictConfig가 적용된다.
LOG_LEVEL은 core.config.Settings.LOG_LEVEL을 통해 .env에서 주입된다.

파일 로깅 정책 (배경: skill/study/2026-05-26_파일_로깅_도입_배경.md):
    - error.log: ERROR 이상만, 100MB × 10 = 1GB 캡 (시연·사고 추적 1순위)
    - app.log:   INFO 이상,  50MB × 5  = 250MB 캡 (startup·정상 흐름 확인)
    - drf-server와 동일한 형식·정책으로 양 서버 로그를 합쳐 보기 쉽게 통일.
"""

import logging.config
from pathlib import Path


def build_logging_config(level: str = "INFO") -> dict:
    # 파일 로깅용 디렉토리 — Docker volume 마운트 시점에 디렉토리가 없어도
    # RotatingFileHandler가 실패하지 않게 보호. dictConfig 적용 직전 1회 생성.
    logs_dir = Path(__file__).resolve().parent.parent / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "diconai": {
                "format": "{asctime} {levelname:<7} {name}: {message}",
                "datefmt": "%Y-%m-%d %H:%M:%S",
                "style": "{",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "diconai",
            },
            "file_error": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": str(logs_dir / "error.log"),
                "maxBytes": 100 * 1024 * 1024,  # 100MB × 10 = 1GB 캡
                "backupCount": 10,
                "level": "ERROR",
                "formatter": "diconai",
                "encoding": "utf-8",
            },
            "file_app": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": str(logs_dir / "app.log"),
                "maxBytes": 50 * 1024 * 1024,  # 50MB × 5 = 250MB 캡
                "backupCount": 5,
                "level": "INFO",
                "formatter": "diconai",
                "encoding": "utf-8",
            },
        },
        "root": {
            "handlers": ["console", "file_error", "file_app"],
            "level": level,
        },
        "loggers": {
            # uvicorn.error: startup/shutdown + 미처리 예외 → 시연 디버깅 핵심 단서.
            # propagate=False 라서 root 핸들러로 안 흘러감 → 파일 핸들러 명시 추가.
            "uvicorn.error": {
                "handlers": ["console", "file_error", "file_app"],
                "level": level,
                "propagate": False,
            },
            # uvicorn.access: HTTP access log → Grafana http_requests_total 메트릭으로 대체.
            # 파일 적재 시 정상 트래픽으로 노이즈 폭증 → console만 유지.
            "uvicorn.access": {
                "handlers": ["console"],
                "level": level,
                "propagate": False,
            },
        },
    }


def setup_logging(level: str = "INFO") -> None:
    """앱 기동 시 1회 호출. 이후 모든 logger가 동일 포맷으로 출력된다."""
    logging.config.dictConfig(build_logging_config(level))
