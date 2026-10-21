# ADR-0010: 최소 HA 버전과 저장소 구성

- 상태: 승인 (2026-10-21)

## 결정
- 최소 지원 HA: 구현 시작 시점의 안정 버전에서 약 6개월 전 릴리스 (예: `2026.4.0`). `hacs.json`의 `homeassistant`에 명시. 정확한 값은 구현 착수 시 확정.
- CI는 최소 버전과 최신 안정 버전 두 가지로 pytest 실행. hassfest, HACS action 검증 포함.
- UI 문구: 영어(`strings.json`, `en.json`) + 한국어(`ko.json`).

## 저장소 구성
```
ha-kocom-rs485/
├── hacs.json
├── custom_components/kocom_rs485/
│   ├── manifest.json
│   ├── __init__.py
│   ├── config_flow.py
│   ├── climate.py
│   ├── coordinator.py       # 상태, Polling, 감청
│   ├── protocol.py          # HA 의존 없음: Packet, 체크섬, Framer
│   ├── transport.py         # TCP 연결/재연결
│   ├── strings.json
│   └── translations/{en,ko}.json
├── tests/
├── tools/capture.py
└── .github/workflows/
```
