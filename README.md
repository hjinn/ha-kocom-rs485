# Kocom RS485 for Home Assistant

> 개발 중 (0.1.0). 아직 설치할 수 있는 상태가 아닙니다.

코콤(Kocom) 호환 RS485 보일러 컨트롤러를 Elfin EW11을 통해 Home Assistant에서 제어하는 custom integration입니다. 방마다 `climate` 엔티티(꺼짐 / 난방 / 외출)를 만듭니다.

- 지원 HA: 2026.4.0 이상
- 연결: EW11 TCP 서버 모드
- 설계 문서: [`CONTEXT.md`](CONTEXT.md), [`docs/adr/`](docs/adr), [`docs/protocol.md`](docs/protocol.md)

## 감사

프로토콜 이해는 [clipman/kocom.py](https://github.com/clipman/kocom.py)와 그 원작자들(날자, 룰루해피, 따분, Susu Daddy)의 작업에 크게 기댔습니다. 이 저장소는 해당 코드를 복사하지 않고 새로 작성했습니다 ([ADR-0011](docs/adr/0011-clean-room-rewrite-mit.md)).

## 라이선스

MIT
