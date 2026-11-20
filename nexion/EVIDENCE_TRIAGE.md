# NEXION v0.3.0 — 독립 증빙 기반 읽기 전용 앵커 불일치 진단

2026-11-20 · 오프라인 연구 시뮬레이션 · Python 표준 라이브러리

## 배경 및 범위
v0.2.9에서는 철회 저널 SQLite 커밋 뒤 앵커 파일 교체 전에 예외가 발생하면 기존 서비스와 open_for_review() 모두 차단됨을 확인했다. 이번 단계는 자동 복구 대신 독립 보관된 증빙을 입력받아 원인을 좁히는 읽기 전용 분류 기능을 실험한다.

nexion/evidence_triage.py의 triage_anchor_mismatch() 입력: 권한 DB, 철회 저널 DB, 앵커 파일 경로, 앵커 HMAC 키, 외부 witness JSON 바이트, 별개의 witness HMAC 키(각 최소 32바이트). 같은 키를 쓰거나 파일 경로가 겹치면 거부한다.

SQLite는 mode=ro와 PRAGMA query_only로 읽고, 앵커는 인증 검증 후 읽기만 한다. witness 서명과 명세, 저널 해시 체인, head, 체크포인트, 철회 상태 및 서명 witness가 지칭하는 논리 상태를 대조한다. 서명 witness를 생성하거나 외부로 전송하는 운영 명령은 제공하지 않는다.

## 판정 기준
| 분류 | 의미 | 허용 범위 |
|---|---|---|
| MATCHED_BUT_NOT_AUTHORIZED | 권한/저널/앵커/witness 논리 상태 일치 | 읽기 전용 진단 결과만 |
| POSSIBLE_POST_COMMIT_ANCHOR_LAG | witness가 최신 상태를 확인하며, 저널이 인증된 앵커보다 정확히 한 이벤트 앞서고 이전 pending 의도가 마지막 철회 대상에 대응 | 장애 패턴 후보(원인 확정 아님) |
| INCOMPLETE_INTENT | 인증된 앵커와 저널에 동일한 미완료 철회 의도가 존재 | 수동 조사만 |
| UNTRUSTED | 증빙 위조/불일치·저널 변조·권한 불일치·파일 누락·체크포인트 오류 등 | 중단 후 독립 조사 |

어떤 분류에서도 delivery_permitted=False, repair_permitted=False. 기존 전송, 철회 및 승인 실행 경로는 바꾸지 않았다. 특히 POSSIBLE 판정은 자동 앵커 재발행 또는 전송·권한 복구 승인이 아니다.

## 외부 witness 입력 형식
format=nexion-external-review-witness-v1. state 안에 sequence(0 이상 정수), digest(저널 해시 head), withdrawn_digest(정렬된 withdrawn ID 배열의 SHA-256), checkpoint_digest(정렬된 replica 체크포인트 배열의 SHA-256)를 기록한다. mac은 format/state JSON을 key 정렬·공백 없는 UTF-8로 정규화하여 별도 키로 HMAC-SHA256한 64자리 소문자 16진수다. 같은 이름의 JSON 필드 중복과 스키마 초과 필드를 거부한다.

**중요**: 이 증빙은 독립기관에서 실제 발행했다는 증거, 서명자 실명 인증, 신선도, 단조 카운터, 재생 공격 방지 또는 원자적 DB 스냅샷을 뜻하지 않는다. 테스트는 임시 SQLite와 별도 더미 키를 쓸 뿐이고 실서비스용 신뢰기관은 미구현이다.

## 검증
실험 브랜치를 체크아웃하고 저장소의 nexion 폴더에서 다음 명령을 실행한다.

    python -m unittest discover -s tests -p 'test_evidence_triage.py' -v
    python -m unittest discover -s tests -q

신규 18개 테스트는 정상 상태의 권한 불허, 앵커 지연 후보, 과거 witness, 서명/키 변조, 원본 파일 내용 변경 여부, 권한/이벤트 불일치, 미완료 의도, 일괄 롤백, 체크포인트 변조 등을 재현한다. 2026-11-20 Python 3.13 로컬에서는 기존 165개 포함 183개를 5회 반복 통과했다. GitHub Actions CI는 별도 확인이 필요하다.

## 다음 미해결 과제
실제 witness 서명자·분리 보관·독립 신원 검증, witness 신선도/단조 체크포인트, 잠금된 증거 사본 및 WAL 포함 일관된 스냅샷, 전원 손실·fsync 오류 내구성, 실제 다중 서버 합의는 미구현이다. 증거 읽기는 서로 다른 SQLite 파일 사이의 원자적 관찰을 보장하지 않는다. 다음 단계에서도 외부 연락, 설비 제어, 구매, 자동 복구는 금지한다.

NEXION은 독립적 생명체가 아니라 검증 가능한 오프라인 연구 소프트웨어이다.
