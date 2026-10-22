# Kocom RS485 for Home Assistant

코콤(Kocom) 호환 RS485 보일러 컨트롤러를 Elfin EW11을 통해 Home Assistant에서 제어하는 custom integration입니다. 방마다 난방 엔티티를 만들고, 꺼짐 / 난방 / 외출과 설정 온도를 제어합니다.

> Controls a Kocom-compatible RS485 boiler controller from Home Assistant through an Elfin EW11 (TCP). One climate entity per room: off / heat / away preset, target temperature. UI in English and Korean.

## 기능

- 방(거실, 안방, 방1, 방2)마다 `climate` 엔티티: 꺼짐 / 난방, 외출 preset, 설정 온도, 현재 온도
- 실내 온도조절기에서 바꾼 상태가 즉시 반영됨
- 설치 시 응답하는 방을 자동으로 찾음
- MQTT 브로커나 별도 애드온이 필요 없음 (HA 안에서 EW11에 직접 TCP로 연결)

## 요구 사항

| 항목 | 내용 |
|---|---|
| Home Assistant | 2026.4.0 이상 |
| 보일러 컨트롤러 | 코콤 호환 RS485 프로토콜 (21바이트 `aa55 … 0d0d` 패킷, 방 주소 `3600`~`3603`) |
| RS485 변환기 | Elfin EW11 (TCP 서버 모드) |

이 integration은 버스의 **유일한 Master**로 동작합니다. 같은 버스에 월패드나 다른 제어 프로그램(예: kocom.py 애드온)이 Master로 붙어 있으면 충돌합니다.

## EW11 설정

EW11 웹 관리 화면에서 다음과 같이 맞춥니다.

| 구분 | 값 |
|---|---|
| 시리얼 | 9600 bps, 데이터 8비트, 패리티 없음, 정지 1비트, 흐름 제어 없음 |
| 네트워크 | **TCP 서버**, 포트 8899 (다른 포트도 가능) |

- MQTT 모드는 지원하지 않습니다 ([ADR-0002](docs/adr/0002-tcp-transport-only.md)).
- EW11에는 이 integration 하나만 연결해 두세요. 다른 프로그램이 같은 EW11에 접속해 있으면 연결이 거부되거나 버스에서 충돌할 수 있습니다.

## 설치

### HACS (custom repository)

1. HACS → 오른쪽 위 ⋮ → **Custom repositories**
2. Repository: `https://github.com/hjinn/ha-kocom-rs485`, Type: **Integration** → **Add**
3. 목록에서 **Kocom RS485** 설치 → Home Assistant 재시작

### 수동 설치

이 저장소의 `custom_components/kocom_rs485` 폴더를 HA의 `config/custom_components/kocom_rs485`로 복사하고 Home Assistant를 재시작합니다.

## 설정

**설정 → 기기 및 서비스 → 통합 추가 → Kocom RS485**

1. EW11 주소(호스트, 포트)를 입력합니다.
2. 연결되면 방을 자동으로 조회합니다 (약 6초, 응답 없는 방마다 2초 추가).
3. 응답한 방이 미리 선택된 화면에서 추가할 방을 확인합니다. 아무 방도 응답하지 않았으면 직접 고릅니다.

### 옵션

| 항목 | 기본값 | 범위 | 설명 |
|---|---|---|---|
| 폴링 주기 | 60초 | 15~3600초 | 현재 온도를 읽어 오는 주기. 상태 변경(온도조절기 조작, HA 명령)은 이 값과 무관하게 즉시 반영됩니다 |

## 엔티티

| 방 | 엔티티 ID | 이름 |
|---|---|---|
| 거실 | `climate.heater_livingroom` | 난방 거실 |
| 안방 | `climate.heater_bedroom` | 난방 안방 |
| 방1 | `climate.heater_room1` | 난방 방1 |
| 방2 | `climate.heater_room2` | 난방 방2 |

엔티티 ID는 HA 언어 설정과 관계없이 위와 같이 만들어지며, 이후 HA 화면에서 바꿀 수 있습니다.

| 컨트롤러 상태 | `hvac_mode` | `preset_mode` | 설정 온도 |
|---|---|---|---|
| 꺼짐 | `off` | `none` | 없음 |
| 난방 | `heat` | `none` | 설정 온도 |
| 외출 | `heat` | `away` | 없음 |

| HA 동작 | 결과 |
|---|---|
| 온도 설정 | 그 온도로 난방. 꺼짐·외출 상태에서도 난방으로 바뀝니다 |
| 모드 `heat` / preset `none` | 그 방의 마지막 난방 설정 온도로 난방 (기록이 없으면 23℃) |
| 모드 `off` | 꺼짐 |
| preset `away` | 외출 |

