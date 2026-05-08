# notifications/services/template_renderer.py
"""
Notification 메시지 렌더링 (Phase 4-f).

[엔진]
Django Template (django.template.Template). 알람 분기 로직({% if %}/{% for %})
지원 — 사용자 결정 (Phase 4 plan §0).

[graceful fallback]
- 템플릿 빈 문자열 또는 None → fallback 반환 (Event.summary 등 호출자가 결정)
- 렌더 실패 (TemplateSyntaxError 등) → fallback + logger.warning

[context 표준 키]
알람 태스크에서 전달하는 context는 다음 키를 보장:
    source_label   : 발생원 이름 ("GS-001 가스센서" 등)
    risk_level     : "normal" | "warning" | "danger"
    summary        : Event.summary
선택 키 (이벤트별):
    gas_name, gas_type, value, unit, threshold_value, channel_name 등
"""

import logging

from django.template import Context, Template, TemplateSyntaxError

logger = logging.getLogger(__name__)


def render_alert_message(template: str, context: dict, fallback: str = "") -> str:
    """
    Django Template으로 알람 메시지 렌더.

    Args:
        template: AlertPolicy.message_template 문자열
        context: 렌더 변수 dict
        fallback: 템플릿 비어있거나 렌더 실패 시 반환할 기본값 (보통 Event.summary)

    Returns:
        렌더된 문자열 또는 fallback.
    """
    if not template:
        return fallback

    try:
        return Template(template).render(Context(context))
    except TemplateSyntaxError as exc:
        logger.warning(
            "[template_renderer] action=syntax_error template=%r error=%s",
            template[:80],
            exc,
        )
        return fallback
    except Exception as exc:
        logger.warning("[template_renderer] action=render_failed error=%s", exc)
        return fallback
