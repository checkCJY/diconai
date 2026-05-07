# drf-server 실행 명령어

> Django REST Framework 서버 (포트 8000) 운영용 명령어 모음

---

## 서버 실행

```bash
python manage.py runserver
```

기본 포트 8000으로 개발 서버 기동. 다른 포트로 띄우려면 `runserver 0.0.0.0:8080` 형태로 지정.

---

## Celery 워커 실행

```bash
celery -A config worker -l info --concurrency=1
```

알람 생성·푸시 등 비동기 태스크 처리 워커. 개발 환경에서는 `--concurrency=1`로 단일 워커 권장
(동시성 이슈 디버깅 용이).

---

## 마이그레이션

| 명령 | 용도 |
|---|---|
| `python manage.py makemigrations` | 모델 변경 사항으로부터 마이그레이션 파일 생성 |
| `python manage.py migrate` | 마이그레이션을 DB에 적용 |
| `python manage.py showmigrations` | 적용 여부를 앱별로 확인 |
