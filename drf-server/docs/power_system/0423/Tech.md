# 기술 명세서 — 전력 차트 임계치 시각화 [PWR-THRESHOLD-001]

> 작성일: 2026-04-23
> 브랜치: `feature/section-11.v3`

---

## 1. 신규·수정 파일

```text
drf-server/static/js/refactors/
└── charts_CJY.js          # [Chart] 임계치 상수 · Y축 설정 수정
```

---

## 2. 엔드포인트 / 라우트

임계치 시각화는 순수 프론트엔드 로직이므로 신규 HTTP 엔드포인트 없음.
관련 WebSocket 경로는 기존 경로 그대로 사용.

| 구분 | 경로 |
|---|---|
| Frontend Route | 메인 대시보드 (기존 경로 유지) |
| DRF WebSocket | `ws://.../ws/dashboard/` (기존 유지) |
| FastAPI WebSocket | 기존 유지 — Phase B 시 페이로드 키 추가 필요 |

---

## 3. 데이터 흐름도

```
[FastAPI WebSocket 서버]
  │  _build_broadcast_payload()
  │  └─ total_kw, equipment[]
  │     (Phase B: + threshold_warning_kw, threshold_danger_kw)
  │
  ▼ WebSocket 메시지
[charts_CJY.js — ws.onmessage]
  │
  ├─ Phase A: 상수 POWER_THRESHOLD_WARNING(2200) / POWER_THRESHOLD_DANGER(2860) 사용
  │
  ├─ Phase B (조건 분기):
  │   if (data.threshold_warning_kw !== undefined)
  │     └─▶ updatePowerThresholds(warnKw, dangerKw)
  │           └─▶ powerChart.options.plugins.annotation.annotations 교체
  │               └─▶ powerChart.update('none')
  │
  └─▶ pushData(powerChart, label, totalKw)
        └─▶ Chart.js 실시간 라인 갱신
```

---

## 4. 임계치 Annotation 구조

`_powerAnnotations(warnKw, dangerKw)` 반환 객체:

```
Chart Y축
─────────────────────────────────────────────────
 ▲
 │  [dangerBand]  적색 반투명 박스 (yMin=2860, yMax=∞)
 │                ← "위험" 레이블 점선 ─ ─ ─ ─ ─ ─ ─ ─  (dangerLine, 2860 kW)
 │  [warnBand]    황색 반투명 박스 (yMin=2200, yMax=2860)
 │                ← "주의" 레이블 점선 ─ ─ ─ ─ ─ ─ ─ ─  (warnLine, 2200 kW)
 │
 │  [안전 영역]   표시 없음 (0 ~ 2200 kW)
 └──────────────────────────────────────────── ▶ 시간
```

---

## 5. Y축 설정 요약

| 옵션 | 값 | 설명 |
|---|---|---|
| `stepSize` | `1000` | 1,000 kW 단위 눈금 |
| `callback` | `value.toLocaleString()` | 천 단위 쉼표 |
| 줌 버튼 step | `1000` | ±1,000 kW 단위 수동 조절 |
| `animation` | `false` | 실시간 갱신 성능 확보 |

---

## 6. Phase A → Phase B 전환 체크리스트

- [ ] `fastapi-server/websocket_CJY.py` → `_build_broadcast_payload()` 에 `threshold_warning_kw`, `threshold_danger_kw` 추가
- [ ] `ws.onmessage` 내 `updatePowerThresholds()` 분기 활성화
- [ ] 헤더 주석 Phase A → Phase B 로 변경
- [ ] 상수 `POWER_THRESHOLD_WARNING` / `POWER_THRESHOLD_DANGER` 제거 또는 기본값 fallback으로 전환
