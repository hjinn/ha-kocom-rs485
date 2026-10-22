# ADR-0016: climate 표현 — hvac off/heat + preset away

- 상태: 승인 (2026-10-21). 외출 설정 확인됨 (2026-10-22, `captures/07-away`). 프리셋 표는 ADR-0019로 대체됨
- 대체: ADR-0005의 "외출은 읽기 전용 attribute" 부분 (온도 범위, 켤 때 설정 온도 규칙은 유지)

## 맥락
실기기 확인으로 Thermo 상태는 꺼짐 / 난방 / 외출 중 하나(ThermoMode)이며, 외출은 온도조절기의 독립 모드다 (`docs/protocol.md`).
외출 → 난방 전환 명령(`11 00 T`)은 동작이 확인됐다 (`05`).

## 결정
| ThermoMode | `hvac_mode` | `preset_mode` | `target_temperature` |
|---|---|---|---|
| OFF | `off` | `none` | 없음 |
| HEAT | `heat` | `none` | 설정 온도 |
| AWAY | `heat` | `away` | 없음 |

- 외출 해제(preset `none` 선택): 마지막으로 관측한 난방 설정 온도로 `11 00 T` (없으면 23℃).
- 외출 설정(preset `away` 선택): `11 01 0a` 송신. 실기기에서 난방→외출, 꺼짐→외출 모두 확인 (ACK 포함, 30초 유지).
- `preset_modes`: `none`, `away`. 꺼짐 상태에서 `away`를 고르면 외출로 전환된다 (장비 동작 그대로).
