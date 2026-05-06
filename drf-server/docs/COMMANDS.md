**/home/cjy/diconai/drf-server/실행명령어.md**

### DJango 실행 명령어
python manage.py runserver

### celery 실행 명령어
celery -A config worker -l info --concurrency=1


### Django 마이그레이션 관련 명령어
python manage.py makemigrations
python manage.py migrate
python manage.py showmigrations
