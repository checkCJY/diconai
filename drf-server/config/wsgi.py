"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

# gunicorn은 이 파일을 진입점으로 사용. 기본값을 prod로 설정.
# docker-compose에서 DJANGO_SETTINGS_MODULE을 명시하면 그 값이 우선 적용됨.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

application = get_wsgi_application()
