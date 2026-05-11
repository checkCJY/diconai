# alerts/services/policy_matcher.py
"""
AlertPolicy 매칭 서비스 (Phase 4-e).

[목적]
Event 생성 시 (event_type, facility, sensor/device/geofence) 정보로 일치하는
AlertPolicy를 찾아 Event.policy / Notification.policy FK를 채운다.

[매칭 우선순위]
1. target_facility 일치 + sensor/device/geofence 일치 (가장 구체적)
2. target_facility 일치 + sensor/device/geofence 빈 배열 (공장 전체)
3. target_facility=NULL + sensor/device/geofence 일치 (전사 + 특정 자산)
4. target_facility=NULL + sensor/device/geofence 빈 배열 (전사)
가장 구체적인 일치 1건만 반환. 없으면 None.

[condition_summary]
목록 화면 캐시 컬럼. AlertPolicy 생성/수정 시 service 레이어에서 호출.
"""

from apps.alerts.models import AlertPolicy
from apps.core.constants import AlarmType


def match_policy(
    event_type: str,
    facility_id: int | None,
    sensor_id: int | None = None,
    device_id: int | None = None,
    geofence_id: int | None = None,
) -> AlertPolicy | None:
    """
    Event 트리거 정보로 일치하는 AlertPolicy 1건 반환.

    가장 구체적 매칭(facility + 자산) 우선. 없으면 전사 정책 fallback.
    """
    qs = AlertPolicy.objects.filter(event_type=event_type, is_active=True)

    candidates = list(qs)
    if not candidates:
        return None

    # (구체성, AlertPolicy) 튜플로 정렬 — 점수 높을수록 구체적
    scored: list[tuple[int, AlertPolicy]] = []
    for policy in candidates:
        score = _score_match(
            policy=policy,
            facility_id=facility_id,
            sensor_id=sensor_id,
            device_id=device_id,
            geofence_id=geofence_id,
        )
        if score is not None:
            scored.append((score, policy))

    if not scored:
        return None

    # 점수 내림차순 → 가장 구체적인 정책 반환
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


def _score_match(
    policy: AlertPolicy,
    facility_id: int | None,
    sensor_id: int | None,
    device_id: int | None,
    geofence_id: int | None,
) -> int | None:
    """
    매칭 점수. 일치 시 점수 반환, 불일치 시 None (제외).

    점수표:
        + facility 일치(전사 정책 NULL은 0점, 특정 facility 일치는 2점)
        + 자산 ID 일치 (sensor/device/geofence 중 1개라도) 1점
        타깃 자산 빈 배열은 자산 무관 매칭(0점) — facility 점수만 반영
    """
    # facility 매칭
    if policy.target_facility_id is None:
        facility_score = 0  # 전사 정책 — 모든 facility에 적용
    elif policy.target_facility_id == facility_id:
        facility_score = 2  # 특정 facility 일치
    else:
        return None  # 불일치 — 제외

    # 자산 매칭
    asset_score = 0
    target_sensors = policy.target_sensor_ids or []
    target_devices = policy.target_device_ids or []
    target_geofences = policy.target_geofence_ids or []

    has_asset_constraint = bool(target_sensors or target_devices or target_geofences)
    if has_asset_constraint:
        sensor_match = sensor_id is not None and sensor_id in target_sensors
        device_match = device_id is not None and device_id in target_devices
        geofence_match = geofence_id is not None and geofence_id in target_geofences
        if not (sensor_match or device_match or geofence_match):
            return None  # 자산 제약 있는데 매칭 안 됨 — 제외
        asset_score = 1

    return facility_score + asset_score


def compute_condition_summary(policy: AlertPolicy) -> str:
    """
    AlertPolicy의 조건을 한 줄 문자열로 요약 — 목록 화면 캐시용.

    형식: "<event_type 라벨> | <facility 라벨> | <자산 요약> | <채널>"
    """
    event_label = dict(AlarmType.choices).get(policy.event_type, policy.event_type)
    facility_label = (
        policy.target_facility.name if policy.target_facility_id else "전사"
    )

    asset_parts = []
    if policy.target_sensor_ids:
        asset_parts.append(f"센서 {len(policy.target_sensor_ids)}개")
    if policy.target_device_ids:
        asset_parts.append(f"전력장치 {len(policy.target_device_ids)}개")
    if policy.target_geofence_ids:
        asset_parts.append(f"위험구역 {len(policy.target_geofence_ids)}개")
    asset_label = ", ".join(asset_parts) if asset_parts else "자산 무관"

    channel_label = ", ".join(policy.channels) if policy.channels else "채널 미지정"

    return f"{event_label} | {facility_label} | {asset_label} | {channel_label}"


def save_policy(policy: AlertPolicy) -> AlertPolicy:
    """
    AlertPolicy 저장 + condition_summary 자동 갱신 (service 진입점).

    view에서 model.save() 직접 호출 대신 본 함수 사용 권장 — condition_summary 동기화 보장.
    """
    policy.condition_summary = compute_condition_summary(policy)
    policy.save()
    return policy
