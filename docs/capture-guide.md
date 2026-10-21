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

## 단계 5 — 명령 되돌림 재현 (보일러 상태가 바뀜)

`05-cmd`에서 꺼짐 → 난방 명령이 2.8초 뒤 저절로 꺼짐으로 되돌아갔다. 원인 후보:

| 가설 | 내용 | 갈리는 실험 |
|---|---|---|
| H1 | ③ 보고에 ④ ACK가 없어서 온도조절기/Controller가 원래 상태를 다시 주장 | 5-2에서 되돌림이 사라짐 |
| H2 | 꺼짐 상태에서는 원격 켜기를 거부 | 5-1, 5-2 모두 되돌림, 5-3은 유지 |
| H3 | 우연 (재현 안 됨) | 5-1에서 되돌림 없음 |

각 실험 사이에 **30초** 쉬고, 각 실험 중 **온도조절기 화면 변화**를 메모해 둔다.

```sh
# 5-1  꺼짐 → 난방, ACK 없이 (05 재현)
python3 tools/probe.py <EW11_IP> -o captures/06-revert.log off 0 23
python3 tools/probe.py <EW11_IP> -o captures/06-revert.log --listen 30 heat 0 24

# 5-2  꺼짐 → 난방, ACK 보냄
python3 tools/probe.py <EW11_IP> -o captures/06-revert.log --ack off 0 23
python3 tools/probe.py <EW11_IP> -o captures/06-revert.log --ack --listen 30 heat 0 24

# 5-3  난방 → 다른 온도, ACK 보냄 (대조군)
python3 tools/probe.py <EW11_IP> -o captures/06-revert.log --ack --listen 30 heat 0 25
```

끝나면 온도조절기에서 원래 상태(외출)로 되돌린다.

## 단계 6 — 외출 켜기 (보일러 상태가 바뀜)

온도조절기가 외출일 때 보고하는 값 `11 01 0a`를 그대로 명령으로 보낸다. 모두 `--ack` 사용 (ADR-0014). 실험 사이 30초 휴식, **온도조절기 화면 변화를 메모**.

```sh
# 6-1  난방 상태로 맞춰 두기
python3 tools/probe.py <EW11_IP> -o captures/07-away.log --ack heat 0 24
# 6-2  외출 켜기
python3 tools/probe.py <EW11_IP> -o captures/07-away.log --ack --listen 30 away 0
# 6-3  꺼짐 → 외출 (꺼진 방에서도 되는가)
python3 tools/probe.py <EW11_IP> -o captures/07-away.log --ack off 0 24
python3 tools/probe.py <EW11_IP> -o captures/07-away.log --ack --listen 30 away 0
```

**판단 포인트:** 6-2, 6-3에서 ③ Report가 `11 01 0a`인가, 온도조절기 화면이 외출로 바뀌는가, 30초 동안 유지되는가.
끝나면 온도조절기에서 원래 상태로 되돌린다.

## 아직 이 도구로 확인할 수 없는 것

- 허용 온도 범위: 범위 밖 값을 보내 보는 것은 Controller 반응을 모르므로 지금은 하지 않는다.
