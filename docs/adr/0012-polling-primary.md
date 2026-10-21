# ADR-0012: 상태 동기화는 Polling 우선, 감청은 보조

- 상태: ADR-0015로 대체됨 (2026-10-21)
- 대체: ADR-0006

## 맥락
ADR-0006은 실제 월패드가 버스의 Master로 Thermo와 통신한다는 가정 위에 있었다.
실제 버스에는 EW11과 Boiler Controller만 있고 월패드는 연결되어 있지 않다. 먼저 말을 거는 장비가 없으므로 감청으로 얻을 상태 변경이 거의 없다.
Integration이 유일한 Master이므로 Polling이 다른 Master와 충돌할 위험도 없다.

## 결정
- `iot_class: local_polling`.
- Polling 기본 60초, 옵션 플로우에서 15~3600초. Room 간 1초 간격.
- 명령 송신 직후 해당 Room만 즉시 query (ADR-0006에서 유지).
- 감청 경로는 남겨 둔다: 수신된 Thermo 상태 패킷은 Polling 여부와 무관하게 즉시 반영.
- "Query" 버튼 없음, `homeassistant.update_entity`로 대체 (ADR-0006에서 유지).

## 재검토 조건
- 캡처 단계 1(`docs/capture-guide.md`)에서 실내 온도조절기 등 자발적 트래픽이 확인되면 감청 비중과 주기를 다시 정한다.
- Relay가 같은 버스에 붙어 Master가 둘이 되면 Polling 주기와 충돌 회피를 다시 정한다.
