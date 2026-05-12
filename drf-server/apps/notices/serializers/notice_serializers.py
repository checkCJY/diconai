"""
notices/serializers/notice_serializers.py

공지사항 API 직렬화 담당 파일.

흐름에서 이 파일의 위치:
  ORM 객체 → [이 파일] → JSON 응답
  JSON 요청 → [이 파일] → validated_data → ORM 저장

직렬화란: ORM 객체(Python)를 JSON으로, 또는 JSON을 validated_data로 변환하는 과정.
"""

from django.utils import timezone
from rest_framework import serializers

from apps.facilities.models import Facility
from apps.notices.models import Notice, NoticeAttachment


# ────────────────────────────────────────────
# 1. 첨부파일 직렬화
# ────────────────────────────────────────────

class NoticeAttachmentSerializer(serializers.ModelSerializer):
    """
    흐름 위치: NoticeDetailSerializer 안에 중첩되어 사용됨.
    역할: 첨부파일 1건을 JSON으로 변환.

    file_url을 SerializerMethodField로 만드는 이유:
      - FileField는 "/media/notices/1/test.pdf" 같은 상대경로만 반환함.
      - 프론트가 바로 <a href>에 쓰려면 "http://localhost:8000/media/..." 전체 URL이 필요함.
      - request.build_absolute_uri()로 절대 URL을 만들어 반환함.
      - request는 뷰에서 context={"request": request}로 전달받음.
    """

    file_url = serializers.SerializerMethodField()

    class Meta:
        model = NoticeAttachment
        fields = ["id", "filename", "size", "file_url", "created_at"]

    def get_file_url(self, obj):
        # context에 request가 없으면(테스트 환경 등) None 반환
        request = self.context.get("request")
        if request and obj.file:
            return request.build_absolute_uri(obj.file.url)
        return None


# ────────────────────────────────────────────
# 2. 목록 응답 직렬화
# ────────────────────────────────────────────

class NoticeListSerializer(serializers.ModelSerializer):
    """
    흐름 위치: NoticeListView.get() → AdminPagination → [이 시리얼라이저] → JSON 응답.
    역할: 공지사항 목록 1건을 가볍게 직렬화.

    content(본문)와 attachments(첨부파일 배열)를 제외하는 이유:
      - 목록은 수십~수백 건이 한 번에 내려감.
      - 본문은 길 수 있고, 첨부파일은 중첩 배열이라 건수만큼 쿼리가 늘어남.
      - 목록 화면에서는 제목, 카테고리, 작성자 정도만 필요하므로 제외가 맞음.

    author_name을 SerializerMethodField로 만드는 이유:
      - author는 FK(외래키)라 그대로 내리면 숫자 id만 반환됨.
      - 프론트에서 "홍길동 관리자"를 보여주려면 추가 API 호출이 필요해짐.
      - 미리 이름을 문자열로 합쳐서 내리면 프론트가 바로 표시 가능.

    category_display를 추가하는 이유:
      - category는 DB에 "general" 같은 코드값으로 저장됨.
      - 화면에서는 "일반 공지"(한글)를 보여줘야 하므로 display값도 함께 내림.
      - get_category_display()는 Django TextChoices가 자동으로 만들어주는 메서드.
    """

    author_name = serializers.SerializerMethodField()
    category_display = serializers.CharField(
        source="get_category_display", read_only=True
    )
    attachment_count = serializers.SerializerMethodField()

    class Meta:
        model = Notice
        fields = [
            "id",
            "title",
            "category",
            "category_display",   # "general" → "일반 공지"
            "is_pinned",
            "author_name",
            "attachment_count",   # 첨부파일 개수 (배열 대신 숫자만)
            "is_active",
            "published_at",
            "created_at",
            "updated_at",
        ]

    def get_author_name(self, obj):
        # author는 탈퇴 시 SET_NULL → None 가능하므로 체크 필수
        if obj.author:
            return obj.author.get_full_name() or obj.author.username
        return None

    def get_attachment_count(self, obj):
        # 뷰에서 prefetch_related("attachments")를 걸어두므로
        # .count()를 쓰면 추가 쿼리가 발생하지 않음
        return obj.attachments.count()


