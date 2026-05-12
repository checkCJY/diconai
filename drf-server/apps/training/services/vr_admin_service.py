"""
apps/training/services/vr_admin_service.py — VR 교육 콘텐츠 어드민 비즈니스 로직.

[책임]
- 공장(facility)별 단일 활성 콘텐츠 조회/교체/메타 수정
- 교체 시 VRTrainingRevision 이력 INSERT + 이전 파일 디스크 제거
- target_type 화면 비노출 정책 → INSERT 시 'general' 기본값 자동 세팅

[트랜잭션 + 파일 시스템 원자성 — Plan §11]
1. DB 트랜잭션 안에서는 파일 시스템을 건드리지 않는다.
2. 새 파일 저장은 호출부(View)에서 트랜잭션 진입 전에 완료해 둔다.
3. 이전 파일 삭제는 `transaction.on_commit`으로 예약 → 커밋 성공 후에만 실행.
4. 본 서비스 호출 도중 예외가 발생하면 호출부가 새로 저장한 파일을 청소한다.
"""

import logging
import os
from urllib.parse import urlparse

from django.conf import settings
from django.db import transaction

from apps.training.models import VRTrainingContent, VRTrainingRevision

logger = logging.getLogger(__name__)


def get_vr_content_for_facility(facility_id: int) -> VRTrainingContent | None:
    """facility의 현재 활성 VR 콘텐츠 1건을 반환.

    [부분 UniqueConstraint와 정합]
    `is_active=True` 조건의 부분 유니크 제약으로 facility당 최대 1건 보장 →
    `.first()`로 충분. 콘텐츠가 한 번도 등록되지 않은 facility는 None.

    [select_related]
    응답 직렬화에서 facility_name과 updated_by_name을 즉시 사용하므로
    N+1 회피용으로 join을 함께 수행.
    """
    return (
        VRTrainingContent.objects.filter(target_facility_id=facility_id, is_active=True)
        .select_related("target_facility", "updated_by")
        .first()
    )


@transaction.atomic
def replace_vr_content(
    *,
    content: VRTrainingContent | None,
    facility_id: int,
    new_content_url: str,
    duration_seconds: int | None,
    name: str | None,
    description: str | None,
    operation_note: str | None,
    user,
) -> VRTrainingContent:
    """영상 교체 또는 최초 등록 — 단일 진입점.

    [분기]
    - `content is None` (최초 등록): `target_type='general'`로 새 행 INSERT.
      target_type은 화면에 노출하지 않는 운영 컨벤션이라 service가 기본값 강제.
    - `content is not None` (교체): 같은 행 UPDATE + `VRTrainingRevision`에
      이전 메타 스냅샷 INSERT + `transaction.on_commit`으로 이전 파일 삭제 예약.

    [같은 행 UPDATE를 택한 이유]
    부분 UniqueConstraint(`uq_vr_active_target`)가 `is_active=True` 조건을
    걸고 있어 새 행 INSERT + 기존 행 비활성화 방식은 일시적으로 두 활성 행이
    공존하는 윈도우가 생기지 않도록 트랜잭션 순서를 신경 써야 한다. 단일
    UPDATE는 제약과 직접 충돌하지 않고 코드도 단순하다.

    [트랜잭션 + 파일 시스템 원자성]
    파일 삭제는 트랜잭션 내부에서 수행하지 않는다 — 롤백 시 파일을 복구할
    수단이 없어 원자성이 깨지기 때문. `transaction.on_commit` 콜백은 커밋이
    실제로 끝난 뒤에만 실행되어 안전.

    Returns:
        갱신된 (또는 신규 생성된) VRTrainingContent 인스턴스.
    """
    if content is None:
        return VRTrainingContent.objects.create(
            target_type=VRTrainingContent.TargetType.GENERAL,
            target_facility_id=facility_id,
            name=name or "VR 교육 콘텐츠",
            content_url=new_content_url,
            description=description or "",
            operation_note=operation_note or "",
            duration_seconds=duration_seconds,
            is_active=True,
            updated_by=user,
        )

    previous_url = content.content_url
    previous_name = content.name

    VRTrainingRevision.objects.create(
        content=content,
        previous_url=previous_url,
        previous_name=previous_name,
        replaced_by=user,
        updated_by=user,
    )

    content.content_url = new_content_url
    content.duration_seconds = duration_seconds
    if name is not None:
        content.name = name
    if description is not None:
        content.description = description
    if operation_note is not None:
        content.operation_note = operation_note
    content.updated_by = user
    content.save(
        update_fields=[
            "content_url",
            "duration_seconds",
            "name",
            "description",
            "operation_note",
            "updated_by",
            "updated_at",
        ]
    )

    transaction.on_commit(lambda: _safe_unlink_media(previous_url))
    return content


