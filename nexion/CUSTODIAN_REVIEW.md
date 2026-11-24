# NEXION v0.3.4 — 다중 증빙 보관자 장애 진단

2026-11-24 / experiment/nexion-v0.1.0-20261110

## 목적 및 정책

v0.3.3의 동시 롤백 한계에 이어, 2~16명의 가상 보관자 명단 및 별개 HMAC 키를 고정 입력으로 받는 읽기 전용 검사기를 추가했다. 모든 보관자의 인증된 floor(scope, min_sequence, min_digest)가 정확히 일치해야 기존 저널 검증기로 진행한다. 응답을 누락한 보관자를 임의로 제외하거나 다수결로 대체하지 않는다. 서로 다른 정상 시점의 floor도 보수적으로 불일치로 분류한다.

| 조건 | 진단 |
|---|---|
| 필수 응답 일부/전체 누락 | CUSTODIAN_UNAVAILABLE |
| 미등록 보관자, 키 재사용, 인증·범위·형식 오류 | UNTRUSTED |
| 인증된 sequence 또는 digest 불일치 | CUSTODIAN_DISAGREEMENT |
| 합의 floor보다 오래된 저널/증빙 | REPLAY_OR_ROLLBACK |
| 합의 floor와 저널이 기존 검사를 통과 | BOUNDED_CONSISTENT |

모든 결과는 delivery_permitted=False 및 repair_permitted=False. 일치 판정은 동의 유효성, 최신성 또는 실행 승인이 아니다. 기존 메시지 전송, 권한, 복구 경로에는 연결하지 않았다.

## 검증

프로젝트 nexion 디렉터리에서 실행:

- python -m unittest discover -s tests -p test_custodian_review.py -v
- python -m unittest discover -s tests -q
- python -m compileall -q nexion tests

Python 3.13.5: 신규 16개 통과. 승인된 이전 ZIP을 재구성한 기준 209개와 신규 16개를 포함한 225개를 5회 반복하여 모두 통과. 신규 파일 Git blob 해시를 원격과 대조한다. 기존 Python 파일 30개 중 24개는 원격 기준과 Git blob SHA 일치, 나머지 6개(__init__, agent, core 및 test_agent, test_consent, test_core)는 불일치하므로 전체 원격 트리와 동일한 환경에서 테스트했다는 의미가 아니다. 기존 SQLite ResourceWarning 및 원격 CI 미확인 사항은 남아 있다.

## 한계 및 다음 과제

별개 키는 독립 보관 또는 키 관리의 증명이 아니다. 모든 보관자가 같은 과거 floor를 제공하는 경우 기존 공동 롤백 한계가 남는다. 현재 응답의 생성 시각, 요청 nonce, 만료 및 전송 신원은 검증하지 않는다. 기존 저널 검증기의 다중 읽기 원자성도 별도 과제다. 다음 단계는 고정 명단에 대한 요청별 nonce 및 만료 검증의 오프라인 모형과 동시 롤백 반례를 검토하는 것이다. 가용성을 포기하는 만장일치 정책이며 BFT 합의가 아니다.

실제 보관자 등록, 외부 연락, 실물 시설 연결, 구매, 원격 제어, 실물 제작, 자동 권한 복구 없음. 모의 SQLite와 더미 키만 사용한다.
