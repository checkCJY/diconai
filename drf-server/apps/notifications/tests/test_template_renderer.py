"""Phase 4-f — template_renderer 단위 테스트."""

# 이성현 수정 — Django SimpleTestCase → pytest 스타일로 전환
# SimpleTestCase는 DB 접근 없는 순수 Python 로직 테스트용.
# pytest 함수 스타일로 전환 시 @pytest.mark.django_db 불필요 — DB 미사용.

from apps.notifications.services.template_renderer import render_alert_message


def test_simple_substitution():
    rendered = render_alert_message(
        template="{{ source_label }}에서 {{ value }}{{ unit }} 초과",
        context={"source_label": "GS-001", "value": 50, "unit": "ppm"},
    )
    assert rendered == "GS-001에서 50ppm 초과"


def test_if_branch_danger():
    template = (
        "{{ source_label }}: "
        "{% if level == 'danger' %}🚨 긴급{% else %}⚠️ 주의{% endif %}"
    )
    rendered = render_alert_message(
        template=template,
        context={"source_label": "GS-001", "level": "danger"},
    )
    assert rendered == "GS-001: 🚨 긴급"


def test_if_branch_warning():
    template = "{% if level == 'danger' %}🚨{% else %}⚠️{% endif %} {{ source_label }}"
    rendered = render_alert_message(
        template=template,
        context={"source_label": "GS-001", "level": "warning"},
    )
    assert rendered == "⚠️ GS-001"


def test_empty_template_returns_fallback():
    rendered = render_alert_message(
        template="", context={"source_label": "GS-001"}, fallback="기본 메시지"
    )
    assert rendered == "기본 메시지"


def test_syntax_error_returns_fallback():
    # 잘못된 문법 — fallback
    rendered = render_alert_message(
        template="{% if %}",  # 표현식 누락
        context={},
        fallback="안전 메시지",
    )
    assert rendered == "안전 메시지"
