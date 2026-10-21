# Kocom Boiler — Domain Context

Home Assistant에서 코콤(Kocom) 월패드의 RS485 버스를 통해 난방을 제어하는 HACS custom integration.

## Glossary

| 용어 | 정의 | 비고 |
|---|---|---|
| **Integration** | HA 프로세스 안에서 동작하는 `custom_components/kocom_rs485/` 패키지. HACS custom repository(`ha-kocom-rs485`)로 배포한다. | App(구 Add-on)과 구분. → ADR-0001, ADR-0008 |
| **EW11** | Elfin EW11. RS485 ⇄ Wi-Fi 변환기. 월패드 RS485 버스에 물려 TCP 서버(기본 포트 8899)로 노출한다. | |
| **Wallpad** | 집에 설치된 CVnet 월패드(물리 장비). 프로토콜은 CVnet이 아닐 수 있음(미확인). **현재 RS485 버스에 연결되어 있지 않다.** | 향후 Relay를 통해 연결 예정. v1 범위 밖 |
| **Master 주소** | Kocom 프로토콜에서 월패드 역할의 주소 `0100`. Boiler Controller는 이 주소에서 오는 명령에 응답한다. 현재 버스에 실제 월패드가 없으므로 Integration이 이 역할을 맡는다. | 물리 Wallpad와 구분할 것 |
| **Boiler Controller** | RS485 버스에 물린 보일러 컨트롤러. **Kocom 호환 프로토콜**로 Thermo 주소(`36xx`)에 응답한다. 현재 버스에는 EW11과 이것만 있다. | 실물 1대가 서브 ID 여러 개에 응답하는 구조로 추정 |
| **Relay** | 향후 만들 Wallpad ⇄ Boiler Controller 프로토콜 중계기. | 계획 단계 |
| **Transport** | Integration과 EW11 사이의 바이트 스트림 연결. v1은 TCP 소켓 구현만 존재한다. | → ADR-0002 |
| **Thermo** | 방별 난방 온도조절기. 장치 코드 `0x36`. 상태: heat/off, away, 설정 온도, 현재 온도. HA `climate` 엔티티 1개에 대응. | "보일러"라는 장치는 프로토콜에 없음. → ADR-0003 |
| **Away** | 외출 모드. Thermo 값 바이트 1이 `01`이면 외출. v1은 읽기 전용(속성). | → ADR-0005 |
| **Room** | Thermo가 설치된 공간. 서브 ID `00` livingroom, `01` bedroom, `02` room1, `03` room2. 기본 표시 이름: 거실, 안방, 방1, 방2. | 설치 시 자동 탐지 → ADR-0004 |
| **Polling** | Integration이 Master로서 Thermo에 query를 보내 상태를 확인하는 것. 상태 동기화의 주 수단, 기본 60초. 감청(버스에 지나가는 패킷 수동 수신)은 보조. | → ADR-0012 |
| **Packet** | RS485 프레임. 21바이트, `aa55` 헤더 + `0d0d` 트레일러, 인덱스 18(0부터 셈, 19번째 바이트)이 체크섬 = 인덱스 2~17 합 mod 256. | 상세: `docs/protocol.md` |

## Open questions

- Master 역할 시 Integration이 Boiler Controller의 상태 보고에 ACK를 보내야 하는가 (`docs/protocol.md` 참조)
- Wallpad(CVnet)의 실제 프로토콜 — Relay 프로젝트에서 확인, v1 범위 밖
- Relay 도입 후 버스 구성 (마스터가 둘이 되는 문제)
- 실기기 캡처·탐색 로그 대기 중 (`docs/capture-guide.md`, 단계 1~4) — 확보 시 테스트 픽스처로 사용 (ADR-0009)
- 실내 온도조절기가 버스에 있는가 — 캡처 단계 1로 확인
- `docs/protocol.md`의 [검증 필요] 항목 (외출 송신, 허용 온도 범위, off 시 설정 온도 바이트, 상태를 싣는 패킷 방향) — 캡처로 확인

