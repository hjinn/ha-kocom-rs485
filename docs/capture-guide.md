# 버스 캡처·탐색 가이드

현재 버스 구성: **EW11 + Boiler Controller** (실제 월패드 없음, 실내 온도조절기 연결 여부 미확인).
목표: `docs/protocol.md`의 [검증 필요] 항목, 특히 Master 부재 시 상태 응답 흐름(①~④) 확정.

## 도구

| 도구 | 버스에 쓰기 | 용도 |
|---|---|---|
| `tools/capture.py` | 안 함 | 수동 감청 |
| `tools/probe.py` | **함** (Master `0100`으로 송신) | 능동 질의·명령 |

공통: 표준 라이브러리만 사용, `-o 파일`로 로그 저장, 로그는 `captures/`에 (git 제외).
EW11에는 **한 번에 하나의 도구만** 연결한다.

## 단계 1 — 버스에 누가 말하는가 (읽기 전용)

```sh
python3 tools/capture.py <EW11_IP> -o captures/01-passive.log
```

1. 아무것도 하지 않고 10분.
2. 실내 온도조절기가 있다면 한 방에서 설정 온도를 바꾸고 1분 (메모 입력 후 조작).
3. 보일러/컨트롤러 본체에 버튼이 있다면 조작하고 1분.

**판단:** 패킷이 하나도 없으면 버스에 먼저 말하는 장비가 없다 → 실내 온도조절기는 버스에 없거나 다른 선에 있다. 감청은 v1에서 의미가 없고 Polling이 유일한 수단.

## 단계 2 — 한 방 질의 (상태 변경 없음)

```sh
python3 tools/probe.py <EW11_IP> -o captures/02-query.log query 0
python3 tools/probe.py <EW11_IP> -o captures/03-query-ack.log --ack query 0
```

**판단 포인트:**
- `SEND` 직후 `RECV ack` 이 오는가 (②) → Controller가 Master 주소 `0100`에 응답함.
- 이어서 `thermo0->wallpad0 send cmd=state` 패킷이 오는가 (③) → 상태는 이 패킷에서 읽는다.
- `--ack` 없이 실행했을 때 ③이 seq `d`, `e`, `f`로 반복되는가 → **Integration이 ④ ACK를 보내야 한다.**
- `--ack`로 실행했을 때 반복이 멈추는가.
- ③ 대신 `wallpad0->thermo0 ack` 형태가 오면 참조 구현 방식이 그대로 맞다.

## 단계 3 — Room 탐색

```sh
python3 tools/probe.py <EW11_IP> -o captures/04-scan.log --ack scan
```

응답하는 Room 서브 ID 확인 (ADR-0004 자동 탐지의 근거). 단계 2 결과에 따라 `--ack` 유무 결정.

## 단계 4 — 명령 (보일러 상태가 바뀜)

현재 상태(단계 2 로그의 모드·설정 온도)를 기록해 두고, 마지막에 원래대로 되돌린다.

```sh
python3 tools/probe.py <EW11_IP> -o captures/05-cmd.log --ack heat 0 <현재설정+1>
python3 tools/probe.py <EW11_IP> -o captures/05-cmd.log --ack off 0 <현재설정+1>
python3 tools/probe.py <EW11_IP> -o captures/05-cmd.log --ack heat 0 <원래설정>
```

**판단 포인트:** 응답 값의 바이트 2(설정 온도)·0(모드)이 명령대로 바뀌는가, off일 때 바이트 2가 유지되는가, 실제 보일러가 반응하는가.

## 아직 이 도구로 확인할 수 없는 것

- 외출 송신 형식: 외출을 설정할 수 있는 장비(월패드)가 버스에 없다. Relay 프로젝트 이후로 미룬다.
- 허용 온도 범위: 범위 밖 값을 보내 보는 것은 Controller 반응을 모르므로 지금은 하지 않는다.
