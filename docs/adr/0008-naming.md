# ADR-0008: 도메인 `kocom_rs485`, 저장소 `ha-kocom-rs485`

- 상태: 승인 (2026-10-21)

## 결정
- integration 도메인: `kocom_rs485` (`custom_components/kocom_rs485/`)
- GitHub 저장소: `ha-kocom-rs485`
- HA 표시 이름은 도메인과 별개로 지정 (예: "Kocom 난방 (RS485)")

## 근거
도메인은 배포 후 변경 시 사용자 설정·자동화가 깨진다.
`kocom`/`kocom_wallpad`는 기존 커뮤니티 integration과 충돌 가능성이 있고, `kocom_thermo`는 향후 장치 확장 시 의미가 어긋난다.
프로토콜 기준 이름은 범위가 바뀌어도 유효하다.
