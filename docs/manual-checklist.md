# 실기기 수동 체크리스트

자동 테스트로 재현할 수 없는 동작. 릴리스 전 실제 EW11·Boiler Controller로 확인한다 (ADR-0009 3단계).

## 연결 (transport)

| # | 절차 | 기대 결과 | 근거 |
|---|---|---|---|
| T1 | HA 동작 중 EW11 전원을 뽑는다 | 최대 약 3분(Polling 주기 × 3) 안에 모든 Room이 `unavailable` | ADR-0013 `idle_timeout` |
| T2 | T1 후 EW11 전원을 다시 꽂는다 | 재연결 백오프(5→10→30→60초) 안에 복구, 즉시 전체 query | ADR-0007 |
| T3 | EW11 Wi-Fi를 끈 상태(전원은 켬)에서 HA를 재시작한다 | 연결 시도가 10초마다 포기되고 백오프대로 재시도. HA 시작이 막히지 않음 | ADR-0013 `connect_timeout` |
| T4 | EW11 웹 UI에서 TCP 서버를 재시작한다 | `unavailable` → 수 초 내 복구 | ADR-0007 |

## 설치와 엔티티 (config flow, climate)

| # | 절차 | 기대 결과 | 근거 |
|---|---|---|---|
| C1 | HACS로 설치 후 통합 추가 → EW11 주소 입력 | 약 6초(응답 없는 방마다 +2초) 뒤 방 선택 화면, **4개 방 모두** 미리 체크됨 | ADR-0004, ADR-0018 |
| C2 | 방 4개 등록 | `climate.heater_livingroom` 등 4개, 이름 "난방 거실" 등 | ADR-0017 |
| C3 | HA에서 거실 온도 변경 | 온도조절기 화면에 반영, 3초 뒤에도 유지 (되돌림 없음) | ADR-0014 |
| C4 | HA에서 꺼짐 → 난방 | 온도조절기가 마지막 설정 온도로 켜짐 | ADR-0005 |
| C5 | HA에서 외출 preset 켜기/끄기 | 온도조절기 화면이 외출 ↔ 난방 | ADR-0016 |
| C6 | 온도조절기에서 직접 조작 | HA 화면이 1초 안에 바뀜 | ADR-0015 |
| C7 | 1시간 그대로 둠, 디버그 로그 켬 (재시작하면 꺼지므로 재시작 후 다시 켬) | 매 Polling마다 4개 방 모두 `answered in 0.3xs`, 첫 방 외에는 `(waited 1.0xs for the controller)`. `missed poll`은 가끔 1회까지 정상, 같은 방이 반복되면 이상. `unavailable` 경고 없음 | ADR-0015, ADR-0018 |
