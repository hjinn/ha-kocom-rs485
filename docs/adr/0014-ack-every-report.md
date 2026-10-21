# ADR-0014: Integration은 모든 Report에 ACK를 보낸다

- 상태: 승인 (2026-10-21)

## 맥락
실기기 실험(`captures/06-revert`, `docs/protocol.md`)에서 확인:
- Master가 보낸 명령의 결과 Report에 ACK가 없으면 Thermo가 c, d, e 재송신 후 약 2.3초 뒤 **명령을 되돌린다**.
- ACK를 보내면 30초 관찰 동안 유지된다.
- 온도조절기 조작으로 생기는 자발적 Report도 ACK가 없으면 3회 흐른다.

## 결정
- Thermo → Master 방향 Report(type send, cmd `00`, 출발지 `36xx`, 목적지 `0100`)를 받으면 요청 여부와 무관하게 즉시 `Packet.ack()`를 보낸다.
- 재송신된 Report(seq d, e)에도 각각 ACK한다.
- 송신 큐에서 ACK는 일반 명령·query보다 **우선**한다. Thermo는 약 300ms 안에 ACK가 없으면 재송신한다.
- 명령 성공 조건: ② ACK 수신 + 요청 상태와 일치하는 ③ Report 수신 + ④ ACK 송신.

## 근거
- 장비는 Master의 ACK를 전제로 동작한다 (실제 월패드의 동작).
- 자발적 Report 재송신이 줄어 버스 충돌 여지가 줄어든다.
- "우리가 요청한 Report인가"를 구분할 필요가 없어 규칙이 단순하다.

## 재검토 조건
Relay가 같은 버스에 붙으면 ACK를 두 장비가 보내게 된다. 그때 ACK 주체를 다시 정한다.
