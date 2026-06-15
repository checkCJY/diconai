# docs/features — 기능정의서 인덱스

기능 ID(CM·MN·VR·admin)별 요구사항·UI·흐름을 정리한 기능정의서 모음입니다. 작성자 접두어(`cjy_`/`hjh_`)와 기능 ID로 구분합니다. 도메인 아키텍처 SoT는 [../domains/](../domains/)를 참고하세요.

## 기능 ID ↔ 문서

| 기능 ID | 주제 | 문서 |
|---|---|---|
| **MN-03 / CM-07 (가스)** | 가스 센서 수신·저장 | [cm07_mn03_가스센서_수신저장.md](cm07_mn03_가스센서_수신저장.md) |
| | 가스 알람·이벤트 | [cm07_mn03_가스알람_이벤트.md](cm07_mn03_가스알람_이벤트.md) |
| | 가스 HTTP 수신 파이프라인 | [gas_sensor_http_pipeline.md](gas_sensor_http_pipeline.md) |
| | 이벤트현황·유해가스현황 (hjh) | [hjh_CM-07_MN-03_이벤트현황_유해가스현황_기능정의서.md](hjh_CM-07_MN-03_이벤트현황_유해가스현황_기능정의서.md) |
| **CM-07 (알람)** | 알람 팝업 개선 (cjy) | [cjy_CM-07_알람팝업개선_기능정의서.md](cjy_CM-07_알람팝업개선_기능정의서.md) |
| | 알람 코어 서비스 (hjh) | [hjh_alarm-core-service_기능정의서.md](hjh_alarm-core-service_기능정의서.md) |
| **MN-04 (작업자/지오펜스)** | 지오펜스 진입 알람 | [cjy_MN-04_geofence_alarm.md](cjy_MN-04_geofence_alarm.md) |
| | 작업자 실시간 위치 | [cjy_MN-04_worker_realtime_기능정의서.md](cjy_MN-04_worker_realtime_기능정의서.md) |
| **VR 교육** | 안전 이력 연동 | [cjy_VR교육관리_안전이력연동_기능정의서.md](cjy_VR교육관리_안전이력연동_기능정의서.md) |
| | 트러블슈팅 | [cjy_VR교육관리_트러블슈팅.md](cjy_VR교육관리_트러블슈팅.md) |
| **Admin** | 공지사항·로그 관리 API (hjh) | [hjh_admin-api_공지사항_로그관리_기능정의서.md](hjh_admin-api_공지사항_로그관리_기능정의서.md) |
| **대시보드** | WebSocket 실시간 패널 | [websocket_realtime_panel.md](websocket_realtime_panel.md) |

## power_system/ — 전력 도메인 전용

| 문서 | 내용 |
|---|---|
| [power_system/cjy_요구사항_정의서.md](power_system/cjy_요구사항_정의서.md) | 전력 시스템 요구사항 |
| [power_system/cjy_API_명세서.md](power_system/cjy_API_명세서.md) | 전력 API 명세 |
| [power_system/cjy_그_외_기술문서.md](power_system/cjy_그_외_기술문서.md) | 전력 기술 문서 (AI·임계치 등) |
