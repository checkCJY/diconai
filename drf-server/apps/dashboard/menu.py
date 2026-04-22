import copy

# ──────────────────────────────────────────────────────────
# 권한별 메뉴 트리 정의
# ──────────────────────────────────────────────────────────
_MENU_WORKER = [
    {
        "id": "safety",
        "label": "나의 안전확인",
        "icon": "shield",
        "children": [
            {
                "id": "SNB-02",
                "label": "작업 전 안전 확인",
                "path": "/dashboard/safety/checklist/",
            },
            {
                "id": "SNB-04",
                "label": "안전 확인 이력",
                "path": "/dashboard/safety/history/",
            },
        ],
    },
    {
        "id": "monitoring",
        "label": "모니터링",
        "icon": "monitor",
        "children": [
            {
                "id": "SNB-06",
                "label": "실시간 모니터링",
                "path": "/dashboard/monitoring/realtime/",
            },
            {
                "id": "SNB-07",
                "label": "실시간/AI 예측 유해가스 현황",
                "path": "/dashboard/monitoring/gas/",
            },
            {
                "id": "SNB-08",
                "label": "실시간/AI 예측 스마트 전력 현황",
                "path": "/dashboard/monitoring/power/",
            },
            {
                "id": "SNB-09",
                "label": "작업자 현황",
                "path": "/dashboard/monitoring/workers/",
            },
            {
                "id": "SNB-10",
                "label": "이벤트 현황",
                "path": "/dashboard/monitoring/events/",
            },
        ],
    },
]

_MENU_ADMIN_EXTRA = {
    "id": "admin_only",
    "label": "관리자 전용",
    "icon": "settings",
    "children": [
        {"id": "SNB-05", "label": "전체 이력 현황", "path": "/admin-panel/history"},
    ],
}


def get_menu_tree(role: str) -> list:
    menus = copy.deepcopy(_MENU_WORKER)
    if role in ("admin", "superadmin"):
        menus.append(copy.deepcopy(_MENU_ADMIN_EXTRA))
    return menus
