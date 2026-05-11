from django.core.exceptions import ValidationError

ALLOWED_EXTENSIONS = {
    "jpg",
    "jpeg",
    "png",
    "gif",
    "pdf",
    "docx",
    "xlsx",
    "pptx",
}
MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10MB


def validate_max_10mb(file):
    if file.size > MAX_SIZE_BYTES:
        raise ValidationError("첨부파일은 10MB를 초과할 수 없습니다.")


def validate_allowed_extension(file):
    name = file.name or ""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(
            f"허용되지 않은 확장자: '{ext}'. 허용: {sorted(ALLOWED_EXTENSIONS)}"
        )
