# ADR-0009: 3단계 테스트 전략

- 상태: 승인 (2026-10-21)

## 결정
1. **프로토콜 단위 테스트** (HA 의존 없음, 순수 Python): 패킷 생성/파싱, 체크섬, 프레임 재조립(분할·병합·쓰레기 바이트·체크섬 불일치).
2. **Integration 테스트** (`pytest-homeassistant-custom-component`): asyncio 가짜 EW11 TCP 서버가 Wallpad/Thermo 응답을 흉내 낸다. config flow 자동 탐지/수동 선택, ACK 누락, 재연결, Room 무응답 → `unavailable`.
3. **실기기 수동 체크리스트**: 릴리스 전 실제 EW11·월패드에서 수행.

## 결과
- 프로토콜 코드는 HA import 없이 독립 모듈로 둔다 (`tools/capture.py`의 Framer와 같은 형태로 시작).
- `tools/capture.py`로 얻은 실기기 로그를 1·2단계 테스트 픽스처로 사용한다. 로그 확보 전에는 참조 구현 기준으로 만든 합성 패킷을 쓰고, 로그 확보 후 교체·보강한다.
