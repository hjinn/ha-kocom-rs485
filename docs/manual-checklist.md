# 실기기 수동 체크리스트

자동 테스트로 재현할 수 없는 동작. 릴리스 전 실제 EW11·Boiler Controller로 확인한다 (ADR-0009 3단계).

## 연결 (transport)

| # | 절차 | 기대 결과 | 근거 |
|---|---|---|---|
| T1 | HA 동작 중 EW11 전원을 뽑는다 | 최대 약 3분(Polling 주기 × 3) 안에 모든 Room이 `unavailable` | ADR-0013 `idle_timeout` |
| T2 | T1 후 EW11 전원을 다시 꽂는다 | 재연결 백오프(5→10→30→60초) 안에 복구, 즉시 전체 query | ADR-0007 |
| T3 | EW11 Wi-Fi를 끈 상태(전원은 켬)에서 HA를 재시작한다 | 연결 시도가 10초마다 포기되고 백오프대로 재시도. HA 시작이 막히지 않음 | ADR-0013 `connect_timeout` |
| T4 | EW11 웹 UI에서 TCP 서버를 재시작한다 | `unavailable` → 수 초 내 복구 | ADR-0007 |
