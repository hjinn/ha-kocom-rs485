# ADR-0001: App(Add-on)이 아닌 HACS custom integration으로 구현

- 상태: 승인 (2026-10-21)

## 맥락
참조 구현 `orig/kocom.py`는 HA Add-on(현 App) 형태로, 별도 컨테이너에서 EW11과 TCP로 통신하고 HA와는 MQTT(+MQTT Discovery)로 연결된다.
배포 목표는 HACS custom repository이며, HACS는 integration만 설치한다.

## 결정
`custom_components/kocom/` custom integration으로 구현한다. 엔티티는 HA 내부에서 직접 생성하고, 설정은 config flow(UI)로 받는다.

## 결과
- kocom.py ⇄ HA 사이의 MQTT 계층과 Mosquitto 의존이 사라진다.
- HA OS가 아닌 설치(Container/Core)에서도 동작한다.
- 블로킹 스레드 구조(threading/queue)를 HA의 asyncio 모델로 재설계해야 한다.
