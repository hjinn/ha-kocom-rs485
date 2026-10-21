# ADR-0003: v1 범위는 방별 Thermo만

- 상태: 승인 (2026-10-21)

## 맥락
코콤 프로토콜에 "보일러" 장치는 없다. 난방은 방별 Thermo(`0x36`)로 요청하고 월패드가 보일러를 구동한다.
참조 구현은 light, gas, fan, elevator도 지원한다.

## 결정
v1은 Thermo만 지원한다. Room 하나당 HA `climate` 엔티티 하나. 대상 Room은 4개(livingroom, bedroom, room1, room2).
light/gas/fan/elevator는 범위 밖.

## 결과
- 코드에 장치 타입 일반화(다른 장치용 추상화)를 미리 넣지 않는다. 필요해지면 그때 확장.
- 수신 패킷 중 Thermo가 아닌 것은 무시(로그만)한다.
