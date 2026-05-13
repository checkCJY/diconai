# syntax=docker/dockerfile:1.6
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN pip install uv==0.5.7

WORKDIR /app
COPY requirements.txt requirements-dev.txt ./
# dev 의존성(pytest, pytest-django, jupyterlab, matplotlib, pandas)을 image 빌드 시 함께 install.
# 이유: UID 매핑 환경에서 컨테이너 안 pip install 은 site-packages 쓰기 권한 없어 실패 →
#       dev tool 은 이미지에 미리 포함시켜 컨테이너 실행 후 추가 install 불필요.
# 현재 이미지 태그 diconai/drf:dev — dev 전용. 운영 배포 시 별도 빌드 권장.
RUN uv pip install --system -r requirements.txt -r requirements-dev.txt


FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY . .

RUN chmod +x ./entrypoint.sh

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8000/health/ || exit 1

ENTRYPOINT ["./entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
