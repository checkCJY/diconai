# 프론트 WebSocket 연결 도메인

> 코드리뷰용 흐름 이해 문서. 관련 커밋: `584a976`(ws-client, alarm-ws)
> 프론트의 모든 실시간 연결은 `ws-client.js` 의 **WSClient** 단일 래퍼를 거친다.

---

## 1. 한눈에 보는 구조

```
shared/ws-client.js  (WSClient)          ★ new WebSocket 은 여기 단 1곳
  connect(path, {attachToken})
  ├─ URL 자동 prefix (AppConfig.wsUrl)
  ├─ path별 캐시 (중복 연결 차단)
  ├─ 자동 재연결: 지수 백오프 1s→30s, ±30% 지터, 최대 20회
  ├─ JWT 만료(close 1008) → Auth._refresh() 후 즉시 재연결 (백오프 우회)
  └─ 60s 지속 끊김 → onFallbackStart → catch-up 폴링 degrade
       ▲ 구독 채널들:
       ├─ shared/alarm-ws.js        /ws/sensors/  → 알람만 (팝업·토스트)
       ├─ dashboard/websocket.js    /ws/sensors/  → 가스·전력 패널 + 알람
       ├─ detail/websocket_gas.js   → 가스 상세 차트
       ├─ detail/websocket_power.js → 전력 상세 차트
       └─ worker-ws.js              /ws/worker/{id}/ → 작업자 개인 알림
```

## 2. WSClient 가 해결하는 것

- **중복 연결 차단**: 같은 페이지에 dashboard + alarm-ws 둘 다 로드돼도 `/ws/sensors/` 는 캐시로 **연결 1개**만 유지, 여러 핸들러에 분배.
- **자동 재연결**: 끊기면 지수 백오프로 재시도. 지터(±30%)로 동시 재연결 폭주 분산. 20회 실패 시 포기(`onError`).
- **토큰 만료 우회**: 서버가 `close(1008, "unauthenticated")` 보내면 (= fastapi `websocket/auth.py` 규약) `Auth._refresh()` 후 즉시 재연결 — 백오프 안 탐. `attachToken` 채널 한정.
- **fallback degrade**: 60초 지속 끊김 시 `onFallbackStart` 발동 → 구독자가 catch-up 폴링으로 전환. 재연결 시 `onFallbackEnd`. 일시(수초) 끊김은 무시.

## 3. 서버 측과의 짝

| 클라 동작 | 서버 (fastapi) |
|---|---|
| `?token=` 쿼리 부착 | `websocket/auth.py` verify_jwt_from_ws_query |
| close 1008 수신 → refresh | auth 실패 시 `close(1008, "unauthenticated")` |
| /ws/sensors/ 구독 | `ws_router.py` broadcast_loop (1초 틱) + alarm_flush_loop (즉시) |
| catch-up 폴링 | drf `AlarmRecordViewSet.catch_up` (since 이후 24h, 최대 100건) |

→ 전체 broadcast 메커니즘은 백엔드 [gas.md](gas.md) §1 / [alerts.md](alerts.md) §5 와 연결.

## 4. 메시지 분배 패턴 (alarm-ws.js 예시)

```js
const ws = WSClient.connect('/ws/sensors/', { attachToken: true });
ws.onMessage((data) => {
  data.alarms.forEach((alarm) => {
    const d = AlarmMapper.fromSensorsAlarm(alarm);   // WS 메시지 → 정규화
    if (alarm.is_new_event || alarm.event_resolved_at) AlarmPopup.show(d);
    // event_resolved_at 박힌 RESOLVED 신호도 흘려보내 같은 event_id 팝업 close
  });
});
```
- `AlarmMapper` 가 WS 페이로드를 정규화 (서버 필드명 ↔ 프론트 모델).
- RESOLVED 신호(`event_resolved_at`)는 별도 알람이 아니라 "기존 팝업 닫기" 신호로 같은 경로를 탐.

## 5. 리뷰 시 주의

- **단일 워커 전제**: 현재 fastapi 단일 워커라 broadcast/개인알림이 정상. 멀티워커 전환 시 Redis pub/sub 필요 — `skill/plan/fastapi-multiworker-redis-pubsub.md` 참조.
- `cache key = path + opts` 직렬화 — token 갱신으로 URL 이 바뀌어도 같은 path 호출이 동일 인스턴스 보장 (이전 full-URL 키 시절 refresh 직후 중복 연결 race 있었음).
- 라이프사이클 콜백(onOpen/onClose/onError/onFallbackStart/onFallbackEnd)은 다중 구독 가능 — 페이지 언마운트 시 반환된 off() 호출로 정리.
- 배너 주석(`/* === */`)은 팀 JS 컨벤션으로 유지 (§6 정비 시에도 배너는 보존, sprint 마커만 제거).
