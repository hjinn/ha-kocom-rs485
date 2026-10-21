# ADR-0006: 상태 동기화는 버스 감청 우선 + 보조 Polling

- 상태: ADR-0012로 대체됨 (2026-10-21)

## 결정
- `iot_class: local_push`. 버스에 지나가는 Wallpad↔Thermo 응답 패킷을 감청해 즉시 상태 반영.
- 보조 Polling: 기본 300초, 옵션 플로우에서 60~3600초 조정. Room 간 1초 간격.
- 명령 송신 직후 해당 Room만 즉시 query하여 결과 확인(참조 구현 `send_wait_response`와 동일).
- 참조 구현의 "Query" 버튼은 만들지 않는다. `homeassistant.update_entity`로 대체.

## 근거
Polling은 RS485 버스 점유를 늘려 Wallpad 자체 통신과의 충돌 확률을 높인다. 감청만으로 대부분의 변경이 반영되므로 Polling은 놓친 변경을 보정하는 용도로 충분하다.
