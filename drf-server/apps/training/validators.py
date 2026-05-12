"""
apps/training/validators.py — VR 영상 업로드 파일 검증.

[제약 — VR 콘텐츠 정책]
- 확장자: mp4 / webm / mov (소문자 비교)
- MIME prefix: video/* (브라우저가 보낸 content_type 1차 가드)
- 최대 크기: 500MB (notices 10MB와 분리 — VR은 대용량 시나리오 가정)

[책임 분리]
File 객체에 대한 단순 검증만 수행한다. duration 추출은 services/ffprobe.py.
"""

from django.core.exceptions import ValidationError

ALLOWED_VIDEO_EXTENSIONS = {"mp4", "webm", "mov"}
ALLOWED_VIDEO_MIME_PREFIX = "video/"
MAX_VIDEO_SIZE_BYTES = 500 * 1024 * 1024  # 500MB


def validate_video_extension(file) -> None:
    """파일명 확장자가 허용 목록에 있는지 검증.

    [대소문자 무시]
    `Sample.MP4` 같은 입력도 통과시키기 위해 소문자 변환 후 비교.

    [확장자 없음 처리]
    확장자가 없는 파일명은 빈 문자열로 취급되어 화이트리스트 불일치로 거부된다.
    """
    name = (file.name or "").lower()
    ext = name.rsplit(".", 1)[-1] if "." in name else ""
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        raise ValidationError(
            f"허용되지 않은 영상 확장자: '{ext}'. "
            f"허용: {sorted(ALLOWED_VIDEO_EXTENSIONS)}"
        )


def validate_video_max_size(file) -> None:
    """업로드 파일 크기가 500MB 한도를 넘지 않는지 검증.

    한도 초과 시 즉시 거부 — gunicorn worker 메모리 보호 + 운영 디스크 폭주
    방지가 목적. 한도값(`MAX_VIDEO_SIZE_BYTES`)은 본 모듈 상단에서 조정 가능.
    """
    if file.size > MAX_VIDEO_SIZE_BYTES:
        raise ValidationError("영상 파일은 500MB를 초과할 수 없습니다.")


def validate_video_mime(file) -> None:
    """브라우저가 보낸 `content_type` 헤더가 `video/*` 계열인지 1차 가드.

    [약식 검증인 이유]
    클라이언트가 보낸 MIME은 위조 가능하다. 정확한 컨테이너 검증은 후속의
    ffprobe 실행이 사실상 수행하므로(잘못된 영상은 duration 추출 자체가 실패)
    본 함수는 거짓양성 비율을 낮추는 빠른 1차 필터 역할만 한다.
    """
    ct = getattr(file, "content_type", "") or ""
    if ct and not ct.startswith(ALLOWED_VIDEO_MIME_PREFIX):
        raise ValidationError(f"영상 MIME 타입이 아닙니다: '{ct}'")
