"""fastapi-server 로깅 설정.

drf-server의 settings.LOGGING과 동일한 포맷·정책을 적용한다.

컨벤션 (docs/dev_convention.md §6):
    - 모듈별 logger: logger = logging.getLogger(__name__)
    - 메시지 포맷: f"[CATEGORY] key=value key=value"
    - 레벨: DEBUG(상세) / INFO(정상완료) / WARNING(주의·재시도) / ERROR(실패)

app.py 진입 시점에 setup_logging()을 1회 호출하면 dictConfig가 적용된다.
LOG_LEVEL은 core.config.Settings.LOG_LEVEL을 통해 .env에서 주입된다.
"""

import logging.config


def build_logging_config(level: str = "INFO") -> dict:
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
        },
        "root": {
            "handlers": ["console"],
            "level": level,
        },
        "loggers": {
            "uvicorn.error": {
                "handlers": ["console"],
                "level": level,
                "propagate": False,
            },
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