@transaction.atomic
def update_vr_metadata(
    *,
    content: VRTrainingContent,
    name: str | None,
    description: str | None,
    operation_note: str | None,
    user,
) -> VRTrainingContent:
    """파일을 동반하지 않는 메타 수정 — 이름/설명/운영 메모.

    [원자성]
    각 인자가 None이면 해당 필드를 건드리지 않는다. PATCH 시맨틱(누락 키는
    유지). 변경된 필드가 하나도 없으면 save 없이 즉시 반환 → 불필요한
    `updated_at` 갱신 회피.

    [updated_by]
    1개 이상 필드가 변경된 경우에만 갱신 — 노옵 save 시 감사 이력이 더러워지는
    것을 막는다.
    """
    fields: list[str] = []
    if name is not None:
        content.name = name
        fields.append("name")
    if description is not None:
        content.description = description
        fields.append("description")
    if operation_note is not None:
        content.operation_note = operation_note
        fields.append("operation_note")
    if not fields:
        return content
    content.updated_by = user
    fields.extend(["updated_by", "updated_at"])
    content.save(update_fields=fields)
    return content


def _safe_unlink_media(url: str) -> None:
    """이전 콘텐츠의 절대 URL을 로컬 경로로 환원해 파일을 제거.

    [path traversal 가드]
    URL에서 추출한 경로가 `MEDIA_ROOT` 외부를 가리키지 않는지 정규화 후
    검증한다. `..` 같은 시도가 들어와도 `os.path.normpath` + prefix 비교로
    탈출이 차단된다.

    [외부 URL은 skip]
    호스트만 다른 외부 저장소를 가리키는 URL이거나 `MEDIA_URL` prefix가
    아닌 경로는 디스크 파일이 아니므로 조용히 무시. (향후 S3 등 전환 시
    삭제 로직이 별도 구성될 자리.)

    [실패 허용]
    파일이 이미 없거나 권한 오류여도 로그만 남기고 예외를 삼킨다. 디스크에
    고아 파일이 남는 것은 DB 정합성보다 사소한 비용으로 간주.
    """
    if not url:
        return
    try:
        parsed = urlparse(url)
    except ValueError:
        logger.warning("이전 URL 파싱 실패: %r", url)
        return
    path = parsed.path or ""
    media_url = settings.MEDIA_URL or "/media/"
    if not path.startswith(media_url):
        return
    rel_path = path[len(media_url) :]
    abs_path = os.path.normpath(os.path.join(settings.MEDIA_ROOT, rel_path))
    media_root = os.path.normpath(str(settings.MEDIA_ROOT))
    if not abs_path.startswith(media_root + os.sep) and abs_path != media_root:
        logger.warning("MEDIA_ROOT 밖 경로 — 삭제 거부: %s", abs_path)
        return
    try:
        os.unlink(abs_path)
    except FileNotFoundError:
        logger.info("이전 영상 파일 없음 (이미 제거됨): %s", abs_path)
    except OSError as exc:
        logger.warning("이전 영상 파일 삭제 실패 %s: %s", abs_path, exc)