설정 온도 범위는 5~40℃, 1℃ 단위입니다.

## 문제 해결

### 로그 보기

통합 페이지 → ⋮ → **디버그 로깅 활성화** → 문제 재현 → **디버그 로깅 비활성화**를 누르면 로그 파일이 내려받아집니다. HA를 재시작하면 디버그 로깅이 꺼지므로, 재시작 후에는 다시 켜야 합니다.

항상 기록하려면 `configuration.yaml`에 추가합니다.

```yaml
logger:
  logs:
    custom_components.kocom_rs485: debug
```

### 로그 메시지

| 수준 | 메시지 | 뜻 |
|---|---|---|
| DEBUG | `room 1 (bedroom) answered in 0.34s (waited 1.00s for the controller)` | 정상. 첫 방이 아니면 앞 방 응답 후 1초 대기가 포함됩니다 |
| DEBUG | `room 1 (bedroom) missed poll 1/2: …` | 한 번 응답이 없었음. 가끔은 정상(버스 충돌) |
| WARNING | `room 1 (bedroom) unavailable after 2 missed polls: …` | 연속 2회 무응답으로 그 방을 사용 불가로 표시 |
| INFO | `room 1 (bedroom) available again` | 다시 응답함 |
| WARNING | `connection to …:8899 lost (…), reconnecting` | EW11 연결이 끊김. 모든 방이 사용 불가가 되고 5→10→30→60초 간격으로 재연결 |
| WARNING | `ignoring report from room N: unobserved value …` | 처음 보는 상태값. [이슈](https://github.com/hjinn/ha-kocom-rs485/issues)로 값과 온도조절기 화면을 알려 주세요 |

### 무응답 이유

| 이유 | 확인할 것 |
|---|---|
| `did not ack 4 tries` | 다른 Master가 버스에 있는지(월패드, 다른 애드온), EW11 Wi-Fi 신호 |
| `acked but did not report` | 컨트롤러가 요청을 받았지만 상태를 보내지 않음. 계속되면 로그와 함께 이슈로 알려 주세요 |
| `reported unobserved value …` | 위 "처음 보는 상태값"과 같음 |

### HA 시작 시 "재시도 중"

시작할 때 10초 안에 EW11에 연결하지 못하면 HA가 설정을 나중에 다시 시도합니다. EW11 전원, Wi-Fi, 주소와 포트, 다른 프로그램의 접속 여부를 확인하세요.

## 동작 방식

통합은 Master 주소(`0100`)로 각 방에 요청을 보내고, 컨트롤러의 상태 보고에는 모두 ACK를 보냅니다. ACK가 없으면 컨트롤러가 명령을 약 3초 뒤 되돌리기 때문입니다. 상태 보고에 ACK한 뒤에는 1초 동안 다음 요청을 보내지 않습니다. 그 사이의 요청은 컨트롤러가 받기만 하고 응답하지 않습니다.

자세한 내용은 [`docs/protocol.md`](docs/protocol.md)와 설계 결정 기록 [`docs/adr/`](docs/adr)에 있습니다.

## 알려진 제한

- 온도 범위 5~40℃는 컨트롤러가 실제로 허용하는 범위로 확인되지 않았습니다.
- 외출 중 설정 온도는 컨트롤러가 10℃로 고정해 보고하며, HA에서는 표시하지 않습니다.
- 현재 온도는 바뀌어도 컨트롤러가 스스로 보고하지 않아 폴링 주기마다 갱신됩니다.
- 버스에 다른 Master(월패드 등)가 함께 있는 구성은 지원하지 않습니다.

## 개발

```sh
uv sync
uv run pytest
```

테스트는 실기기 캡처를 바탕으로 만든 가짜 EW11·컨트롤러(TCP)를 사용합니다. 실기기 확인 항목은 [`docs/manual-checklist.md`](docs/manual-checklist.md), 버스 캡처·탐색 도구는 `tools/`와 [`docs/capture-guide.md`](docs/capture-guide.md)를 참고하세요.

## 감사

프로토콜 이해는 [clipman/kocom.py](https://github.com/clipman/kocom.py)와 그 원작자들(날자, 룰루해피, 따분, Susu Daddy)의 작업에 크게 기댔습니다. 이 저장소는 해당 코드를 복사하지 않고 새로 작성했습니다 ([ADR-0011](docs/adr/0011-clean-room-rewrite-mit.md)).

## 라이선스

[MIT](LICENSE)
