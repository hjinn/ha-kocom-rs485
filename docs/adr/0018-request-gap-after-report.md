# ADR-0018: Report ACK 후 1초 동안 다음 요청 보류

- 상태: 승인 (2026-10-22)

## 맥락
실기기 설치 후 방이 불규칙하게 `unavailable`이 되었다. 디버그 로그(`captures/ha.log`, 16분)에서 Polling 결과가 매번 같았다:
거실 응답 → 안방 `acked but did not report` → 방1 응답 → 방2 `acked but did not report`.
실패한 방은 항상 **바로 앞 방이 응답한 직후** 조회한 방이었다. 앞 방이 실패해 1.2초를 기다린 뒤 조회한 방은 성공했다.

참조 구현은 방 사이 1초를 쉬었고 ADR-0006/0012/0015도 "Room 간 1초 간격"을 적었으나, coordinator에 구현되지 않았다.

## 결정
- Master는 Report에 ACK를 쓴 시점부터 `request_gap`(기본 1초) 동안 새 요청(재송신 포함)을 보내지 않는다.
- 우리 query의 응답이든 자발적 Report든 같다 (Controller에게는 같은 Report 처리).
- Master에 두어 Polling, 방 탐지, 명령에 모두 적용된다.

## 결과
- Polling 1회(방 4개) ≈ 5초, 방 탐지 ≈ 6초 (모두 응답 시). 60초 주기에는 영향 없음.
- Report 직후의 HA 명령은 최대 1초 늦게 나간다.
- Controller가 바쁜 정확한 시간은 모른다. 1초는 참조 구현과 `probe.py`에서 동작이 확인된 값이다.

## 함께 고친 것
- 보류 중에 도착한 이전 Report 재송신이 다음 요청의 답으로 쓰이던 문제: 요청마다 ACK 표시를 초기화한다.
