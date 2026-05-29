from django.db import models

from apps.core.models.base import BaseModel


class CodeGroup(BaseModel):
    """
    공통 코드 그룹 마스터 — 운영자가 어드민에서 편집

    [예시]
    - GAS_TYPE: 가스 종류 (CO/H2S/CO2/...)
    - DEVICE_TYPE: 장비 유형
    - NOTI_CHANNEL: 알림 채널

    [코드 이넘과의 관계]
    파이썬 이넘(GasTypeChoices 등)이 1차 진실 공급원.
    CodeGroup/CommonCode는 운영자 UI 편집용 메타(라벨/설명/정렬).
    동기화는 CI 정합성 테스트로 강제 (Phase 1: GAS_TYPE만).
    """

    code = models.CharField(max_length=50, unique=True, verbose_name="그룹 코드")
    name = models.CharField(max_length=100, verbose_name="그룹 명")
    # Figma "관리범위" 입력칸 — 이 코드그룹이 어느 도메인에 쓰이는지 자유 텍스트
    # (예: "가스 종류", "장비 유형"). blank=True 이므로 기존 데이터에 영향 없음.
    scope = models.CharField(max_length=200, blank=True, default="", verbose_name="관리 범위")
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.code} ({self.name})"

    class Meta:
        db_table = "ref_code_group"
        ordering = ["code"]
