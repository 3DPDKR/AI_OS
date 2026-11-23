# NEXION v0.3.3 — 동시 롤백의 관측 불가능성 오프라인 검증

**일자:** 2026-11-23 · **브랜치:** experiment/nexion-v0.1.0-20261110 · **변경:** 신규 테스트와 문서만 추가

## 목적

v0.3.2의 verify_witness_floor()는 인증된 외부 high-water floor가 **독립적으로 유지되는 경우에만** 과거 저널/증빙의 재생을 탐지한다. 이 가정이 깨졌을 때 실제 SQLite 권한 DB, 철회 저널, 로컬 HMAC 앵커와 HMAC 증빙을 함께 복구하는 실험으로 한계를 검증한다.

실험은 가상의 동의자(example.invalid), 임시 디렉터리의 SQLite 파일, 공개되어도 무방한 더미 키만 사용한다. 본 연구는 실제 데이터 복구 공격 수행, 원격 제어, 권한 갱신, 외부 연락, 실물 제작 기능을 추가하지 않는다.

## 두 역사(History)의 비교

1. 초기 상태 S0에 대해 권한 DB, journal DB, anchor 파일, 인증된 witness 및 floor를 보관한다.
2. 역사 A: 철회가 발생하지 않는다.
3. 역사 B: 모의 참여자의 철회를 정상 기록한 뒤, 닫힌 임시 DB·앵커와 witness/floor를 **모두** S0로 복원한다.
4. 두 역사의 검사기 입력은 바이트 단위로 같고, 둘 다 BOUNDED_CONSISTENT를 반환한다. 이는 검증기가 **유실된 과거 철회라는 사실을 판별할 수 없다**는 재현 가능한 반례다.
5. 역사 B에서 외부 보관자가 갱신된 floor를 유지하는 대조군은 REPLAY_OR_ROLLBACK으로 판별한다.

| 조건 | 관측 결과 | 해석 |
|---|---|---|
| 철회가 없고 모든 기록이 S0 | BOUNDED_CONSISTENT | 로컬 일관성 |
| 철회 후 전체 증빙 동시 롤백(S0) | BOUNDED_CONSISTENT | **공동 롤백을 알아볼 수 없음** |
| 외부 최신 floor를 보존하고 로컬 DB·앵커를 S0로 롤백 | REPLAY_OR_ROLLBACK | 독립 신뢰 경계가 있을 때 탐지 |
| 현재 journal + 과거 witness/floor | UNTRUSTED | witness와 저널 head가 다름 |
| 현재 journal + 현재 witness + 과거 floor | BOUNDED_CONSISTENT | floor 단독 퇴행도 별도로 탐지하지 못함 |
| 잘못된 MAC | UNTRUSTED | 인증 실패 |

**모든 시험에서 delivery_permitted=False, repair_permitted=False.** BOUNDED_CONSISTENT는 FRESH, 참여자 동의의 유효성, 자동 복구 승인 또는 실서비스 사용 허가를 의미하지 않는다.

## 재현

프로젝트의 nexion 디렉터리에서 아래 명령을 실행한다.

- python -m unittest discover -s tests -p 'test_joint_rollback_limits.py' -v
- python -m unittest discover -s tests -q
- python -m compileall -q nexion tests

총 8개의 신규 테스트는 파일 바이트 동등성, 외부 floor 독립 보존 대조군, 부분 롤백, MAC 변조, 재시작 후 불가시성, 검사 전후 파일 해시 불변을 확인한다. 기존 운영 소스/권한 API/메시지 경로는 수정하지 않는다.

## 안전 경계와 미해결 과제

이 결과는 오프라인 단일 호스트 시뮬레이션일 뿐 실물 스토리지 장애나 실제 공격 환경의 검증이 아니다. 독립적이며 단조 증가가 보장되고 신원 인증이 가능한 외부 기록 보관자 또는 신뢰할 만한 하드웨어 카운터가 없는 한, **모든 증빙의 동시 롤백**을 로컬 검사로 구분할 수 없다.

다음에는 외부 보관자 장애, 서로 다른 보관자 간 엇갈린 체크포인트, 고수위 증빙 만료에 대한 fail-closed 판정 **모형**을 검증할 수 있다. 외부인 동의 및 시설별 권한 없이 네트워크 연결·실제 시설 제어·구매·실물 제작을 수행하지 않는다.
