"""Phase 4-f — template_renderer 단위 테스트."""

from django.test import SimpleTestCase

from apps.notifications.services.template_renderer import render_alert_message


class TemplateRendererTest(SimpleTestCase):
    def test_simple_substitution(self):
        rendered = render_alert_message(
            template="{{ source_label }}에서 {{ value }}{{ unit }} 초과",
            context={"source_label": "GS-001", "value": 50, "unit": "ppm"},
        )
        self.assertEqual(rendered, "GS-001에서 50ppm 초과")

    def test_if_branch_danger(self):
        template = (
            "{{ source_label }}: "
            "{% if level == 'danger' %}🚨 긴급{% else %}⚠️ 주의{% endif %}"
        )
        rendered = render_alert_message(
            template=template,
            context={"source_label": "GS-001", "level": "danger"},
        )
        self.assertEqual(rendered, "GS-001: 🚨 긴급")

    def test_if_branch_warning(self):
        template = (
            "{% if level == 'danger' %}🚨{% else %}⚠️{% endif %} {{ source_label }}"
        )
        rendered = render_alert_message(
            template=template,
            context={"source_label": "GS-001", "level": "warning"},
        )
        self.assertEqual(rendered, "⚠️ GS-001")

    def test_empty_template_returns_fallback(self):
        rendered = render_alert_message(
            template="", context={"source_label": "GS-001"}, fallback="기본 메시지"
        )
        self.assertEqual(rendered, "기본 메시지")

    def test_syntax_error_returns_fallback(self):
        # 잘못된 문법 — fallback
        rendered = render_alert_message(
            template="{% if %}",  # 표현식 누락
            context={},
            fallback="안전 메시지",
        )
        self.assertEqual(rendered, "안전 메시지")