# ────────────────────────────────────────────
# 3. 상세 응답 직렬화
# ────────────────────────────────────────────

class NoticeDetailSerializer(serializers.ModelSerializer):
    """
    흐름 위치: NoticeDetailView.get() → [이 시리얼라이저] → JSON 응답.
               NoticeListView.post() 등록 성공 후 → [이 시리얼라이저] → 201 응답.
    역할: 공지사항 1건을 첨부파일 포함 전체 직렬화.

    목록 시리얼라이저와 다른 점:
      - content(본문) 포함
      - attachments(첨부파일 배열) 포함 — NoticeAttachmentSerializer 중첩
      - target_facility 포함

    attachments에 read_only=True를 붙이는 이유:
      - 첨부파일 업로드는 별도 엔드포인트(/notices/{id}/attachments/)에서 처리.
      - 이 시리얼라이저는 응답(읽기)에만 첨부파일을 보여주고,
        입력(쓰기)에서는 첨부파일을 받지 않음.
    """

    author_name = serializers.SerializerMethodField()
    category_display = serializers.CharField(
        source="get_category_display", read_only=True
    )
    # many=True: 첨부파일이 여러 개이므로 배열로 직렬화
    # context 전달: file_url 절대경로 생성에 request가 필요함
    attachments = NoticeAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = Notice
        fields = [
            "id",
            "title",
            "content",
            "category",
            "category_display",
            "is_pinned",
            "author_name",
            "attachments",
            "target_facility",
            "is_active",
            "published_at",
            "created_at",
            "updated_at",
        ]

    def get_author_name(self, obj):
        if obj.author:
            return obj.author.get_full_name() or obj.author.username
        return None


# ────────────────────────────────────────────
# 4. 등록 / 수정 입력 직렬화
# ────────────────────────────────────────────

class NoticeCreateUpdateSerializer(serializers.ModelSerializer):
    """
    흐름 위치: 요청 JSON → [이 시리얼라이저.is_valid()] → validated_data → DB 저장.
    역할: 등록(POST) / 수정(PATCH) 요청 데이터 유효성 검사.

    응답 직렬화(읽기)와 입력 직렬화(쓰기)를 분리하는 이유:
      - 응답에는 author_name(계산된 값)이 필요하지만 입력에는 불필요.
      - 입력에는 title, content 같은 쓰기 가능 필드만 선언해야 명확함.
      - 하나의 시리얼라이저에 read_only/write_only를 섞으면 코드가 복잡해짐.

    author를 입력 필드로 두지 않는 이유:
      - 클라이언트가 author를 임의 지정하면 다른 사람 이름으로 공지 등록 가능 → 보안 문제.
      - author는 뷰의 perform_create()에서 request.user로 강제 주입함.

    published_at 기본값 처리:
      - 클라이언트가 보내지 않으면 None → validate_published_at()에서 현재 시각으로 변환.
      - 미래 시각을 보내면 예약 발행이 가능한 구조.

    target_facility allow_null=True인 이유:
      - NULL = 전사 공지, 값 있음 = 특정 공장 공지.
      - 전사 공지를 만들 때는 이 필드를 비우면 되므로 null 허용.
    """

    target_facility = serializers.PrimaryKeyRelatedField(
        queryset=Facility.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Notice
        fields = [
            "title",
            "content",
            "category",
            "is_pinned",
            "target_facility",
            "is_active",
            "published_at",
        ]

    def validate_published_at(self, value):
        """
        흐름: is_valid() 호출 시 각 필드의 validate_<field>()가 자동 실행됨.
        역할: published_at이 None이면 현재 시각으로 채워 반환.

        None을 그냥 저장하면 DB에 NULL이 들어가 정렬/필터에 문제가 생김.
        뷰보다 시리얼라이저에서 처리하는 이유: validated_data에 이미 값이 있어야
        뷰 코드가 단순해지고, 이 규칙이 어디서 적용되는지 한 곳에서 관리됨.
        """
        if value is None:
            return timezone.now()
        return value
