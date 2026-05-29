"""AlertPolicy 변경 시 signals.py 의 receiver 가 policy_matcher 캐시를 자동 invalidate.

receiver 자체의 동작만 직접 검증 — `policy_matcher.invalidate_policy_cache`
의 키 포맷 (`alert_policies:{event_type}`) 에 sentinel 값을 prime 후,
AlertPolicy 변경 후 `cache.get` 이 None 인지 확인. policy_matcher 의 DB 조회
경로는 본 테스트 범위 밖 (별도 단위테스트 거리).
"""

from django.core.cache import cache
from django.test import TestCase

from apps.alerts.models import AlertPolicy
from apps.alerts.services.policy_matcher import _POLICY_CACHE_KEY
from apps.core.constants import AlarmType


class AlertPolicySignalsTest(TestCase):
    """signals.py 의 post_save / post_delete receiver 검증."""

    def setUp(self):
        self.event_type = AlarmType.GAS_THRESHOLD
        self.cache_key = _POLICY_CACHE_KEY.format(event_type=self.event_type)

    def _prime_cache(self):
        """캐시에 sentinel 값을 미리 넣어, signal 발화 시 비워졌는지 확인 가능하게."""
        cache.set(self.cache_key, ["sentinel"], 300)
        self.assertEqual(cache.get(self.cache_key), ["sentinel"])

    def test_post_save_on_create_invalidates_cache(self):
        """AlertPolicy.objects.create() — POST/admin/shell 등 모든 생성 경로 커버."""
        self._prime_cache()
        AlertPolicy.objects.create(name="test-create", event_type=self.event_type)
        self.assertIsNone(cache.get(self.cache_key))

    def test_post_save_on_update_invalidates_cache(self):
        """기존 정책 instance.save() — PATCH/admin save_model/save_policy 모든 갱신 경로 커버."""
        policy = AlertPolicy.objects.create(
            name="test-update", event_type=self.event_type
        )
        self._prime_cache()
        policy.recommended_actions = {"danger": ["환기 후 관리자 보고"]}
        policy.save()
        self.assertIsNone(cache.get(self.cache_key))

    def test_post_delete_invalidates_cache(self):
        """AlertPolicy.delete() — DRF DELETE/admin delete_model 모든 삭제 경로 커버."""
        policy = AlertPolicy.objects.create(
            name="test-delete", event_type=self.event_type
        )
        self._prime_cache()
        policy.delete()
        self.assertIsNone(cache.get(self.cache_key))
