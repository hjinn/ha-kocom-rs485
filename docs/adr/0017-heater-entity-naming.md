# ADR-0017: 엔티티 이름 — `climate.heater_<room>`

- 상태: 승인 (2026-10-22)

## 맥락
엔티티 ID의 도메인(`climate.`)은 HA가 정한 엔티티 종류라 바꿀 수 없다. `water_heater`는 급탕용이라 난방 모드·외출 preset이 없다.
`climate`여야 온도조절기 카드와 음성 비서(Google, Alexa, HomeKit, Assist)가 동작한다.
자동 생성 ID는 HA 언어에 따라 달라진다 (한국어 이름 → `geosil` 같은 로마자).

## 결정
- 엔티티 종류: `climate` (ADR-0016)
- 엔티티 ID 기본값: `climate.heater_livingroom`, `climate.heater_bedroom`, `climate.heater_room1`, `climate.heater_room2` — HA 언어와 무관하게 고정
- 화면 이름: 기기 이름 + 방 이름 = "난방 거실" / "Heater Living room" (번역)
- 기기: EW11(config entry)당 1개
- 사용자는 HA 화면에서 ID·이름을 바꿀 수 있다. 여기서 정하는 것은 처음 등록 시 기본값이다.
- EW11을 둘 이상 등록하면 HA가 겹치는 ID에 `_2`를 붙인다.

## 검토한 대안
- `climate.boiler_<room>`: 제어 대상이 보일러 컨트롤러라 의미가 맞지만, 사용자가 `heater`를 선택했다.
- 자동 생성: 언어에 따라 ID가 달라져 자동화에서 예측하기 어렵다.
