import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("diconai")

# CELERY_ 네임스페이스로 settings.py에서 설정을 읽는다.
app.config_from_object("django.conf:settings", namespace="CELERY")

# INSTALLED_APPS의 모든 앱에서 tasks.py를 자동 탐색한다.
app.autodiscover_tasks()
