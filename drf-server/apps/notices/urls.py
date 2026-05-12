"""
notices/urls.py

공지사항 API URL 라우팅.

config/urls.py에서 "api/admin/" 프리픽스로 include됨.
실제 접근 경로:
  GET/POST   /api/admin/notices/
  GET/PATCH/DELETE /api/admin/notices/{id}/
  POST       /api/admin/notices/{id}/attachments/
  DELETE     /api/admin/notices/{id}/attachments/{att_id}/
"""

from django.urls import path

from apps.notices.views import NoticeAttachmentView, NoticeDetailView, NoticeListView

urlpatterns = [
    # 목록 조회 + 등록
    path("notices/", NoticeListView.as_view(), name="notice-list"),

    # 상세 조회 + 수정 + 삭제
    # <int:pk>: pk는 정수여야 함. 문자열이 들어오면 404가 아닌 URL 미매칭으로 처리됨.
    path("notices/<int:pk>/", NoticeDetailView.as_view(), name="notice-detail"),

    # 첨부파일 업로드
    path(
        "notices/<int:pk>/attachments/",
        NoticeAttachmentView.as_view(),
        name="notice-attachment-upload",
    ),

    # 첨부파일 삭제
    # att_id를 별도 파라미터로 받아 "이 공지사항의 이 첨부파일"을 특정
    path(
        "notices/<int:pk>/attachments/<int:att_id>/",
        NoticeAttachmentView.as_view(),
        name="notice-attachment-delete",
    ),
]
